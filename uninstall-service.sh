#!/usr/bin/env bash
# Uninstall MacRemote LaunchAgent service
PLIST_NAME="com.antigravity.macremote.plist"
TARGET_FILE="$HOME/Library/LaunchAgents/$PLIST_NAME"

if [ -f "$TARGET_FILE" ]; then
    echo "Unloading and removing $TARGET_FILE..."
    launchctl unload "$TARGET_FILE" 2>/dev/null || true
    rm -f "$TARGET_FILE"
    echo "✅ LaunchAgent uninstalled."
else
    echo "Service was not installed."
fi
