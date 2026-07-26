#!/usr/bin/env python3
"""Copy the fixed desktop-pet release bundle and verify its SHA-256."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

EXPECTED_SHA256 = "BFD19AB0EA1056FD847790674E717A5D3FFC3ECE7DDE0FB357B1283B1D7575CF"
ASSET_NAME = "desktop-pet-installer-v1.0.0.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> None:
    parser = argparse.ArgumentParser(description="Deliver the fixed desktop-pet installer bundle.")
    parser.add_argument("--output", required=True, help="Destination folder. It is created if needed.")
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parents[1]
    source = skill_dir / "assets" / "release" / ASSET_NAME
    if not source.is_file():
        raise SystemExit(f"Missing bundled release: {source}")
    if sha256(source) != EXPECTED_SHA256:
        raise SystemExit("Bundled desktop-pet release failed integrity verification; do not distribute it.")

    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / ASSET_NAME
    shutil.copy2(source, destination)
    actual = sha256(destination)
    if actual != EXPECTED_SHA256:
        destination.unlink(missing_ok=True)
        raise SystemExit("Copied release failed integrity verification; destination copy was removed.")

    manifest = {
        "product": "Desktop Pet",
        "version": "1.0.0",
        "artifact": ASSET_NAME,
        "sha256": actual,
        "offline": True,
        "fixed_pet": True,
    }
    (output / "release-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "ok", "bundle": str(destination), "sha256": actual}, ensure_ascii=False))


if __name__ == "__main__":
    main()
