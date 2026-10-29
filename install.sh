#!/bin/sh
set -eu

if [ "${1:-}" = "--legacy" ]; then
  SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
  if [ ! -f "$SCRIPT_DIR/setup.sh" ]; then
    echo "Run the legacy installer from a repository checkout." >&2
    exit 1
  fi
  exec "$SCRIPT_DIR/setup.sh"
fi

START_AFTER_INSTALL=0
case "${1:-}" in
  "") ;;
  --start) START_AFTER_INSTALL=1 ;;
  *)
    echo "Usage: install.sh [--start]" >&2
    exit 2
    ;;
esac

VERSION="v0.2.0-preview.2"
REPOSITORY="ard-tube/mac-remote-agent"
INSTALL_DIR="${MACREMOTE_INSTALL_DIR:-$HOME/.local/lib/macremote}"
BIN_DIR="${MACREMOTE_BIN_DIR:-$HOME/.local/bin}"
ARCHIVE_URL="https://github.com/$REPOSITORY/releases/download/$VERSION/MacRemote-CLI.tar"
ARCHIVE_SHA256="3718d582e761983feed07b8c4c933c99878eac6a29f40dc38653908525fdcf65"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "The MacRemote host daemon currently supports macOS only." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "MacRemote requires Python 3.9 or newer. Install Python 3 and rerun this installer." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/macremote-install.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
trap 'exit 1' HUP INT TERM

echo "Downloading MacRemote CLI $VERSION..."
curl --fail --location --silent --show-error "$ARCHIVE_URL" -o "$TMP_DIR/MacRemote-CLI.tar"
printf '%s  %s\n' "$ARCHIVE_SHA256" "$TMP_DIR/MacRemote-CLI.tar" | shasum -a 256 -c >/dev/null || {
  echo "The downloaded MacRemote archive failed its SHA-256 integrity check." >&2
  exit 1
}
mkdir -p "$INSTALL_DIR" "$BIN_DIR"
tar -xf "$TMP_DIR/MacRemote-CLI.tar" -C "$INSTALL_DIR"
cat > "$BIN_DIR/macremote" <<EOF
#!/bin/sh
exec python3 "$INSTALL_DIR/macremote.py" "\$@"
EOF
chmod 755 "$BIN_DIR/macremote"

if ! command -v qrencode >/dev/null 2>&1; then
  echo "Note: install qrencode (for example: brew install qrencode) to show pairing QR codes."
fi
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Add $BIN_DIR to PATH to use the macremote command." ;;
esac
echo "Installed MacRemote CLI. Start it with: $BIN_DIR/macremote start"
if [ "$START_AFTER_INSTALL" -eq 1 ]; then
  "$BIN_DIR/macremote" start
fi
