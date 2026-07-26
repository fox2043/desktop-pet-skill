from __future__ import annotations

import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image


CANVAS_SIZE = 768
FRAME_COUNT = 5
ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class PoseSpec:
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0
    bend: float = 0.0
    head_dx: float = 0.0
    head_dy: float = 0.0
    paw_dx: float = 0.0
    paw_dy: float = 0.0
    body_dx: float = 0.0
    body_dy: float = 0.0
    lift: float = 0.0


CAT_POSES = {
    "idle": PoseSpec(body_dy=1.0),
    "sleeping": PoseSpec(scale_x=1.008, scale_y=0.995, body_dy=1.0),
    "waiting": PoseSpec(rotation=0.8, body_dx=1.0),
    "waving": PoseSpec(rotation=-1.2, body_dx=-2.0, lift=4.0),
    "jumping": PoseSpec(scale_x=0.985, scale_y=1.015, lift=78.0),
    "failed": PoseSpec(rotation=1.2, body_dy=3.0),
    "working": PoseSpec(body_dx=2.0, body_dy=1.0),
    "review": PoseSpec(rotation=1.8, body_dx=2.0),
    "walking-right": PoseSpec(body_dx=6.0, lift=7.0),
    "walking-left": PoseSpec(body_dx=6.0, lift=7.0),
    "feeding": PoseSpec(rotation=0.6, body_dy=5.0),
    "playing": PoseSpec(rotation=-1.4, body_dx=4.0, lift=18.0),
    "happy": PoseSpec(rotation=1.0, lift=12.0),
}


DOG_POSES = {
    "idle": PoseSpec(body_dy=1.0),
    "sleeping": PoseSpec(scale_x=1.008, scale_y=0.995, body_dy=1.0),
    "waiting": PoseSpec(rotation=1.6, body_dx=2.0),
    "waving": PoseSpec(rotation=-2.0, body_dx=-3.0, lift=7.0),
    "jumping": PoseSpec(scale_x=0.98, scale_y=1.02, lift=92.0),
    "failed": PoseSpec(rotation=1.5, body_dy=4.0),
    "working": PoseSpec(body_dx=2.0, body_dy=2.0),
    "review": PoseSpec(rotation=2.6, body_dx=3.0),
    "walking-right": PoseSpec(body_dx=8.0, lift=10.0),
    "walking-left": PoseSpec(body_dx=8.0, lift=10.0),
    "feeding": PoseSpec(rotation=0.8, body_dy=6.0),
    "playing": PoseSpec(rotation=-2.2, body_dx=6.0, lift=24.0),
    "happy": PoseSpec(rotation=1.6, lift=18.0),
}


SOURCE_KIND = {
    "idle": "balanced",
    "sleeping": "wide",
    "waiting": "tall",
    "waving": "tall",
    "jumping": "tall",
    "failed": "wide",
    "working": "wide",
    "review": "balanced",
    "walking-right": "wide",
    "walking-left": "wide",
    "feeding": "wide",
    "playing": "balanced",
    "happy": "tall",
}

TEMPLATE_POSE_INDEX = {
    "idle": 0,
    "sleeping": 1,
    "waiting": 2,
    "waving": 3,
    "jumping": 4,
    "failed": 1,
    "working": 5,
    "review": 2,
    "walking-right": 6,
    "walking-left": 6,
    "feeding": 7,
}

HEAD_LAYOUT = {
    "idle": (0.50, 0.25, 0.25, 0.25),
    "sleeping": (0.21, 0.57, 0.23, 0.26),
    "waiting": (0.51, 0.25, 0.25, 0.25),
    "waving": (0.48, 0.23, 0.24, 0.24),
    "jumping": (0.24, 0.37, 0.23, 0.25),
    "failed": (0.21, 0.57, 0.23, 0.26),
    "working": (0.49, 0.37, 0.23, 0.24),
    "review": (0.51, 0.25, 0.25, 0.25),
    "walking-right": (0.77, 0.35, 0.20, 0.23),
    "walking-left": (0.77, 0.35, 0.20, 0.23),
    "feeding": (0.77, 0.69, 0.21, 0.22),
}


def _alpha_bounds(rgba: np.ndarray) -> tuple[int, int, int, int]:
    alpha = rgba[:, :, 3]
    visible = np.argwhere(alpha > 16)
    if visible.size == 0:
        raise ValueError("透明素材中没有检测到宠物主体。")
    top, left = visible.min(axis=0)
    bottom, right = visible.max(axis=0)
    return int(left), int(top), int(right) + 1, int(bottom) + 1


def _load_rgba(path: Path) -> np.ndarray:
    with Image.open(path) as opened:
        rgba = np.array(opened.convert("RGBA"))
    left, top, right, bottom = _alpha_bounds(rgba)
    return rgba[top:bottom, left:right]


def _normalize_to_canvas(rgba: np.ndarray) -> np.ndarray:
    height, width = rgba.shape[:2]
    ratio = min(642.0 / max(1, width), 612.0 / max(1, height))
    resized = cv2.resize(
        rgba,
        (max(1, int(round(width * ratio))), max(1, int(round(height * ratio)))),
        interpolation=cv2.INTER_AREA if ratio < 1 else cv2.INTER_LANCZOS4,
    )
    canvas = np.zeros((CANVAS_SIZE, CANVAS_SIZE, 4), dtype=np.uint8)
    target_x = (CANVAS_SIZE - resized.shape[1]) // 2
    target_y = 716 - resized.shape[0]
    target_y = max(24, target_y)
    canvas[
        target_y : target_y + resized.shape[0],
        target_x : target_x + resized.shape[1],
    ] = resized
    return canvas


def _template_path(species: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets" / "templates" / f"{species}-pose-sheet.png"


def _template_pose(sheet: np.ndarray, state: str) -> np.ndarray:
    index = TEMPLATE_POSE_INDEX[state]
    cell_width = sheet.shape[1] // 4
    cell_height = sheet.shape[0] // 2
    column = index % 4
    row = index // 4
    cell = sheet[
        row * cell_height : (row + 1) * cell_height,
        column * cell_width : (column + 1) * cell_width,
    ]
    left, top, right, bottom = _alpha_bounds(cell)
    padding = 10
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(cell.shape[1], right + padding)
    bottom = min(cell.shape[0], bottom + padding)
    return cell[top:bottom, left:right].copy()


def _appearance_texture(
    images: list[np.ndarray], size: int = 320, blur_sigma: float = 9.0
) -> np.ndarray:
    accumulated = np.zeros((size, size, 3), dtype=np.float32)
    weights = np.zeros((size, size), dtype=np.float32)
    coat_samples: list[np.ndarray] = []
    for rgba in images:
        resized = cv2.resize(rgba, (size, size), interpolation=cv2.INTER_AREA)
        rgb = resized[:, :, :3].astype(np.float32)
        alpha = resized[:, :, 3].astype(np.float32) / 255.0
        green_excess = np.maximum(
            0.0, rgb[:, :, 1] - (rgb[:, :, 0] + rgb[:, :, 2]) * 0.5
        )
        color_confidence = np.exp(-green_excess / 18.0)
        weight = alpha**3.0 * color_confidence
        accumulated += resized[:, :, :3].astype(np.float32) * weight[:, :, None]
        weights += weight
        sample_mask = (alpha > 0.78) & (green_excess < 18.0)
        if np.any(sample_mask):
            coat_samples.append(rgb[sample_mask])
    if coat_samples:
        samples = np.concatenate(coat_samples, axis=0)
        if len(samples) > 100_000:
            samples = samples[:: max(1, len(samples) // 100_000)]
        coat_color = np.median(samples, axis=0)
    else:
        coat_color = np.array((150.0, 150.0, 150.0), dtype=np.float32)
    valid = weights > 0.12
    atlas = accumulated / np.maximum(weights[:, :, None], 0.001)
    atlas[~valid] = coat_color
    atlas = np.clip(atlas, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(
        atlas, (0, 0), sigmaX=blur_sigma, sigmaY=blur_sigma
    )


def _identity_textures(cutouts: list[Path]) -> tuple[np.ndarray, np.ndarray]:
    images = [_load_rgba(path) for path in cutouts]
    body_texture = _appearance_texture(images)
    head_source = min(
        images,
        key=lambda rgba: rgba.shape[1] / max(1.0, float(rgba.shape[0])),
    )
    height, width = head_source.shape[:2]
    head_crop = head_source[
        : max(1, int(height * 0.50)),
        int(width * 0.08) : max(int(width * 0.08) + 1, int(width * 0.92)),
    ]
    try:
        left, top, right, bottom = _alpha_bounds(head_crop)
        head_crop = head_crop[top:bottom, left:right]
    except ValueError:
        head_crop = head_source
    head_texture = _appearance_texture([head_crop], blur_sigma=2.5)
    return body_texture, head_texture


def _recolor_template(
    template: np.ndarray,
    body_texture: np.ndarray,
    head_texture: np.ndarray,
    state: str,
) -> np.ndarray:
    height, width = template.shape[:2]
    identity = cv2.resize(
        body_texture, (width, height), interpolation=cv2.INTER_CUBIC
    )
    template_rgb = template[:, :, :3].astype(np.float32)
    identity_rgb = identity.astype(np.float32)
    luminance = (
        template_rgb[:, :, 0] * 0.2126
        + template_rgb[:, :, 1] * 0.7152
        + template_rgb[:, :, 2] * 0.0722
    )
    soft_luminance = cv2.GaussianBlur(luminance, (0, 0), sigmaX=8.0)
    detail = np.clip(
        (luminance + 10.0) / np.maximum(12.0, soft_luminance + 10.0),
        0.58,
        1.45,
    )

    # Preserve the template's tiny dark facial landmarks while replacing the coat.
    template_saturation = template_rgb.max(axis=2) - template_rgb.min(axis=2)
    facial_detail = np.clip(
        (72.0 - luminance) / 45.0 + template_saturation / 120.0, 0.0, 0.72
    )
    recolored = identity_rgb * detail[:, :, None]
    center_x, center_y, radius_x, radius_y = HEAD_LAYOUT[state]
    yy, xx = np.indices((height, width), dtype=np.float32)
    local_x = (xx / max(1.0, float(width)) - (center_x - radius_x)) / (
        radius_x * 2.0
    )
    local_y = (yy / max(1.0, float(height)) - (center_y - radius_y)) / (
        radius_y * 2.0
    )
    head_map_x = np.clip(
        local_x * (head_texture.shape[1] - 1), 0, head_texture.shape[1] - 1
    )
    head_map_y = np.clip(
        local_y * (head_texture.shape[0] - 1), 0, head_texture.shape[0] - 1
    )
    mapped_head = cv2.remap(
        head_texture,
        head_map_x.astype(np.float32),
        head_map_y.astype(np.float32),
        interpolation=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    ).astype(np.float32)
    ellipse = np.clip(
        1.0
        - ((local_x - 0.5) / 0.5) ** 2
        - ((local_y - 0.5) / 0.5) ** 2,
        0.0,
        1.0,
    )
    head_weight = (ellipse**0.55) * 0.82
    head_recolored = mapped_head * detail[:, :, None]
    recolored = (
        recolored * (1.0 - head_weight[:, :, None])
        + head_recolored * head_weight[:, :, None]
    )
    recolored = (
        recolored * (1.0 - facial_detail[:, :, None])
        + template_rgb * facial_detail[:, :, None]
    )

    output = template.copy()
    output[:, :, :3] = np.clip(recolored, 0, 255).astype(np.uint8)
    output[output[:, :, 3] < 3] = 0
    return output


def _micro_pose(state: str, species: str) -> PoseSpec:
    dog = species == "dog"
    return {
        "idle": PoseSpec(body_dy=1.0),
        "sleeping": PoseSpec(scale_x=1.006, scale_y=0.994, body_dy=1.0),
        "waiting": PoseSpec(head_dx=3.5 if dog else 2.5, rotation=0.4),
        "waving": PoseSpec(
            rotation=-0.4,
            paw_dx=-2.5,
            paw_dy=-10.0 if dog else -8.0,
            body_dx=1.5,
        ),
        "jumping": PoseSpec(lift=18.0 if dog else 14.0),
        "failed": PoseSpec(scale_x=1.006, scale_y=0.994, head_dy=2.0),
        "working": PoseSpec(paw_dx=2.0, paw_dy=5.0, body_dy=1.0),
        "review": PoseSpec(head_dx=-4.0 if dog else -3.0, rotation=0.5),
        "walking-right": PoseSpec(
            bend=2.5 if dog else 1.8, body_dx=2.0, lift=4.0 if dog else 3.0
        ),
        "walking-left": PoseSpec(
            bend=2.5 if dog else 1.8, body_dx=2.0, lift=4.0 if dog else 3.0
        ),
        "feeding": PoseSpec(head_dy=5.0, body_dy=1.0),
    }[state]


def _source_metrics(path: Path) -> tuple[float, float]:
    rgba = _load_rgba(path)
    height, width = rgba.shape[:2]
    ratio = width / max(1.0, float(height))
    alpha = rgba[:, :, 3]
    solidity = float(np.count_nonzero(alpha > 32)) / max(1, width * height)
    return ratio, solidity


def _choose_source(
    sources: list[Path], metrics: list[tuple[float, float]], kind: str
) -> Path:
    if kind == "wide":
        index = max(
            range(len(sources)),
            key=lambda item: metrics[item][0] + metrics[item][1] * 0.22,
        )
    elif kind == "tall":
        index = min(
            range(len(sources)),
            key=lambda item: metrics[item][0] - metrics[item][1] * 0.12,
        )
    else:
        index = min(
            range(len(sources)),
            key=lambda item: abs(math.log(max(0.12, metrics[item][0])))
            - metrics[item][1] * 0.15,
        )
    return sources[index]


def _gaussian(
    xx: np.ndarray,
    yy: np.ndarray,
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
) -> np.ndarray:
    return np.exp(
        -(
            ((xx - center_x) / max(1.0, radius_x)) ** 2
            + ((yy - center_y) / max(1.0, radius_y)) ** 2
        )
        * 2.0
    )


def _deform_frame(
    base: np.ndarray, spec: PoseSpec, phase: float, species: str, state: str
) -> np.ndarray:
    eased = 0.5 - 0.5 * math.cos(phase * math.tau)
    signed = math.sin(phase * math.tau)
    height, width = base.shape[:2]

    dynamic_scale_x = spec.scale_x + signed * (
        0.006 if state in {"idle", "sleeping"} else 0.012
    )
    dynamic_scale_y = spec.scale_y - signed * (
        0.008 if state in {"idle", "sleeping"} else 0.014
    )
    dynamic_rotation = spec.rotation + signed * (
        0.5 if state in {"idle", "sleeping"} else 1.2
    )
    center_x = width / 2.0
    center_y = height * 0.58
    angle = math.radians(dynamic_rotation)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    a = cosine * dynamic_scale_x
    b = sine * dynamic_scale_x
    c = -sine * dynamic_scale_y
    d = cosine * dynamic_scale_y
    matrix = np.array(
        (
            (
                a,
                b,
                center_x - a * center_x - b * center_y + spec.body_dx * signed,
            ),
            (
                c,
                d,
                center_y
                - c * center_x
                - d * center_y
                + spec.body_dy * eased
                - spec.lift * eased,
            ),
        ),
        dtype=np.float32,
    )
    affine = cv2.warpAffine(
        base,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )

    if not any(
        (
            spec.bend,
            spec.head_dx,
            spec.head_dy,
            spec.paw_dx,
            spec.paw_dy,
        )
    ):
        affine[affine[:, :, 3] < 3] = 0
        return affine

    yy, xx = np.indices((height, width), dtype=np.float32)
    map_x = xx.copy()
    map_y = yy.copy()
    body_weight = np.sin(np.clip((yy - 110.0) / 600.0, 0.0, 1.0) * math.pi)
    map_x -= spec.bend * signed * body_weight

    head_weight = _gaussian(xx, yy, width * 0.5, height * 0.28, 170.0, 150.0)
    map_x -= spec.head_dx * signed * head_weight
    map_y -= spec.head_dy * eased * head_weight

    paw_center_x = width * (0.36 if species == "cat" else 0.27)
    paw_weight = _gaussian(xx, yy, paw_center_x, height * 0.79, 112.0, 138.0)
    map_x -= spec.paw_dx * signed * paw_weight
    map_y -= spec.paw_dy * eased * paw_weight

    if state == "working":
        second_paw = _gaussian(
            xx, yy, width * 0.64, height * 0.79, 108.0, 135.0
        )
        map_y -= spec.paw_dy * (1.0 - eased) * second_paw
        map_x += spec.paw_dx * signed * second_paw

    result = cv2.remap(
        affine,
        map_x,
        map_y,
        interpolation=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    result[result[:, :, 3] < 3] = 0
    return result


def _save_png(array: np.ndarray, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array, "RGBA").save(destination, "PNG", optimize=True)


def generate_action_pack(
    cutouts: list[Path],
    output_dir: Path,
    species: str,
    progress: ProgressCallback | None = None,
) -> dict[str, list[str]]:
    if species not in {"cat", "dog"}:
        raise ValueError("宠物类型只能是猫或狗。")
    if not 1 <= len(cutouts) <= 4:
        raise ValueError("请提供 1–4 张本地宠物素材。")
    if not all(path.exists() for path in cutouts):
        raise ValueError("有宠物参考素材不存在。")

    staging = output_dir.with_name(output_dir.name + "-staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    specs = CAT_POSES if species == "cat" else DOG_POSES
    metrics = [_source_metrics(path) for path in cutouts]
    total = len(specs) * FRAME_COUNT
    current = 0
    generated: dict[str, list[str]] = {}

    try:
        for state, spec in specs.items():
            source = _choose_source(cutouts, metrics, SOURCE_KIND[state])
            base = _normalize_to_canvas(_load_rgba(source))
            state_paths: list[str] = []
            for frame_index in range(FRAME_COUNT):
                phase = frame_index / max(1, FRAME_COUNT - 1)
                frame = _deform_frame(base, spec, phase, species, state)
                destination = staging / state / f"{frame_index:02d}.png"
                _save_png(frame, destination)
                state_paths.append(str(output_dir / state / destination.name))
                current += 1
                if progress:
                    progress(current, total, state)
            generated[state] = state_paths

        if output_dir.exists():
            backup = output_dir.with_name(output_dir.name + "-previous")
            if backup.exists():
                shutil.rmtree(backup)
            output_dir.replace(backup)
            staging.replace(output_dir)
            shutil.rmtree(backup)
        else:
            staging.replace(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return generated
