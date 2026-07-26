#!/usr/bin/env python3
"""Validate desktop-pet frame names, transparency, and visible motion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


STATES = (
    "idle", "sleeping", "waiting", "waving", "jumping", "failed", "working",
    "review", "walking-right", "walking-left", "feeding", "playing", "happy",
)


def read_frame(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        if image.mode != "RGBA":
            raise ValueError(f"{path} is not RGBA")
        return np.asarray(image, dtype=np.uint8)


def border_is_clear(alpha: np.ndarray) -> bool:
    border = np.concatenate((alpha[:2].ravel(), alpha[-2:].ravel(), alpha[:, :2].ravel(), alpha[:, -2:].ravel()))
    return bool(np.max(border, initial=0) <= 8)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actions", required=True, help="Root folder containing one folder per action")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    root = Path(args.actions).resolve()
    errors: list[str] = []
    details: dict[str, dict[str, object]] = {}
    for state in STATES:
        paths = sorted((root / state).glob("*.png"))
        if len(paths) != 5:
            errors.append(f"{state}: expected 5 PNG frames, found {len(paths)}")
            continue
        frames = [read_frame(path) for path in paths]
        shapes = {frame.shape for frame in frames}
        if len(shapes) != 1:
            errors.append(f"{state}: frame dimensions differ")
            continue
        hashes = {frame.tobytes() for frame in frames}
        if len(hashes) != 5:
            errors.append(f"{state}: contains duplicate static frames")
        alpha = [frame[:, :, 3] for frame in frames]
        if any(not border_is_clear(value) for value in alpha):
            errors.append(f"{state}: nontransparent background touches canvas border")
        if any(np.count_nonzero(value > 12) == 0 for value in alpha):
            errors.append(f"{state}: blank frame")
        changes = [
            float(np.mean(np.abs(frames[index].astype(np.int16) - frames[index - 1].astype(np.int16))))
            for index in range(1, len(frames))
        ]
        if max(changes, default=0.0) < 0.45:
            errors.append(f"{state}: frame changes are too small to read as motion")
        details[state] = {"frames": len(paths), "max_frame_delta": round(max(changes, default=0.0), 3)}
    report = {"ok": not errors, "states": len(STATES), "frames_expected": 65, "details": details, "errors": errors}
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
