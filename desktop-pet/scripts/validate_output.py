from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


EXPECTED_STATES = {
    "idle",
    "sleeping",
    "waiting",
    "waving",
    "jumping",
    "failed",
    "working",
    "review",
    "walking-right",
    "walking-left",
    "feeding",
    "playing",
    "happy",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    result_path = Path(args.result).resolve()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    project = Path(result["project"])
    manifest_path = project / "assets" / "bootstrap" / "pet.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actions = manifest.get("actions", {})
    if set(actions) != EXPECTED_STATES:
        raise SystemExit(
            f"动作状态不完整：实际 {sorted(actions)}，预期 {sorted(EXPECTED_STATES)}"
        )

    pet_root = manifest_path.parent / "pet"
    frame_count = 0
    for state, values in actions.items():
        if len(values) != 5:
            raise SystemExit(f"{state} 应有 5 帧，实际 {len(values)} 帧。")
        for value in values:
            path = pet_root / value
            if not path.exists():
                raise SystemExit(f"缺少动作帧：{path}")
            with Image.open(path) as image:
                if image.mode != "RGBA":
                    raise SystemExit(f"动作帧不是 RGBA：{path}")
                minimum, maximum = image.getchannel("A").getextrema()
                if minimum > 5 or maximum < 245:
                    raise SystemExit(f"透明通道异常：{path}")
            frame_count += 1

    runtime = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (
            project / "src" / "custom_pet.py",
            project / "src" / "local_action_generator.py",
        )
    )
    forbidden = (
        "import requests",
        "from requests",
        "import openai",
        "from openai",
        "http://",
        "https://",
    )
    found = [value for value in forbidden if value in runtime]
    if found:
        raise SystemExit("运行时代码包含网络/API 痕迹：" + ", ".join(found))

    deliverables = [Path(value) for value in result.get("deliverables", [])]
    missing = [str(path) for path in deliverables if not path.exists()]
    if missing:
        raise SystemExit("交付文件不存在：\n" + "\n".join(missing))

    report = {
        "status": "ok",
        "name": result["name"],
        "species": result["species"],
        "states": len(actions),
        "frames": frame_count,
        "deliverables": [
            {
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in deliverables
        ],
    }
    report_path = result_path.with_name("validation.json")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
