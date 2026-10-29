#!/usr/bin/env python3
"""
MacRemote Agent - Control any Apple Silicon Mac from your phone via Telegram.
Universal support for all Apple M-Series Macs (M1, M2, M3, M4, Air, Pro, Max, Ultra, Studio, Mini).
Features Antigravity AI integration, Google Drive syncing, and complete macOS automation.
"""

import base64
import os
import sys
import json
import time
import uuid
import glob
import signal
import socket
import atexit
import shutil
import logging
import secrets
import datetime
import platform
import sqlite3
import tempfile
import subprocess
import threading
from contextlib import closing
import urllib.request
import urllib.parse
import urllib.error

if os.name == "nt":
    import msvcrt
else:
    import fcntl

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MacRemoteAgent")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("MRA_DATA_DIR"):
    DATA_DIR = os.path.expanduser(os.environ["MRA_DATA_DIR"])
elif os.name == "nt":
    DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MacRemote")
elif sys.platform == "darwin":
    DATA_DIR = os.path.expanduser("~/Library/Application Support/MacRemote")
else:
    DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "mac-remote")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LEGACY_CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TASK_DB_FILE = os.path.join(DATA_DIR, "pending_tasks.sqlite3")
TMP_DIR = os.path.join(tempfile.gettempdir(), "mac_remote")
os.makedirs(TMP_DIR, exist_ok=True)
LOCK_FILE = os.path.join(TMP_DIR, "mac_remote_agent.lock")
PID_FILE = os.path.join(BASE_DIR, "agent.pid")

DEFAULT_CONFIG = {
    "bot_token": "",
    "allowed_user_ids": [],
    "pairing_pin": "",
    "google_drive_path": os.path.expanduser("~/Google Drive/My Drive"),
    "antigravity_bin": os.path.expanduser("~/.local/bin/agy"),
    "claude_bin": "",
    "working_directory": os.path.expanduser("~"),
    "relay_url": "",
    "relay_host_id": "",
    "relay_host_token": "",
    "keep_awake": True
}

lock_file_handle = None
keep_awake_instance = None
active_cli_process = None
active_cli_process_lock = threading.Lock()
shutdown_event = threading.Event()


def acquire_instance_lock():
    """Ensures only a single instance of MacRemote Agent runs."""
    global lock_file_handle
    try:
        lock_file_handle = open(LOCK_FILE, "a+")
        if os.name == "nt":
            lock_file_handle.seek(0)
            if not lock_file_handle.read(1):
                lock_file_handle.write("\0")
                lock_file_handle.flush()
            lock_file_handle.seek(0)
            msvcrt.locking(lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with open(PID_FILE, "w") as pf:
            pf.write(str(os.getpid()))
        return True
    except (IOError, OSError, BlockingIOError):
        existing_pid = None
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as pf:
                    existing_pid = pf.read().strip()
            except Exception:
                pass
        err_msg = "❌ Another instance of MacRemote Agent is already running"
        if existing_pid:
            err_msg += f" (PID: {existing_pid})"
        err_msg += "!\nRun 'mra stop' or 'mra restart' to manage it."
        logger.error(err_msg)
        return False


def cleanup_handler(signum=None, frame=None):
    """Cleanly terminates child processes and releases the instance lock."""
    global keep_awake_instance, lock_file_handle
    shutdown_event.set()
    if keep_awake_instance:
        try:
            keep_awake_instance.stop()
        except Exception:
            pass
        keep_awake_instance = None

    with active_cli_process_lock:
        cli_process = active_cli_process
        if cli_process and cli_process.poll() is None:
            try:
                cli_process.terminate()
            except OSError:
                logger.exception("Could not stop the active coding-agent process")
    if cli_process and cli_process.poll() is None:
        try:
            cli_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                cli_process.kill()
            except OSError:
                logger.exception("Could not kill the active coding-agent process")

    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    if lock_file_handle:
        try:
            if os.name == "nt":
                lock_file_handle.seek(0)
                msvcrt.locking(lock_file_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file_handle, fcntl.LOCK_UN)
            lock_file_handle.close()
        except Exception:
            pass
        lock_file_handle = None

    if signum is not None:
        logger.info(f"Received signal {signum}. Agent shut down cleanly.")
        sys.exit(0)


# Register signal and exit handlers
signal.signal(signal.SIGINT, cleanup_handler)
signal.signal(signal.SIGTERM, cleanup_handler)
# If started with nohup/daemon, SIGHUP is SIG_IGN - keep it ignored so agent stays alive.
# If started interactively in a terminal, trap SIGHUP to cleanly shut down child shells when terminal closes.
if hasattr(signal, "SIGHUP") and signal.getsignal(signal.SIGHUP) != signal.SIG_IGN:
    signal.signal(signal.SIGHUP, cleanup_handler)
atexit.register(cleanup_handler)


def load_config():
    config_path = CONFIG_FILE if os.path.exists(CONFIG_FILE) else LEGACY_CONFIG_FILE
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                merged = {**DEFAULT_CONFIG, **cfg}
                return merged
        except (OSError, TypeError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Unable to load configuration from {config_path}: {e}") from e
    # Generate random 4-digit PIN for first setup
    cfg = DEFAULT_CONFIG.copy()
    cfg["pairing_pin"] = f"{secrets.randbelow(9000) + 1000}"
    if not save_config(cfg):
        raise RuntimeError(f"Unable to create configuration file at {CONFIG_FILE}.")
    return cfg


def save_config(cfg):
    temp_path = CONFIG_FILE + ".tmp"
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as f:
            if os.name != "nt":
                os.chmod(temp_path, 0o600)
            json.dump(cfg, f, indent=2)
        os.replace(temp_path, CONFIG_FILE)
        return True
    except (OSError, TypeError, ValueError) as e:
        logger.error(f"Error saving config.json: {e}")
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass
        return False


config = DEFAULT_CONFIG.copy()


class TelegramBot:
    """Zero-dependency Telegram Bot API client using standard urllib."""
    def __init__(self, token):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"

    def request(self, method, data=None, files=None, timeout=30):
        url = f"{self.api_url}/{method}"
        try:
            if files:
                boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
                body = bytearray()
                if data:
                    for k, v in data.items():
                        body.extend(f"--{boundary}\r\n".encode("utf-8"))
                        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
                        body.extend(str(v).encode("utf-8"))
                        body.extend(b"\r\n")
                for field_name, (filename, file_bytes, mime) in files.items():
                    body.extend(f"--{boundary}\r\n".encode("utf-8"))
                    body.extend(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8"))
                    body.extend(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
                    body.extend(file_bytes)
                    body.extend(b"\r\n")
                body.extend(f"--{boundary}--\r\n".encode("utf-8"))
                req = urllib.request.Request(
                    url,
                    data=bytes(body),
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
                )
            elif data:
                json_data = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=json_data,
                    headers={"Content-Type": "application/json"}
                )
            else:
                req = urllib.request.Request(url)

            with urllib.request.urlopen(req, timeout=timeout) as response:
                res_body = response.read().decode("utf-8")
                return json.loads(res_body)
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            logger.error(f"HTTPError in {method}: {e.code} - {err_msg}")
            return {"ok": False, "error": err_msg}
        except Exception as e:
            logger.error(f"Request exception in {method}: {e}")
            return {"ok": False, "error": str(e)}

    def get_me(self):
        return self.request("getMe")

    def set_my_commands(self):
        """Registers the bot command menu and Menu button on Telegram."""
        commands = [
            {"command": "status", "description": "🔋 Battery, AC power, disk & system status"},
            {"command": "ss", "description": "📸 Take screenshot of Mac screen"},
            {"command": "finder", "description": "📂 Browse Finder files"},
            {"command": "drive", "description": "💾 Share file to Google Drive"},
            {"command": "get", "description": "📥 Download file directly to phone"},
            {"command": "agy", "description": "🤖 Run Antigravity AI prompt"},
            {"command": "claude", "description": "🧠 Run Claude Code prompt"},
            {"command": "lock", "description": "🔒 Lock computer"},
            {"command": "help", "description": "ℹ️ Show all available commands"}
        ]
        res = self.request("setMyCommands", {"commands": commands})
        self.request("setChatMenuButton", {"menu_button": {"type": "commands"}})
        if res.get("ok"):
            logger.info("Bot commands and menu button successfully registered with Telegram.")
        else:
            logger.warning(f"Could not register commands with Telegram: {res.get('error')}")
        return res

    def get_updates(self, offset=None, timeout=25):
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        query_str = urllib.parse.urlencode(params)
        url = f"{self.api_url}/getUpdates?{query_str}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout + 10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            if e.code == 409:
                logger.warning(
                    "Telegram 409 Conflict: Another instance is polling getUpdates. "
                    "Make sure only one bot instance is running. Retrying in 5 seconds..."
                )
                time.sleep(5)
            elif e.code == 401:
                logger.error("Telegram 401 Unauthorized: Invalid bot token.")
                time.sleep(10)
            else:
                logger.error(f"HTTPError in getUpdates: {e.code} - {err_body}")
                time.sleep(2)
            return {"ok": False, "error": err_body}
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            # Normal long-polling timeout when no updates arrive
            return {"ok": True, "result": []}
        except Exception as e:
            logger.error(f"Exception in getUpdates: {e}")
            time.sleep(2)
            return {"ok": False, "error": str(e)}

    def send_chat_action(self, chat_id, action="typing"):
        return self.request("sendChatAction", {"chat_id": chat_id, "action": action})

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="Markdown"):
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        res = self.request("sendMessage", payload)
        # If Markdown parsing fails due to unescaped chars, fallback to plain text
        if not res.get("ok") and parse_mode:
            payload.pop("parse_mode", None)
            res = self.request("sendMessage", payload)
        return res

    def send_photo(self, chat_id, photo_path, caption=None):
        self.send_chat_action(chat_id, "upload_photo")
        with open(photo_path, "rb") as f:
            file_bytes = f.read()
        filename = os.path.basename(photo_path)
        files = {"photo": (filename, file_bytes, "image/jpeg")}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        return self.request("sendPhoto", data=data, files=files, timeout=60)

    def send_document(self, chat_id, doc_path, caption=None):
        self.send_chat_action(chat_id, "upload_document")
        with open(doc_path, "rb") as f:
            file_bytes = f.read()
        filename = os.path.basename(doc_path)
        files = {"document": (filename, file_bytes, "application/octet-stream")}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        return self.request("sendDocument", data=data, files=files, timeout=120)


class RelayClient:
    """Authenticated outbound client for the optional MacRemote relay."""

    def __init__(self, base_url, host_id, token):
        parsed = urllib.parse.urlparse(base_url)
        loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("Relay URL must use HTTPS (HTTP is allowed for localhost development only).")
        if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Relay URL must be a base URL without credentials, query, or fragment.")
        if not host_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in host_id):
            raise ValueError("Relay host ID is invalid.")
        if not token:
            raise ValueError("Relay host token is required.")
        self.base_url = base_url.rstrip("/")
        self.host_id = host_id
        self.token = token
        self.commands_url = (
            f"{self.base_url}/v1/hosts/{urllib.parse.quote(host_id, safe='')}/commands"
        )

    def request(self, url, method="GET", body=None, timeout=35):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Relay returned HTTP {error.code}.") from error
        except (urllib.error.URLError, TimeoutError, socket.timeout) as error:
            raise RuntimeError(f"Could not reach the MacRemote relay: {error}") from error

    def poll_commands(self):
        url = f"{self.commands_url}?wait=25"
        result = self.request(url, timeout=35)
        commands = result.get("commands")
        if not isinstance(commands, list):
            raise RuntimeError("Relay returned an invalid command response.")
        return commands

    def report_command(self, command_id, status, result):
        url = f"{self.commands_url}/{urllib.parse.quote(command_id, safe='')}/result"
        return self.request(url, method="POST", body={"status": status, "result": result})

    def run_forever(self, bot):
        while not shutdown_event.is_set():
            try:
                for command in self.poll_commands():
                    if shutdown_event.is_set():
                        return
                    handle_relay_command(self, bot, command)
            except Exception:
                logger.exception("Relay polling failed")
                shutdown_event.wait(5)


def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "📸 Screenshot"}, {"text": "🔋 Status"}],
            [{"text": "📂 Open Finder"}, {"text": "💾 Google Drive"}],
            [{"text": "🤖 Antigravity AI"}, {"text": "🧠 Claude Code"}],
            [{"text": "🔒 Lock Screen"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }


def get_host_model_info():
    """Returns a human-readable name for the machine running the agent."""
    if sys.platform == "darwin":
        chip = "Apple Silicon"
        model = "Mac"
        try:
            res = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=2)
            if res.stdout.strip():
                chip = res.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass

        try:
            res = subprocess.run(["system_profiler", "SPHardwareDataType"], capture_output=True, text=True, timeout=3)
            for line in res.stdout.split("\n"):
                if "Model Name:" in line:
                    model = line.split(":", 1)[1].strip()
                    break
        except (OSError, subprocess.SubprocessError):
            pass
        return f"{model} ({chip})"

    return f"{platform.node() or 'Computer'} ({platform.system()} {platform.machine()})"


class SystemActions:
    """Local automation methods for the supported host operating systems."""

    @staticmethod
    def take_screenshot():
        """Captures a screenshot using the host operating system."""
        out_path = os.path.join(TMP_DIR, f"ss_{int(time.time())}.jpg")
        try:
            if sys.platform == "darwin":
                subprocess.run(["caffeinate", "-u", "-t", "2"], timeout=3)
                res = subprocess.run(
                    ["screencapture", "-x", "-t", "jpg", out_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            elif os.name == "nt":
                escaped_path = out_path.replace("'", "''")
                script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "Add-Type -AssemblyName System.Drawing; "
                    "$s=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
                    "$b=New-Object System.Drawing.Bitmap($s.Width,$s.Height); "
                    "$g=[System.Drawing.Graphics]::FromImage($b); "
                    "$g.CopyFromScreen($s.X,$s.Y,0,0,$b.Size); "
                    f"$b.Save('{escaped_path}',[System.Drawing.Imaging.ImageFormat]::Jpeg); "
                    "$g.Dispose(); $b.Dispose()"
                )
                res = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
            else:
                return None, f"Screenshot is not supported on {platform.system()}."
            if res.returncode == 0 and os.path.exists(out_path):
                return out_path, None
            else:
                return None, f"Screenshot error: {res.stderr}"
        except (OSError, subprocess.SubprocessError) as e:
            return None, str(e)

    @staticmethod
    def open_finder(target_path=None):
        """Opens Finder at target path and returns folder listing."""
        if not target_path or target_path.strip() == "":
            target_path = os.path.expanduser("~")
        else:
            target_path = os.path.expanduser(target_path.strip())

        if not os.path.exists(target_path):
            return f"❌ Path does not exist: `{target_path}`"

        try:
            if sys.platform == "darwin":
                subprocess.run(["open", target_path], check=True, timeout=5)
                subprocess.run(["osascript", "-e", 'tell application "Finder" to activate'], timeout=5)
            elif os.name == "nt":
                os.startfile(target_path)
            else:
                return f"Opening folders is not supported on {platform.system()}."

            items = os.listdir(target_path)
            item_list = []
            for item in sorted(items)[:15]:
                if not item.startswith("."):
                    full_p = os.path.join(target_path, item)
                    icon = "📁" if os.path.isdir(full_p) else "📄"
                    item_list.append(f"{icon} `{item}`")

            listing = "\n".join(item_list) if item_list else "_Folder is empty._"
            return (
                f"📂 *Opened folder:*\n`{target_path}`\n\n"
                f"*Contents (top {len(item_list)}):*\n{listing}\n\n"
                f"💡 _Tip: Reply with `/drive <filename>` or `/get <filename>` to share or download._"
            )
        except (OSError, subprocess.SubprocessError) as e:
            return f"❌ Error opening Finder: {str(e)}"

    @staticmethod
    def share_to_google_drive(source_path):
        """Copies file or folder to Google Drive."""
        drive_base = config.get("google_drive_path", os.path.expanduser("~/Google Drive/My Drive"))
        dest_dir = os.path.join(drive_base, "Remote_Shared")
        os.makedirs(dest_dir, exist_ok=True)

        resolved_source = os.path.expanduser(source_path.strip())
        if not os.path.exists(resolved_source):
            fallback = os.path.expanduser(f"~/Downloads/{source_path.strip()}")
            if os.path.exists(fallback):
                resolved_source = fallback
            else:
                return f"❌ File not found: `{source_path}`"

        filename = os.path.basename(resolved_source)
        dest_path = os.path.join(dest_dir, filename)

        try:
            if os.path.isdir(resolved_source):
                if os.path.exists(dest_path):
                    shutil.rmtree(dest_path)
                shutil.copytree(resolved_source, dest_path)
            else:
                shutil.copy2(resolved_source, dest_path)

            file_size_mb = os.path.getsize(dest_path) / (1024 * 1024) if os.path.isfile(dest_path) else 0

            return (
                f"✅ *Shared to Google Drive!*\n\n"
                f"📄 *File:* `{filename}` ({file_size_mb:.2f} MB)\n"
                f"💾 *Drive Location:*\n`Google Drive > My Drive > Remote_Shared > {filename}`\n\n"
                f"Google Drive will automatically sync this to your phone in seconds."
            )
        except Exception as e:
            return f"❌ Error copying to Google Drive: {str(e)}"

    @staticmethod
    def get_system_status():
        """Gathers portable power, disk, and uptime information."""
        host_name = get_host_model_info()
        lines = [f"💻 *{host_name} Status*\n"]

        if sys.platform == "darwin":
            try:
                batt_res = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3)
                batt_out = batt_res.stdout
                is_ac = "AC Power" in batt_out
                power_source = "🔌 Plugged into AC Power" if is_ac else "🔋 Running on Battery"
                lines.append(f"*Power:* {power_source}")
                for part in batt_out.split(";"):
                    if "%" in part:
                        lines.append(f"*Battery Level:* `{part.strip()}`")
                        break
            except (OSError, subprocess.SubprocessError):
                lines.append("*Power:* Unknown")
        elif os.name == "nt":
            try:
                import ctypes

                class SystemPowerStatus(ctypes.Structure):
                    _fields_ = [
                        ("ACLineStatus", ctypes.c_byte),
                        ("BatteryFlag", ctypes.c_byte),
                        ("BatteryLifePercent", ctypes.c_byte),
                        ("Reserved1", ctypes.c_byte),
                        ("BatteryLifeTime", ctypes.c_ulong),
                        ("BatteryFullLifeTime", ctypes.c_ulong),
                    ]

                power = SystemPowerStatus()
                if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
                    if power.ACLineStatus in (0, 1):
                        source = "🔌 Plugged into AC Power" if power.ACLineStatus == 1 else "🔋 Running on Battery"
                        lines.append(f"*Power:* {source}")
                    if power.BatteryLifePercent != 255:
                        lines.append(f"*Battery Level:* `{power.BatteryLifePercent}%`")
                else:
                    lines.append("*Power:* Unknown")
            except (AttributeError, OSError):
                lines.append("*Power:* Unknown")
        else:
            lines.append(f"*Power:* Not available on {platform.system()}")

        try:
            drive = os.environ.get("SystemDrive", "C:") + os.sep if os.name == "nt" else os.path.abspath(os.sep)
            disk = shutil.disk_usage(drive)
            total_gb = disk.total / (1024 ** 3)
            free_gb = disk.free / (1024 ** 3)
            used_percent = 100 - (disk.free * 100 // disk.total)
            lines.append(f"*Disk:* `{free_gb:.1f} GB free` of `{total_gb:.1f} GB` ({used_percent}% used)")
        except OSError:
            lines.append("*Disk:* Unknown")

        try:
            if os.name == "nt":
                import ctypes
                uptime_seconds = ctypes.windll.kernel32.GetTickCount64() // 1000
                lines.append(f"*Uptime:* `{datetime.timedelta(seconds=uptime_seconds)}`")
            else:
                up_res = subprocess.run(["uptime"], capture_output=True, text=True, timeout=3)
                if up_res.stdout.strip():
                    lines.append(f"*Uptime:* `{up_res.stdout.strip()}`")
        except (AttributeError, OSError, subprocess.SubprocessError):
            pass

        lines.append(f"\n⏰ *Time:* `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
        return "\n".join(lines)

    @staticmethod
    def lock_screen():
        """Locks the host workstation."""
        try:
            if sys.platform == "darwin":
                subprocess.run(["pmset", "displaysleepnow"], check=True, timeout=3)
            elif os.name == "nt":
                import ctypes
                if not ctypes.windll.user32.LockWorkStation():
                    raise OSError("Windows could not lock the workstation.")
            else:
                return f"Lock screen is not supported on {platform.system()}."
            return f"🔒 *{platform.node()} screen locked.*"
        except (AttributeError, OSError, subprocess.SubprocessError) as e:
            return f"❌ Failed to lock: {e}"

    @staticmethod
    def find_cli_bin(provider):
        """Finds a configured coding-agent CLI without invoking a shell."""
        key, candidates = {
            "antigravity": (
                "antigravity_bin",
                [
                    os.path.expanduser("~/.local/bin/agy"),
                    os.path.expanduser("~/.gemini/antigravity-ide/bin/agy"),
                    shutil.which("agy"),
                ],
            ),
            "claude": ("claude_bin", [shutil.which("claude"), shutil.which("claude.exe")]),
        }[provider]

        configured = config.get(key, "")
        if configured:
            expanded = os.path.expanduser(configured)
            if os.path.isfile(expanded) and (os.name == "nt" or os.access(expanded, os.X_OK)):
                return expanded
        for candidate in candidates:
            if candidate and os.path.isfile(candidate) and (os.name == "nt" or os.access(candidate, os.X_OK)):
                if os.name == "nt" and candidate.lower().endswith((".cmd", ".bat")):
                    continue
                return candidate
        return None

    @staticmethod
    def run_agent_cli(provider, prompt):
        """Runs a locally installed coding-agent CLI after host approval."""
        cli_path = SystemActions.find_cli_bin(provider)
        if not cli_path:
            return f"❌ {provider} CLI was not found. Configure it in the host app or install the CLI."
        working_directory = os.path.expanduser(config.get("working_directory") or os.path.expanduser("~"))
        if not os.path.isdir(working_directory):
            return f"❌ Agent working directory does not exist: `{working_directory}`"
        command = [cli_path, "-p", prompt]
        global active_cli_process
        process = None
        try:
            with active_cli_process_lock:
                active_cli_process = subprocess.Popen(
                    command,
                    cwd=working_directory,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                process = active_cli_process
            try:
                stdout, stderr = process.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                return f"⏱️ {provider} task timed out after 10 minutes."
            output = stdout.strip() or stderr.strip()
            if len(output) > 3800:
                output = output[:3800] + "\n...[response truncated]"
            if process.returncode:
                return output or f"❌ {provider} exited with code {process.returncode}."
            return output or f"✅ {provider} completed the approved task."
        except OSError as error:
            logger.exception("Could not start %s CLI", provider)
            return f"❌ Could not start {provider}: {error}"
        finally:
            with active_cli_process_lock:
                if active_cli_process is process:
                    active_cli_process = None


def initialize_task_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    with closing(sqlite3.connect(TASK_DB_FILE, timeout=5)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_tasks (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL CHECK (provider IN ('antigravity', 'claude')),
                prompt TEXT NOT NULL,
                requester_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'running', 'completed', 'rejected')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                result TEXT,
                delivery_channel TEXT NOT NULL DEFAULT 'telegram',
                relay_host_id TEXT,
                relay_command_id TEXT,
                response_sent INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        task_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(agent_tasks)").fetchall()
        }
        for column, definition in (
            ("delivery_channel", "TEXT NOT NULL DEFAULT 'telegram'"),
            ("relay_host_id", "TEXT"),
            ("relay_command_id", "TEXT"),
            ("response_sent", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if column not in task_columns:
                connection.execute(f"ALTER TABLE agent_tasks ADD COLUMN {column} {definition}")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_tasks_relay_command "
            "ON agent_tasks(relay_command_id) WHERE relay_command_id IS NOT NULL"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status, created_at)"
        )
    if os.name != "nt":
        os.chmod(TASK_DB_FILE, 0o600)


def enqueue_agent_task(
    provider,
    prompt,
    requester_id,
    chat_id,
    delivery_channel="telegram",
    relay_host_id=None,
    relay_command_id=None,
):
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("The task prompt cannot be empty.")
    if len(prompt) > 4000:
        raise ValueError("Task prompts must be 4,000 characters or fewer.")

    task_id = uuid.uuid4().hex
    with closing(sqlite3.connect(TASK_DB_FILE, timeout=5)) as connection, connection:
        if relay_command_id:
            existing = connection.execute(
                "SELECT id FROM agent_tasks WHERE relay_command_id = ?",
                (relay_command_id,),
            ).fetchone()
            if existing:
                return existing[0]
        pending_count = connection.execute(
            "SELECT COUNT(*) FROM agent_tasks WHERE status IN ('pending', 'approved', 'running')"
        ).fetchone()[0]
        if pending_count >= 100:
            raise ValueError("The host task queue is full. Review pending tasks in MacRemote first.")
        connection.execute(
            "INSERT INTO agent_tasks "
            "(id, provider, prompt, requester_id, chat_id, status, delivery_channel, relay_host_id, relay_command_id) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
            (task_id, provider, prompt, requester_id, chat_id, delivery_channel, relay_host_id, relay_command_id),
        )
    return task_id


def process_approved_agent_tasks(bot, relay_client=None):
    with closing(sqlite3.connect(TASK_DB_FILE, timeout=5)) as connection, connection:
        connection.row_factory = sqlite3.Row
        channel_filter = "AND (delivery_channel = 'relay' OR ? IS NOT NULL)"
        task = connection.execute(
            "SELECT id, provider, prompt, chat_id, delivery_channel FROM agent_tasks "
            f"WHERE status = 'approved' {channel_filter} ORDER BY created_at LIMIT 1",
            (1 if bot is not None else None,),
        ).fetchone()
        if not task:
            return
        updated = connection.execute(
            "UPDATE agent_tasks SET status = 'running' WHERE id = ? AND status = 'approved'",
            (task["id"],),
        ).rowcount
        if not updated:
            return

    result = SystemActions.run_agent_cli(task["provider"], task["prompt"])
    status = "failed" if result.startswith(("❌", "⏱️")) else "completed"
    with closing(sqlite3.connect(TASK_DB_FILE, timeout=5)) as connection, connection:
        connection.execute(
            "UPDATE agent_tasks SET status = ?, result = ?, response_sent = ? WHERE id = ?",
            (status, result, int(task["delivery_channel"] == "telegram"), task["id"]),
        )
    if task["delivery_channel"] == "telegram":
        bot.send_message(
            task["chat_id"],
            f"🤖 *{task['provider'].title()} task {task['id']} finished:*\n\n{result}",
            reply_markup=get_main_keyboard(),
        )
    elif relay_client:
        process_relay_task_responses(relay_client)


def process_relay_task_responses(relay_client):
    with closing(sqlite3.connect(TASK_DB_FILE, timeout=5)) as connection, connection:
        connection.row_factory = sqlite3.Row
        tasks = connection.execute(
            "SELECT id, relay_command_id, status, result FROM agent_tasks "
            "WHERE delivery_channel = 'relay' AND response_sent = 0 "
            "AND status IN ('completed', 'rejected') ORDER BY created_at LIMIT 10"
        ).fetchall()
    for task in tasks:
        result = task["result"] or (
            "This coding-agent request was rejected on the host."
            if task["status"] == "rejected"
            else "Task finished without a result."
        )
        relay_status = "failed" if task["status"] == "rejected" or result.startswith(("❌", "⏱️")) else "completed"
        try:
            relay_client.report_command(
                task["relay_command_id"],
                relay_status,
                {"taskId": task["id"], "text": result},
            )
            with closing(sqlite3.connect(TASK_DB_FILE, timeout=5)) as connection, connection:
                connection.execute(
                    "UPDATE agent_tasks SET response_sent = 1 WHERE id = ? AND response_sent = 0",
                    (task["id"],),
                )
        except Exception:
            logger.exception("Could not send the completed relay task result")


def handle_relay_command(relay_client, bot, command):
    command_id = command.get("id")
    action = command.get("action")
    payload = command.get("payload") or {}
    if not isinstance(command_id, str) or not isinstance(action, str):
        logger.error("Relay returned a malformed command.")
        return

    try:
        if action == "status":
            result = {"text": SystemActions.get_system_status()}
        elif action == "screenshot":
            photo_path, error = SystemActions.take_screenshot()
            if not photo_path:
                raise RuntimeError(error or "Screenshot could not be captured.")
            try:
                with open(photo_path, "rb") as photo:
                    image = photo.read(3_500_001)
                if len(image) > 3_500_000:
                    raise RuntimeError("Screenshot is too large to send through the relay.")
                result = {
                    "mediaType": "image/jpeg",
                    "imageBase64": base64.b64encode(image).decode("ascii"),
                }
            finally:
                try:
                    os.remove(photo_path)
                except OSError:
                    logger.warning("Could not remove temporary screenshot %s", photo_path)
        elif action == "lock":
            result = {"text": SystemActions.lock_screen()}
        elif action == "open_folder":
            result = {"text": SystemActions.open_finder(payload.get("path", ""))}
        elif action == "agent_task":
            task_id = enqueue_agent_task(
                payload.get("provider", ""),
                payload.get("prompt", ""),
                requester_id=0,
                chat_id=0,
                delivery_channel="relay",
                relay_host_id=relay_client.host_id,
                relay_command_id=command_id,
            )
            result = {"taskId": task_id, "text": "Waiting for approval on the host."}
            relay_client.report_command(command_id, "awaiting_approval", result)
            return
        else:
            raise ValueError(f"Unsupported relay action: {action}")

        message = result.get("text", "")
        status = "failed" if message.startswith("❌") else "completed"
        relay_client.report_command(command_id, status, result)
    except Exception as error:
        logger.exception("Relay command %s failed", command_id)
        try:
            relay_client.report_command(command_id, "failed", {"error": str(error)})
        except Exception:
            logger.exception("Could not report relay command failure")


def run_agent_task_worker(bot, relay_client=None):
    while not shutdown_event.wait(2):
        try:
            process_approved_agent_tasks(bot, relay_client)
            if relay_client:
                process_relay_task_responses(relay_client)
        except Exception:
            logger.exception("Approved task worker failed")


class KeepAwakeManager:
    """Keeps the host awake using its native power-management API."""
    def __init__(self):
        self.process = None
        self.running = False
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        if os.name == "nt":
            logger.info("KeepAwakeManager started (Windows system sleep prevention active).")
            try:
                import ctypes
                continuous = 0x80000000
                system_required = 0x00000001
                while self.running:
                    class SystemPowerStatus(ctypes.Structure):
                        _fields_ = [
                            ("ACLineStatus", ctypes.c_byte),
                            ("BatteryFlag", ctypes.c_byte),
                            ("BatteryLifePercent", ctypes.c_byte),
                            ("Reserved1", ctypes.c_byte),
                            ("BatteryLifeTime", ctypes.c_ulong),
                            ("BatteryFullLifeTime", ctypes.c_ulong),
                        ]

                    power = SystemPowerStatus()
                    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
                        logger.error("Windows could not read the current power state.")
                        return
                    state = continuous | (system_required if power.ACLineStatus == 1 else 0)
                    if not ctypes.windll.kernel32.SetThreadExecutionState(state):
                        logger.error("Windows could not set the keep-awake state.")
                        return
                    if self.stop_event.wait(30):
                        break
                ctypes.windll.kernel32.SetThreadExecutionState(continuous)
            except (AttributeError, OSError):
                logger.exception("Windows keep-awake could not be enabled.")
            return

        logger.info("KeepAwakeManager started (caffeinate assertion active).")
        while self.running:
            try:
                self.process = subprocess.Popen(["caffeinate", "-s", "-i", "-m"])
                self.process.wait()
            except (OSError, subprocess.SubprocessError) as e:
                if self.running:
                    logger.error(f"Caffeinate error: {e}")
            if self.running:
                self.stop_event.wait(3)

    def stop(self):
        self.running = False
        self.stop_event.set()
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
        self.thread = None


def handle_message(bot, msg):
    chat_id = msg.get("chat", {}).get("id")
    user_id = msg.get("from", {}).get("id")
    username = msg.get("from", {}).get("username", "Unknown")
    text = (msg.get("text") or "").strip()

    if not chat_id or not user_id:
        return

    # Reload config to get latest allowed users in case it was edited
    global config
    try:
        config = load_config()
    except RuntimeError as error:
        logger.error("%s", error)
        return
    allowed_users = config.get("allowed_user_ids", [])
    pairing_pin = str(config.get("pairing_pin", "")).strip()

    # Security / Pairing Verification
    if user_id not in allowed_users:
        clean_text = text.strip()
        candidate_pin = None

        if clean_text == pairing_pin:
            candidate_pin = clean_text
        elif clean_text.lower().startswith("/pair"):
            candidate_pin = clean_text[5:].strip()
        elif clean_text.lower().startswith("pair "):
            candidate_pin = clean_text[5:].strip()
        elif clean_text.lower().startswith("/start"):
            args = clean_text[6:].strip()
            if args.lower().startswith("pair_"):
                candidate_pin = args[5:].strip()
            elif args.lower().startswith("pair"):
                candidate_pin = args[4:].strip()
            elif args:
                candidate_pin = args

        if candidate_pin and candidate_pin == pairing_pin:
            if user_id not in config["allowed_user_ids"]:
                config["allowed_user_ids"].append(user_id)
                if not save_config(config):
                    config["allowed_user_ids"].remove(user_id)
                    bot.send_message(
                        chat_id,
                        "❌ Pairing could not be saved on this computer. Check the MacRemote activity log.",
                    )
                    return
            mac_name = get_host_model_info()
            bot.send_message(
                chat_id,
                f"🎉 *Successfully Paired!*\n\n"
                f"Welcome, @{username}! Your phone is now authorized to control this *{mac_name}*.\n\n"
                f"📱 Tap any button below or open the *Menu* to send commands anytime.",
                reply_markup=get_main_keyboard()
            )
            logger.info(f"New user paired: {user_id} (@{username})")
            return
        elif candidate_pin and candidate_pin != pairing_pin:
            bot.send_message(
                chat_id,
                f"❌ *Incorrect PIN.* Check your Mac terminal for the correct 4-digit pairing PIN.\n\n"
                f"Reply with: `/pair {pairing_pin}`"
            )
            return
        elif len(allowed_users) == 0 or clean_text.lower().startswith("/start"):
            mac_name = get_host_model_info()
            bot.send_message(
                chat_id,
                f"🔒 *MacRemote Agent for {mac_name}*\n\n"
                f"Authorization is required to control this Mac.\n\n"
                f"To pair your phone, tap below or reply with:\n"
                f"`/pair {pairing_pin}`\n\n"
                f"*(Or reply with your PIN: `{pairing_pin}`)*"
            )
            return
        else:
            bot.send_message(
                chat_id,
                "⛔ *Access Denied.* This Mac is paired with another account."
            )
            return

    # User is authorized - Process Commands
    lower_text = text.lower()
    logger.info("Received message from authorized user %s", user_id)

    # 0. START
    if lower_text == "/start":
        mac_name = get_host_model_info()
        bot.send_message(
            chat_id,
            f"👋 *MacRemote Agent Active!*\n\n"
            f"Connected to: *{mac_name}*\n"
            f"Tap any button below or open the *Menu* to send commands.\n"
            f"Send `/help` for detailed command guide.",
            reply_markup=get_main_keyboard()
        )
        return

    # 1. SCREENSHOT
    if lower_text in ["📸 screenshot", "/ss", "ss", "screenshot", "take a ss", "take screenshot", "ekran görüntüsü"]:
        bot.send_chat_action(chat_id, "upload_photo")
        photo_path, err = SystemActions.take_screenshot()
        if photo_path and os.path.exists(photo_path):
            caption = f"📸 *Screen* • {datetime.datetime.now().strftime('%H:%M:%S')}"
            bot.send_photo(chat_id, photo_path, caption=caption)
            try:
                os.remove(photo_path)
            except Exception:
                pass
        else:
            bot.send_message(chat_id, f"❌ Failed to capture screen: {err}", reply_markup=get_main_keyboard())

    # 2. STATUS
    elif lower_text in ["🔋 status", "/status", "status", "battery", "durum", "pil"]:
        bot.send_chat_action(chat_id, "typing")
        status_msg = SystemActions.get_system_status()
        bot.send_message(chat_id, status_msg, reply_markup=get_main_keyboard())

    # 3. OPEN FINDER
    elif lower_text.startswith("/finder") or lower_text.startswith("open finder") or lower_text == "📂 open finder":
        bot.send_chat_action(chat_id, "typing")
        target = ""
        if lower_text.startswith("/finder"):
            target = text[len("/finder"):].strip()
        elif lower_text.startswith("open finder"):
            target = text[len("open finder"):].strip()
        else:
            target = "~/Downloads"

        result = SystemActions.open_finder(target)
        bot.send_message(chat_id, result, reply_markup=get_main_keyboard())

    # 4. GOOGLE DRIVE SHARE
    elif lower_text.startswith("/drive") or lower_text.startswith("share on drive") or lower_text.startswith("share to drive") or lower_text == "💾 google drive":
        bot.send_chat_action(chat_id, "typing")
        parts = text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            filepath = parts[1].strip()
            result = SystemActions.share_to_google_drive(filepath)
            bot.send_message(chat_id, result, reply_markup=get_main_keyboard())
        else:
            drive_folder = os.path.join(config.get("google_drive_path", ""), "Remote_Shared")
            os.makedirs(drive_folder, exist_ok=True)
            files = os.listdir(drive_folder)
            flist = "\n".join([f"• `{f}`" for f in files[:10]]) if files else "_No files in Remote_Shared yet._"
            msg = (
                f"💾 *Google Drive Remote Sync*\n\n"
                f"To share any file from your Mac to Google Drive, send:\n"
                f"`/drive <filepath>`\n"
                f"Example: `/drive ~/Downloads/myfile.pdf`\n\n"
                f"*Recently Shared Files:*\n{flist}"
            )
            bot.send_message(chat_id, msg, reply_markup=get_main_keyboard())

    # 5. GET / DOWNLOAD FILE DIRECTLY TO PHONE
    elif lower_text.startswith("/get") or lower_text.startswith("/file") or lower_text.startswith("send me"):
        bot.send_chat_action(chat_id, "upload_document")
        target = text.split(maxsplit=1)[1].strip() if " " in text else ""
        resolved = os.path.expanduser(target)
        if not os.path.exists(resolved):
            resolved = os.path.expanduser(f"~/Downloads/{target}")

        if os.path.exists(resolved) and os.path.isfile(resolved):
            size_mb = os.path.getsize(resolved) / (1024 * 1024)
            if size_mb > 48:
                bot.send_message(chat_id, f"⚠️ File is too large for direct Telegram transfer ({size_mb:.1f} MB > 50MB limit). Use `/drive {target}` instead!", reply_markup=get_main_keyboard())
            else:
                bot.send_document(chat_id, resolved, caption=f"📄 {os.path.basename(resolved)}")
        else:
            bot.send_message(chat_id, f"❌ File not found: `{target}`", reply_markup=get_main_keyboard())

    # 6. LOCK SCREEN
    elif lower_text in ["🔒 lock screen", "/lock", "lock", "kilitle"]:
        res = SystemActions.lock_screen()
        bot.send_message(chat_id, res, reply_markup=get_main_keyboard())

    # 7. DISABLE REMOTE SHELL COMMANDS
    elif lower_text.startswith("/sh ") or lower_text.startswith("/cmd ") or lower_text.startswith("/bash "):
        bot.send_message(
            chat_id,
            "⛔ Remote shell commands are disabled. Use a built-in action or submit a coding-agent task for local host approval.",
            reply_markup=get_main_keyboard(),
        )

    # 8. CODING-AGENT TASKS
    elif lower_text.startswith("/agy ") or lower_text.startswith("antigravity ") or lower_text == "🤖 antigravity ai":
        if lower_text == "🤖 antigravity ai":
            bot.send_message(
                chat_id,
                f"🤖 *Antigravity AI Agent*\n\n"
                f"Send me any task or prompt, for example:\n"
                f"`/agy write a python script to organize my desktop`\n"
                f"`/agy summarize my recent git commits`\n\n"
                f"The task will wait for approval in the MacRemote host app before it starts.",
                reply_markup=get_main_keyboard()
            )
        else:
            prompt = text.split(maxsplit=1)[1].strip()
            try:
                task_id = enqueue_agent_task("antigravity", prompt, user_id, chat_id)
            except ValueError as error:
                bot.send_message(chat_id, f"❌ {error}", reply_markup=get_main_keyboard())
                return
            bot.send_message(
                chat_id,
                f"⏳ Antigravity task `{task_id}` is waiting for approval on the host.",
                reply_markup=get_main_keyboard(),
            )

    elif lower_text == "🧠 claude code":
        bot.send_message(
            chat_id,
            "🧠 *Claude Code*\n\nSend a task with `/claude <prompt>`. It will wait for approval in the host app.",
            reply_markup=get_main_keyboard(),
        )

    elif lower_text.startswith("/claude ") or lower_text.startswith("claude code "):
        prompt = text.split(maxsplit=1)[1].strip()
        try:
            task_id = enqueue_agent_task("claude", prompt, user_id, chat_id)
        except ValueError as error:
            bot.send_message(chat_id, f"❌ {error}", reply_markup=get_main_keyboard())
            return
        bot.send_message(
            chat_id,
            f"⏳ Claude Code task `{task_id}` is waiting for approval on the host.",
            reply_markup=get_main_keyboard(),
        )

    # 9. HELP
    elif lower_text in ["/help", "help", "yardım"]:
        mac_name = get_host_model_info()
        help_text = (
            f"🚀 *MacRemote Agent for {mac_name}*\n\n"
            f"Control your computer from your phone:\n\n"
            f"📸 *Screenshot:* Tap `📸 Screenshot` or type `/ss`\n"
            f"🔋 *Battery & Power:* Tap `🔋 Status` or type `/status`\n"
            f"📂 *Open folder:* Tap `📂 Open Finder` or type `/finder <path>`\n"
            f"💾 *Share to Drive:* Tap `💾 Google Drive` or `/drive <file>`\n"
            f"📥 *Send File to Phone:* Type `/get <filepath>`\n"
            f"🤖 *Antigravity:* Type `/agy <prompt>`\n"
            f"🧠 *Claude Code:* Type `/claude <prompt>`\n"
            f"🔒 *Lock Screen:* Tap `🔒 Lock Screen` or type `/lock`\n"
            f"Agent tasks wait for approval in the host app before they run.\n\n"
            f"💡 *Menu Button:* Tap the blue *Menu* button in the corner to see all commands."
        )
        bot.send_message(chat_id, help_text, reply_markup=get_main_keyboard())

    # 10. NATURAL LANGUAGE SMART ROUTING
    else:
        bot.send_chat_action(chat_id, "typing")
        if any(w in lower_text for w in ["screenshot", "screen shot", "ss al", "ekran"]):
            photo_path, err = SystemActions.take_screenshot()
            if photo_path:
                bot.send_photo(chat_id, photo_path, caption=f"📸 Screen captured • {datetime.datetime.now().strftime('%H:%M:%S')}")
                try:
                    os.remove(photo_path)
                except Exception:
                    pass
                return

        if "open finder" in lower_text or "finder aç" in lower_text:
            words = text.split()
            path = words[-1] if len(words) > 2 and not words[-1].lower() in ["finder", "open", "aç"] else "~/Downloads"
            res = SystemActions.open_finder(path)
            bot.send_message(chat_id, res, reply_markup=get_main_keyboard())
            return

        if "drive" in lower_text and any(w in lower_text for w in ["share", "copy", "at", "yükle", "open"]):
            words = text.split()
            found_path = None
            for w in words:
                if "/" in w or "." in w:
                    found_path = w.strip("'\"")
                    break
            if found_path:
                res = SystemActions.share_to_google_drive(found_path)
                bot.send_message(chat_id, res, reply_markup=get_main_keyboard())
                return

        bot.send_message(
            chat_id,
            "I didn’t recognize that as a built-in action. Use `/agy <prompt>` or `/claude <prompt>` to submit a task for host approval.",
            reply_markup=get_main_keyboard(),
        )


def main():
    global config
    logger.info("Starting MacRemote Agent...")

    # Single-instance lock check
    if not acquire_instance_lock():
        sys.exit(1)

    try:
        config = load_config()
    except RuntimeError as error:
        logger.error("%s", error)
        return
    initialize_task_store()

    bot_token = config.get("bot_token", "").strip()
    relay_url = config.get("relay_url", "").strip()
    relay_host_id = config.get("relay_host_id", "").strip()
    relay_host_token = config.get("relay_host_token", "").strip()
    relay_client = None
    relay_fields = [relay_url, relay_host_id, relay_host_token]
    if any(relay_fields):
        if not all(relay_fields):
            logger.error("Relay settings are incomplete. Configure relay URL, host ID, and host token together.")
        else:
            try:
                relay_client = RelayClient(relay_url, relay_host_id, relay_host_token)
                logger.info("Relay connection configured.")
            except ValueError as error:
                logger.error("Relay configuration error: %s", error)

    bot = None
    bot_info = {}
    if bot_token:
        candidate_bot = TelegramBot(bot_token)
        me = candidate_bot.get_me()
        if me.get("ok"):
            bot = candidate_bot
            bot_info = me.get("result", {})
            logger.info("Bot connected: @%s (%s)", bot_info.get("username"), bot_info.get("first_name"))
            bot.set_my_commands()
        else:
            logger.error("Could not connect to Telegram; relay mode will continue if configured.")
    if bot is None and relay_client is None:
        logger.error("Configure a Telegram bot or a MacRemote relay in the host app.")
        return

    threading.Thread(
        target=run_agent_task_worker,
        args=(bot, relay_client),
        daemon=True,
    ).start()
    if relay_client:
        threading.Thread(
            target=relay_client.run_forever,
            args=(bot,),
            daemon=True,
        ).start()

    # Start sleep prevention daemon
    global keep_awake_instance
    if config.get("keep_awake", True):
        keep_awake_instance = KeepAwakeManager()
        keep_awake_instance.start()

    pin = config.get("pairing_pin")
    allowed = config.get("allowed_user_ids", [])
    if bot and not allowed:
        print("\n" + "="*60)
        print(f"🔑 BOT READY FOR PAIRING!")
        print(f"Open Telegram on your phone, start @{bot_info.get('username')},")
        print(f"and send this command:")
        print(f"   /pair {pin}")
        print("="*60 + "\n")
    elif bot:
        logger.info(f"Authorized users: {allowed}")

    offset = None
    logger.info("Host agent is ready for phone commands and locally approved coding tasks.")

    while not shutdown_event.is_set():
        try:
            if bot is None:
                shutdown_event.wait(1)
                continue
            updates = bot.get_updates(offset=offset, timeout=5)
            if updates.get("ok"):
                for update in updates.get("result", []):
                    offset = update.get("update_id") + 1
                    msg = update.get("message")
                    if msg:
                        handle_message(bot, msg)
            else:
                time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Shutting down MacRemote Agent...")
            break
        except Exception as e:
            logger.error(f"Unexpected loop exception: {e}")
            time.sleep(3)

    cleanup_handler()


if __name__ == "__main__":
    main()
