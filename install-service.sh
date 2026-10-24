#!/usr/bin/env bash
# Install MacRemote Agent as a persistent 24/7 macOS LaunchAgent
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PLIST_NAME="com.antigravity.macremote.plist"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_FILE="$TARGET_DIR/$PLIST_NAME"
PYTHON_BIN="$(which python3)"

mkdir -p "$TARGET_DIR"

echo "Creating LaunchAgent: $TARGET_FILE"

cat << EOF > "$TARGET_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.antigravity.macremote</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>$DIR/agent.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$DIR/agent.log</string>
    <key>StandardErrorPath</key>
    <string>$DIR/agent.log</string>
</dict>
</plist>
EOF

# Unload previous instance if any
launchctl unload "$TARGET_FILE" 2>/dev/null || true

# Load service
launchctl load "$TARGET_FILE"

echo "✅ LaunchAgent installed and loaded successfully!"
echo "MacRemote Agent will now start automatically whenever your Mac starts up."
echo "To check logs: tail -f $DIR/agent.log"
