#!/usr/bin/env bash
# ==============================================================================
# MacRemote Agent Setup Script
# Universal Apple Silicon Edition (M1, M2, M3, M4 - Air, Pro, Mini, Studio)
# Configures your Mac for remote control from your Android phone
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Apple Silicon")

echo "=============================================================="
echo "    🚀 MacRemote Agent Setup — Apple Silicon ($CHIP)"
echo "=============================================================="
echo "Universal remote control for all M-Series Macs (M1 / M2 / M3 / M4)"
echo ""
echo "This tool allows you to control your Mac from your Android phone:"
echo "  • Take Retina screenshots & receive them instantly on your phone"
echo "  • Open Finder, browse files, and copy them to Google Drive"
echo "  • Download Mac files directly to your phone via Telegram"
echo "  • Run Antigravity AI agents on your Mac from anywhere"
echo "  • Monitor battery %, AC power, disk space, and lock your screen"
echo ""
echo "--------------------------------------------------------------"
echo "STEP 1: Telegram Bot Token"
echo "--------------------------------------------------------------"
echo "If you haven't created a bot yet:"
echo "  1. Open Telegram on your Android phone."
echo "  2. Search for @BotFather and tap START."
echo "  3. Send: /newbot"
echo "  4. Give it a name (e.g. MyMacBook) and username (e.g. MyMac_Remote_bot)."
echo "  5. Copy the API Token (looks like: 123456789:ABCDefgh-xyz)."
echo ""

read -p "Enter your Telegram Bot Token: " USER_TOKEN

if [ -z "$USER_TOKEN" ]; then
    echo "⚠️ No token entered. You can manually edit config.json later."
else
    # Verify token
    echo "Checking bot token..."
    RESPONSE=$(curl -s "https://api.telegram.org/bot${USER_TOKEN}/getMe" || echo '{"ok":false}')
    IS_OK=$(echo "$RESPONSE" | grep -o '"ok":true' || true)

    if [ "$IS_OK" = '"ok":true' ]; then
        BOT_USER=$(echo "$RESPONSE" | grep -o '"username":"[^"]*' | cut -d'"' -f4)
        echo "✅ Bot verified successfully: @$BOT_USER"
        
        # Update config.json with token
        python3 -c "
import json
with open('config.json', 'r') as f:
    cfg = json.load(f)
cfg['bot_token'] = '$USER_TOKEN'
with open('config.json', 'w') as f:
    json.dump(cfg, f, indent=2)
"
    else
        echo "❌ Invalid bot token! Please recheck and try again."
        exit 1
    fi
fi

echo ""
echo "--------------------------------------------------------------"
echo "STEP 2: Clamshell & Sleep Prevention (Plugged into AC Power)"
echo "--------------------------------------------------------------"
echo "To prevent your Apple Silicon MacBook from sleeping when the lid is closed"
echo "while plugged into power, macOS can disable sleep on AC adapter."
echo ""
read -p "Do you want to configure Mac to stay awake when plugged in? (y/n): " CONFIGURE_SLEEP
if [[ "$CONFIGURE_SLEEP" =~ ^[Yy]$ ]]; then
    echo "Running pmset configuration (requires Mac admin password)..."
    sudo pmset -c sleep 0
    echo "✅ Sleep disabled while connected to charger."
fi

echo ""
echo "--------------------------------------------------------------"
echo "STEP 3: Background Service Setup (Optional)"
echo "--------------------------------------------------------------"
read -p "Do you want MacRemote to run automatically in background on boot? (y/n): " AUTOSTART
if [[ "$AUTOSTART" =~ ^[Yy]$ ]]; then
    ./install-service.sh
fi

# Setup global 'mra' CLI command
mkdir -p "$HOME/.local/bin"
chmod +x "$DIR/mra"
ln -sf "$DIR/mra" "$HOME/.local/bin/mra"

echo ""
echo "=============================================================="
echo "🎉 Setup Complete!"
echo "=============================================================="
echo "You can now control MacRemote from any terminal using:"
echo "   mra          - Open status dashboard"
echo "   mra start    - Start in background"
echo "   mra stop     - Stop agent & all shells"
echo "   mra run      - Run in current terminal (stops when closed)"
echo "   mra logs     - View real-time logs"
echo "   mra pin      - View pairing PIN"
echo ""
echo "To start the agent now, simply run:"
echo "   mra start"
echo ""

