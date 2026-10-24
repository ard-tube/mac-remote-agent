#!/usr/bin/env bash
# ==============================================================================
# MacRemote Agent 1-Line Installer for macOS Apple Silicon
# ==============================================================================

set -e

INSTALL_DIR="$HOME/mac-remote-agent"
REPO_URL="https://github.com/ard-tube/mac-remote-agent.git"

echo "=============================================================="
echo "    🚀 Installing MacRemote Agent for Apple Silicon Macs"
echo "=============================================================="

# Check macOS & Apple Silicon
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ Error: MacRemote Agent requires macOS."
    exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
    echo "⚠️ Warning: Detected non-arm64 architecture ($ARCH). Designed for Apple Silicon (M1/M2/M3/M4)."
fi

# Clone or pull repo
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation in $INSTALL_DIR..."
    cd "$INSTALL_DIR"
    git pull origin main || true
else
    echo "Cloning repository to $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

chmod +x *.sh
./setup.sh
