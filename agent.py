#!/usr/bin/env python3
"""
MacRemote Agent - Control any Apple Silicon Mac from your phone via Telegram.
Universal support for all Apple M-Series Macs (M1, M2, M3, M4, Air, Pro, Max, Ultra, Studio, Mini).
Features Antigravity AI integration, Google Drive syncing, and complete macOS automation.
"""

import os
import sys
import json
import time
import uuid
import glob
import fcntl
import signal
import socket
import atexit
import shutil
import logging
import datetime
import subprocess
import threading
import urllib.request
import urllib.parse
import urllib.error

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MacRemoteAgent")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TMP_DIR = "/tmp/mac_remote"
os.makedirs(TMP_DIR, exist_ok=True)
LOCK_FILE = os.path.join(TMP_DIR, "mac_remote_agent.lock")
PID_FILE = os.path.join(BASE_DIR, "agent.pid")

DEFAULT_CONFIG = {
    "bot_token": "",
    "allowed_user_ids": [],
    "pairing_pin": "",
    "google_drive_path": os.path.expanduser("~/Google Drive/My Drive"),
    "antigravity_bin": os.path.expanduser("~/.local/bin/agy"),
    "keep_awake": True
}

lock_file_handle = None
keep_awake_instance = None


def acquire_instance_lock():
    """Ensures only a single instance of MacRemote Agent runs to prevent 409 Conflict."""
    global lock_file_handle
    try:
        lock_file_handle = open(LOCK_FILE, "a+")
        fcntl.flock(lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with open(PID_FILE, "w") as pf:
            pf.write(str(os.getpid()))
        return True
    except (IOError, BlockingIOError):
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
    """Cleanly terminates child processes, caffeinate assertions, and releases locks."""
    global keep_awake_instance, lock_file_handle
    if keep_awake_instance:
        try:
            keep_awake_instance.stop()
        except Exception:
            pass
        keep_awake_instance = None

    # Kill any orphaned caffeinate child processes
    try:
        subprocess.run(["pkill", "-f", "caffeinate -s -i -m"], capture_output=True, timeout=2)
    except Exception:
        pass

    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    if lock_file_handle:
        try:
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
if signal.getsignal(signal.SIGHUP) != signal.SIG_IGN:
    signal.signal(signal.SIGHUP, cleanup_handler)
atexit.register(cleanup_handler)


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                merged = {**DEFAULT_CONFIG, **cfg}
                return merged
        except Exception as e:
            logger.error(f"Error loading config.json: {e}")
    # Generate random 4-digit PIN for first setup
    cfg = DEFAULT_CONFIG.copy()
    cfg["pairing_pin"] = f"{int(time.time()) % 9000 + 1000}"
    save_config(cfg)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving config.json: {e}")


config = load_config()


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
            {"command": "sh", "description": "⚙️ Run terminal shell command"},
            {"command": "agy", "description": "🤖 Run Antigravity AI prompt"},
            {"command": "lock", "description": "🔒 Lock Mac display"},
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


def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "📸 Screenshot"}, {"text": "🔋 Status"}],
            [{"text": "📂 Open Finder"}, {"text": "💾 Google Drive"}],
            [{"text": "🤖 Antigravity AI"}, {"text": "🔒 Lock Screen"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }


def get_mac_model_info():
    """Dynamically detects Mac model and Apple Silicon chip (M1, M2, M3, M4, etc.)."""
    chip = "Apple Silicon"
    model = "Mac"
    try:
        res = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=2)
        if res.stdout.strip():
            chip = res.stdout.strip()
    except Exception:
        pass

    try:
        res = subprocess.run(["system_profiler", "SPHardwareDataType"], capture_output=True, text=True, timeout=3)
        for line in res.stdout.split("\n"):
            if "Model Name:" in line:
                model = line.split(":", 1)[1].strip()
                break
    except Exception:
        pass

    return f"{model} ({chip})"


class SystemActions:
    """macOS local automation methods."""

    @staticmethod
    def take_screenshot():
        """Wakes screen buffer and captures a JPEG screenshot."""
        out_path = os.path.join(TMP_DIR, f"ss_{int(time.time())}.jpg")
        try:
            # Wake display assertion for 2 seconds to ensure frame buffer is updated
            subprocess.run(["caffeinate", "-u", "-t", "2"], timeout=3)
            # Capture display as JPEG
            res = subprocess.run(
                ["screencapture", "-x", "-t", "jpg", out_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            if res.returncode == 0 and os.path.exists(out_path):
                return out_path, None
            else:
                return None, f"Screenshot error: {res.stderr}"
        except Exception as e:
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
            subprocess.run(["open", target_path], check=True, timeout=5)
            subprocess.run(["osascript", "-e", 'tell application "Finder" to activate'], timeout=5)

            items = os.listdir(target_path)
            item_list = []
            for item in sorted(items)[:15]:
                if not item.startswith("."):
                    full_p = os.path.join(target_path, item)
                    icon = "📁" if os.path.isdir(full_p) else "📄"
                    item_list.append(f"{icon} `{item}`")

            listing = "\n".join(item_list) if item_list else "_Folder is empty._"
            return (
                f"📂 *Opened Finder in:*\n`{target_path}`\n\n"
                f"*Contents (top {len(item_list)}):*\n{listing}\n\n"
                f"💡 _Tip: Reply with `/drive <filename>` or `/get <filename>` to share or download._"
            )
        except Exception as e:
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
        """Gathers battery, power adapter, disk, CPU, and uptime status for any M-series Mac."""
        mac_name = get_mac_model_info()
        lines = [f"💻 *{mac_name} Status*\n"]

        # Battery / AC power
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
        except Exception:
            lines.append("*Power:* Unknown")

        # Disk space
        try:
            df_res = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=3)
            df_lines = df_res.stdout.strip().split("\n")
            if len(df_lines) > 1:
                parts = df_lines[1].split()
                lines.append(f"*Disk (Macintosh HD):* `{parts[3]} free` of `{parts[1]}` ({parts[4]} used)")
        except Exception:
            pass

        # Uptime
        try:
            up_res = subprocess.run(["uptime"], capture_output=True, text=True, timeout=3)
            lines.append(f"*Uptime:* `{up_res.stdout.strip()}`")
        except Exception:
            pass

        lines.append(f"\n⏰ *Time:* `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
        return "\n".join(lines)

    @staticmethod
    def lock_screen():
        """Puts displays to sleep / locks Mac screen."""
        try:
            subprocess.run(["pmset", "displaysleepnow"], timeout=3)
            return "🔒 *Mac screen locked and display turned off.*"
        except Exception as e:
            return f"❌ Failed to lock: {e}"

    @staticmethod
    def run_terminal(cmd):
        """Runs a bash/zsh terminal command."""
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                executable="/bin/zsh",
                capture_output=True,
                text=True,
                timeout=45
            )
            out = res.stdout
            err = res.stderr
            combined = ""
            if out:
                combined += out
            if err:
                combined += f"\n[stderr]\n{err}"
            if not combined.strip():
                combined = "[Command executed successfully with no output]"
            if len(combined) > 3500:
                combined = combined[:3500] + "\n...[truncated]"
            return f"```\n{combined}\n```"
        except subprocess.TimeoutExpired:
            return "⏱️ *Command timed out after 45 seconds.*"
        except Exception as e:
            return f"❌ *Execution error:* `{str(e)}`"

    @staticmethod
    def find_antigravity_bin():
        """Dynamically locates the Antigravity CLI binary."""
        configured = config.get("antigravity_bin", "")
        if configured:
            expanded = os.path.expanduser(configured)
            if os.path.exists(expanded) and os.access(expanded, os.X_OK):
                return expanded
        for p in [
            os.path.expanduser("~/.local/bin/agy"),
            os.path.expanduser("~/.gemini/antigravity-ide/bin/agy"),
            shutil.which("agy")
        ]:
            if p and os.path.exists(p) and os.access(p, os.X_OK):
                return p
        return configured or "agy"

    @staticmethod
    def run_antigravity(prompt):
        """Runs Antigravity CLI non-interactively with the given prompt."""
        agy_bin = SystemActions.find_antigravity_bin()
        if not os.path.exists(agy_bin) and not shutil.which(agy_bin):
            return f"❌ Antigravity CLI binary not found at `{agy_bin}`. Configure in config.json or install Antigravity."
        try:
            cmd = [agy_bin, "-p", prompt]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            out = res.stdout.strip()
            if not out and res.stderr:
                out = res.stderr.strip()
            if len(out) > 3800:
                out = out[:3800] + "\n...[response truncated]"
            return out if out else "🤖 Antigravity completed the task."
        except subprocess.TimeoutExpired:
            return "⏱️ Antigravity prompt timed out after 2 minutes."
        except Exception as e:
            return f"❌ Antigravity execution error: {str(e)}"


class KeepAwakeManager:
    """Keeps the Mac awake while plugged in on AC power."""
    def __init__(self):
        self.process = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self):
        logger.info("KeepAwakeManager started (caffeinate assertion active while on AC).")
        while self.running:
            try:
                self.process = subprocess.Popen(["caffeinate", "-s", "-i", "-m"])
                self.process.wait()
            except Exception as e:
                if self.running:
                    logger.error(f"Caffeinate error: {e}")
            if self.running:
                time.sleep(3)

    def stop(self):
        self.running = False
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
        # Clean up any orphan caffeinate processes
        try:
            subprocess.run(["pkill", "-f", "caffeinate -s -i -m"], capture_output=True, timeout=2)
        except Exception:
            pass


def handle_message(bot, msg):
    chat_id = msg.get("chat", {}).get("id")
    user_id = msg.get("from", {}).get("id")
    username = msg.get("from", {}).get("username", "Unknown")
    text = (msg.get("text") or "").strip()

    if not chat_id or not user_id:
        return

    # Reload config to get latest allowed users in case it was edited
    global config
    config = load_config()
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
                save_config(config)
            mac_name = get_mac_model_info()
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
            mac_name = get_mac_model_info()
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
    logger.info(f"Received command from {user_id}: {text}")

    # 0. START
    if lower_text == "/start":
        mac_name = get_mac_model_info()
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
            caption = f"📸 *Mac Screen* • {datetime.datetime.now().strftime('%H:%M:%S')}"
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

    # 7. RUN TERMINAL COMMAND
    elif lower_text.startswith("/sh ") or lower_text.startswith("/cmd ") or lower_text.startswith("/bash "):
        bot.send_chat_action(chat_id, "typing")
        cmd = text.split(maxsplit=1)[1].strip()
        bot.send_message(chat_id, f"⚙️ *Executing:* `{cmd}`...")
        res = SystemActions.run_terminal(cmd)
        bot.send_message(chat_id, res, reply_markup=get_main_keyboard())

    # 8. ANTIGRAVITY AI
    elif lower_text.startswith("/agy ") or lower_text.startswith("antigravity ") or lower_text == "🤖 antigravity ai":
        bot.send_chat_action(chat_id, "typing")
        if lower_text == "🤖 antigravity ai":
            bot.send_message(
                chat_id,
                f"🤖 *Antigravity AI Agent*\n\n"
                f"Send me any task or prompt, for example:\n"
                f"`/agy write a python script to organize my desktop`\n"
                f"`/agy summarize my recent git commits`\n\n"
                f"Antigravity will execute on your Mac and report the results right here!",
                reply_markup=get_main_keyboard()
            )
        else:
            prompt = text.split(maxsplit=1)[1].strip()
            bot.send_message(chat_id, f"🤖 *Antigravity is working on:* \"{prompt}\"...\n_Please wait..._")
            res = SystemActions.run_antigravity(prompt)
            bot.send_message(chat_id, res, reply_markup=get_main_keyboard())

    # 9. HELP
    elif lower_text in ["/help", "help", "yardım"]:
        mac_name = get_mac_model_info()
        help_text = (
            f"🚀 *MacRemote Agent for {mac_name}*\n\n"
            f"Control your Mac anytime, anywhere from your phone:\n\n"
            f"📸 *Screenshot:* Tap `📸 Screenshot` or type `/ss`\n"
            f"🔋 *Battery & Power:* Tap `🔋 Status` or type `/status`\n"
            f"📂 *Open Finder:* Tap `📂 Open Finder` or type `/finder <path>`\n"
            f"💾 *Share to Drive:* Tap `💾 Google Drive` or `/drive <file>`\n"
            f"📥 *Send File to Phone:* Type `/get <filepath>`\n"
            f"⚙️ *Run Command:* Type `/sh <command>`\n"
            f"🤖 *Antigravity Agent:* Type `/agy <prompt>`\n"
            f"🔒 *Lock Screen:* Tap `🔒 Lock Screen` or type `/lock`\n\n"
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

        # Fallback to Antigravity AI
        bot.send_message(chat_id, f"🤖 *Consulting Antigravity for:* \"{text}\"...")
        res = SystemActions.run_antigravity(text)
        bot.send_message(chat_id, res, reply_markup=get_main_keyboard())


def main():
    logger.info("Starting MacRemote Agent...")

    # Single-instance lock check
    if not acquire_instance_lock():
        sys.exit(1)

    bot_token = config.get("bot_token", "").strip()

    if not bot_token:
        print("\n" + "="*60)
        print("⚠️  TELEGRAM BOT TOKEN REQUIRED")
        print("="*60)
        print("1. Open Telegram on your phone.")
        print("2. Search for '@BotFather' and tap START.")
        print("3. Send: /newbot")
        print("4. Follow the prompts to choose a Name and Username for your bot.")
        print("5. Copy the HTTP API token provided by BotFather.")
        print(f"6. Paste the token into:\n   {CONFIG_FILE}")
        print(f"   Or run: ./setup.sh")
        print(f"\nYour Pairing PIN: {config.get('pairing_pin')}")
        print("="*60 + "\n")
        return

    bot = TelegramBot(bot_token)
    me = bot.get_me()
    if not me.get("ok"):
        logger.error(f"Failed to connect to Telegram: {me.get('error')}. Please verify bot_token in config.json.")
        return

    bot_info = me.get("result", {})
    logger.info(f"Bot connected: @{bot_info.get('username')} ({bot_info.get('first_name')})")

    # Register command menu and Menu button on Telegram
    bot.set_my_commands()

    # Start sleep prevention daemon
    global keep_awake_instance
    if config.get("keep_awake", True):
        keep_awake_instance = KeepAwakeManager()
        keep_awake_instance.start()

    pin = config.get("pairing_pin")
    allowed = config.get("allowed_user_ids", [])
    if not allowed:
        print("\n" + "="*60)
        print(f"🔑 BOT READY FOR PAIRING!")
        print(f"Open Telegram on your phone, start @{bot_info.get('username')},")
        print(f"and send this command:")
        print(f"   /pair {pin}")
        print("="*60 + "\n")
    else:
        logger.info(f"Authorized users: {allowed}")

    offset = None
    logger.info("Agent is listening for remote commands from your phone...")

    while True:
        try:
            updates = bot.get_updates(offset=offset, timeout=25)
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
