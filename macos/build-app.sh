#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="MacRemote"
APP_DIR="$ROOT_DIR/dist/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"

swift build --package-path "$ROOT_DIR/macos" --configuration release
BIN_DIR="$(swift build --package-path "$ROOT_DIR/macos" --configuration release --show-bin-path)"

mkdir -p "$CONTENTS_DIR/MacOS" "$CONTENTS_DIR/Resources"
cp "$BIN_DIR/$APP_NAME" "$CONTENTS_DIR/MacOS/$APP_NAME"
cp "$ROOT_DIR/agent.py" "$CONTENTS_DIR/Resources/agent.py"
cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>MacRemote</string>
    <key>CFBundleIdentifier</key>
    <string>com.ardtube.macremote</string>
    <key>CFBundleName</key>
    <string>MacRemote</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
</dict>
</plist>
PLIST
codesign --force --deep --sign - "$APP_DIR"
codesign --verify --deep --strict "$APP_DIR"
printf 'Built app bundle: %s\n' "$APP_DIR"
