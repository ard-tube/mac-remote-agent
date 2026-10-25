# 🚀 MacRemote — Universal Remote Control for Apple Silicon Macs

[![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon%20(M1%2FM2%2FM3%2FM4)-black?logo=apple&style=for-the-badge)](https://apple.com)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&style=for-the-badge)](https://python.org)
[![Telegram](https://img.shields.io/badge/Control-Telegram%20Bot%20API-0088cc?logo=telegram&style=for-the-badge)](https://telegram.org)
[![Antigravity](https://img.shields.io/badge/Agent-Google%20Antigravity%20AI-purple?style=for-the-badge)](https://antigravity.google)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

> Control any **Apple Silicon Mac (M1, M2, M3, M4 / Air, Pro, Mini, Studio)** from your **phone** anytime, anywhere via Telegram.
> Featuring instant Retina screenshots, Finder automation, Google Drive syncing, and full **Google Antigravity AI** integration.

---

## ⚡ Key Highlights

- 🍏 **Universal M-Series Support:** Engineered for all Apple Silicon Macs:
  - **M1 Series:** M1, M1 Pro, M1 Max, M1 Ultra (MacBook Air, MacBook Pro, Mac mini, iMac, Mac Studio)
  - **M2 Series:** M2, M2 Pro, M2 Max, M2 Ultra (MacBook Air 13"/15", MacBook Pro 14"/16", Mac mini, Mac Studio, Mac Pro)
  - **M3 Series:** M3, M3 Pro, M3 Max (MacBook Air 13"/15", MacBook Pro 14"/16", iMac)
  - **M4 Series:** M4, M4 Pro, M4 Max (MacBook Pro, Mac mini, iMac)
- 💻 **Instant `mra` CLI Access:** Control, start, stop, monitor, or view live logs from anywhere by typing `mra` in Terminal.
- 📱 **Telegram Bot Commands Menu:** All commands automatically registered and visible on your phone in the Telegram **Menu** button.
- 📸 **Retina Screenshot Streaming:** Wakes screen buffer and captures high-res display shots in ~2 seconds.
- 📂 **Remote Finder Navigation:** Open any directory, view files, or reveal specific files in Finder.
- 💾 **Google Drive Auto-Sync:** 1-command copying to Google Drive (`Remote_Shared`) with instant mobile sync.
- 📥 **Direct Telegram File Transfer:** Request any file from your Mac and have it delivered directly into your Telegram chat.
- 🤖 **Antigravity AI Agent Bridge:** Delegate coding, debugging, or complex automation tasks to Antigravity CLI directly from your phone.
- 🔌 **Smart Clamshell Keep-Awake:** Prevents sleep while plugged into AC power even with lid closed.
- 🔒 **End-to-End Pairing Security:** PIN-protected pairing ensures only your authorized phone can command your Mac.
- 🛡️ **Clean Lifecycle & Conflict Protection:** OS-level singleton locking prevents duplicate instance conflicts (HTTP 409), and clean signal handling ensures all subshells and caffeinate processes shut down properly.

---

## 💻 Quick Terminal Access: `mra`

Type `mra` in any terminal window to access the agent controller:

```bash
mra          # Open status dashboard and quick actions
mra start    # Start agent in background (stays alive after closing terminal)
mra stop     # Stop agent and cleanly shut down all subshells & processes
mra restart  # Cleanly restart agent
mra run      # Run in foreground (closes cleanly when terminal is closed)
mra status   # Check agent, battery %, and AC power status
mra logs     # Stream real-time agent logs (tail -f)
mra pin      # Display your 4-digit pairing PIN & Telegram command
mra service  # Manage 24/7 background macOS LaunchAgent
```

---

## 📱 Bot Commands & Phone Controls

Tap the blue **Menu** button in Telegram or tap the persistent keyboard buttons:

| Button / Command | Action | Example |
| :--- | :--- | :--- |
| `📸 Screenshot` or `/ss` | Captures your Mac's screen and sends the photo | `/ss` |
| `📂 Open Finder` or `/finder` | Opens Finder window and lists top files | `/finder ~/Downloads` |
| `💾 Google Drive` or `/drive` | Copies file to Google Drive sync folder | `/drive report.pdf` |
| `/get` or `/file` | Sends the file directly to your phone via Telegram | `/get ~/Desktop/notes.txt` |
| `🤖 Antigravity AI` or `/agy` | Runs Antigravity AI prompt on your Mac | `/agy organize my desktop files` |
| `🔋 Status` or `/status` | Shows battery %, AC power, disk space, and uptime | `/status` |
| `🔒 Lock Screen` or `/lock` | Locks your Mac screen and puts display to sleep | `/lock` |
| `/sh <command>` | Executes bash/zsh shell command | `/sh git status` |
| `/help` | Displays command list and usage guide | `/help` |

### 💬 Natural Language Support
You can also send natural language requests in plain text:
- *"take a screenshot"*
- *"open finder ~/Downloads"*
- *"share report.pdf on drive"*
- Unrecognized or complex requests are automatically routed to **Google Antigravity AI**!

---

## ⚡ 2-Minute Setup

### 1. Create a Bot on Telegram
1. On your phone, open Telegram and message `@BotFather`.
2. Send `/newbot`, name your bot (e.g. `MyMacBookBot`), and copy the **API Token**.

### 2. Run Setup on your Mac
```bash
git clone https://github.com/ard-tube/mac-remote-agent.git ~/mac-remote-agent
cd ~/mac-remote-agent
./setup.sh
```
Enter your Bot Token when prompted.

### 3. Pair your Phone
1. Open your bot in Telegram on your phone and tap **Start**.
2. Tap or send the pairing command:
   ```text
   /pair <PIN>
   ```
   *(Your PIN is shown in terminal or by running `mra pin`).*

---

## 🔌 Closed-Lid Clamshell Mode on Apple Silicon

To keep your MacBook awake while connected to the charger with the lid closed:
```bash
# Keep awake on AC power
./clamshell-config.sh enable

# Optional: keep awake with lid closed even without an external display
sudo pmset -a disablesleep 1
```
*(To restore standard sleep behavior: `sudo pmset -a disablesleep 0` or `./clamshell-config.sh disable`)*

---

## 🔄 Run Automatically 24/7 in Background

Install the persistent macOS LaunchAgent service:
```bash
mra service install
```
To stop or check status:
```bash
mra status
mra stop
```

---

## 📄 License

MIT License. Designed with ❤️ for Apple Silicon and Google Antigravity.
By Arda Borulu
