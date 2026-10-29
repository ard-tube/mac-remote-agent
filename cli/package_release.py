#!/usr/bin/env python3
"""Create a reproducible Homebrew/standalone CLI archive."""

import io
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "MacRemote-CLI.tar"
FILES = (
    (ROOT / "agent.py", "agent.py"),
    (ROOT / "cli" / "macremote.py", "macremote.py"),
    (ROOT / "cli" / "dashboard" / "app.css", "dashboard/app.css"),
    (ROOT / "cli" / "dashboard" / "app.js", "dashboard/app.js"),
    (ROOT / "cli" / "dashboard" / "index.html", "dashboard/index.html"),
)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("wb") as raw_archive:
        with tarfile.open(fileobj=raw_archive, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for source, target in sorted(FILES, key=lambda item: item[1]):
                metadata = archive.gettarinfo(str(source), arcname=target)
                metadata.uid = metadata.gid = 0
                metadata.uname = metadata.gname = ""
                metadata.mtime = 0
                metadata.mode = 0o755 if target == "macremote.py" else 0o644
                content = source.read_bytes().replace(b"\r\n", b"\n")
                metadata.size = len(content)
                archive.addfile(metadata, io.BytesIO(content))


if __name__ == "__main__":
    main()
