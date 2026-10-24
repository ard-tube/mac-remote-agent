#!/usr/bin/env python3
"""
MacRemote Agent - Control any Apple Silicon Mac from your Android phone via Telegram.
Universal support for all Apple M-Series Macs (M1, M2, M3, M4, Air, Pro, Max, Ultra, Studio, Mini).
Features Antigravity AI integration, Google Drive syncing, and complete macOS automation.
"""

import os
import sys
import json
import time
import uuid
import glob
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

DEFAULT_CONFIG = {
    "bot_token": "",
    "allowed_user_ids": [],
    "pairing_pin": "",
    "google_drive_path": os.path.expanduser("~/Google Drive/My Drive"),
    "antigravity_bin": "/Users/sddsd/.local/bin/agy",
    "keep_awake": True
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                # merge with defaults
                merged = {**DEFAULT_CONFIG, **cfg}
                return merged
        except Exception as e:
            logger.error(f"Error loading config.json: {e}")
    # generate a random 4-digit PIN for first setup
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
        except Exception as e:
            # timeout during long polling is expected
            return {"ok": True, "result": []}

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
            # Capture Retina display as high-quality JPEG
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
            # Open Finder window
            subprocess.run(["open", target_path], check=True, timeout=5)
            # Activate Finder
            subprocess.run(["osascript", "-e", 'tell application "Finder" to activate'], timeout=5)

            # List top files
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
            # Check Downloads folder fallback
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
                f"Google Drive will automatically sync this to your Android phone in seconds."
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
            # parse percentage
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
            return "🔒 *MacBook screen locked and display turned off.*"
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
            # Trim to Telegram limit
            if len(combined) > 3500:
                combined = combined[:3500] + "\n...[truncated]"
            return f"```\n{combined}\n```"
        except subprocess.TimeoutExpired:
            return "⏱️ *Command timed out after 45 seconds.*"
        except Exception as e:
            return f"❌ *Execution error:* `{str(e)}`"

    @staticmethod
    def run_antigravity(prompt):
        """Runs Antigravity CLI non-interactively with the given prompt."""
        agy_bin = config.get("antigravity_bin", "/Users/sddsd/.local/bin/agy")
        if not os.path.exists(agy_bin):
            return "❌ Antigravity CLI binary not found at " + agy_bin
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
                # -s: prevent system sleep on AC power
                # -i: prevent idle sleep
                # -m: prevent disk sleep
                self.process = subprocess.Popen(["caffeinate", "-s", "-i", "-m"])
                self.process.wait()
            except Exception as e:
                logger.error(f"Caffeinate error: {e}")
            time.sleep(5)

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass


def handle_message(bot, msg):
    chat_id = msg.get("chat", {}).get("id")
    user_id = msg.get("from", {}).get("id")
    username = msg.get("from", {}).get("username", "Unknown")
    text = (msg.get("text") or "").strip()

    if not chat_id or not user_id:
        return

    allowed_users = config.get("allowed_user_ids", [])
    pairing_pin = config.get("pairing_pin", "")

    # Security / Pairing Verification
    if user_id not in allowed_users:
        # Check for pairing attempt
        if text.startswith("/pair") or text == pairing_pin:
            parts = text.split()
            provided_pin = parts[1] if len(parts) > 1 else parts[0]
            if provided_pin == pairing_pin:
                config["allowed_user_ids"].append(user_id)
                save_config(config)
                mac_name = get_mac_model_info()
                bot.send_message(
                    chat_id,
                    f"🎉 *Successfully Paired!*\n\n"
                    f"Welcome, @{username}! Your Android phone is now authorized to control this *{mac_name}*.\n\n"
                    f"Tap any button below or send commands anytime.",
                    reply_markup=get_main_keyboard()
                )
                logger.info(f"New user paired: {user_id} (@{username})")
                return
            else:
                bot.send_message(
                    chat_id,
                    f"❌ *Incorrect PIN.* Check your Mac terminal for the correct 4-digit pairing PIN."
                )
                return
        elif len(allowed_users) == 0:
            # First user ever: prompt for pairing
            bot.send_message(
                chat_id,
                f"🔒 *MacRemote Agent - Authorization Required*\n\n"
                f"To pair your Android phone with this Mac, reply with:\n"
                f"`/pair {pairing_pin}`\n\n"
                f"*(PIN is displayed in your Mac terminal)*"
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

    # 1. SCREENSHOT
    if lower_text in ["📸 screenshot", "/ss", "ss", "screenshot", "take a ss", "take screenshot", "ekran görüntüsü"]:
        bot.send_chat_action(chat_id, "upload_photo")
        photo_path, err = SystemActions.take_screenshot()
        if photo_path and os.path.exists(photo_path):
            caption = f"📸 *MacBook Screen* • {datetime.datetime.now().strftime('%H:%M:%S')}"
            bot.send_photo(chat_id, photo_path, caption=caption)
            try:
                os.remove(photo_path)
            except Exception:
                pass
        else:
            bot.send_message(chat_id, f"❌ Failed to capture screen: {err}")

    # 2. STATUS
    elif lower_text in ["🔋 status", "/status", "status", "battery", "durum", "pil"]:
        bot.send_chat_action(chat_id, "typing")
        status_msg = SystemActions.get_system_status()
        bot.send_message(chat_id, status_msg, reply_markup=get_main_keyboard())

    # 3. OPEN FINDER
    elif lower_text.startswith("/finder") or lower_text.startswith("open finder") or lower_text == "📂 open finder":
        bot.send_chat_action(chat_id, "typing")
        # Extract path if provided
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
            # Show Google Drive Remote_Shared folder info
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

    # 5. GET / DOWNLOAD FILE TO PHONE DIRECTLY
    elif lower_text.startswith("/get") or lower_text.startswith("/file") or lower_text.startswith("send me"):
        bot.send_chat_action(chat_id, "upload_document")
        target = text.split(maxsplit=1)[1].strip() if " " in text else ""
        resolved = os.path.expanduser(target)
        if not os.path.exists(resolved):
            resolved = os.path.expanduser(f"~/Downloads/{target}")

        if os.path.exists(resolved) and os.path.isfile(resolved):
            size_mb = os.path.getsize(resolved) / (1024 * 1024)
            if size_mb > 48:
                bot.send_message(chat_id, f"⚠️ File is too large for Telegram ({size_mb:.1f} MB > 50MB limit). Use `/drive {target}` instead!")
            else:
                bot.send_document(chat_id, resolved, caption=f"📄 {os.path.basename(resolved)}")
        else:
            bot.send_message(chat_id, f"❌ File not found: `{target}`")

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

    # 8. ANTIGRAVITY AI EXPLICIT
    elif lower_text.startswith("/agy ") or lower_text.startswith("antigravity ") or lower_text == "🤖 antigravity ai":
        bot.send_chat_action(chat_id, "typing")
        if lower_text == "🤖 antigravity ai":
            bot.send_message(
                chat_id,
                f"🤖 *Antigravity AI Agent*\n\n"
                f"Send me any task or prompt, for example:\n"
                f"`/agy write a python script to organize my desktop`\n"
                f"`/agy summarize my recent git commits`\n\n"
                f"Antigravity will run on your Mac and report the results right here!",
                reply_markup=get_main_keyboard()
            )
        else:
            prompt = text.split(maxsplit=1)[1].strip()
            bot.send_message(chat_id, f"🤖 *Antigravity is working on:* \"{prompt}\"...\n_Please wait..._")
            res = SystemActions.run_antigravity(prompt)
            bot.send_message(chat_id, res, reply_markup=get_main_keyboard())

    # 9. START / HELP
    elif lower_text in ["/start", "/help", "help", "yardım"]:
        mac_name = get_mac_model_info()
        help_text = (
            f"🚀 *MacRemote Agent for {mac_name}*\n\n"
            f"Control your Mac anytime, anywhere from your Android phone:\n\n"
            f"📸 *Screenshot:* Tap `📸 Screenshot` or type `/ss`\n"
            f"🔋 *Battery & Power:* Tap `🔋 Status` or type `/status`\n"
            f"📂 *Open Finder:* Tap `📂 Open Finder` or type `/finder <path>`\n"
            f"💾 *Share to Drive:* Tap `💾 Google Drive` or `/drive <file>`\n"
            f"📥 *Send File to Phone:* Type `/get <filepath>`\n"
            f"⚙️ *Run Command:* Type `/sh <command>`\n"
            f"🤖 *Antigravity Agent:* Type `/agy <prompt>`\n"
            f"🔒 *Lock Screen:* Tap `🔒 Lock Screen` or type `/lock`\n\n"
            f"💬 *Natural Language:* You can also type natural requests like:\n"
            f"• _\"take a screenshot\"_\n"
            f"• _\"open finder ~/Downloads\"_\n"
            f"• _\"share ~/Documents/report.pdf on drive\"_"
        )
        bot.send_message(chat_id, help_text, reply_markup=get_main_keyboard())

    # 10. NATURAL LANGUAGE SMART ROUTING
    else:
        bot.send_chat_action(chat_id, "typing")
        # Check natural language patterns
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
            # look for a file path
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

        # Fallback to Antigravity AI!
        bot.send_message(chat_id, f"🤖 *Consulting Antigravity for:* \"{text}\"...")
        res = SystemActions.run_antigravity(text)
        bot.send_message(chat_id, res, reply_markup=get_main_keyboard())


def main():
    logger.info("Starting MacRemote Agent...")
    bot_token = config.get("bot_token", "").strip()

    if not bot_token:
        print("\n" + "="*60)
        print("⚠️  TELEGRAM BOT TOKEN REQUIRED")
        print("="*60)
        print("1. Open Telegram on your Android phone.")
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

    # Start sleep prevention daemon
    if config.get("keep_awake", True):
        keep_awake = KeepAwakeManager()
        keep_awake.start()

    pin = config.get("pairing_pin")
    allowed = config.get("allowed_user_ids", [])
    if not allowed:
        print("\n" + "="*60)
        print(f"🔑 BOT READY FOR PAIRING!")
        print(f"Open Telegram on your Android phone, start @{bot_info.get('username')},")
        print(f"and send this command:")
        print(f"   /pair {pin}")
        print("="*60 + "\n")
    else:
        logger.info(f"Authorized users: {allowed}")

    offset = None
    logger.info("Agent is listening for remote commands from your Android phone...")

    while True:
        try:
            updates = bot.get_updates(offset=offset, timeout=25)
            if updates.get("ok"):
                for update in updates.get("result", []):
                    offset = update.get("update_id") + 1
                    msg = update.get("message")
                    if msg:
                        handle_message(bot, msg)
        except KeyboardInterrupt:
            logger.info("Shutting down MacRemote Agent...")
            break
        except Exception as e:
            logger.error(f"Unexpected loop exception: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
