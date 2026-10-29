# 🚀 MacRemote — Phone Control for Mac and Windows

[![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon%20(M1%2FM2%2FM3%2FM4)-black?logo=apple&style=for-the-badge)](https://apple.com)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&style=for-the-badge)](https://python.org)
[![Telegram](https://img.shields.io/badge/Control-Telegram%20Bot%20API-0088cc?logo=telegram&style=for-the-badge)](https://telegram.org)
[![Antigravity](https://img.shields.io/badge/Agent-Google%20Antigravity%20AI-purple?style=for-the-badge)](https://antigravity.google)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

> MacRemote combines native Mac and Windows host-app previews with phone controls. The Android companion and relay are buildable previews; Windows runtime testing and signed public releases are still outstanding.

---

## ⚡ Key Highlights

- 🖥️ **Desktop host apps:** SwiftUI menu-bar app for macOS and a window/tray app for Windows.
- 📱 **Phone controls:** Existing Telegram bot flow plus a native Android companion connected through a self-hosted relay.
- 🤖 **Coding-agent requests:** Submit Antigravity or Claude Code tasks; each waits for approval at the host before execution.
- 🔐 **Restricted remote actions:** Built-in allowlist only; arbitrary remote shell execution is disabled.
- 🌐 **Outbound host connection:** Host polls the relay over HTTPS; no inbound router port is required.
- ⚠️ **Relay trust model:** TLS protects traffic in transit, but the relay is not end-to-end encrypted and can read prompts, screenshots, and results.

---

## 🖥️ Native macOS App Preview

The macOS menu-bar app provides Telegram and relay settings, task review, local approval, and an activity log. Build it on macOS 13 or later with Swift 5.9+ and Python 3 installed:

```bash
./macos/build-app.sh
open dist/MacRemote.app
```

In the app, enter your Telegram bot token, optional Antigravity and Claude Code executable paths, and the folder the agents should work in. Configure the relay URL, host ID, and host token only if using relay control. Configuration is stored under `~/Library/Application Support/MacRemote`. The app bundle is an unsigned development build.

## 🪟 Windows Host App Preview

The Windows app source includes a native window and system-tray controls. Build it on a Windows machine with Python 3.9 or later and PowerShell:

```powershell
.\windows\build-app.ps1
```

The script packages a Windows app folder and `dist\MacRemote-Windows.zip`. The Windows build and runtime still need verification on a Windows machine before distribution.

## 📲 Android companion and relay preview

The Android source is under `android/`. The desktop build workflow creates an installable debug APK as an artifact; it is not a signed production release. The app accepts an HTTPS relay URL plus a host ID and phone token, and stores the connection settings encrypted with Android Keystore.

Run the relay on infrastructure you control, configure an HTTPS reverse proxy, and provision a host using the instructions in [`relay/README.md`](relay/README.md). Enter the host token in the desktop app and the phone token in Android. **Do not expose the relay's HTTP listener directly to the internet.** The relay operator can read command prompts, screenshots, and results.

---

## 🧰 Optional CLI utilities

The desktop apps are the user-facing host interface. The repository also retains the original optional `mra` CLI helpers for development and existing installations.

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
| `🤖 Antigravity AI` or `/agy <prompt>` | Shows instructions or queues an Antigravity task for local host approval | `/agy summarize recent commits` |
| `🧠 Claude Code` or `/claude <prompt>` | Shows instructions or queues a Claude Code task for local host approval | `/claude review this project` |
| `🔋 Status` or `/status` | Shows battery %, AC power, disk space, and uptime | `/status` |
| `🔒 Lock Screen` or `/lock` | Locks your Mac screen and puts display to sleep | `/lock` |
| `/help` | Displays command list and usage guide | `/help` |

Remote shell commands are disabled. Unrecognized plain-text messages are not executed; use an explicit built-in command or submit a coding-agent prompt. Requests are stored locally and appear in the Mac menu-bar app for review before execution.

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

## 🌐 Website deployment

The `Deploy GitHub Pages` workflow publishes the static site in `docs/` to GitHub Pages when changes are pushed to `main`. Enable GitHub Pages with **GitHub Actions** as the repository's deployment source in repository settings.

Pushing a `v*` tag runs the cross-platform build workflow and publishes a GitHub prerelease with the Mac, Windows, and Android preview artifacts. These are not signed production releases; shipping signed installers requires platform signing credentials and a production Android signing key.

---

## 📄 License

MIT License. Designed with ❤️ for Apple Silicon and Google Antigravity.
By Arda Borulu
