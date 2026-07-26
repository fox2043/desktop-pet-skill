from __future__ import annotations

import ctypes
import datetime
import json
import math
import os
import random
import shutil
import sys
import time
import winreg
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps
from PySide6.QtCore import QPoint, QRectF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from local_action_generator import generate_action_pack


APP_NAME = "我的桌面宠物"
APP_VERSION = "3.0.0"
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_VALUE = "MyCustomDesktopPet"
CELL_W, CELL_H = 220, 238
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PET_CLASS_IDS = {"cat": 16, "dog": 17}

STATE_CYCLES = {
    "idle": 8.8,
    "sleeping": 12.0,
    "waiting": 8.4,
    "waving": 7.2,
    "jumping": 4.2,
    "failed": 9.6,
    "working": 9.4,
    "review": 9.0,
    "walking-right": 6.4,
    "walking-left": 6.4,
    "feeding": 8.6,
    "playing": 7.6,
    "happy": 8.0,
}

MIN_DWELL_SECONDS = {
    "idle": 18.0,
    "sleeping": 30.0,
    "review": 12.0,
    "waiting": 10.0,
    "waving": 8.0,
    "jumping": 4.2,
    "failed": 10.0,
    "working": 12.0,
    "feeding": 20.0,
    "playing": 12.0,
    "happy": 12.0,
}


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def app_data_dir() -> Path:
    override = os.environ.get("CUSTOM_PET_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "MyCustomDesktopPet"


def config_path() -> Path:
    return app_data_dir() / "pet.json"


def resource_path(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets" / name


def seconds_since_input() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    elapsed_ms = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return max(0.0, elapsed_ms / 1000.0)


def load_config() -> dict | None:
    path = config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.get("species") not in {"cat", "dog"}:
            return None
        if int(data.get("version", 1)) < 3:
            return None
        actions = data.get("actions")
        if isinstance(actions, dict) and actions:
            validated: dict[str, list[str]] = {}
            for state, values in actions.items():
                if not isinstance(values, list):
                    continue
                paths = [Path(value) for value in values]
                if paths and all(item.exists() for item in paths):
                    validated[str(state)] = [str(item) for item in paths]
            if "idle" not in validated:
                return None
            data["actions"] = validated
            data["images"] = validated["idle"]
            return data
        images = [Path(value) for value in data.get("images", [])]
        if not 1 <= len(images) <= 4 or not all(path.exists() for path in images):
            return None
        data["images"] = [str(path) for path in images]
        return data
    except (OSError, ValueError, TypeError):
        return None


def save_config(data: dict) -> None:
    root = app_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    target = config_path()
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(target)


def install_bootstrap_config() -> dict | None:
    source_root = resource_path("bootstrap")
    manifest_path = source_root / "pet.json"
    pet_source = source_root / "pet"
    if not manifest_path.exists() or not pet_source.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if data.get("species") not in {"cat", "dog"}:
            return None
        destination = app_data_dir() / "pet"
        shutil.copytree(pet_source, destination, dirs_exist_ok=True)
        actions: dict[str, list[str]] = {}
        for state, values in data.get("actions", {}).items():
            paths = [destination / Path(value) for value in values]
            if not paths or not all(path.exists() for path in paths):
                return None
            actions[str(state)] = [str(path) for path in paths]
        if "idle" not in actions:
            return None
        references = [
            str(destination / Path(value))
            for value in data.get("references", [])
            if (destination / Path(value)).exists()
        ]
        installed = {
            **data,
            "version": 2,
            "references": references,
            "actions": actions,
            "images": actions["idle"],
            "installed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        save_config(installed)
        return load_config()
    except (OSError, ValueError, TypeError):
        return None


def _largest_foreground(mask: np.ndarray) -> np.ndarray:
    binary = (mask > 0).astype(np.uint8)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    if count <= 1:
        return binary
    height, width = binary.shape
    center = np.array([width / 2.0, height / 2.0])
    diagonal = max(1.0, math.hypot(width, height))
    best_label = 1
    best_score = -1.0
    for label in range(1, count):
        area = float(stats[label, cv2.CC_STAT_AREA])
        if area < width * height * 0.004:
            continue
        distance = float(np.linalg.norm(centroids[label] - center)) / diagonal
        score = area * max(0.25, 1.25 - distance)
        if score > best_score:
            best_label = label
            best_score = score
    return (labels == best_label).astype(np.uint8)


def _fallback_border_mask(rgb: np.ndarray) -> np.ndarray:
    height, width, _ = rgb.shape
    band = max(2, min(height, width) // 30)
    border = np.concatenate(
        (
            rgb[:band].reshape(-1, 3),
            rgb[-band:].reshape(-1, 3),
            rgb[:, :band].reshape(-1, 3),
            rgb[:, -band:].reshape(-1, 3),
        ),
        axis=0,
    )
    background = np.median(border.astype(np.float32), axis=0)
    difference = np.linalg.norm(rgb.astype(np.float32) - background, axis=2)
    threshold = max(24.0, float(np.percentile(difference, 58)))
    return (difference > threshold).astype(np.uint8)


class PetSegmenter:
    def __init__(self) -> None:
        model_path = resource_path("models/MaskRCNN-12-int8.onnx")
        if not model_path.exists():
            raise RuntimeError("缺少猫狗识别模型。")
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

    def extract_alpha(self, rgb: np.ndarray, species: str) -> np.ndarray:
        height, width = rgb.shape[:2]
        ratio = min(800.0 / min(width, height), 1333.0 / max(width, height))
        resized_w = max(1, int(round(width * ratio)))
        resized_h = max(1, int(round(height * ratio)))
        resized = cv2.resize(
            rgb,
            (resized_w, resized_h),
            interpolation=cv2.INTER_AREA if ratio < 1 else cv2.INTER_LINEAR,
        )
        tensor = resized[:, :, ::-1].astype(np.float32)
        tensor = np.transpose(tensor, (2, 0, 1))
        tensor -= np.array(
            [102.9801, 115.9465, 122.7717], dtype=np.float32
        )[:, None, None]
        padded_h = int(math.ceil(resized_h / 32) * 32)
        padded_w = int(math.ceil(resized_w / 32) * 32)
        padded = np.zeros((3, padded_h, padded_w), dtype=np.float32)
        padded[:, :resized_h, :resized_w] = tensor

        boxes, labels, scores, masks = self.session.run(
            None, {self.input_name: padded}
        )
        target_class = PET_CLASS_IDS[species]
        candidates = [
            index
            for index, (label, score) in enumerate(zip(labels, scores))
            if int(label) == target_class and float(score) >= 0.28
        ]
        if not candidates:
            animal = "猫" if species == "cat" else "狗"
            raise ValueError(
                f"没有在照片里识别到清晰的{animal}。请使用主体更完整、更清楚的照片。"
            )
        best = max(
            candidates,
            key=lambda index: float(scores[index])
            * max(
                1.0,
                float(boxes[index][2] - boxes[index][0])
                * float(boxes[index][3] - boxes[index][1]),
            )
            ** 0.12,
        )
        x0, y0, x1, y1 = boxes[best]
        left = max(0, min(resized_w - 1, int(math.floor(float(x0)))))
        top = max(0, min(resized_h - 1, int(math.floor(float(y0)))))
        right = max(left + 1, min(resized_w, int(math.ceil(float(x1)))))
        bottom = max(top + 1, min(resized_h, int(math.ceil(float(y1)))))
        mask = masks[best][0].astype(np.float32)
        resized_mask = cv2.resize(
            mask, (right - left, bottom - top), interpolation=cv2.INTER_CUBIC
        )
        probability = np.zeros((resized_h, resized_w), dtype=np.float32)
        probability[top:bottom, left:right] = np.maximum(
            probability[top:bottom, left:right], resized_mask
        )
        probability = cv2.resize(
            probability, (width, height), interpolation=cv2.INTER_CUBIC
        )
        probability = np.clip((probability - 0.18) / 0.58, 0.0, 1.0)
        hard = _largest_foreground((probability > 0.12).astype(np.uint8))
        padded_inverse = 1 - np.pad(hard, 1, constant_values=0)
        flood_mask = np.zeros(
            (padded_inverse.shape[0] + 2, padded_inverse.shape[1] + 2),
            dtype=np.uint8,
        )
        cv2.floodFill(padded_inverse, flood_mask, (0, 0), 2)
        holes = (padded_inverse[1:-1, 1:-1] == 1).astype(np.uint8)
        silhouette_area = max(1, int(hard.sum() + holes.sum()))
        if float(holes.sum()) / silhouette_area > 0.11:
            raise ValueError(
                "宠物身体被其他物体大面积遮挡，无法形成完整桌面形象。"
                "请换一张没有明显遮挡的照片。"
            )
        probability[holes > 0] = 1.0
        hard = np.maximum(hard, holes)
        keeper = cv2.dilate(hard, np.ones((5, 5), np.uint8), iterations=1)
        probability[keeper == 0] = 0.0
        alpha = np.clip(probability * 255.0, 0, 255).astype(np.uint8)
        return cv2.GaussianBlur(alpha, (0, 0), sigmaX=0.7)


_PET_SEGMENTER: PetSegmenter | None = None


def _semantic_pet_alpha(rgb: np.ndarray, species: str) -> np.ndarray:
    global _PET_SEGMENTER
    if _PET_SEGMENTER is None:
        _PET_SEGMENTER = PetSegmenter()
    return _PET_SEGMENTER.extract_alpha(rgb, species)


def make_transparent_pet(
    source: Path, destination: Path, species: str = "cat"
) -> None:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        image.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
        rgba = image.convert("RGBA")

    rgba_array = np.array(rgba)
    existing_alpha = rgba_array[:, :, 3]
    if np.percentile(existing_alpha, 15) < 245:
        alpha = existing_alpha
    else:
        rgb = rgba_array[:, :, :3]
        alpha = _semantic_pet_alpha(rgb, species)

    rgba_array[:, :, 3] = alpha
    visible = np.argwhere(alpha > 18)
    if visible.size == 0:
        raise ValueError("没有识别到清晰的宠物主体，请换一张背景更简单的照片。")
    top, left = visible.min(axis=0)
    bottom, right = visible.max(axis=0)
    pad = max(8, int(min(rgba.width, rgba.height) * 0.025))
    left = max(0, int(left) - pad)
    top = max(0, int(top) - pad)
    right = min(rgba.width - 1, int(right) + pad)
    bottom = min(rgba.height - 1, int(bottom) + pad)
    cropped = Image.fromarray(rgba_array, "RGBA").crop(
        (left, top, right + 1, bottom + 1)
    )
    cropped.thumbnail((850, 850), Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(destination, "PNG", optimize=True)


class SetupWindow(QWidget):
    created = Signal(dict)

    def __init__(self, existing: dict | None = None) -> None:
        super().__init__()
        self.existing = existing
        self.photo_paths: list[Path] = []
        self.generated = False
        self.setAcceptDrops(True)
        self.setWindowTitle("创建我的桌面宠物")
        self.setWindowIcon(QIcon(str(resource_path("pet.ico"))))
        self.setMinimumSize(650, 590)
        self.resize(700, 640)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #f7f4ef; color: #2f2a26; font-size: 14px; }
            QFrame#card { background: #ffffff; border: 1px solid #e5ded5;
                          border-radius: 18px; }
            QLineEdit, QComboBox, QListWidget {
                background: #fbfaf8; border: 1px solid #d8cec2;
                border-radius: 10px; padding: 9px;
            }
            QPushButton {
                background: #4f6f64; color: white; border: 0;
                border-radius: 11px; padding: 10px 18px; font-weight: 600;
            }
            QPushButton:hover { background: #3f5e54; }
            QPushButton#secondary { background: #e8e1d8; color: #3a342f; }
            QPushButton#danger { background: #a86458; }
            QProgressBar { border: 0; border-radius: 6px; background: #e9e4de; }
            QProgressBar::chunk { border-radius: 6px; background: #76998b; }
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)

        title = QLabel("让你的宠物住进电脑桌面")
        title.setFont(QFont("Microsoft YaHei UI", 22, QFont.Bold))
        subtitle = QLabel(
            "选择猫或狗，导入 1–4 张真实照片。本机直接保留宠物原本的品种、脸型、"
            "毛色和身体比例，照片不会上传。"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #71675f;")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如：雪球、豆包、旺财")
        if self.existing:
            self.name_input.setText(str(self.existing.get("name", "")))
        self.species_combo = QComboBox()
        self.species_combo.addItem("猫", "cat")
        self.species_combo.addItem("狗", "dog")
        if self.existing and self.existing.get("species") == "dog":
            self.species_combo.setCurrentIndex(1)
        form.addRow("宠物名字", self.name_input)
        form.addRow("宠物类型", self.species_combo)
        card_layout.addLayout(form)

        photo_header = QHBoxLayout()
        photo_label = QLabel("宠物照片（最多 4 张）")
        photo_label.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        choose_button = QPushButton("选择照片")
        choose_button.clicked.connect(self._choose_photos)
        photo_header.addWidget(photo_label)
        photo_header.addStretch()
        photo_header.addWidget(choose_button)
        card_layout.addLayout(photo_header)

        self.photo_list = QListWidget()
        self.photo_list.setIconSize(QSize(74, 74))
        self.photo_list.setMinimumHeight(190)
        self.photo_list.setSpacing(6)
        self.photo_list.setToolTip("也可以把照片直接拖到这里")
        card_layout.addWidget(self.photo_list)

        hint = QLabel(
            "不会再把宠物替换成通用猫狗模型。建议包含坐姿、趴姿、正面和侧面；"
            "照片姿态越丰富，睡觉、散步、玩耍和喂食越自然。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #83766c; font-size: 12px;")
        card_layout.addWidget(hint)

        list_actions = QHBoxLayout()
        remove_button = QPushButton("移除选中")
        remove_button.setObjectName("secondary")
        remove_button.clicked.connect(self._remove_selected)
        clear_button = QPushButton("清空照片")
        clear_button.setObjectName("secondary")
        clear_button.clicked.connect(self._clear_photos)
        list_actions.addWidget(remove_button)
        list_actions.addWidget(clear_button)
        list_actions.addStretch()
        card_layout.addLayout(list_actions)
        outer.addWidget(card)

        self.status_label = QLabel("等待选择照片")
        self.status_label.setStyleSheet("color: #71675f;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        outer.addWidget(self.status_label)
        outer.addWidget(self.progress)

        bottom = QHBoxLayout()
        if self.existing:
            cancel = QPushButton("取消")
            cancel.setObjectName("secondary")
            cancel.clicked.connect(self.close)
            bottom.addWidget(cancel)
        bottom.addStretch()
        self.generate_button = QPushButton("生成并开始陪伴")
        self.generate_button.clicked.connect(self._generate)
        bottom.addWidget(self.generate_button)
        outer.addLayout(bottom)

    def _append_photos(self, paths: list[str]) -> None:
        added = 0
        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() not in VALID_EXTENSIONS or not path.exists():
                continue
            if path in self.photo_paths:
                continue
            if len(self.photo_paths) >= 4:
                break
            self.photo_paths.append(path)
            pixmap = QPixmap(str(path))
            item = QListWidgetItem(QIcon(pixmap), path.name)
            item.setToolTip(str(path))
            self.photo_list.addItem(item)
            added += 1
        self.status_label.setText(
            f"已选择 {len(self.photo_paths)} 张照片"
            if self.photo_paths
            else "等待选择照片"
        )
        if len(paths) > added and len(self.photo_paths) >= 4:
            QMessageBox.information(self, "最多 4 张", "每只宠物最多使用 4 张照片。")

    def _choose_photos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择宠物照片（最多 4 张）",
            str(Path.home() / "Pictures"),
            "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp)",
        )
        self._append_photos(paths)

    def _remove_selected(self) -> None:
        selected_rows = sorted(
            {self.photo_list.row(item) for item in self.photo_list.selectedItems()},
            reverse=True,
        )
        for row in selected_rows:
            self.photo_list.takeItem(row)
            self.photo_paths.pop(row)
        self.status_label.setText(
            f"已选择 {len(self.photo_paths)} 张照片"
            if self.photo_paths
            else "等待选择照片"
        )

    def _clear_photos(self) -> None:
        self.photo_paths.clear()
        self.photo_list.clear()
        self.status_label.setText("等待选择照片")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self._append_photos(
            [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        )
        event.acceptProposedAction()

    def _generate(self) -> None:
        if not self.photo_paths:
            QMessageBox.warning(self, "还没有照片", "请先选择至少 1 张宠物照片。")
            return
        species = str(self.species_combo.currentData())
        name = self.name_input.text().strip()
        if not name:
            name = "我的猫咪" if species == "cat" else "我的狗狗"
        if len(name) > 16:
            QMessageBox.warning(self, "名字太长", "宠物名字请控制在 16 个字符以内。")
            return

        output_dir = app_data_dir() / "pet"
        output_dir.mkdir(parents=True, exist_ok=True)
        reference_dir = output_dir / "references-new"
        if reference_dir.exists():
            shutil.rmtree(reference_dir)
        reference_dir.mkdir(parents=True)
        references: list[Path] = []
        self.generate_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for index, source in enumerate(self.photo_paths, start=1):
                self.status_label.setText(
                    f"正在提取第 {index}/{len(self.photo_paths)} 张身份参考：{source.name}"
                )
                self.progress.setValue(
                    int((index - 1) / len(self.photo_paths) * 30)
                )
                QApplication.processEvents()
                destination = reference_dir / f"reference_{index}.png"
                make_transparent_pet(source, destination, species)
                references.append(destination)

            action_dir = output_dir / "actions"

            def report(current: int, total: int, state: str) -> None:
                labels = {
                    "idle": "安静发呆",
                    "sleeping": "趴下睡觉",
                    "waiting": "抬头观察",
                    "waving": "打招呼",
                    "jumping": "玩耍跳跃",
                    "failed": "委屈趴下",
                    "working": "陪伴工作",
                    "review": "歪头卖萌",
                    "walking-right": "向右散步",
                    "walking-left": "向左散步",
                    "feeding": "低头进食",
                    "playing": "开心玩耍",
                    "happy": "撒娇开心",
                }
                self.status_label.setText(
                    f"正在本地生成动作：{labels.get(state, state)} "
                    f"({current}/{total})"
                )
                self.progress.setValue(30 + int(current / max(1, total) * 68))
                QApplication.processEvents()

            actions = generate_action_pack(
                references, action_dir, species, progress=report
            )
            final_reference_dir = output_dir / "references"
            if final_reference_dir.exists():
                shutil.rmtree(final_reference_dir)
            reference_dir.replace(final_reference_dir)
            final_references = [
                str(final_reference_dir / item.name) for item in references
            ]
            data = {
                "version": 3,
                "name": name,
                "species": species,
                "references": final_references,
                "actions": actions,
                "images": actions["idle"],
                "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "generator": "offline-photo-identity-rig",
            }
            save_config(data)
            self.progress.setValue(100)
            self.status_label.setText(f"完成！{name}已经准备好陪你了。")
            self.generated = True
            self.created.emit(data)
        except Exception as error:
            QMessageBox.critical(
                self,
                "生成失败",
                f"本地定装没有完成：\n{error}\n\n请尝试背景更简单、主体更完整的照片。",
            )
        finally:
            QApplication.restoreOverrideCursor()
            self.generate_button.setEnabled(True)

    def closeEvent(self, event) -> None:
        if not self.existing and not self.generated:
            QApplication.quit()
        event.accept()


class PetWindow(QWidget):
    edit_requested = Signal()

    def __init__(self, config: dict) -> None:
        super().__init__()
        self.settings = QSettings("CustomPetStudio", "DesktopPet")
        self.scale_factor = float(self.settings.value("scale", 0.9))
        self.paused = False
        self.always_on_top = True
        self.state = "idle"
        self.state_started_at = time.monotonic()
        self.state_until = 0.0
        self.sequence: list[tuple[str, float]] = []
        self.dragging = False
        self.drag_offset = QPoint()
        self.press_global = QPoint()
        self.drag_moved = False
        self.last_cursor = QCursor.pos()
        self.last_cursor_at = time.monotonic()
        self.last_surprise = 0.0
        self.cursor_inside_last = False
        self.hover_started_at = 0.0
        self.hover_acted = False
        self.hover_long_acted = False
        self.stroke_score = 0.0
        self.last_dx_sign = 0
        self.rest_state = "idle"
        self.rest_until = time.monotonic() + random.uniform(50, 90)
        self.rest_cycle_index = 1
        self.next_roam_at = time.monotonic() + random.uniform(55, 105)
        self.roam_target_x: int | None = None
        self.next_work_pose_at = time.monotonic() + random.uniform(35, 70)
        self.next_long_idle_reaction = time.monotonic() + random.uniform(110, 180)
        self.next_companion_message_at = time.monotonic() + random.uniform(2700, 5400)
        self.last_bedtime_key = ""
        self.exiting = False
        self._load_pet(config)

        self.setWindowTitle(f"{self.pet_name} · {APP_NAME}")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint
        )
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self._apply_size()
        self._restore_position()
        self._render_frame(time.monotonic())

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon(self.pet_images[0]))
        self.tray.setToolTip(f"{self.pet_name}正在陪你")
        self.tray.setContextMenu(self._build_menu())
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _load_pet(self, config: dict) -> None:
        self.config = config
        self.pet_name = str(config.get("name") or "我的宠物")
        self.species = str(config.get("species") or "cat")
        self.pet_frames: dict[str, list[QPixmap]] = {}
        for state, paths in config.get("actions", {}).items():
            frames = []
            for path in paths:
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    frames.append(pixmap)
            if frames:
                self.pet_frames[str(state)] = frames
        self.pet_images = []
        for path in config.get("images", []):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.pet_images.append(pixmap)
        if not self.pet_images and self.pet_frames.get("idle"):
            self.pet_images = list(self.pet_frames["idle"])
        if not self.pet_images:
            raise RuntimeError("本地宠物动作包不存在，请重新定装。")
        if self.species == "cat":
            self.rest_cycle = (
                ("review", 20, 34),
                ("waiting", 14, 24),
                ("sleeping", 62, 115),
                ("review", 18, 30),
                ("idle", 32, 58),
                ("sleeping", 70, 125),
            )
            self.behavior = {
                "hover_short": 2.0,
                "hover_long": 8.0,
                "near_distance": 180.0,
                "near_speed": 100.0,
                "surprise_speed": 950.0,
                "roam_low": 65.0,
                "roam_high": 130.0,
                "work_low": 45.0,
                "work_high": 85.0,
                "random_action": 0.00028,
            }
        else:
            self.rest_cycle = (
                ("waiting", 16, 27),
                ("sleeping", 46, 84),
                ("review", 16, 28),
                ("idle", 34, 66),
                ("sleeping", 50, 92),
            )
            self.behavior = {
                "hover_short": 1.2,
                "hover_long": 5.0,
                "near_distance": 245.0,
                "near_speed": 65.0,
                "surprise_speed": 760.0,
                "roam_low": 42.0,
                "roam_high": 88.0,
                "work_low": 30.0,
                "work_high": 58.0,
                "random_action": 0.00052,
            }
        now = time.monotonic()
        self.next_roam_at = now + random.uniform(
            self.behavior["roam_low"], self.behavior["roam_high"]
        )
        self.next_work_pose_at = now + random.uniform(
            self.behavior["work_low"], self.behavior["work_high"]
        )

    def _greet_sequence(self) -> tuple[tuple[str, float], ...]:
        if self.species == "cat":
            return (
                ("waiting", 10.0),
                ("waving", 8.0),
                ("happy", 12.0),
                ("idle", 18.0),
            )
        return (
            ("waving", 9.0),
            ("happy", 12.0),
            ("waiting", 10.0),
            ("idle", 18.0),
        )

    def _cute_sequence(self) -> tuple[tuple[str, float], ...]:
        if self.species == "cat":
            return (
                ("waiting", 10.0),
                ("happy", 14.0),
                ("playing", 12.0),
                ("idle", 18.0),
                ("review", 12.0),
            )
        return (
            ("review", 10.0),
            ("happy", 14.0),
            ("playing", 12.0),
            ("jumping", 4.2),
            ("waiting", 10.0),
        )

    def _work_sequence(self) -> tuple[tuple[str, float], ...]:
        if self.species == "cat":
            return (("working", 16.0), ("idle", 20.0))
        return (("waiting", 10.0), ("working", 18.0), ("idle", 20.0))

    def _petting_sequence(self) -> tuple[tuple[str, float], ...]:
        if self.species == "cat":
            return (
                ("happy", 14.0),
                ("working", 14.0),
                ("idle", 20.0),
            )
        return (
            ("happy", 14.0),
            ("waiting", 10.0),
            ("playing", 12.0),
            ("idle", 18.0),
        )

    def reload_pet(self, config: dict) -> None:
        self._load_pet(config)
        self.setWindowTitle(f"{self.pet_name} · {APP_NAME}")
        self.tray.setIcon(QIcon(self.pet_images[0]))
        self.tray.setToolTip(f"{self.pet_name}正在陪你")
        self.tray.setContextMenu(self._build_menu())
        self.set_state("waiting", 10.0)

    def _photo_for_state(self, state: str, now: float | None = None) -> QPixmap:
        frames = self.pet_frames.get(state)
        if not frames and state == "walking-left":
            frames = self.pet_frames.get("walking-right")
        if frames:
            if len(frames) == 1:
                return frames[0]
            moment = time.monotonic() if now is None else now
            cycle = STATE_CYCLES.get(state, 8.0)
            progress = ((moment - self.state_started_at) % cycle) / cycle
            index = min(len(frames) - 1, int(progress * len(frames)))
            return frames[index]
        count = len(self.pet_images)
        mapping = {
            "idle": 0,
            "sleeping": 0,
            "review": min(1, count - 1),
            "waiting": min(1, count - 1),
            "walking-right": min(2, count - 1),
            "walking-left": min(2, count - 1),
            "working": min(2, count - 1),
            "waving": min(3, count - 1),
            "jumping": min(3, count - 1),
            "feeding": min(1, count - 1),
            "failed": 0,
            "playing": min(2, count - 1),
            "happy": min(1, count - 1),
        }
        return self.pet_images[mapping.get(state, 0)]

    def _apply_size(self) -> None:
        width = max(110, int(CELL_W * self.scale_factor))
        height = max(119, int(CELL_H * self.scale_factor))
        self.setFixedSize(width, height)
        if hasattr(self, "label"):
            self.label.setGeometry(self.rect())

    def _restore_position(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        x = int(self.settings.value("x", screen.right() - self.width() - 28))
        y = int(self.settings.value("y", screen.bottom() - self.height() - 18))
        x = min(max(screen.left(), x), screen.right() - self.width())
        y = min(max(screen.top(), y), screen.bottom() - self.height())
        self.move(x, y)

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        change = QAction("更换宠物或照片…", self)
        change.triggered.connect(self.edit_requested.emit)
        menu.addAction(change)
        menu.addSeparator()

        greet = QAction(f"和{self.pet_name}打招呼", self)
        greet.triggered.connect(lambda: self.play_sequence(*self._greet_sequence()))
        menu.addAction(greet)

        jump = QAction(f"逗{self.pet_name}跳一下", self)
        jump.triggered.connect(
            lambda: self.play_sequence(("jumping", 4.2), ("idle", 18.0))
        )
        menu.addAction(jump)

        cute = QAction(f"让{self.pet_name}卖个萌", self)
        cute.triggered.connect(lambda: self.play_sequence(*self._cute_sequence()))
        menu.addAction(cute)

        play = QAction(f"陪{self.pet_name}玩一会儿", self)
        play.triggered.connect(
            lambda: self.play_sequence(
                ("playing", 14.0), ("happy", 12.0), ("idle", 18.0)
            )
        )
        menu.addAction(play)

        pet_action = QAction(f"摸摸{self.pet_name}", self)
        pet_action.triggered.connect(
            lambda: self.play_sequence(("happy", 14.0), ("idle", 20.0))
        )
        menu.addAction(pet_action)

        food = "猫粮" if self.species == "cat" else "狗粮"
        feed = QAction(f"喂{self.pet_name}吃{food}", self)
        feed.triggered.connect(
            lambda: self.play_sequence(("feeding", 20.0), ("idle", 18.0))
        )
        menu.addAction(feed)

        work_text = (
            f"让{self.pet_name}踩奶陪我工作"
            if self.species == "cat"
            else f"让{self.pet_name}趴下陪我工作"
        )
        work = QAction(work_text, self)
        work.triggered.connect(lambda: self.play_sequence(*self._work_sequence()))
        menu.addAction(work)
        menu.addSeparator()

        self.pause_action = QAction("暂停动作", self, checkable=True)
        self.pause_action.setChecked(self.paused)
        self.pause_action.toggled.connect(self._set_paused)
        menu.addAction(self.pause_action)

        size_menu = menu.addMenu("宠物大小")
        for label, value in (("小", 0.65), ("中", 0.9), ("大", 1.2), ("超大", 1.5)):
            action = QAction(label, self)
            action.triggered.connect(
                lambda checked=False, selected=value: self._set_scale(selected)
            )
            size_menu.addAction(action)

        self.top_action = QAction("始终置顶", self, checkable=True)
        self.top_action.setChecked(self.always_on_top)
        self.top_action.toggled.connect(self._set_topmost)
        menu.addAction(self.top_action)

        self.startup_action = QAction("开机自动启动", self, checkable=True)
        self.startup_action.setChecked(self._is_startup_enabled())
        self.startup_action.toggled.connect(self._set_startup)
        menu.addAction(self.startup_action)
        menu.addSeparator()

        quit_action = QAction(f"退出{self.pet_name}", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)
        return menu

    def set_state(self, state: str, duration: float = 0.0) -> None:
        if state not in STATE_CYCLES:
            return
        if self.state != state:
            self.state = state
            self.state_started_at = time.monotonic()
            self._render_frame(self.state_started_at)
        self.state_until = time.monotonic() + duration if duration else 0.0

    def play_sequence(self, *items: tuple[str, float]) -> None:
        self.sequence = []
        for state, duration in items:
            minimum = MIN_DWELL_SECONDS.get(state, STATE_CYCLES[state])
            self.sequence.append((state, max(duration, minimum)))
        self._play_next_sequence_item()

    def _play_next_sequence_item(self) -> None:
        if not self.sequence:
            return
        state, duration = self.sequence.pop(0)
        self.set_state(state, duration)

    def _choose_rest(self, now: float) -> None:
        self.rest_cycle_index = (self.rest_cycle_index + 1) % len(self.rest_cycle)
        self.rest_state, low, high = self.rest_cycle[self.rest_cycle_index]
        self.rest_until = now + random.uniform(low, high)
        self.set_state(self.rest_state)

    def _bedtime_key(self) -> str:
        local = datetime.datetime.now()
        if local.hour >= 23:
            return local.date().isoformat()
        if local.hour < 5:
            return (local.date() - datetime.timedelta(days=1)).isoformat()
        return ""

    def _tick(self) -> None:
        if self.paused:
            return
        now = time.monotonic()
        cursor = QCursor.pos()
        elapsed = max(0.001, now - self.last_cursor_at)
        dx = cursor.x() - self.last_cursor.x()
        dy = cursor.y() - self.last_cursor.y()
        speed = math.hypot(dx, dy) / elapsed
        distance = math.hypot(
            cursor.x() - self.geometry().center().x(),
            cursor.y() - self.geometry().center().y(),
        )
        cursor_inside = self.geometry().contains(cursor)
        if cursor_inside and not self.cursor_inside_last:
            self.hover_started_at = now
            self.hover_acted = False
            self.hover_long_acted = False
        elif not cursor_inside:
            self.hover_started_at = 0.0
            self.hover_acted = False
            self.hover_long_acted = False
        hover_seconds = now - self.hover_started_at if self.hover_started_at else 0.0

        dx_sign = 1 if dx > 5 else -1 if dx < -5 else 0
        if cursor_inside and dx_sign and self.last_dx_sign and dx_sign != self.last_dx_sign:
            self.stroke_score += 1.0
        else:
            self.stroke_score = max(0.0, self.stroke_score - 0.018)
        if dx_sign:
            self.last_dx_sign = dx_sign

        if self.dragging:
            self.move(cursor - self.drag_offset)
            self.set_state("walking-right" if dx >= 0 else "walking-left")
        elif self.state_until and now < self.state_until:
            pass
        elif self.sequence:
            self._play_next_sequence_item()
        elif (bedtime_key := self._bedtime_key()) and bedtime_key != self.last_bedtime_key:
            self.last_bedtime_key = bedtime_key
            self.tray.showMessage(
                APP_NAME,
                f"已经很晚啦，{self.pet_name}困了。你也早点休息，好吗？",
            )
            self.play_sequence(
                ("waiting", 10.0),
                ("idle", 20.0),
                ("failed", 10.0),
                ("sleeping", 60.0),
            )
        elif now >= self.next_companion_message_at and seconds_since_input() < 10:
            self.next_companion_message_at = now + random.uniform(2700, 5400)
            self.tray.showMessage(
                APP_NAME,
                random.choice(
                    (
                        (
                            f"{self.pet_name}在旁边眯着呢，慢慢来。",
                            f"辛苦啦，摸摸{self.pet_name}再继续。",
                            f"忙了这么久，记得喝口水。{self.pet_name}安静陪着你。",
                        )
                        if self.species == "cat"
                        else (
                            f"{self.pet_name}一直守在旁边陪你。",
                            f"{self.pet_name}看着你呢，摸摸它再继续吧。",
                            f"忙了这么久，记得喝口水。{self.pet_name}等着你。",
                        )
                    )
                ),
            )
            if self.species == "cat":
                self.play_sequence(
                    ("waiting", 10.0),
                    ("happy", 12.0),
                    ("sleeping", 34.0),
                )
            else:
                self.play_sequence(
                    ("happy", 12.0),
                    ("waiting", 10.0),
                    ("sleeping", 28.0),
                )
        else:
            self.state_until = 0.0
            idle_seconds = seconds_since_input()
            if self.stroke_score >= 4:
                self.stroke_score = 0.0
                self.play_sequence(*self._petting_sequence())
            elif (
                cursor_inside
                and hover_seconds > self.behavior["hover_long"]
                and not self.hover_long_acted
            ):
                self.hover_long_acted = True
                if self.species == "cat":
                    self.play_sequence(
                        ("working", 10.0),
                        ("happy", 12.0),
                        ("idle", 16.0),
                    )
                else:
                    self.play_sequence(
                        ("happy", 12.0),
                        ("playing", 12.0),
                        ("waiting", 10.0),
                        ("idle", 16.0),
                    )
            elif (
                cursor_inside
                and hover_seconds > self.behavior["hover_short"]
                and not self.hover_acted
            ):
                self.hover_acted = True
                if self.species == "cat":
                    self.play_sequence(
                        ("waiting", 10.0),
                        ("happy", 12.0),
                        ("idle", 14.0),
                    )
                else:
                    self.play_sequence(
                        ("review", 10.0), ("happy", 12.0), ("idle", 14.0)
                    )
            elif (
                distance < 280
                and speed > self.behavior["surprise_speed"]
                and now - self.last_surprise > 3.0
            ):
                self.last_surprise = now
                if self.species == "cat":
                    self.play_sequence(
                        ("jumping", 4.2), ("idle", 12.0), ("review", 12.0)
                    )
                else:
                    self.play_sequence(
                        ("jumping", 4.2), ("happy", 12.0), ("idle", 14.0)
                    )
            elif (
                distance < self.behavior["near_distance"]
                and speed > self.behavior["near_speed"]
            ):
                self.set_state(
                    "walking-right" if dx >= 0 else "walking-left", 0.7
                )
            elif self.roam_target_x is not None:
                delta = self.roam_target_x - self.x()
                if abs(delta) <= 3:
                    self.roam_target_x = None
                    self.next_roam_at = now + random.uniform(
                        self.behavior["roam_low"], self.behavior["roam_high"]
                    )
                    if self.species == "cat":
                        self.play_sequence(
                            ("review", 12.0), ("happy", 12.0), ("idle", 18.0)
                        )
                    else:
                        self.play_sequence(
                            ("waiting", 10.0), ("happy", 12.0), ("idle", 16.0)
                        )
                else:
                    step = 2 if delta > 0 else -2
                    self.move(self.x() + step, self.y())
                    self.set_state("walking-right" if step > 0 else "walking-left")
            elif idle_seconds < 2.5:
                if now >= self.next_work_pose_at:
                    self.next_work_pose_at = now + random.uniform(
                        self.behavior["work_low"], self.behavior["work_high"]
                    )
                    self.play_sequence(*self._work_sequence())
                else:
                    self.set_state(self.rest_state)
            elif (
                (8 if self.species == "dog" else 12)
                < idle_seconds
                < (55 if self.species == "dog" else 45)
                and now >= self.next_roam_at
            ):
                screen = self.screen().availableGeometry()
                distance_low, distance_high = (
                    (80, 180) if self.species == "dog" else (55, 140)
                )
                target = (
                    self.x()
                    + random.choice((-1, 1))
                    * random.randint(distance_low, distance_high)
                )
                self.roam_target_x = min(
                    max(screen.left(), target), screen.right() - self.width()
                )
            elif idle_seconds > 100 and now >= self.next_long_idle_reaction:
                self.next_long_idle_reaction = now + random.uniform(140, 260)
                if self.species == "cat":
                    self.play_sequence(
                        ("waiting", 10.0),
                        ("idle", 16.0),
                        ("failed", 10.0),
                        ("idle", 24.0),
                    )
                else:
                    self.play_sequence(
                        ("waiting", 10.0),
                        ("waving", 7.0),
                        ("idle", 18.0),
                    )
            elif random.random() < self.behavior["random_action"]:
                if self.species == "cat":
                    choices = (
                        (("happy", 12.0), ("idle", 16.0)),
                        (("playing", 12.0), ("idle", 18.0)),
                        (("waiting", 10.0), ("idle", 16.0), ("review", 12.0)),
                        (("review", 12.0), ("idle", 18.0)),
                    )
                else:
                    choices = (
                        (("review", 10.0), ("happy", 12.0), ("idle", 14.0)),
                        (("playing", 12.0), ("waiting", 10.0), ("idle", 16.0)),
                        (("happy", 12.0), ("idle", 14.0)),
                    )
                self.play_sequence(*random.choice(choices))
            elif now >= self.rest_until:
                self._choose_rest(now)
            else:
                self.set_state(self.rest_state)

        self._render_frame(now)
        self.last_cursor = cursor
        self.last_cursor_at = now
        self.cursor_inside_last = cursor_inside

    def _render_frame(self, now: float) -> None:
        canvas = QPixmap(CELL_W, CELL_H)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        cycle = STATE_CYCLES[self.state]
        if self.species == "dog" and self.state in {
            "waiting",
            "waving",
            "jumping",
            "walking-right",
            "walking-left",
            "feeding",
            "playing",
            "happy",
        }:
            cycle *= 0.92
        phase = ((now - self.state_started_at) % cycle) / cycle
        wave = math.sin(phase * math.tau)
        pulse = math.sin(phase * math.tau * 2)
        x_offset = 0.0
        y_offset = 0.0
        rotation = 0.0
        scale_x = 1.0
        scale_y = 1.0

        if self.species == "cat":
            if self.state == "idle":
                y_offset = 0.7 * wave
                scale_x = 1.0 - 0.002 * wave
                scale_y = 1.0 + 0.004 * wave
            elif self.state == "sleeping":
                y_offset = 0.5 * wave
                scale_x = 1.0 - 0.002 * wave
                scale_y = 1.0 + 0.003 * wave
            elif self.state == "waiting":
                rotation = 0.8 * wave
                y_offset = -0.6 * max(0.0, wave)
            elif self.state == "waving":
                rotation = 1.2 * math.sin(phase * math.tau)
                y_offset = -1.2 * max(0.0, wave)
            elif self.state == "jumping":
                y_offset = -5.0 * max(0.0, wave)
            elif self.state == "failed":
                rotation = -0.8 + 0.4 * wave
                y_offset = 2.0 + 0.6 * wave
            elif self.state == "working":
                rotation = 0.4 * pulse
                x_offset = 0.8 * wave
                y_offset = 0.6 * abs(pulse)
            elif self.state == "review":
                rotation = 0.9 * wave
                x_offset = 0.6 * wave
            elif self.state in {"walking-right", "walking-left"}:
                y_offset = -1.2 * abs(pulse)
                rotation = 0.5 * pulse
            elif self.state == "feeding":
                y_offset = 8.0 + 1.2 * abs(wave)
                rotation = 0.6 * wave
            elif self.state == "playing":
                x_offset = 2.5 * wave
                y_offset = -3.5 * abs(pulse)
                rotation = 1.2 * wave
            elif self.state == "happy":
                x_offset = 1.5 * wave
                y_offset = -2.0 * abs(wave)
                rotation = 0.8 * wave
        else:
            if self.state == "idle":
                y_offset = 0.8 * wave
                rotation = 0.25 * math.sin(phase * math.tau)
                scale_y = 1.0 + 0.004 * wave
            elif self.state == "sleeping":
                y_offset = 0.6 * wave
                scale_y = 1.0 + 0.004 * wave
            elif self.state == "waiting":
                rotation = 1.5 * wave
                x_offset = 0.8 * wave
                y_offset = -0.8 * max(0.0, wave)
            elif self.state == "waving":
                rotation = 2.2 * math.sin(phase * math.tau)
                x_offset = 1.8 * math.sin(phase * math.tau)
                y_offset = -1.8 * abs(pulse)
            elif self.state == "jumping":
                y_offset = -7.0 * max(0.0, wave)
                rotation = 0.8 * wave
            elif self.state == "failed":
                rotation = -1.0 + 0.5 * wave
                y_offset = 2.5 + 0.7 * wave
            elif self.state == "working":
                y_offset = 1.5 + 0.6 * wave
                rotation = 0.5 * wave
            elif self.state == "review":
                rotation = 1.8 * wave
                x_offset = 0.9 * wave
            elif self.state in {"walking-right", "walking-left"}:
                y_offset = -1.8 * abs(pulse)
                rotation = 0.9 * pulse
            elif self.state == "feeding":
                y_offset = 8.0 + 1.8 * abs(pulse)
                rotation = 0.9 * pulse
            elif self.state == "playing":
                x_offset = 4.0 * wave
                y_offset = -5.0 * abs(pulse)
                rotation = 1.8 * wave
            elif self.state == "happy":
                x_offset = 2.5 * wave
                y_offset = -3.0 * abs(wave)
                rotation = 1.3 * wave

        pet = self._photo_for_state(self.state, now)
        available_w = 184.0
        available_h = 174.0 if self.state == "feeding" else 194.0
        ratio = min(available_w / pet.width(), available_h / pet.height())
        draw_w = pet.width() * ratio
        draw_h = pet.height() * ratio
        center_x = CELL_W / 2 + x_offset
        bottom = CELL_H - (22 if self.state == "feeding" else 8) + y_offset

        painter.save()
        painter.translate(center_x, bottom - draw_h / 2)
        if self.state == "walking-left":
            painter.scale(-1.0, 1.0)
        painter.rotate(rotation)
        painter.scale(scale_x, scale_y)
        destination = QRectF(-draw_w / 2, -draw_h / 2, draw_w, draw_h)
        painter.drawPixmap(destination, pet, QRectF(pet.rect()))
        painter.restore()

        if self.state in {"happy", "waving"}:
            heart_font = QFont("Segoe UI Symbol", 17, QFont.Bold)
            painter.setFont(heart_font)
            painter.setPen(QColor(238, 105, 126, 225))
            heart_y = 48 - int(5 * max(0.0, wave))
            painter.drawText(QRectF(36, heart_y, 34, 32), Qt.AlignCenter, "♥")
            if self.state == "happy":
                painter.setPen(QColor(255, 151, 166, 205))
                painter.setFont(QFont("Segoe UI Symbol", 12, QFont.Bold))
                painter.drawText(
                    QRectF(61, heart_y + 17, 26, 26), Qt.AlignCenter, "♥"
                )

        if self.state == "playing":
            ball_x = 93 + 25 * wave
            ball_y = CELL_H - 31
            painter.setPen(Qt.NoPen)
            if self.species == "cat":
                painter.setBrush(QColor("#d58a9b"))
                painter.drawEllipse(QRectF(ball_x, ball_y, 23, 23))
                painter.setPen(QColor("#8f5965"))
                painter.drawArc(
                    QRectF(ball_x + 4, ball_y + 5, 15, 11), 15 * 16, 170 * 16
                )
                painter.drawLine(
                    int(ball_x + 19),
                    int(ball_y + 7),
                    int(ball_x + 31 + 5 * wave),
                    int(ball_y - 5),
                )
            else:
                painter.setBrush(QColor("#d9d94a"))
                painter.drawEllipse(QRectF(ball_x, ball_y, 24, 24))
                painter.setPen(QColor("#f6f5c1"))
                painter.drawArc(
                    QRectF(ball_x + 2, ball_y + 3, 20, 18), 70 * 16, 150 * 16
                )

        if self.state == "feeding":
            bowl_y = CELL_H - 29
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#a96345"))
            painter.drawRoundedRect(QRectF(62, bowl_y, 96, 22), 9, 9)
            painter.setBrush(QColor("#6f3726"))
            painter.drawEllipse(QRectF(69, bowl_y - 4, 82, 14))
            food_color = QColor("#8b5a32") if self.species == "cat" else QColor("#98663d")
            painter.setBrush(food_color)
            for index in range(8):
                angle = index / 8 * math.tau
                painter.drawEllipse(
                    QRectF(
                        105 + math.cos(angle) * 25,
                        bowl_y + 1 + math.sin(angle) * 4,
                        6,
                        4,
                    )
                )
        painter.end()
        scaled = canvas.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(scaled)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_moved = False
            self.press_global = event.globalPosition().toPoint()
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
        elif event.button() == Qt.RightButton:
            self.tray.contextMenu().popup(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.dragging:
            current = event.globalPosition().toPoint()
            if (current - self.press_global).manhattanLength() > 5:
                self.drag_moved = True
            self.move(current - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            if self.drag_moved:
                self.settings.setValue("x", self.x())
                self.settings.setValue("y", self.y())
                self.play_sequence(
                    ("review", 12.0), ("happy", 12.0), ("idle", 18.0)
                )
            else:
                self.play_sequence(
                    *random.choice(
                        (
                            (("waiting", 10.0), ("happy", 12.0)),
                            (("jumping", 4.2), ("happy", 12.0)),
                            (("happy", 14.0), ("idle", 18.0)),
                        )
                    )
                )
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.play_sequence(
                ("playing", 12.0),
                ("jumping", 4.2),
                ("happy", 14.0),
                ("idle", 18.0),
            )
            event.accept()

    def _set_paused(self, paused: bool) -> None:
        self.paused = paused
        if not paused:
            self.set_state("idle")

    def _set_scale(self, scale: float) -> None:
        self.scale_factor = scale
        self.settings.setValue("scale", scale)
        self._apply_size()
        self._render_frame(time.monotonic())

    def _set_topmost(self, enabled: bool) -> None:
        self.always_on_top = enabled
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if enabled:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _startup_command(self) -> str:
        executable = Path(sys.executable).resolve()
        if getattr(sys, "frozen", False):
            return f'"{executable}"'
        return f'"{executable}" "{Path(__file__).resolve()}"'

    def _is_startup_enabled(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY) as key:
                winreg.QueryValueEx(key, STARTUP_VALUE)
            return True
        except OSError:
            return False

    def _set_startup(self, enabled: bool) -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enabled:
                    winreg.SetValueEx(
                        key, STARTUP_VALUE, 0, winreg.REG_SZ, self._startup_command()
                    )
                else:
                    try:
                        winreg.DeleteValue(key, STARTUP_VALUE)
                    except FileNotFoundError:
                        pass
        except OSError:
            self.startup_action.blockSignals(True)
            self.startup_action.setChecked(not enabled)
            self.startup_action.blockSignals(False)

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.raise_()
            self.play_sequence(("happy", 12.0), ("idle", 18.0))

    def _quit_app(self) -> None:
        self.exiting = True
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if self.exiting:
            event.accept()
            return
        event.ignore()
        self.hide()


class AppController:
    def __init__(self) -> None:
        self.pet: PetWindow | None = None
        self.setup: SetupWindow | None = None
        existing = load_config() or install_bootstrap_config()
        if existing:
            self._show_pet(existing)
        else:
            self._show_setup(None)

    def _show_pet(self, config: dict) -> None:
        if self.pet:
            self.pet.reload_pet(config)
            self.pet.show()
            self.pet.raise_()
        else:
            self.pet = PetWindow(config)
            self.pet.edit_requested.connect(self.open_setup)
            self.pet.show()
        if self.setup:
            self.setup.close()
            self.setup = None

    def _show_setup(self, existing: dict | None) -> None:
        if self.setup:
            self.setup.show()
            self.setup.raise_()
            self.setup.activateWindow()
            return
        self.setup = SetupWindow(existing)
        self.setup.created.connect(self._show_pet)
        self.setup.destroyed.connect(self._setup_destroyed)
        self.setup.show()
        self.setup.raise_()

    def _setup_destroyed(self) -> None:
        self.setup = None

    def open_setup(self) -> None:
        self._show_setup(load_config())


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("我的桌面宠物仅支持 Windows。")
    if len(sys.argv) == 5 and sys.argv[1] == "--generate-offline-pack":
        species = sys.argv[2]
        if species not in {"cat", "dog"}:
            raise SystemExit(2)
        source = Path(sys.argv[3])
        output = Path(sys.argv[4])
        reference = output / "references" / "reference_1.png"
        make_transparent_pet(source, reference, species)
        actions = generate_action_pack(
            [reference], output / "actions", species
        )
        (output / "manifest.json").write_text(
            json.dumps(
                {
                    "version": 3,
                    "species": species,
                    "actions": actions,
                    "generator": "offline-photo-identity-rig",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0
    if len(sys.argv) == 5 and sys.argv[1] == "--process-photo":
        species = sys.argv[2]
        if species not in {"cat", "dog"}:
            raise SystemExit(2)
        make_transparent_pet(Path(sys.argv[3]), Path(sys.argv[4]), species)
        return 0
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(str(resource_path("pet.ico"))))
    controller = AppController()
    app.aboutToQuit.connect(
        lambda: controller.pet.settings.sync() if controller.pet else None
    )
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
