# 🚀 MacRemote — Universal Remote Control for Apple Silicon Macs

[![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon%20(M1%2FM2%2FM3%2FM4)-black?logo=apple&style=for-the-badge)](https://apple.com)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&style=for-the-badge)](https://python.org)
[![Telegram](https://img.shields.io/badge/Control-Telegram%20Bot%20API-0088cc?logo=telegram&style=for-the-badge)](https://telegram.org)
[![Antigravity](https://img.shields.io/badge/Agent-Google%20Antigravity%20AI-purple?style=for-the-badge)](https://antigravity.google)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

> Control any **Apple Silicon Mac (M1, M2, M3, M4 / Air, Pro, Mini, Studio)** from your **Android phone** anytime, anywhere.
> Featuring instant Retina screenshots, Finder automation, Google Drive syncing, and full **Google Antigravity AI** integration.

---

## ⚡ Key Highlights

- 🍏 **Universal M-Series Support:** Engineered for all Apple Silicon Macs:
  - **M1 Series:** M1, M1 Pro, M1 Max, M1 Ultra (MacBook Air, MacBook Pro, Mac mini, iMac, Mac Studio)
  - **M2 Series:** M2, M2 Pro, M2 Max, M2 Ultra (MacBook Air 13"/15", MacBook Pro 14"/16", Mac mini, Mac Studio, Mac Pro)
  - **M3 Series:** M3, M3 Pro, M3 Max (MacBook Air 13"/15", MacBook Pro 14"/16", iMac)
  - **M4 Series:** M4, M4 Pro, M4 Max (MacBook Pro, Mac mini, iMac)
- 📸 **Retina Screenshot Streaming:** Wakes screen buffer and captures high-res display shots in ~2 seconds.
- 📂 **Remote Finder Navigation:** Open any directory, view files, or reveal specific files in Finder.
- 💾 **Google Drive Auto-Sync:** 1-command copying to Google Drive (`Remote_Shared`) with instant mobile sync.
- 📥 **Direct Telegram File Transfer:** Request any file from your Mac and have it delivered directly into your Telegram chat.
- 🤖 **Antigravity AI Agent Bridge:** Delegate coding, debugging, or complex automation tasks to Antigravity CLI directly from your phone.
- 🔌 **Smart Clamshell Keep-Awake:** Prevents sleep while plugged into AC power even with lid closed.
- 🔒 **End-to-End Pairing Security:** PIN-protected pairing ensures only your authorized phone can command your Mac.
- 🌐 **Zero Port Forwarding:** Uses outbound HTTPS long-polling. Works on cellular data, cafe Wi-Fi, or home networks.

---

## 📱 Quick Command Reference

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

### 💬 Natural Language Support
You can also send natural language requests in English or Turkish:
- *"take a screenshot"* or *"ss al"*
- *"open finder ~/Downloads"* or *"finder aç"*
- *"share report.pdf on drive"* or *"drive'a yükle"*
- Unrecognized or complex requests are automatically routed to **Google Antigravity AI**!

---

## ⚡ 2-Minute Setup

### 1. Create a Bot on Telegram
1. On your Android phone, open Telegram and message `@BotFather`.
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
2. Send the pairing command:
   ```text
   /pair <PIN>
   ```
   *(Your PIN is shown in terminal or inside `config.json`).*

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
./install-service.sh
```
To stop or check status:
```bash
./status.sh
./stop.sh
```

---

## 📄 License

MIT License. Designed with ❤️ for Apple Silicon and Google Antigravity.
