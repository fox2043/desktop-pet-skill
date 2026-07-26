#!/usr/bin/env python3
"""Create a photo-count-independent desktop-pet action manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


STATES = (
    "idle", "sleeping", "waiting", "greeting", "jumping", "cute", "working",
    "review", "walking-right", "walking-left", "feeding", "playing", "happy",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--species", required=True, choices=("cat", "dog"))
    parser.add_argument("--photo", required=True, action="append")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    photos = [Path(value).expanduser().resolve() for value in args.photo]
    if not 1 <= len(photos) <= 4:
        raise SystemExit("Provide 1 to 4 reference photos.")
    missing = [str(photo) for photo in photos if not photo.is_file()]
    if missing:
        raise SystemExit("Missing reference photos: " + ", ".join(missing))

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    actions = {
        state: {
            "frames": [f"actions/{state}/{index:02d}.png" for index in range(5)],
            "source_identity": "all_reference_photos",
            "must_differ_from": ["idle"] if state != "idle" else [],
        }
        for state in STATES
    }
    manifest = {
        "version": 1,
        "species": args.species,
        "references": [str(photo) for photo in photos],
        "reference_count": len(photos),
        "action_count": len(STATES),
        "frame_count": len(STATES) * 5,
        "photo_count_controls_actions": False,
        "actions": actions,
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "actions": 13, "frames": 65, "manifest": str(output)}))


if __name__ == "__main__":
    main()
