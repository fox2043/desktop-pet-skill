from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pet_root = manifest_path.parent / "pet"
    states = list(manifest["actions"])
    cell_width, cell_height, header = 210, 240, 28
    columns = 5
    rows = (len(states) + columns - 1) // columns
    sheet = Image.new(
        "RGBA", (columns * cell_width, rows * (cell_height + header)), "#f5f1eb"
    )
    draw = ImageDraw.Draw(sheet)
    for index, state in enumerate(states):
        row, column = divmod(index, columns)
        left = column * cell_width
        top = row * (cell_height + header)
        draw.rectangle(
            (left + 4, top + 4, left + cell_width - 4, top + cell_height + header - 4),
            fill="#ffffff",
            outline="#ded6cc",
        )
        draw.text((left + 10, top + 8), state, fill="#302d29")
        frames = manifest["actions"][state]
        frame = pet_root / frames[len(frames) // 2]
        with Image.open(frame) as opened:
            pet = opened.convert("RGBA")
        pet.thumbnail((cell_width - 28, cell_height - 28), Image.Resampling.LANCZOS)
        x = left + (cell_width - pet.width) // 2
        y = top + header + cell_height - pet.height - 8
        sheet.alpha_composite(pet, (x, y))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(output, quality=94)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
