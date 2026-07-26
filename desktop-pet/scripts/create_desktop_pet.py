from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_TEMPLATE = SKILL_ROOT / "assets" / "project-template"
INVALID_NAME_CHARS = '<>:"/\\|?*'


def safe_pet_name(value: str) -> str:
    cleaned = "".join("_" if char in INVALID_NAME_CHARS else char for char in value)
    cleaned = cleaned.strip(" ._")
    if not cleaned:
        raise ValueError("宠物名字不能为空。")
    return cleaned[:24]


def require_runtime_dependencies() -> None:
    missing = [
        package
        for package in ("PySide6", "PIL", "cv2", "numpy", "onnxruntime")
        if importlib.util.find_spec(package) is None
    ]
    if missing:
        requirements = PROJECT_TEMPLATE / "requirements.txt"
        raise RuntimeError(
            "缺少本地生成依赖："
            + ", ".join(missing)
            + f"\n请先运行：{sys.executable} -m pip install -r \"{requirements}\""
        )


def relative_action_manifest(
    actions: dict[str, list[str]], pet_root: Path
) -> dict[str, list[str]]:
    return {
        state: [
            Path(value).resolve().relative_to(pet_root.resolve()).as_posix()
            for value in values
        ]
        for state, values in actions.items()
    }


def personalize_project(project: Path, pet_name: str) -> None:
    token = hashlib.sha256(pet_name.encode("utf-8")).hexdigest()[:12]
    source = project / "src" / "custom_pet.py"
    content = source.read_text(encoding="utf-8")
    content = content.replace(
        'STARTUP_VALUE = "MyCustomDesktopPet"',
        f'STARTUP_VALUE = "DesktopPet-{token}"',
    )
    content = content.replace(
        'return Path(base) / "MyCustomDesktopPet"',
        f'return Path(base) / "DesktopPet-{token}"',
    )
    content = content.replace(
        'QSettings("CustomPetStudio", "DesktopPet")',
        f'QSettings("CustomPetStudio", "DesktopPet-{token}")',
    )
    source.write_text(content, encoding="utf-8")

    installer = project / "installer" / "custom-desktop-pet.iss"
    iss = installer.read_text(encoding="utf-8-sig")
    app_id = uuid.uuid5(uuid.NAMESPACE_URL, f"desktop-pet:{pet_name}")
    lines = [
        "AppId={{" + str(app_id).upper() + "}"
        if line.startswith("AppId=")
        else line
        for line in iss.splitlines()
    ]
    iss = "\n".join(lines) + "\n"
    iss = iss.replace(
        r"DefaultDirName={localappdata}\Programs\我的桌面宠物",
        r"DefaultDirName={localappdata}\Programs\{#MyAppName}",
    )
    iss = iss.replace(
        "DefaultGroupName=我的桌面宠物",
        "DefaultGroupName={#MyAppName}",
    )
    installer.write_text(iss, encoding="utf-8")


def write_bootstrap_manifest(
    project: Path, name: str, species: str, photos: list[Path]
) -> dict:
    require_runtime_dependencies()
    sys.path.insert(0, str(project / "src"))
    try:
        from custom_pet import make_transparent_pet
        from local_action_generator import generate_action_pack
    finally:
        sys.path.pop(0)

    bootstrap = project / "assets" / "bootstrap"
    pet_root = bootstrap / "pet"
    references_dir = pet_root / "references"
    references_dir.mkdir(parents=True, exist_ok=True)

    references: list[Path] = []
    for index, photo in enumerate(photos, start=1):
        destination = references_dir / f"reference_{index}.png"
        print(f"[{index}/{len(photos)}] 提取身份参考：{photo.name}", flush=True)
        make_transparent_pet(photo, destination, species)
        references.append(destination)

    print("生成猫狗专属透明动作包（13 类、65 帧）…", flush=True)
    actions = generate_action_pack(references, pet_root / "actions", species)
    manifest = {
        "version": 2,
        "name": name,
        "species": species,
        "references": [
            path.resolve().relative_to(pet_root.resolve()).as_posix()
            for path in references
        ],
        "actions": relative_action_manifest(actions, pet_root),
        "generator": "offline-local-motion-rig",
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    bootstrap.mkdir(parents=True, exist_ok=True)
    (bootstrap / "pet.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def build_executable(project: Path, deliverables: Path, pet_name: str) -> Path:
    require_runtime_dependencies()
    if importlib.util.find_spec("PyInstaller") is None:
        requirements = project / "requirements.txt"
        raise RuntimeError(
            "缺少 PyInstaller。请先运行："
            f"{sys.executable} -m pip install -r \"{requirements}\""
        )
    build_name = "DesktopPet"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--log-level",
        "WARN",
        "--workpath",
        str(project / "build"),
        "--distpath",
        str(project / "dist"),
        "--onefile",
        "--windowed",
        "--name",
        build_name,
        "--icon",
        str(project / "assets" / "pet.ico"),
        "--add-data",
        f"{project / 'assets'}{os.pathsep}assets",
        "--collect-all",
        "cv2",
        str(project / "src" / "custom_pet.py"),
    ]
    print("正在打包 Windows EXE，这一步通常需要 1–3 分钟…", flush=True)
    subprocess.run(command, cwd=project, check=True)
    built = project / "dist" / f"{build_name}.exe"
    if not built.exists():
        raise RuntimeError("PyInstaller 没有生成预期的 EXE。")
    deliverables.mkdir(parents=True, exist_ok=True)
    final = deliverables / f"{pet_name}桌面宠物.exe"
    shutil.copy2(built, final)
    shutil.copy2(built, project / "dist" / "我的桌面宠物.exe")
    return final


def find_iscc(explicit: str | None) -> Path | None:
    candidates = [
        Path(explicit) if explicit else None,
        Path(os.environ["ISCC_EXE"]) if os.environ.get("ISCC_EXE") else None,
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 7\ISCC.exe"),
    ]
    return next((path for path in candidates if path and path.exists()), None)


def build_installer(
    project: Path,
    deliverables: Path,
    pet_name: str,
    iscc_value: str | None,
) -> Path:
    iscc = find_iscc(iscc_value)
    if not iscc:
        raise RuntimeError(
            "未找到 Inno Setup。安装 Inno Setup 6/7，或通过 --iscc 指定 ISCC.exe。"
        )
    script = project / "installer" / "custom-desktop-pet.iss"
    content = script.read_text(encoding="utf-8-sig")
    content = content.replace(
        '#define MyAppName "我的桌面宠物"',
        f'#define MyAppName "{pet_name}桌面宠物"',
    )
    content = content.replace(
        '#define MyAppPublisher "自定义桌面宠物"',
        '#define MyAppPublisher "电脑桌面宠物 Skill"',
    )
    content = content.replace(
        "OutputBaseFilename=自定义桌面宠物安装程序-v{#MyAppVersion}",
        f"OutputBaseFilename={pet_name}桌面宠物安装程序-v{{#MyAppVersion}}",
    )
    script.write_text(content, encoding="utf-8")
    (project / "README.md").write_text(
        f"# {pet_name}桌面宠物\n\n由“电脑桌面宠物”Skill 完全离线生成。\n",
        encoding="utf-8",
    )
    print("正在生成安装程序…", flush=True)
    subprocess.run([str(iscc), str(script)], cwd=project, check=True)
    installers = sorted((project / "release").glob("*.exe"))
    if not installers:
        raise RuntimeError("Inno Setup 没有生成安装程序。")
    final = deliverables / installers[-1].name
    shutil.copy2(installers[-1], final)
    return final


def write_portable_zip(
    executable: Path, deliverables: Path, pet_name: str
) -> Path:
    instructions = deliverables / "使用说明.txt"
    instructions.write_text(
        f"{pet_name}桌面宠物\n"
        "====================\n\n"
        "双击 EXE 即可运行。程序完全离线，不上传宠物照片，也不连接任何 API。\n"
        "右键桌面宠物可打招呼、跳跃、卖萌、喂食、陪工作或退出。\n"
        "第一次运行会把内置动作包复制到当前 Windows 用户的本地数据目录。\n",
        encoding="utf-8",
    )
    archive = deliverables / f"{pet_name}桌面宠物-便携版.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        package.write(executable, executable.name)
        package.write(instructions, instructions.name)
    return archive


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 1–4 张猫狗照片制作完全离线的 Windows 桌面宠物。"
    )
    parser.add_argument("--name", required=True, help="宠物名字")
    parser.add_argument("--species", required=True, choices=("cat", "dog"))
    parser.add_argument(
        "--photo",
        action="append",
        required=True,
        help="宠物照片路径；可重复 1–4 次",
    )
    parser.add_argument("--output", required=True, help="新建输出目录")
    parser.add_argument(
        "--assets-only",
        action="store_true",
        help="只生成透明动作包和工程，不构建 EXE",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="额外使用 Inno Setup 构建安装程序",
    )
    parser.add_argument("--iscc", help="ISCC.exe 的路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if sys.platform != "win32":
        raise SystemExit("当前版本只支持在 Windows 上构建桌面宠物。")
    name = safe_pet_name(args.name)
    photos = [Path(value).expanduser().resolve() for value in args.photo]
    if not 1 <= len(photos) <= 4:
        raise SystemExit("请提供 1–4 张照片。")
    missing = [str(path) for path in photos if not path.is_file()]
    if missing:
        raise SystemExit("照片不存在：\n" + "\n".join(missing))
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise SystemExit(f"输出目录已存在，请换一个新目录：{output}")
    project = output / "project"
    deliverables = output / "deliverables"
    output.mkdir(parents=True)
    shutil.copytree(PROJECT_TEMPLATE, project)
    personalize_project(project, name)

    manifest = write_bootstrap_manifest(
        project, name, args.species, photos
    )
    result = {
        "name": name,
        "species": args.species,
        "frames": sum(len(values) for values in manifest["actions"].values()),
        "project": str(project),
        "deliverables": [],
    }
    if not args.assets_only:
        executable = build_executable(project, deliverables, name)
        result["deliverables"].append(str(executable))
        result["deliverables"].append(
            str(write_portable_zip(executable, deliverables, name))
        )
        if args.installer:
            result["deliverables"].append(
                str(
                    build_installer(
                        project, deliverables, name, args.iscc
                    )
                )
            )
    summary = output / "result.json"
    summary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"完成：{summary}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
