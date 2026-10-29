# 🚀 MacRemote — Terminal-first host control for macOS

[![macOS](https://img.shields.io/badge/macOS-CLI%20%2B%20local%20dashboard-black?logo=apple&style=for-the-badge)](https://apple.com)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&style=for-the-badge)](https://python.org)
[![Telegram](https://img.shields.io/badge/Control-Telegram%20Bot%20API-0088cc?logo=telegram&style=for-the-badge)](https://telegram.org)
[![Antigravity](https://img.shields.io/badge/Agent-Google%20Antigravity%20AI-purple?style=for-the-badge)](https://antigravity.google)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

> MacRemote gives you a macOS terminal controller, a private local dashboard, and an Android companion for a self-hosted relay. Optional native Mac and Windows app previews are still available.

---

## ⚡ Key Highlights

- 🖥️ **Desktop host apps:** SwiftUI menu-bar app for macOS and a window/tray app for Windows.
- ⌨️ **Terminal-first Mac host:** Start, stop, inspect, and follow the host from `macremote`; no downloaded `.app` bundle required.
- 🌌 **Private local dashboard:** Pair a phone, manage host settings, review approvals, and watch logs on loopback.
- 📱 **Phone controls:** Existing Telegram bot flow plus a native Android companion connected through a self-hosted relay.
- 🤖 **Coding-agent requests:** Submit Antigravity or Claude Code tasks; each waits for approval at the host before execution.
- 🔐 **Restricted remote actions:** Built-in allowlist only; arbitrary remote shell execution is disabled.
- 🌐 **Outbound host connection:** Host polls the relay over HTTPS; no inbound router port is required.
- ⚠️ **Relay trust model:** TLS protects traffic in transit, but the relay is not end-to-end encrypted and can read prompts, screenshots, and results.

---

## ⌨️ Recommended: terminal app and local dashboard

Install the Mac CLI with Homebrew:

```bash
brew tap ard-tube/mac-remote-agent https://github.com/ard-tube/mac-remote-agent
brew install macremote
```

Or use the one-line installer:

```bash
curl -fsSL https://raw.githubusercontent.com/ard-tube/mac-remote-agent/main/install.sh | sh
```

Then start MacRemote and open its local dashboard:

```bash
macremote start
```

The dashboard is bound to `127.0.0.1`, requires a private local token, and uses no third-party QR service. Add your self-hosted HTTPS relay details in **Settings**, then scan the locally generated pairing code with the Android app. Incoming coding-agent prompts remain pending until you explicitly approve them on the Mac; remote shell execution is disabled.

```bash
macremote status     # Host, daemon, relay, and dashboard status
macremote ui         # Open the dashboard
macremote pairing    # Print the Android pairing QR in the terminal
macremote logs -f    # Follow daemon and host logs
macremote stop       # Stop the dashboard and host agent
```

The CLI avoids launching the Gatekeeper-blocked preview bundle. It does **not** make the optional native app Developer ID signed or notarized. `qrencode` is needed for QR display in the terminal; Homebrew installs it with the formula. Install it separately (`brew install qrencode`) for the standalone installer.

## 🖥️ Optional native macOS app preview

The macOS menu-bar app provides Telegram and relay settings, task review, local approval, and an activity log. Build it on macOS 13 or later with Swift 5.9+ and Python 3 installed:

```bash
./macos/build-app.sh
open dist/MacRemote.app
```

In the app, enter your Telegram bot token, optional Antigravity and Claude Code executable paths, and the folder the agents should work in. Configure the relay URL, host ID, and host token only if using relay control. Configuration is stored under `~/Library/Application Support/MacRemote`. The app is ad-hoc signed to keep its bundle valid, but it is not Developer ID signed or notarized. macOS Gatekeeper may block downloaded preview builds; a trusted public build requires an Apple Developer ID certificate and notarization.

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

## 🧰 Legacy `mra` CLI utilities

The older `mra` helpers remain available for existing installations and repository development. New installs should use `macremote`.

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

### 1. Install the Mac host

Use the Homebrew or one-line installer above. `macremote start` opens the local dashboard. If you also use Telegram, continue with the optional bot setup below.

### 2. Create a Bot on Telegram (optional)
1. On your phone, open Telegram and message `@BotFather`.
2. Send `/newbot`, name your bot (e.g. `MyMacBookBot`), and copy the **API Token**.

### 3. Configure and pair your phone

Run your self-hosted relay behind HTTPS and provision the host ID, host token, and phone token using [`relay/README.md`](relay/README.md). Enter them in **Settings** in the local dashboard, save, then open **Pair phone** and scan the QR code. The Android app imports the relay URL, host ID, and phone token; review them and tap **Save connection** to store them encrypted with Android Keystore.

For legacy repository-based setup only:

```bash
git clone https://github.com/ard-tube/mac-remote-agent.git ~/mac-remote-agent
cd ~/mac-remote-agent
./install.sh --legacy
```

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

Run the host and dashboard in the background:
```bash
macremote daemon
```
To stop or inspect:
```bash
macremote status
macremote stop
```

## 🌐 Website deployment

The `Deploy GitHub Pages` workflow publishes the static site in `docs/` to GitHub Pages when changes are pushed to `main`. Enable GitHub Pages with **GitHub Actions** as the repository's deployment source in repository settings.

Pushing a `v*` tag runs the cross-platform build workflow and publishes the CLI archive, Mac and Windows app previews, and Android debug APK. The optional native apps remain unsigned or ad-hoc signed previews, and the APK is not a signed production build. A CLI install does not require the native Mac bundle.

---

## 📄 License

MIT License. Designed with ❤️ for Apple Silicon and Google Antigravity.
By Arda Borulu
