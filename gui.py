from __future__ import annotations

import argparse
from collections.abc import Callable
from copy import deepcopy
import csv
import importlib
import json
import math
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from time import perf_counter

from pose_estimators import (
    BasePoseEstimator,
    RTMLIB_POSE_ASSETS,
    VITPOSE_ASSETS,
    clamped_target_box,
    clear_cuda_cache as _estimator_clear_cuda_cache,
    configure_hf_environment,
    configure_onnxruntime_environment,
    create_pose_estimator as _factory_create_pose_estimator,
    draw_pose_skeleton,
    has_cached_vitpose_onnx,
    resolve_rtmlib_selection,
    resolve_vitpose_selection,
    validate_pose_settings,
)
from pose_estimators.base import get_udp_warp_matrix
from pose_estimators.factory import normalize_pose_engine

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "gui_settings.json"
HOME = Path.home()

# GUIの初期値。通常の入力動画指定はGUIで行います。
INPUT_ROOT = (
    Path.home()
    / "解析用動画ファイル"
    / "9-18-SMZ"
    / "踏切左-SONY"
)
INPUT_VIDEO_NAME = "H7.MP4"

# GUIの初期値。解析時の出力先と名前はGUIから設定します。
OUTPUT_ROOT = (
    Path.home()
    / "動画解析出力"
    / "9-18-SMZ-rtmlib"
    / "踏切左-SONY"
)
OUTPUT_FOLDER_NAME = "踏切左-7"
OUTPUT_VIDEO_NAME = "踏切左-7.mp4"
OUTPUT_CROP_VIDEO_NAME = "踏切左-7-crop.mp4"
OUTPUT_CROP_SKELETON_VIDEO_NAME = "踏切左-7-crop-skeleton.mp4"
OUTPUT_CSV_NAME = "踏切左-7.csv"
OUTPUT_METADATA_NAME = "踏切左-7_metadata.txt"
OUTPUT_METADATA_JSON_NAME = "踏切左-7_metadata.json"
OUTPUT_NPZ_NAME = "踏切左-7.npz"

# YOLO/ByteTrack設定。YOLO_MODELは初回実行時に自動ダウンロードされます。
# 高速なnではなく、精度優先のmを使用します。
YOLO_MODEL = "yolo11m.pt"
YOLO_TRACKER = "bytetrack.yaml"
YOLO_IMAGE_SIZE = 1280
YOLO_CONFIDENCE = 0.20
YOLO_IOU = 0.50
YOLO_CLASSES = [0]  # COCOのperson
YOLO_BATCH_SIZE = 1

COCO_KEYPOINTS = [
    "鼻", "左目", "右目", "左耳", "右耳",
    "左肩", "右肩", "左肘", "右肘", "左手首", "右手首",
    "左股関節", "右股関節", "左膝", "右膝", "左足首", "右足首",
]

POSE_ENGINE = "rtmpose"
BACKEND = "onnxruntime"
DEVICE = "auto"
RTMLIB_POSE_MODEL = "x"
RTMLIB_POSE_INPUT_SIZE = "384x288"
RTMPOSE_BATCH_SIZE = 1
VITPOSE_MODEL = "h"
VITPOSE_INPUT_SIZE = "256x192"
VITPOSE_BATCH_SIZE = 4
VITPOSE_FLIP_TEST = True
VITPOSE_PRECISION = "fp16"

# 対象選定戦略（"long_jump" / "legacy"）
TARGET_SELECTION_STRATEGY = "long_jump"

# 出力モード（ENGINE_DEFAULTS には含めず内部制御用: "full" | "data_only" | "web_video"）
OUTPUT_MODE = "full"
VALID_OUTPUT_MODES = ("full", "data_only", "web_video")


def normalize_output_mode(value: object) -> str:
    """Normalize internal output mode option to full, data_only, or web_video."""
    mode = str(value or "full").strip().lower()
    if mode in VALID_OUTPUT_MODES:
        return mode
    return "full"

# 各種設定
CAPTURE_FPS = None
KEYPOINT_THRESHOLD = 0.45
SKELETON_LINE_WIDTH = 2
KEYPOINT_RADIUS = 4
LABEL_FONT_SCALE = 1.0
TRACK_MAX_MISSED_FRAMES = 8
TRACK_MATCH_THRESHOLD = 2.0
TRACK_VELOCITY_SMOOTHING = 0.35
TRACK_RAW_ID_BONUS = 2.0
TRACK_PREDICTED_BOX_WEIGHT = 0.35
TRACK_PREDICTION_MAX_FRAMES = 2
TARGET_SELECTION_MIN_FRAMES = 15
TARGET_SELECTION_COVERAGE_WEIGHT = 0.5
TARGET_BOX_FILL_MAX_FRAMES = 60


ENGINE_SETTING_NAMES = (
    "INPUT_ROOT", "INPUT_VIDEO_NAME",
    "OUTPUT_ROOT", "OUTPUT_FOLDER_NAME", "OUTPUT_VIDEO_NAME", "OUTPUT_CROP_VIDEO_NAME",
    "OUTPUT_CROP_SKELETON_VIDEO_NAME", "OUTPUT_CSV_NAME", "OUTPUT_METADATA_NAME",
    "OUTPUT_METADATA_JSON_NAME", "OUTPUT_NPZ_NAME",
    "YOLO_MODEL", "YOLO_TRACKER",
    "YOLO_IMAGE_SIZE", "YOLO_CONFIDENCE", "YOLO_IOU", "YOLO_CLASSES", "YOLO_BATCH_SIZE",
    "POSE_ENGINE", "BACKEND", "DEVICE", "RTMLIB_POSE_MODEL", "RTMLIB_POSE_INPUT_SIZE",
    "RTMPOSE_BATCH_SIZE", "VITPOSE_MODEL", "VITPOSE_INPUT_SIZE",
    "VITPOSE_BATCH_SIZE", "VITPOSE_FLIP_TEST", "VITPOSE_PRECISION",
    "CAPTURE_FPS", "KEYPOINT_THRESHOLD", "SKELETON_LINE_WIDTH", "KEYPOINT_RADIUS", "LABEL_FONT_SCALE",
    "TRACK_MAX_MISSED_FRAMES", "TRACK_MATCH_THRESHOLD",
    "TRACK_VELOCITY_SMOOTHING", "TRACK_RAW_ID_BONUS", "TRACK_PREDICTED_BOX_WEIGHT",
    "TRACK_PREDICTION_MAX_FRAMES", "TARGET_SELECTION_MIN_FRAMES",
    "TARGET_SELECTION_COVERAGE_WEIGHT", "TARGET_BOX_FILL_MAX_FRAMES",
)
ENGINE_DEFAULTS = {key: globals()[key] for key in ENGINE_SETTING_NAMES}
PATH_SETTING_KEYS = {"INPUT_ROOT", "OUTPUT_ROOT"}
OUTPUT_NAME_KEYS = {
    "OUTPUT_VIDEO_NAME",
    "OUTPUT_CROP_VIDEO_NAME",
    "OUTPUT_CROP_SKELETON_VIDEO_NAME",
    "OUTPUT_CSV_NAME",
    "OUTPUT_METADATA_NAME",
    "OUTPUT_METADATA_JSON_NAME",
    "OUTPUT_NPZ_NAME",
}

DEFAULTS = {
    "INPUT_VIDEO_FILE": str(INPUT_ROOT / INPUT_VIDEO_NAME),
    "OUTPUT_DIRECTORY": str(OUTPUT_ROOT / OUTPUT_FOLDER_NAME),
}
DEFAULTS.update({
    key: value for key, value in ENGINE_DEFAULTS.items()
    if key not in PATH_SETTING_KEYS and key not in OUTPUT_NAME_KEYS
})

GROUPS = [
    ("入力・出力", ["INPUT_VIDEO_FILE", "OUTPUT_DIRECTORY", "CAPTURE_FPS"]),
    ("YOLO・対象人物", ["YOLO_MODEL", "YOLO_TRACKER", "YOLO_IMAGE_SIZE", "YOLO_CONFIDENCE",
                    "YOLO_IOU", "YOLO_CLASSES", "YOLO_BATCH_SIZE",
                    "TARGET_SELECTION_MIN_FRAMES", "TARGET_SELECTION_COVERAGE_WEIGHT",
                    "TARGET_BOX_FILL_MAX_FRAMES"]),
    ("姿勢推定・追跡", ["POSE_ENGINE", "RTMLIB_POSE_MODEL", "RTMLIB_POSE_INPUT_SIZE",
                     "RTMPOSE_BATCH_SIZE", "VITPOSE_MODEL", "VITPOSE_INPUT_SIZE",
                     "VITPOSE_BATCH_SIZE", "VITPOSE_FLIP_TEST", "VITPOSE_PRECISION",
                     "BACKEND", "DEVICE",
                     "KEYPOINT_THRESHOLD", "SKELETON_LINE_WIDTH", "KEYPOINT_RADIUS", "LABEL_FONT_SCALE",
                     "TRACK_MAX_MISSED_FRAMES", "TRACK_MATCH_THRESHOLD",
                     "TRACK_VELOCITY_SMOOTHING", "TRACK_RAW_ID_BONUS",
                     "TRACK_PREDICTED_BOX_WEIGHT", "TRACK_PREDICTION_MAX_FRAMES"]),
]
PATH_KEYS = {"OUTPUT_DIRECTORY"}
FILE_KEYS = {"INPUT_VIDEO_FILE"}
BOOL_KEYS = {key for key, value in DEFAULTS.items() if isinstance(value, bool)}
INT_KEYS = {key for key, value in DEFAULTS.items() if isinstance(value, int) and not isinstance(value, bool)}
FLOAT_KEYS = {key for key, value in DEFAULTS.items() if isinstance(value, float)}
NULLABLE_FLOAT_KEYS = {"CAPTURE_FPS"}
LABELS = {
    "INPUT_VIDEO_FILE": "入力動画",
    "OUTPUT_DIRECTORY": "出力先フォルダ",
    "CAPTURE_FPS": "撮影FPS（実時間基準・空欄で自動）",
    "YOLO_MODEL": "YOLOモデルサイズ",
    "YOLO_BATCH_SIZE": "YOLOバッチサイズ",
    "POSE_ENGINE": "姿勢推定エンジン",
    "RTMLIB_POSE_MODEL": "RTMPoseモデル",
    "RTMLIB_POSE_INPUT_SIZE": "RTMPose入力解像度",
    "RTMPOSE_BATCH_SIZE": "RTMPoseバッチサイズ",
    "VITPOSE_MODEL": "ViTPose++モデルサイズ",
    "VITPOSE_INPUT_SIZE": "ViTPose++入力解像度",
    "VITPOSE_BATCH_SIZE": "ViTPose++バッチサイズ",
    "VITPOSE_FLIP_TEST": "Flip Test（左右反転TTA）",
    "VITPOSE_PRECISION": "ViTPose++推論精度",
    "DEVICE": "実行デバイス（YOLO・姿勢推定）",
    "SKELETON_LINE_WIDTH": "骨格線の太さ",
    "KEYPOINT_RADIUS": "キーポイント円の半径",
    "LABEL_FONT_SCALE": "ラベル文字サイズ",
}
CHOICES = {
    "YOLO_MODEL": ("n", "s", "m", "l", "x"),
    "POSE_ENGINE": ("rtmpose", "vitpose"),
    "RTMLIB_POSE_MODEL": ("t", "s", "m", "l", "x"),
    "RTMLIB_POSE_INPUT_SIZE": ("256x192", "384x288"),
    "VITPOSE_MODEL": ("s", "b", "l", "h"),
    "VITPOSE_INPUT_SIZE": ("256x192",),
    "VITPOSE_PRECISION": ("fp16", "fp32"),
    "DEVICE": ("auto", "cpu", "cuda"),
}

_LEGACY_MODE_POSE = {
    "performance": ("x", "384x288"),
    "balanced": ("m", "256x192"),
    "lightweight": ("s", "256x192"),
}
_REMOVED_RTMLIB_SETTING_KEYS = (
    "MODEL_MODE",
    "RTMLIB_PERSON_DETECTOR",
    "RTMLIB_DETECTOR_SCORE_THRESHOLD",
    "RTMLIB_DETECTOR_NMS_THRESHOLD",
    "OUTPUT_YOLO_VIDEO_NAME",
    "THUMBNAIL_ROOT",
    "THUMBNAIL_IMAGE_NAME",
    "YOLO_TRACK_ID",
    "CROP_PADDING_RATIO",
    "TARGET_REACQUIRE_MAX_DISTANCE",
    "TARGET_REACQUIRE_MIN_IOU",
    "TRACK_MAX_DISTANCE",
    "CSV_MAX_PERSONS",
    "TRACK_CENTER_WEIGHT",
    "TRACK_KEYPOINT_WEIGHT",
    "TRACK_POSE_WEIGHT",
    "TRACK_BBOX_WEIGHT",
    "TARGET_TRACK_MATCH_THRESHOLD",
    "TARGET_TRACK_MIN_IOU",
    "TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING",
    "TARGET_LOCK_RAW_ID",
    "POSE_TRACK_KEYPOINT_WEIGHT",
    "POSE_TRACK_CENTER_WEIGHT",
    "POSE_TRACK_SHAPE_WEIGHT",
    "POSE_BOX_IOU_WEIGHT",
    "POSE_BOX_CENTER_WEIGHT",
    "POSE_TEMPORAL_WEIGHT",
)


def normalize_legacy_rtmlib_settings(settings: dict) -> dict:
    """Convert legacy MODEL_MODE / 'mode' / unused detector keys into explicit pose settings."""
    out = dict(settings)
    if "POSE_ENGINE" in out:
        out["POSE_ENGINE"] = normalize_pose_engine(out.get("POSE_ENGINE"))
    else:
        out["POSE_ENGINE"] = "rtmpose"

    legacy_mode = str(out.get("MODEL_MODE") or "performance")
    mode_pose, mode_resolution = _LEGACY_MODE_POSE.get(legacy_mode, ("x", "384x288"))

    raw_pose = out.get("RTMLIB_POSE_MODEL")
    if raw_pose == "mode" or ("MODEL_MODE" in out and raw_pose in (None, "")):
        out["RTMLIB_POSE_MODEL"] = mode_pose

    raw_res = out.get("RTMLIB_POSE_INPUT_SIZE")
    if raw_res == "mode" or ("MODEL_MODE" in out and raw_res in (None, "")):
        resolved_pose = str(out.get("RTMLIB_POSE_MODEL") or mode_pose)
        supported = RTMLIB_POSE_ASSETS.get(resolved_pose)
        if supported:
            out["RTMLIB_POSE_INPUT_SIZE"] = (
                mode_resolution if mode_resolution in supported else next(iter(supported))
            )
        else:
            out["RTMLIB_POSE_INPUT_SIZE"] = mode_resolution

    for legacy_key in _REMOVED_RTMLIB_SETTING_KEYS:
        out.pop(legacy_key, None)

    folder_name = str(out.get("OUTPUT_FOLDER_NAME") or "").strip()
    if folder_name:
        out.setdefault("OUTPUT_CROP_VIDEO_NAME", f"{folder_name}-crop.mp4")
        out.setdefault("OUTPUT_CROP_SKELETON_VIDEO_NAME", f"{folder_name}-crop-skeleton.mp4")
        out.setdefault("OUTPUT_METADATA_JSON_NAME", f"{folder_name}_metadata.json")
        out.setdefault("OUTPUT_NPZ_NAME", f"{folder_name}.npz")
    if "VITPOSE_PRECISION" in out:
        prec = str(out.get("VITPOSE_PRECISION") or "fp16").strip().lower()
        out["VITPOSE_PRECISION"] = prec if prec in ("fp16", "fp32") else "fp16"
    return out


def build_job_summary(settings: dict) -> dict:
    """Build UI summary fields for a serialized reservation job."""
    raw_capture_fps = settings.get("CAPTURE_FPS")
    capture_fps = None
    if raw_capture_fps not in (None, "", "None", "null", "auto"):
        try:
            parsed_fps = float(raw_capture_fps)
            if math.isfinite(parsed_fps) and parsed_fps > 0:
                capture_fps = parsed_fps
        except (ValueError, TypeError):
            capture_fps = None
    return {
        "pose_engine": normalize_pose_engine(settings.get("POSE_ENGINE", "rtmpose")),
        "pose_model": settings.get("RTMLIB_POSE_MODEL", "x"),
        "pose_input_size": settings.get("RTMLIB_POSE_INPUT_SIZE", "384x288"),
        "vitpose_model": str(settings.get("VITPOSE_MODEL", "h")).lower(),
        "vitpose_input_size": str(settings.get("VITPOSE_INPUT_SIZE", "256x192")),
        "vitpose_flip_test": bool(settings.get("VITPOSE_FLIP_TEST", True)),
        "vitpose_precision": str(settings.get("VITPOSE_PRECISION", "fp16")).lower(),
        "capture_fps": capture_fps,
        "yolo_model": settings.get("YOLO_MODEL", "yolo11m.pt"),
        "device": settings.get("DEVICE", "auto"),
    }


def output_names(output_directory: Path) -> dict[str, str]:
    """選択された出力フォルダ名から出力ファイル名を作ります。"""
    name = output_directory.name
    if not name:
        raise ValueError("出力先フォルダを指定してください。")
    return {
        "OUTPUT_VIDEO_NAME": f"{name}.mp4",
        "OUTPUT_CROP_VIDEO_NAME": f"{name}-crop.mp4",
        "OUTPUT_CROP_SKELETON_VIDEO_NAME": f"{name}-crop-skeleton.mp4",
        "OUTPUT_CSV_NAME": f"{name}.csv",
        "OUTPUT_METADATA_NAME": f"{name}_metadata.txt",
        "OUTPUT_METADATA_JSON_NAME": f"{name}_metadata.json",
        "OUTPUT_NPZ_NAME": f"{name}.npz",
    }


def find_input_video() -> Path:
    direct_match = INPUT_ROOT / INPUT_VIDEO_NAME
    if direct_match.is_file():
        return direct_match
    matches = sorted(
        path
        for path in INPUT_ROOT.rglob(INPUT_VIDEO_NAME)
        if path.is_file()
    )
    if not matches:
        raise FileNotFoundError(
            f"Input video was not found under {INPUT_ROOT.resolve()}: "
            f"{INPUT_VIDEO_NAME}"
        )
    if len(matches) > 1:
        print(
            f"Multiple input videos found. Using: {matches[0].resolve()}",
            flush=True,
        )
    return matches[0]


def probe_capture_fps(input_video: Path) -> tuple[float | None, str | None]:
    """Probe camera capture FPS metadata tags (exiftool/ffprobe) when container FPS differs from real speed."""
    tag_candidates = (
        "CaptureFPS",
        "RecordFrameRate",
        "CameraFrameRate",
        "com.apple.quicktime.camera.frame_rate",
    )
    for tag in tag_candidates:
        try:
            res = subprocess.run(
                ["exiftool", "-s3", "-n", f"-{tag}", str(input_video)],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in res.stdout.splitlines():
                raw = line.strip()
                if not raw:
                    continue
                try:
                    val = float(raw)
                    if math.isfinite(val) and val > 0.0:
                        return val, f"exiftool:{tag}"
                except ValueError:
                    continue
        except FileNotFoundError:
            break

    try:
        res = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format_tags:stream_tags",
                "-of",
                "default=noprint_wrappers=1",
                str(input_video),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in res.stdout.splitlines():
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k_lower = k.strip().lower()
            if any(
                token in k_lower
                for token in (
                    "camera.frame_rate",
                    "capturefps",
                    "capture_fps",
                    "recordframerate",
                    "record_frame_rate",
                )
            ):
                try:
                    val = float(v.strip())
                    if math.isfinite(val) and val > 0.0:
                        return val, f"ffprobe:{k.strip()}"
                except ValueError:
                    continue
    except FileNotFoundError:
        pass
    return None, None


def resolve_capture_fps(
    input_video: Path,
    playback_fps: float,
    manual_capture_fps: float | None = None,
) -> tuple[float, str]:
    """Resolve real capture FPS using manual override > camera metadata > playback fallback."""
    if manual_capture_fps is not None:
        try:
            manual_val = float(manual_capture_fps)
            if math.isfinite(manual_val) and manual_val > 0.0:
                return manual_val, "manual"
        except (TypeError, ValueError):
            pass

    probed_fps, _tag_name = probe_capture_fps(input_video)
    if probed_fps is not None and probed_fps > 0.0:
        return probed_fps, "metadata"

    fallback = float(playback_fps) if (playback_fps and playback_fps > 0.0) else 30.0
    return fallback, "container_fallback"


def write_video_metadata(
    input_video: Path,
    output_path: Path,
    total_frames: int,
    width: int,
    height: int,
    fps: float,
    *,
    metadata_total_frames: int | None = None,
    playback_fps: float | None = None,
    capture_fps: float | None = None,
    capture_fps_source: str = "container_fallback",
    is_vfr: bool | None = None,
    yolo_model: str | None = None,
    pose_engine_label: str | None = None,
    target_stable_id: int | None = None,
) -> None:
    eff_playback_fps = float(playback_fps if playback_fps is not None else fps)
    eff_capture_fps = float(capture_fps if capture_fps is not None else eff_playback_fps)
    duration_seconds = total_frames / eff_capture_fps if eff_capture_fps > 0 else 0.0
    container_frames = total_frames if metadata_total_frames is None else metadata_total_frames
    source_labels = {
        "manual": "手動指定 (CAPTURE_FPS)",
        "metadata": "カメラメタデータ自動取得",
        "container_fallback": "コンテナ再生FPSフォールバック",
    }
    vfr_text = "はい (VFR警告)" if is_vfr else ("いいえ (CFR)" if is_vfr is not None else "未計測")

    lines = [
        "元動画情報",
        "====================",
        f"元動画: {input_video.resolve()}",
        f"動画名: {input_video.name}",
        f"確定実フレーム数: {total_frames}",
        f"コンテナ情報フレーム数: {container_frames}",
        f"解像度（横 x 縦）: {width} x {height}",
        f"実撮影FPS（時間計算基準）: {eff_capture_fps:.6f} ({source_labels.get(capture_fps_source, capture_fps_source)})",
        f"コンテナ再生FPS: {eff_playback_fps:.6f}",
        f"VFR検知: {vfr_text}",
        f"実時間（秒）: {duration_seconds:.3f}",
    ]
    if yolo_model:
        lines.append(f"人物検出AI (YOLO): {yolo_model}")
    if pose_engine_label:
        lines.append(f"骨格推定AI: {pose_engine_label}")
    if target_stable_id is not None:
        lines.append(f"解析対象トラッキングID: {target_stable_id}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def box_center(box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


MAX_BATCH_SIZE = 512


def clamp_batch_size(value, minimum: int = 1, maximum: int = MAX_BATCH_SIZE) -> int:
    """Coerce a batch size setting to an integer within [minimum, maximum]."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(maximum, parsed))


def resolve_effective_batch_size(requested, device: str, stage_name: str) -> int:
    """Resolve effective batch size, forcing 1 when running on CPU."""
    batch_size = clamp_batch_size(requested)
    if not str(device or "").lower().startswith("cuda"):
        if batch_size > 1:
            print(
                f"{stage_name}: CPU実行のためバッチサイズを 1 に固定します（設定値: {batch_size}）",
                flush=True,
            )
        return 1
    return batch_size


def is_cuda_oom_error(exc: BaseException) -> bool:
    """Return True if an exception indicates a CUDA / GPU memory allocation failure."""
    if type(exc).__name__ == "OutOfMemoryError":
        return True
    message = str(exc).lower()
    oom_markers = (
        "out of memory",
        "cudaerrormemoryallocation",
        "bfcarena",
        "failed to allocate memory",
        "memory allocation failed with oom",
        "cublas_status_alloc_failed",
        "cudnn_status_alloc_failed",
    )
    return any(marker in message for marker in oom_markers)


def _clear_cuda_cache() -> None:
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _cuda_device_index(device: str) -> int | None:
    text = str(device or "").strip().lower()
    if text == "cuda":
        return 0
    if text.startswith("cuda:") and text[5:].isdigit():
        return int(text[5:])
    return None


def _get_cuda_free_total_gb(device: str) -> tuple[float, float] | None:
    idx = _cuda_device_index(device)
    if idx is None:
        return None
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        free_b, total_b = torch.cuda.mem_get_info(idx)
        return free_b / (1024**3), total_b / (1024**3)
    except Exception:
        return None


def configure_cuda_memory_fraction(device: str) -> float | None:
    """Cap PyTorch CUDA allocations to physical free VRAM so Windows WDDM fails fast instead of swapping."""
    idx = _cuda_device_index(device)
    if idx is None:
        return None
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        free_b, total_b = torch.cuda.mem_get_info(idx)
        reserved_b = torch.cuda.memory_reserved(idx)
        if total_b <= 0:
            return None
        budget_b = reserved_b + free_b * 0.90
        frac = min(0.95, max(0.25, budget_b / total_b))
        torch.cuda.set_per_process_memory_fraction(frac, idx)
        return frac
    except Exception:
        return None


def _yolo_model_vram_factor(model_name: str) -> float:
    stem = Path(str(model_name)).stem.lower()
    for suffix, factor in (("n", 0.45), ("s", 0.65), ("m", 1.0), ("l", 1.25), ("x", 1.55)):
        if stem.endswith(suffix):
            return factor
    return 1.0


def cap_yolo_batch_by_vram(
    requested: int,
    device: str,
    model_name: str,
    imgsz: int,
) -> int:
    """Cap YOLO batch size conservatively from remaining free VRAM to prevent WDDM swap hangs."""
    if requested <= 1:
        return requested
    mem_info = _get_cuda_free_total_gb(device)
    if mem_info is None:
        return requested
    free_gb, _ = mem_info
    usable_gb = max(0.4, free_gb * 0.85 - 0.4)
    model_factor = _yolo_model_vram_factor(model_name)
    pixel_factor = (max(int(imgsz), 320) / 640.0) ** 2
    est_gb_per_frame = 0.070 * model_factor * pixel_factor
    max_safe = max(1, int(usable_gb / max(est_gb_per_frame, 1e-4)))
    if requested > max_safe:
        print(
            f"YOLO: 利用可能VRAM ({free_gb:.1f} GB) に合わせてバッチサイズを "
            f"{requested} -> {max_safe} に自動調整しました",
            flush=True,
        )
        return max_safe
    return requested


def _get_available_system_ram_bytes() -> int | None:
    """Return currently available system RAM in bytes if determinable."""
    try:
        psutil_mod = importlib.import_module("psutil")
        avail = int(psutil_mod.virtual_memory().available)
        if avail > 0:
            return avail
    except Exception:
        pass

    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.is_file():
            for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("MemAvailable:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) * 1024
    except Exception:
        pass

    if os.name == "nt":
        try:
            import ctypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_uint32),
                    ("dwMemoryLoad", ctypes.c_uint32),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except Exception:
            pass
    return None


def _cap_max_buffered_by_ram(
    default_max_buffered: int,
    effective_pose_batch: int,
    width: int,
    height: int,
    avail_bytes: int | None = None,
) -> int:
    """Cap full-frame RAM buffer count safely under low-RAM runtimes (e.g., Colab 12.7 GB)."""
    default_cap = max(1, int(default_max_buffered))
    if avail_bytes is None:
        avail_bytes = _get_available_system_ram_bytes()
    if avail_bytes is None or avail_bytes <= 0:
        return default_cap

    frame_bytes = max(1, int(width) * int(height) * 3)
    budget_bytes = int(avail_bytes * 0.35)
    min_floor = max(1, min(int(effective_pose_batch), 8))
    ram_safe_frames = max(min_floor, budget_bytes // frame_bytes)
    return min(default_cap, ram_safe_frames)


def _compute_overlay_params(
    width: int,
    height: int,
    crop_w: int,
    crop_h: int,
    settings: dict | None = None,
) -> dict:
    """Compute consistent full-frame and crop overlay styling parameters."""
    import numpy as np

    cfg = settings if isinstance(settings, dict) else globals()
    kpt_thr = float(cfg.get("KEYPOINT_THRESHOLD", globals().get("KEYPOINT_THRESHOLD", 0.45)))
    label_font_scale = max(0.3, float(cfg.get("LABEL_FONT_SCALE", globals().get("LABEL_FONT_SCALE", 1.0))))
    label_thickness = max(1, int(round(2.0 * label_font_scale)))
    skel_line_w = max(1, int(cfg.get("SKELETON_LINE_WIDTH", globals().get("SKELETON_LINE_WIDTH", 2))))
    kpt_rad = max(1, int(cfg.get("KEYPOINT_RADIUS", globals().get("KEYPOINT_RADIUS", 4))))
    crop_scale_ratio = max(
        0.4,
        min(1.0, (max(crop_w, crop_h) / max(min(width, height), 1)) * 1.5),
    )
    crop_line_w = max(1, int(round(skel_line_w * crop_scale_ratio)))
    crop_kpt_rad = max(1, int(round(kpt_rad * crop_scale_ratio)))
    crop_udp_span = np.array([max(crop_w - 1, 1), max(crop_h - 1, 1)], dtype=np.float32)
    return {
        "kpt_thr": kpt_thr,
        "label_font_scale": label_font_scale,
        "label_thickness": label_thickness,
        "skel_line_w": skel_line_w,
        "kpt_rad": kpt_rad,
        "crop_line_w": crop_line_w,
        "crop_kpt_rad": crop_kpt_rad,
        "crop_udp_span": crop_udp_span,
    }


def _draw_frame_index_label(frame, idx: int, label_font_scale: float, label_thickness: int) -> None:
    """Draw 1-based frame index text onto frame in-place."""
    cv2.putText(
        frame,
        f"Frame: {idx + 1}",
        (40, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        label_font_scale,
        (0, 0, 255),
        label_thickness,
        cv2.LINE_AA,
    )


def annotate_pose_on_frame(
    frame,
    target_box,
    restored_keypoints,
    pose_scores,
    *,
    keypoint_threshold: float | None = None,
    skeleton_line_width: int | None = None,
    keypoint_radius: int | None = None,
) -> None:
    """Draw skeleton directly onto frame in-place without sub-region cropping."""
    import numpy as np

    if restored_keypoints is None or pose_scores is None:
        return
    kpt_thr = (
        float(keypoint_threshold)
        if keypoint_threshold is not None
        else float(globals().get("KEYPOINT_THRESHOLD", 0.45))
    )
    line_w = (
        int(skeleton_line_width)
        if skeleton_line_width is not None
        else int(globals().get("SKELETON_LINE_WIDTH", 2))
    )
    kpt_rad = (
        int(keypoint_radius)
        if keypoint_radius is not None
        else int(globals().get("KEYPOINT_RADIUS", 4))
    )
    kpts_arr = np.asarray([restored_keypoints], dtype=np.float32)
    scores_arr = np.asarray([pose_scores], dtype=np.float32)
    annotated = draw_pose_skeleton(
        frame,
        kpts_arr,
        scores_arr,
        kpt_thr=kpt_thr,
        skeleton_line_width=line_w,
        keypoint_radius=kpt_rad,
    )
    if annotated is not None and annotated is not frame:
        np.copyto(frame, annotated)


def bbox_iou(first, second) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def get_csv_fieldnames() -> list[str]:
    fieldnames = ["frame", "time_seconds", "person_0_id"]
    for name in COCO_KEYPOINTS:
        fieldnames.extend([
            f"person_0_{name}_x",
            f"person_0_{name}_y",
            f"person_0_{name}_score",
        ])
    return fieldnames


def make_csv_row(frame_data: dict) -> dict:
    row = {
        "frame": frame_data["frame"],
        "time_seconds": frame_data["time_seconds"],
    }
    persons = frame_data.get("persons") or []
    person = persons[0] if persons else None
    row["person_0_id"] = "" if person is None else person["person_id"]
    for name in COCO_KEYPOINTS:
        keypoint = None if person is None else person[name]
        row[f"person_0_{name}_x"] = "" if keypoint is None else keypoint["x"]
        row[f"person_0_{name}_y"] = "" if keypoint is None else keypoint["y"]
        row[f"person_0_{name}_score"] = "" if keypoint is None else keypoint["score"]
    return row


def predict_track_box(track: dict) -> tuple[float, float, float, float]:
    elapsed = min(
        track["missed_frames"] + 1,
        TRACK_PREDICTION_MAX_FRAMES,
    )
    dx = track["velocity"][0] * elapsed
    dy = track["velocity"][1] * elapsed
    return (
        track["bbox"][0] + dx,
        track["bbox"][1] + dy,
        track["bbox"][2] + dx,
        track["bbox"][3] + dy,
    )


def yolo_box_cost(
    track: dict,
    box: tuple[float, float, float, float],
    raw_track_id: int | None,
) -> float:
    predicted_box = predict_track_box(track)
    elapsed = min(
        track["missed_frames"] + 1,
        TRACK_PREDICTION_MAX_FRAMES,
    )
    predicted_center = (
        track["center"][0] + track["velocity"][0] * elapsed,
        track["center"][1] + track["velocity"][1] * elapsed,
    )
    center_distance = math.dist(predicted_center, box_center(box))
    scale = max(
        math.hypot(
            track["bbox"][2] - track["bbox"][0],
            track["bbox"][3] - track["bbox"][1],
        ),
        1.0,
    )
    return (
        center_distance / scale
        + TRACK_PREDICTED_BOX_WEIGHT * (1.0 - bbox_iou(predicted_box, box))
        - (
            TRACK_RAW_ID_BONUS
            if raw_track_id is not None and raw_track_id == track["raw_track_id"]
            else 0.0
        )
    )


def stabilize_yolo_ids(
    boxes,
    tracks: dict,
    next_id: int,
):
    detections = [
        {
            "bbox": tuple(float(value) for value in box.xyxy[0].tolist()),
            "raw_track_id": None if box.id is None else int(box.id[0].item()),
        }
        for box in boxes
    ]

    matches = []
    for detection_index, detection in enumerate(detections):
        for stable_id, track in tracks.items():
            if track["missed_frames"] <= TRACK_MAX_MISSED_FRAMES:
                cost = yolo_box_cost(
                    track,
                    detection["bbox"],
                    detection["raw_track_id"],
                )
                if (
                    cost <= TRACK_MATCH_THRESHOLD
                    or (
                        detection["raw_track_id"] is not None
                        and detection["raw_track_id"] == track["raw_track_id"]
                    )
                ):
                    matches.append((cost, detection_index, stable_id))

    assigned_detections = set()
    assigned_ids = set()
    stable_ids = [None] * len(detections)
    for _, detection_index, stable_id in sorted(matches):
        if detection_index in assigned_detections or stable_id in assigned_ids:
            continue
        stable_ids[detection_index] = stable_id
        assigned_detections.add(detection_index)
        assigned_ids.add(stable_id)

    for detection_index, detection in enumerate(detections):
        stable_id = stable_ids[detection_index]
        if stable_id is None:
            stable_id = next_id
            next_id += 1
        detection_box = detection["bbox"]
        center = box_center(detection_box)
        previous = tracks.get(stable_id)
        if previous is None:
            velocity = (0.0, 0.0)
        else:
            prev_missed = previous["missed_frames"]
            dt = prev_missed + 1
            if prev_missed == 0:
                measured = (
                    (center[0] - previous["center"][0]) / dt,
                    (center[1] - previous["center"][1]) / dt,
                )
                velocity = (
                    TRACK_VELOCITY_SMOOTHING * previous["velocity"][0]
                    + (1.0 - TRACK_VELOCITY_SMOOTHING) * measured[0],
                    TRACK_VELOCITY_SMOOTHING * previous["velocity"][1]
                    + (1.0 - TRACK_VELOCITY_SMOOTHING) * measured[1],
                )
            else:
                # Preserve velocity direction/magnitude across brief detection gaps (Option A).
                velocity = previous["velocity"]
        tracks[stable_id] = {
            "center": center,
            "bbox": detection_box,
            "raw_track_id": detection["raw_track_id"],
            "velocity": velocity,
            "missed_frames": 0,
        }
        assigned_ids.add(stable_id)
        stable_ids[detection_index] = stable_id

    for stable_id in list(tracks.keys()):
        if stable_id not in assigned_ids:
            tracks[stable_id]["missed_frames"] += 1
            if tracks[stable_id]["missed_frames"] > TRACK_MAX_MISSED_FRAMES:
                del tracks[stable_id]

    return [
        {
            "stable_id": stable_id,
            "bbox": detection["bbox"],
            "raw_track_id": detection["raw_track_id"],
        }
        for stable_id, detection in zip(stable_ids, detections)
    ], next_id


def _select_moving_target_id_legacy(frame_detections, total_frames):
    trajectories = {}
    for frame_index, detections in enumerate(frame_detections):
        for detection in detections:
            stable_id = detection["stable_id"]
            trajectories.setdefault(stable_id, []).append(
                (frame_index, box_center(detection["bbox"]))
            )

    candidates = []
    for stable_id, observations in trajectories.items():
        if len(observations) < TARGET_SELECTION_MIN_FRAMES:
            continue
        path_length = sum(
            math.dist(previous[1], current[1])
            for previous, current in zip(observations, observations[1:])
        )
        net_displacement = math.dist(observations[0][1], observations[-1][1])
        coverage = len(observations) / max(total_frames, 1)
        movement_score = (
            path_length * (1.0 - TARGET_SELECTION_COVERAGE_WEIGHT)
            + net_displacement * TARGET_SELECTION_COVERAGE_WEIGHT
        ) * (0.5 + 0.5 * coverage)
        candidates.append((movement_score, coverage, path_length, stable_id))

    if not candidates:
        return max(
            trajectories,
            key=lambda stable_id: len(trajectories[stable_id]),
            default=None,
        )
    return max(candidates)[3]


def _select_moving_target_id_long_jump(frame_detections, total_frames):
    """Select long-jump athlete using height-normalized speed, directional run, and foreground scale."""
    trajectories: dict = {}
    for frame_index, detections in enumerate(frame_detections):
        for detection in detections:
            stable_id = detection["stable_id"]
            bbox = detection["bbox"]
            cx, cy = box_center(bbox)
            bh = max(1.0, float(bbox[3]) - float(bbox[1]))
            trajectories.setdefault(stable_id, []).append((frame_index, cx, cy, bh))

    eligible: list[dict] = []
    max_median_h = 1.0
    for stable_id, obs in trajectories.items():
        if len(obs) < TARGET_SELECTION_MIN_FRAMES:
            continue
        heights = sorted(item[3] for item in obs)
        median_h = heights[len(heights) // 2]
        max_median_h = max(max_median_h, median_h)

        # Sliding-window horizontal & 2D approach speeds normalized by median person height
        win_speeds: list[float] = []
        win_dx_sum = 0.0
        win = min(5, max(1, len(obs) - 1))
        for i in range(len(obs) - win):
            dt = max(1, obs[i + win][0] - obs[i][0])
            dx = obs[i + win][1] - obs[i][1]
            dy = obs[i + win][2] - obs[i][2]
            win_speeds.append((math.hypot(dx, dy) / dt) / median_h)

        abs_dx_total = sum(abs(b[1] - a[1]) for a, b in zip(obs, obs[1:]))
        path_length = sum(
            math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(obs, obs[1:])
        )
        net_dx = abs(obs[-1][1] - obs[0][1])
        net_disp = math.hypot(obs[-1][1] - obs[0][1], obs[-1][2] - obs[0][2])

        if win_speeds:
            sorted_speeds = sorted(win_speeds)
            p85_idx = min(len(sorted_speeds) - 1, int(len(sorted_speeds) * 0.85))
            burst_speed_norm = sorted_speeds[p85_idx]
        else:
            burst_speed_norm = 0.0

        # Suppress stationary jitter & tiny oscillatory motions by measuring unidirectional progress
        directional_purity = net_dx / max(abs_dx_total, median_h * 0.5, 1.0)
        net_disp_norm = net_disp / median_h
        coverage = len(obs) / max(total_frames, 1)
        win_dx_sum = path_length / median_h

        eligible.append({
            "stable_id": stable_id,
            "median_h": median_h,
            "burst_speed_norm": burst_speed_norm,
            "directional_purity": directional_purity,
            "net_disp_norm": net_disp_norm,
            "path_norm": win_dx_sum,
            "coverage": coverage,
        })

    if not eligible:
        return max(
            trajectories,
            key=lambda stable_id: len(trajectories[stable_id]),
            default=None,
        )

    candidates = []
    cov_w = float(globals().get("TARGET_SELECTION_COVERAGE_WEIGHT", 0.5))
    for item in eligible:
        size_weight = 0.5 + 0.5 * (item["median_h"] / max_median_h)
        motion_core = (
            item["path_norm"] * (1.0 - cov_w)
            + item["net_disp_norm"] * cov_w
        )
        directional_factor = 0.35 + 0.65 * min(1.0, item["directional_purity"])
        speed_factor = 1.0 + min(4.0, item["burst_speed_norm"] * 12.0)
        coverage_factor = 0.5 + 0.5 * item["coverage"]
        score = (
            motion_core
            * directional_factor
            * speed_factor
            * size_weight
            * coverage_factor
        )
        candidates.append((score, item["coverage"], item["net_disp_norm"], item["stable_id"]))
    return max(candidates)[3]


def select_moving_target_id(frame_detections, total_frames):
    strategy = str(globals().get("TARGET_SELECTION_STRATEGY", "long_jump")).strip().lower()
    if strategy == "legacy":
        return _select_moving_target_id_legacy(frame_detections, total_frames)
    return _select_moving_target_id_long_jump(frame_detections, total_frames)


def fill_target_box_gaps(frame_detections, target_stable_id):
    target_boxes = [
        next(
            (
                detection["bbox"]
                for detection in detections
                if detection["stable_id"] == target_stable_id
            ),
            None,
        )
        for detections in frame_detections
    ]
    observed = [
        index for index, target_box in enumerate(target_boxes)
        if target_box is not None
    ]
    if not observed:
        return target_boxes

    for left_index, right_index in zip(observed, observed[1:]):
        gap = right_index - left_index - 1
        if gap <= 0 or gap > TARGET_BOX_FILL_MAX_FRAMES:
            continue
        left_box = target_boxes[left_index]
        right_box = target_boxes[right_index]
        for index in range(left_index + 1, right_index):
            ratio = (index - left_index) / (right_index - left_index)
            target_boxes[index] = tuple(
                left_value + (right_value - left_value) * ratio
                for left_value, right_value in zip(left_box, right_box)
            )
    return target_boxes


def compute_target_box_states(
    frame_detections: list,
    target_boxes: list,
    target_stable_id: int | None,
) -> list[int]:
    """Classify each frame box as 0 (none), 1 (YOLO observed), or 2 (interpolated)."""
    states: list[int] = []
    for idx, target_box in enumerate(target_boxes):
        if target_box is None:
            states.append(0)
            continue
        if target_stable_id is not None and idx < len(frame_detections):
            observed_here = any(
                d.get("stable_id") == target_stable_id for d in frame_detections[idx]
            )
            states.append(1 if observed_here else 2)
        else:
            states.append(1)
    return states


def _is_torch_cuda_available(torch_mod) -> bool:
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module=r"torch\.cuda")
        return bool(torch_mod.cuda.is_available())


def prepare_runtime(
    backend: str,
    device: str,
    pose_engine: str = "rtmpose",
) -> tuple[str, str]:
    """両方の推論エンジンで使えるデバイスを選び、CUDA DLLを読み込みます。"""
    import torch

    engine = normalize_pose_engine(pose_engine)
    device = device.strip().lower()
    if device not in {"auto", "cpu", "cuda"} and not (
        device.startswith("cuda:") and device[5:].isdigit()
    ):
        raise ValueError("DEVICE は auto / cpu / cuda / cuda:番号 を指定してください。")
    if device == "cpu":
        print("実行デバイス: CPU", flush=True)
        return "cpu", "cpu"

    reason = None
    if engine == "rtmpose" and backend != "onnxruntime":
        reason = "GPU実行には BACKEND=onnxruntime を指定してください。"
    elif not _is_torch_cuda_available(torch):
        reason = "PyTorchでCUDAを利用できません。GPU版PyTorchとNVIDIAドライバーを確認してください。"
    elif engine == "rtmpose":
        import onnxruntime as ort

        # PyTorchと同じCUDA/cuDNN DLLを使います（特にWindowsで必要）。
        configure_onnxruntime_environment(ort, preload_cuda=True)
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            reason = "ONNX RuntimeでCUDAを利用できません。onnxruntime-gpuを導入してください。"
    if reason is not None:
        if device != "auto":
            raise RuntimeError(reason)
        print(f"実行デバイス: CPU（{reason}）", flush=True)
        return "cpu", "cpu"

    index = int(device.split(":")[1]) if ":" in device else 0
    if index >= torch.cuda.device_count():
        raise ValueError(f"GPU番号 {index} は存在しません。")
    print(f"実行デバイス: CUDA:{index} ({torch.cuda.get_device_name(index)})", flush=True)
    return f"cuda:{index}", f"cuda:{index}"


def _active_pose_settings_from_globals() -> dict:
    return {
        "POSE_ENGINE": globals().get("POSE_ENGINE", "rtmpose"),
        "BACKEND": globals().get("BACKEND", "onnxruntime"),
        "RTMLIB_POSE_MODEL": globals().get("RTMLIB_POSE_MODEL", "x"),
        "RTMLIB_POSE_INPUT_SIZE": globals().get("RTMLIB_POSE_INPUT_SIZE", "384x288"),
        "VITPOSE_MODEL": globals().get("VITPOSE_MODEL", "h"),
        "VITPOSE_INPUT_SIZE": globals().get("VITPOSE_INPUT_SIZE", "256x192"),
        "VITPOSE_FLIP_TEST": globals().get("VITPOSE_FLIP_TEST", True),
        "VITPOSE_PRECISION": globals().get("VITPOSE_PRECISION", "fp16"),
    }


def create_pose_estimator_from_globals(device: str) -> BasePoseEstimator:
    """Build the configured BasePoseEstimator (RTMPose or ViTPose++) for Pass 2."""
    settings = _active_pose_settings_from_globals()
    estimator = _factory_create_pose_estimator(settings, device)
    print(f"姿勢モデル: {estimator.display_name}", flush=True)
    return estimator


MPEG4_MAX_TIMEBASE_DENOMINATOR = 65535


def sanitize_mp4v_fps(fps: float) -> float:
    """Return an FPS whose 1000-based rational fits MPEG-4's 65535 denominator limit."""
    if not math.isfinite(fps) or fps <= 0:
        return 30.0
    if fps > MPEG4_MAX_TIMEBASE_DENOMINATOR:
        return float(MPEG4_MAX_TIMEBASE_DENOMINATOR)

    target_milli = fps * 1000.0
    base_milli = round(target_milli)
    if base_milli <= 0:
        return fps

    def _is_valid(milli: int) -> bool:
        return milli > 0 and (milli // math.gcd(1000, milli)) <= MPEG4_MAX_TIMEBASE_DENOMINATOR

    if _is_valid(base_milli):
        return fps

    for offset in range(1, 1001):
        candidates = [
            milli for milli in (base_milli - offset, base_milli + offset)
            if _is_valid(milli)
        ]
        if candidates:
            best = min(candidates, key=lambda milli: abs(milli - target_milli))
            return best / 1000.0

    return float(round(fps))


class AsyncFrameReader:
    """Bounded background thread that prefetches decoded frames from VideoCapture."""

    _SENTINEL = object()

    def __init__(
        self,
        capture,
        max_queue_size: int = 16,
        max_frames: int | None = None,
    ) -> None:
        self._capture = capture
        self._max_frames = max_frames
        self._queue: queue.Queue = queue.Queue(maxsize=max(2, max_queue_size))
        self._stop_event = threading.Event()
        self._error: BaseException | None = None
        self._eof = False
        self.frame_timestamps_ms: list[float] = []
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="AsyncFrameReader",
        )
        self._thread.start()

    def _put_with_stop(self, item) -> bool:
        while not self._stop_event.is_set():
            try:
                self._queue.put(item, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def _run(self) -> None:
        read_count = 0
        try:
            while not self._stop_event.is_set():
                if self._max_frames is not None and read_count >= self._max_frames:
                    break
                success, frame = self._capture.read()
                if not success:
                    break
                try:
                    pts_ms = float(self._capture.get(cv2.CAP_PROP_POS_MSEC))
                except Exception:
                    pts_ms = -1.0
                self.frame_timestamps_ms.append(pts_ms if math.isfinite(pts_ms) else -1.0)
                read_count += 1
                if not self._put_with_stop(frame):
                    break
        except BaseException as exc:
            self._error = exc
        finally:
            while True:
                try:
                    self._queue.put(self._SENTINEL, timeout=0.05)
                    break
                except queue.Full:
                    if self._stop_event.is_set():
                        try:
                            self._queue.get_nowait()
                        except queue.Empty:
                            pass

    def read_frame(self):
        if self._eof:
            return None
        item = self._queue.get()
        if item is self._SENTINEL:
            self._eof = True
            if self._error is not None:
                raise self._error
            return None
        return item

    def read_batch(self, count: int) -> list:
        frames = []
        for _ in range(max(1, count)):
            frame = self.read_frame()
            if frame is None:
                break
            frames.append(frame)
        return frames

    def close(self) -> None:
        self._stop_event.set()
        while self._thread.is_alive():
            try:
                while True:
                    self._queue.get_nowait()
            except queue.Empty:
                pass
            self._thread.join(timeout=0.05)


class AsyncVideoWriter:
    """Bounded background thread that encodes and writes frames to VideoWriter."""

    _SENTINEL = object()

    def __init__(self, writer, max_queue_size: int = 16) -> None:
        self._writer = writer
        self._queue: queue.Queue = queue.Queue(maxsize=max(2, max_queue_size))
        self._stop_event = threading.Event()
        self._error: BaseException | None = None
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="AsyncVideoWriter",
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            while True:
                item = self._queue.get()
                if item is self._SENTINEL:
                    break
                self._writer.write(item)
        except BaseException as exc:
            self._error = exc
            self._stop_event.set()

    def write(self, frame) -> None:
        if self._error is not None:
            raise self._error
        while not self._stop_event.is_set():
            try:
                self._queue.put(frame, timeout=0.05)
                return
            except queue.Full:
                continue
        if self._error is not None:
            raise self._error

    def close(self, drain: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        if not drain:
            self._stop_event.set()
            try:
                while True:
                    self._queue.get_nowait()
            except queue.Empty:
                pass
        while self._thread.is_alive():
            try:
                self._queue.put(self._SENTINEL, timeout=0.05)
                break
            except queue.Full:
                if not drain:
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        pass
        self._thread.join()
        if drain and self._error is not None:
            raise self._error


def open_mp4v_writer(output_path: Path, fps: float, width: int, height: int):
    writer_fps = sanitize_mp4v_fps(fps)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        writer_fps,
        (width, height),
    )
    return writer, writer_fps


def _reset_and_offload_yolo(detector) -> None:
    """Clear Ultralytics predictor/tracker state and move model weights off GPU."""
    if detector is None:
        return
    predictor = getattr(detector, "predictor", None)
    if predictor is not None:
        hook = getattr(predictor, "_hook", None)
        if hook is not None:
            try:
                hook.remove()
            except Exception:
                pass
            try:
                predictor._hook = None
            except Exception:
                pass
        if hasattr(predictor, "trackers"):
            predictor.trackers = []
        detector.predictor = None
    if hasattr(detector, "to"):
        detector.to("cpu")
    _clear_cuda_cache()


class WorkerModelCache:
    """Persistently cache YOLO and Pose estimator instances across queued jobs."""

    def __init__(self) -> None:
        self._yolo_detector = None
        self._yolo_key: str | None = None
        self._pose_estimator: BasePoseEstimator | None = None
        self._pose_key: tuple | None = None
        self._pose_device: str | None = None

    @staticmethod
    def _build_pose_key(device: str) -> tuple:
        settings = _active_pose_settings_from_globals()
        return (tuple(sorted(settings.items())), str(device))

    def has_cached_pose(self, device: str) -> bool:
        if self._pose_estimator is None:
            return False
        return self._pose_key == self._build_pose_key(device)

    def release_yolo(self) -> None:
        if self._yolo_detector is not None:
            _reset_and_offload_yolo(self._yolo_detector)
            self._yolo_detector = None
            self._yolo_key = None
            _clear_cuda_cache()

    def release_pose(self) -> None:
        if self._pose_estimator is not None:
            try:
                self._pose_estimator.close()
            finally:
                self._pose_estimator = None
                self._pose_key = None
                self._pose_device = None
                _clear_cuda_cache()

    def prepare_for_yolo_pass(
        self,
        yolo_device: str,
        yolo_model: str | Path,
        yolo_imgsz: int,
        yolo_batch_size: int = 16,
    ) -> None:
        """Ensure sufficient free VRAM before Pass 1 (YOLO) when caching CUDA pose models."""
        if self._pose_estimator is None:
            return
        if not str(yolo_device).lower().startswith("cuda"):
            return
        if not str(self._pose_device or "").lower().startswith("cuda"):
            return
        mem_info = _get_cuda_free_total_gb(str(yolo_device))
        model_factor = _yolo_model_vram_factor(str(yolo_model))
        pixel_factor = (max(int(yolo_imgsz), 320) / 640.0) ** 2
        # cap_yolo_batch_by_vram clamps large requested batches (e.g. 512) to fit remaining
        # free VRAM, so only evict the cached pose model if free VRAM cannot fit a minimal probe batch.
        max_probe_batch = 1 if pixel_factor >= 8.0 else 4
        batch = min(max(1, int(yolo_batch_size)), max_probe_batch)
        half_factor = 0.65 if str(yolo_device).lower().startswith("cuda") else 1.0
        min_free_gb = max(2.0, 1.0 + batch * 0.070 * model_factor * pixel_factor * half_factor + 0.6)
        if mem_info is None or mem_info[0] < min_free_gb:
            free_desc = f"{mem_info[0]:.1f} GB" if mem_info is not None else "unknown"
            print(
                "VRAM管理: Pass 1 (YOLO) の空きVRAM確保のためキャッシュ済み姿勢モデルを一時解放します "
                f"(空きVRAM: {free_desc})",
                flush=True,
            )
            self.release_pose()

    def get_or_load_yolo(self, yolo_model: str | Path):
        key = str(yolo_model)
        if self._yolo_detector is not None and self._yolo_key == key:
            _reset_and_offload_yolo(self._yolo_detector)
            return self._yolo_detector
        self.release_yolo()
        detector = YOLO(yolo_model)
        self._yolo_detector = detector
        self._yolo_key = key
        return detector

    def finish_yolo_pass(self, detector) -> None:
        _reset_and_offload_yolo(detector)

    def get_or_create_pose_estimator(self, device: str) -> BasePoseEstimator:
        key = self._build_pose_key(device)
        if self._pose_estimator is not None and self._pose_key == key:
            print(
                f"姿勢モデル (キャッシュ再利用): {self._pose_estimator.display_name}",
                flush=True,
            )
            return self._pose_estimator
        self.release_pose()
        estimator = create_pose_estimator_from_globals(device)
        self._pose_estimator = estimator
        self._pose_key = key
        self._pose_device = str(device)
        return estimator

    def close(self) -> None:
        try:
            self.release_pose()
        finally:
            self.release_yolo()


_LAST_VFR_INFO: dict[str, dict] = {}


def _analyze_pts_timestamps(
    pts_ms_list: list[float],
    container_fps: float,
) -> tuple[bool, float]:
    """Detect variable frame rate (VFR) and compute effective playback FPS from frame PTS (ms)."""
    import numpy as np

    base_fps = float(container_fps) if (container_fps and container_fps > 0.0) else 30.0
    valid_pts = [p for p in pts_ms_list if p is not None and p >= 0.0]
    if len(valid_pts) < 6:
        return False, base_fps

    # Ignore leading zeros if VideoCapture yields 0.0 on all synthetic/unindexed frames
    diffs = np.diff(np.asarray(valid_pts, dtype=np.float64))
    non_zero_diffs = diffs[diffs > 0.0]
    if len(non_zero_diffs) < 5:
        return False, base_fps

    non_monotonic = bool(np.any(diffs < -1e-3))
    mean_dt = float(np.mean(non_zero_diffs))
    median_dt = float(np.median(non_zero_diffs))
    if median_dt <= 0.0:
        return non_monotonic, base_fps

    effective_fps = 1000.0 / median_dt
    rel_std = float(np.std(non_zero_diffs) / max(mean_dt, 1e-6))
    fps_drift = abs(effective_fps - base_fps) / max(base_fps, 1e-6)
    is_vfr = non_monotonic or rel_std > 0.08 or fps_drift > 0.05
    if fps_drift > 0.05 and math.isfinite(effective_fps) and effective_fps > 0.0:
        return is_vfr, effective_fps
    return is_vfr, base_fps


def _create_synced_tracker_yaml(tracker_spec: str, yolo_confidence: float) -> tuple[str, Path | None]:
    """Create a temp tracker YAML syncing track_high_thresh/new_track_thresh with YOLO_CONFIDENCE."""
    try:
        import yaml
    except ImportError:
        return tracker_spec, None

    cfg_path: Path | None = None
    candidate = Path(tracker_spec)
    if candidate.is_file():
        cfg_path = candidate
    else:
        try:
            import ultralytics

            pkg_tracker = Path(ultralytics.__file__).resolve().parent / "cfg" / "trackers" / tracker_spec
            if pkg_tracker.is_file():
                cfg_path = pkg_tracker
        except Exception:
            cfg_path = None

    if cfg_path is None:
        return tracker_spec, None

    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return tracker_spec, None
        conf = max(0.01, min(0.95, float(yolo_confidence)))
        data["track_high_thresh"] = conf
        data["new_track_thresh"] = conf
        orig_low = float(data.get("track_low_thresh", 0.1))
        data["track_low_thresh"] = min(orig_low, conf)
        fd, tmp_name = tempfile.mkstemp(prefix="yolo_tracker_", suffix=".yaml")
        os.close(fd)
        tmp_path = Path(tmp_name)
        tmp_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return str(tmp_path), tmp_path
    except Exception:
        return tracker_spec, None


def run_yolo_pass(
    input_video: Path,
    progress_total_frames=0,
    device="cpu",
    model_cache: WorkerModelCache | None = None,
    pose_device: str | None = None,
):
    capture = cv2.VideoCapture(str(input_video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open input video: {input_video.resolve()}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    container_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    fps = container_fps
    total_frames = progress_total_frames or int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    configure_cuda_memory_fraction(device)
    detector = (
        model_cache.get_or_load_yolo(YOLO_MODEL)
        if model_cache is not None
        else YOLO(YOLO_MODEL)
    )
    effective_batch = resolve_effective_batch_size(YOLO_BATCH_SIZE, device, "YOLO")
    effective_batch = cap_yolo_batch_by_vram(
        effective_batch, device, YOLO_MODEL, YOLO_IMAGE_SIZE
    )
    print(f"YOLOバッチサイズ: {effective_batch}", flush=True)
    tracks = {}
    next_id = 0
    target_stable_id = None
    frame_detections = []
    processed_frames = 0
    last_progress = -1
    print("PROGRESS:0:YOLO", flush=True)

    tracker_arg, temp_tracker_path = _create_synced_tracker_yaml(YOLO_TRACKER, YOLO_CONFIDENCE)
    use_half = str(device).strip().lower().startswith("cuda")
    extra_track_kwargs = {"half": True} if use_half else {}

    def _track_single(single_frame):
        return detector.track(
            single_frame,
            device=device,
            persist=True,
            tracker=tracker_arg,
            imgsz=YOLO_IMAGE_SIZE,
            conf=YOLO_CONFIDENCE,
            iou=YOLO_IOU,
            classes=YOLO_CLASSES,
            max_det=30,
            verbose=False,
            **extra_track_kwargs,
        )

    def _emit_yolo_results(results_chunk) -> None:
        nonlocal next_id, processed_frames, last_progress
        for result in results_chunk:
            detections, next_id = stabilize_yolo_ids(
                result.boxes,
                tracks,
                next_id,
            )
            frame_detections.append(detections)
            processed_frames += 1
            if total_frames > 0:
                progress = min(49, int(processed_frames * 50 / total_frames))
                if progress > last_progress:
                    print(f"PROGRESS:{progress}:YOLO", flush=True)
                    last_progress = progress

    def _run_yolo_chunk(frames_chunk) -> None:
        nonlocal effective_batch
        if not frames_chunk:
            return
        if effective_batch > 1 and len(frames_chunk) > 1:
            oom_occurred = False
            try:
                results = detector.track(
                    frames_chunk,
                    device=device,
                    persist=True,
                    tracker=tracker_arg,
                    imgsz=YOLO_IMAGE_SIZE,
                    conf=YOLO_CONFIDENCE,
                    iou=YOLO_IOU,
                    classes=YOLO_CLASSES,
                    max_det=30,
                    batch=len(frames_chunk),
                    verbose=False,
                    **extra_track_kwargs,
                )
            except Exception as exc:
                if not is_cuda_oom_error(exc):
                    raise
                oom_occurred = True
            if not oom_occurred:
                _emit_yolo_results(results)
                return

            # Retry outside the except block so exc.__traceback__ releases GPU tensors first.
            _clear_cuda_cache()
            next_batch = max(1, min(effective_batch, len(frames_chunk)) // 2)
            print(
                f"YOLO: CUDAメモリ不足（OOM）が発生したため、バッチサイズを {next_batch} に下げて続行します。",
                flush=True,
            )
            effective_batch = next_batch
            for start in range(0, len(frames_chunk), next_batch):
                _run_yolo_chunk(frames_chunk[start : start + next_batch])
            return

        for single_frame in frames_chunk:
            results = [_track_single(single_frame)[0]]
            _emit_yolo_results(results)

    queue_depth = max(8, min(48, effective_batch + 8))
    reader = AsyncFrameReader(capture, max_queue_size=queue_depth)
    preimport_thread = None
    if normalize_pose_engine(globals().get("POSE_ENGINE")) == "vitpose":
        effective_pose_device = pose_device if pose_device is not None else device
        pose_already_cached = (
            model_cache is not None
            and model_cache.has_cached_pose(effective_pose_device)
        )
        onnx_already_cached = has_cached_vitpose_onnx(
            str(globals().get("VITPOSE_MODEL", "h")),
            str(globals().get("VITPOSE_INPUT_SIZE", "256x192")),
            fp16=(
                str(effective_pose_device).lower().startswith("cuda")
                and str(globals().get("VITPOSE_PRECISION", "fp16")).strip().lower() == "fp16"
            ),
        )
        if not pose_already_cached and not onnx_already_cached:
            from pose_estimators.vitpose import preimport_vitpose_dependencies

            preimport_thread = threading.Thread(
                target=preimport_vitpose_dependencies,
                daemon=True,
                name="ViTPosePreimport",
            )
            preimport_thread.start()
    try:
        while True:
            _check_cancel_requested()
            batch_frames = reader.read_batch(effective_batch)
            if not batch_frames:
                break
            _run_yolo_chunk(batch_frames)
    finally:
        try:
            reader.close()
        finally:
            if temp_tracker_path is not None:
                temp_tracker_path.unlink(missing_ok=True)
            if preimport_thread is not None:
                preimport_thread.join()
            capture.release()
            if model_cache is not None:
                model_cache.finish_yolo_pass(detector)
            else:
                del detector
                _clear_cuda_cache()
    is_vfr, effective_fps = _analyze_pts_timestamps(reader.frame_timestamps_ms, container_fps)
    fps = effective_fps
    if is_vfr:
        print(
            f"警告: 可変フレームレート(VFR)の可能性があります "
            f"(コンテナFPS: {container_fps:.3f}, 実効FPS: {effective_fps:.3f})",
            flush=True,
        )
    _LAST_VFR_INFO[str(input_video)] = {
        "is_vfr": is_vfr,
        "container_fps": float(container_fps),
        "effective_fps": float(effective_fps),
    }
    print(f"YOLO処理フレーム数: {processed_frames}（動画情報の値: {total_frames}）", flush=True)
    print("PROGRESS:50:YOLO", flush=True)
    if target_stable_id is None:
        target_stable_id = select_moving_target_id(
            frame_detections,
            len(frame_detections),
        )
    target_boxes = fill_target_box_gaps(frame_detections, target_stable_id)
    return frame_detections, target_boxes, target_stable_id, width, height, fps


def run_analysis(model_cache: WorkerModelCache | None = None) -> None:
    import numpy as np

    pose_settings = _active_pose_settings_from_globals()
    pose_engine = normalize_pose_engine(pose_settings.get("POSE_ENGINE"))
    validate_pose_settings(pose_settings)
    yolo_device, pose_device = prepare_runtime(BACKEND, DEVICE, pose_engine=pose_engine)

    input_video = find_input_video()
    output_directory = OUTPUT_ROOT / OUTPUT_FOLDER_NAME
    default_names = output_names(output_directory)
    output_video = output_directory / OUTPUT_VIDEO_NAME
    output_crop_video = output_directory / (
        globals().get("OUTPUT_CROP_VIDEO_NAME") or default_names["OUTPUT_CROP_VIDEO_NAME"]
    )
    output_crop_skeleton_video = output_directory / (
        globals().get("OUTPUT_CROP_SKELETON_VIDEO_NAME")
        or default_names["OUTPUT_CROP_SKELETON_VIDEO_NAME"]
    )
    output_csv = output_directory / OUTPUT_CSV_NAME
    output_metadata = output_directory / OUTPUT_METADATA_NAME
    output_metadata_json = output_directory / (
        globals().get("OUTPUT_METADATA_JSON_NAME")
        or default_names["OUTPUT_METADATA_JSON_NAME"]
    )
    output_npz = output_directory / (
        globals().get("OUTPUT_NPZ_NAME")
        or default_names["OUTPUT_NPZ_NAME"]
    )

    output_directory.mkdir(parents=True, exist_ok=True)

    metadata_capture = cv2.VideoCapture(str(input_video))
    if not metadata_capture.isOpened():
        raise RuntimeError(f"Could not open input video: {input_video.resolve()}")
    metadata_total_frames = int(metadata_capture.get(cv2.CAP_PROP_FRAME_COUNT))
    metadata_width = int(metadata_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    metadata_height = int(metadata_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    metadata_fps = metadata_capture.get(cv2.CAP_PROP_FPS) or 30.0
    metadata_capture.release()

    manual_capture_fps = globals().get("CAPTURE_FPS")
    pre_capture_fps, capture_fps_source = resolve_capture_fps(
        input_video,
        metadata_fps,
        manual_capture_fps,
    )

    write_video_metadata(
        input_video,
        output_metadata,
        metadata_total_frames,
        metadata_width,
        metadata_height,
        metadata_fps,
        metadata_total_frames=metadata_total_frames,
        playback_fps=metadata_fps,
        capture_fps=pre_capture_fps,
        capture_fps_source=capture_fps_source,
        yolo_model=YOLO_MODEL,
    )

    yolo_started_at = perf_counter()
    if model_cache is not None:
        model_cache.prepare_for_yolo_pass(
            yolo_device,
            YOLO_MODEL,
            YOLO_IMAGE_SIZE,
            YOLO_BATCH_SIZE,
        )
        frame_detections, target_boxes, target_stable_id, width, height, fps = run_yolo_pass(
            input_video,
            metadata_total_frames,
            device=yolo_device,
            model_cache=model_cache,
            pose_device=pose_device,
        )
    else:
        frame_detections, target_boxes, target_stable_id, width, height, fps = run_yolo_pass(
            input_video,
            metadata_total_frames,
            device=yolo_device,
        )
    yolo_elapsed_seconds = perf_counter() - yolo_started_at
    vfr_info = _LAST_VFR_INFO.get(str(input_video), {})
    is_vfr = bool(vfr_info.get("is_vfr", False))
    effective_playback_fps = float(vfr_info.get("effective_fps", fps) or fps)
    effective_capture_fps, capture_fps_source = resolve_capture_fps(
        input_video,
        effective_playback_fps,
        manual_capture_fps,
    )
    planned_box_states = compute_target_box_states(
        frame_detections, target_boxes, target_stable_id
    )

    # Pass 1 (YOLO) が解放された後にのみ Pass 2 の姿勢推定モデルをロードする（12GB VRAM競合防止）
    pose_init_started_at = perf_counter()
    estimator = (
        model_cache.get_or_create_pose_estimator(pose_device)
        if model_cache is not None
        else create_pose_estimator_from_globals(pose_device)
    )
    pose_init_seconds = perf_counter() - pose_init_started_at

    output_mode = normalize_output_mode(globals().get("OUTPUT_MODE", "full"))
    write_videos = output_mode != "data_only"

    try:
        pose_started_at = perf_counter()
        capture = cv2.VideoCapture(str(input_video))
        if not capture.isOpened():
            raise RuntimeError(f"Could not reopen input video: {input_video.resolve()}")
        crop_w, crop_h = estimator.model_input_size
        phase_code = estimator.progress_phase
        phase_label = "ViTPose++" if pose_engine == "vitpose" else "RTMPose"
        writer = None
        crop_writer = None
        crop_skeleton_writer = None
        if write_videos:
            try:
                writer, writer_fps = open_mp4v_writer(output_video, fps, width, height)
                if not writer.isOpened():
                    raise RuntimeError(f"Could not create output video: {output_video.resolve()}")
                if writer_fps != fps:
                    print(
                        f"動画書き出しFPS調整: {fps:.6f} -> {writer_fps:.3f} (mp4v制限対応)",
                        flush=True,
                    )
                crop_writer, _ = open_mp4v_writer(output_crop_video, fps, crop_w, crop_h)
                if not crop_writer.isOpened():
                    raise RuntimeError(
                        f"Could not create crop output video: {output_crop_video.resolve()}"
                    )
                crop_skeleton_writer, _ = open_mp4v_writer(
                    output_crop_skeleton_video, fps, crop_w, crop_h
                )
                if not crop_skeleton_writer.isOpened():
                    raise RuntimeError(
                        f"Could not create crop skeleton output video: {output_crop_skeleton_video.resolve()}"
                    )
            except Exception:
                for w in (crop_skeleton_writer, crop_writer, writer):
                    if w is not None:
                        w.release()
                capture.release()
                raise
        else:
            print("出力モード: data_only（MP4動画生成をスキップし数値データのみ出力します）", flush=True)

        requested_batch = (
            globals().get("VITPOSE_BATCH_SIZE", 4)
            if pose_engine == "vitpose"
            else globals().get("RTMPOSE_BATCH_SIZE", 1)
        )
        effective_pose_batch = resolve_effective_batch_size(
            requested_batch, pose_device, phase_label
        )
        effective_pose_batch = estimator.cap_batch_by_vram(
            effective_pose_batch, pose_device
        )
        if effective_pose_batch > 1:
            is_dynamic, dim_info = estimator.supports_dynamic_batch()
            if not is_dynamic:
                print(
                    f"{phase_label}: モデルが静的バッチ（shape[0]={dim_info}）のため、"
                    f"バッチサイズを 1 にフォールバックします（設定値: {effective_pose_batch}）",
                    flush=True,
                )
                effective_pose_batch = 1
        print(f"{phase_label}バッチサイズ: {effective_pose_batch}", flush=True)

        black_crop = np.zeros((crop_h, crop_w, 3), dtype=np.uint8) if write_videos else None

        with output_csv.open("w", newline="", encoding="utf-8-sig") as csv_file:
            csv_writer = csv.DictWriter(csv_file, fieldnames=get_csv_fieldnames())
            csv_writer.writeheader()

            reader = AsyncFrameReader(
                capture,
                max_queue_size=max(8, min(48, effective_pose_batch + 8)),
                max_frames=len(target_boxes),
            )
            writer_queue_size = max(8, min(32, effective_pose_batch + 8))
            writer_worker = AsyncVideoWriter(writer, max_queue_size=writer_queue_size) if write_videos else None
            crop_writer_worker = (
                AsyncVideoWriter(crop_writer, max_queue_size=writer_queue_size) if write_videos else None
            )
            crop_skeleton_writer_worker = (
                AsyncVideoWriter(crop_skeleton_writer, max_queue_size=writer_queue_size)
                if write_videos
                else None
            )
            batch_buffer: dict = {}
            frame_count = 0
            target_box_count = 0
            pose_call_count = 0
            pose_success_count = 0
            last_progress = 50
            total_pose_frames = len(target_boxes)
            if total_pose_frames > 0 and effective_pose_batch > total_pose_frames:
                effective_pose_batch = total_pose_frames
            aborted = False

            overlay = _compute_overlay_params(width, height, crop_w, crop_h)
            label_font_scale = overlay["label_font_scale"]
            label_thickness = overlay["label_thickness"]
            crop_line_w = overlay["crop_line_w"]
            crop_kpt_rad = overlay["crop_kpt_rad"]
            crop_udp_span = overlay["crop_udp_span"]

            npz_target_boxes: list[list[float]] = []
            npz_box_states: list[int] = []
            npz_crop_centers: list[list[float]] = []
            npz_crop_scales: list[list[float]] = []
            npz_crop_kpts: list[np.ndarray] = []
            npz_kpts_xy: list[np.ndarray] = []
            npz_kpts_score: list[np.ndarray] = []

            def _emit_pose_frame(
                idx, frame, target_box, restored_keypoints, pose_scores, crop_info=None
            ) -> None:
                nonlocal frame_count, target_box_count, pose_success_count, last_progress
                if target_box is not None:
                    target_box_count += 1
                    npz_target_boxes.append([float(v) for v in target_box[:4]])
                    box_state_val = (
                        planned_box_states[idx]
                        if idx < len(planned_box_states)
                        else 1
                    )
                else:
                    npz_target_boxes.append([np.nan, np.nan, np.nan, np.nan])
                    box_state_val = 0
                npz_box_states.append(int(box_state_val))

                if restored_keypoints is not None:
                    pose_success_count += 1
                    if write_videos:
                        annotate_pose_on_frame(frame, target_box, restored_keypoints, pose_scores)

                if crop_info is not None:
                    crop_bgr, crop_center, crop_scale = crop_info
                    c_arr = np.asarray(crop_center, dtype=np.float32)
                    s_arr = np.asarray(crop_scale, dtype=np.float32)
                    npz_crop_centers.append([float(c_arr[0]), float(c_arr[1])])
                    npz_crop_scales.append([float(s_arr[0]), float(s_arr[1])])
                    if write_videos:
                        assert crop_writer_worker is not None and crop_skeleton_writer_worker is not None
                        crop_writer_worker.write(crop_bgr)
                        try:
                            crop_skeleton = estimator.render_pose_on_crop(
                                crop_bgr,
                                restored_keypoints,
                                pose_scores,
                                crop_center,
                                crop_scale,
                                KEYPOINT_THRESHOLD,
                                skeleton_line_width=crop_line_w,
                                keypoint_radius=crop_kpt_rad,
                            )
                        except TypeError:
                            crop_skeleton = estimator.render_pose_on_crop(
                                crop_bgr,
                                restored_keypoints,
                                pose_scores,
                                crop_center,
                                crop_scale,
                                KEYPOINT_THRESHOLD,
                            )
                        crop_skeleton_writer_worker.write(crop_skeleton)
                else:
                    npz_crop_centers.append([np.nan, np.nan])
                    npz_crop_scales.append([np.nan, np.nan])
                    if write_videos:
                        assert crop_writer_worker is not None and crop_skeleton_writer_worker is not None
                        crop_writer_worker.write(black_crop)
                        crop_skeleton_writer_worker.write(black_crop)

                if restored_keypoints is not None and pose_scores is not None:
                    k_arr = np.asarray(restored_keypoints, dtype=np.float32)
                    s_arr_k = np.asarray(pose_scores, dtype=np.float32)
                    npz_kpts_xy.append(k_arr)
                    npz_kpts_score.append(s_arr_k)
                    if crop_info is not None:
                        _, cc, cs = crop_info
                        cc_arr = np.asarray(cc, dtype=np.float32)
                        cs_arr = np.where(np.asarray(cs, dtype=np.float32) == 0.0, 1.0, np.asarray(cs, dtype=np.float32))
                        crop_k_arr = ((k_arr - cc_arr) / cs_arr + 0.5) * crop_udp_span
                        npz_crop_kpts.append(crop_k_arr.astype(np.float32))
                    else:
                        npz_crop_kpts.append(np.full((17, 2), np.nan, dtype=np.float32))
                else:
                    npz_kpts_xy.append(np.full((17, 2), np.nan, dtype=np.float32))
                    npz_kpts_score.append(np.full((17,), np.nan, dtype=np.float32))
                    npz_crop_kpts.append(np.full((17, 2), np.nan, dtype=np.float32))

                frame_data = {
                    "frame": idx,
                    "time_seconds": idx / effective_capture_fps,
                    "persons": [],
                }
                if restored_keypoints is not None:
                    person = {
                        "person_id": target_stable_id,
                    }
                    for kp_index, name in enumerate(COCO_KEYPOINTS):
                        x, y = restored_keypoints[kp_index]
                        person[name] = {
                            "x": x,
                            "y": y,
                            "score": float(pose_scores[kp_index]),
                        }
                    frame_data["persons"].append(person)

                csv_writer.writerow(make_csv_row(frame_data))

                if write_videos:
                    assert writer_worker is not None
                    _draw_frame_index_label(frame, idx, label_font_scale, label_thickness)
                    writer_worker.write(frame)
                frame_count += 1

                if total_pose_frames > 0:
                    progress = 50 + int(frame_count * 50 / total_pose_frames)
                    if progress > last_progress:
                        print(f"PROGRESS:{progress}:{phase_code}", flush=True)
                        last_progress = progress

            try:
                print(f"PROGRESS:50:{phase_code}", flush=True)
                next_read_idx = 0
                eof = False
                default_max_buffered = min(
                    effective_pose_batch + 64,
                    max(effective_pose_batch * 2, 16),
                )
                max_buffered = _cap_max_buffered_by_ram(
                    default_max_buffered,
                    effective_pose_batch,
                    width,
                    height,
                )
                while next_read_idx < total_pose_frames and not eof:
                    _check_cancel_requested()
                    buffered = []
                    valid_positions = []
                    while (
                        next_read_idx < total_pose_frames
                        and len(valid_positions) < effective_pose_batch
                        and len(buffered) < max_buffered
                    ):
                        frame = reader.read_frame()
                        if frame is None:
                            eof = True
                            break
                        idx = next_read_idx
                        next_read_idx += 1
                        target_box = target_boxes[idx]
                        is_valid = (
                            clamped_target_box(target_box, frame.shape[1], frame.shape[0])
                            is not None
                        )
                        if not buffered and not is_valid:
                            _emit_pose_frame(idx, frame, target_box, None, None, None)
                            continue
                        pos = len(buffered)
                        buffered.append((idx, frame, target_box))
                        if is_valid:
                            valid_positions.append(pos)

                    if not buffered:
                        continue

                    pose_results = [((None, None), None) for _ in buffered]
                    if valid_positions:
                        pose_call_count += len(valid_positions)
                        batch_items = [
                            (buffered[pos][1], buffered[pos][2]) for pos in valid_positions
                        ]
                        if effective_pose_batch > 1:
                            def _run_pose_chunk(items_chunk):
                                nonlocal effective_pose_batch
                                if effective_pose_batch > 1:
                                    oom_occurred = False
                                    try:
                                        fixed_bs = effective_pose_batch
                                        return estimator.infer_batch(
                                            items_chunk,
                                            fixed_batch_size=fixed_bs,
                                            batch_buffer=batch_buffer,
                                            return_crop=True,
                                        )
                                    except Exception as exc:
                                        if not is_cuda_oom_error(exc):
                                            raise
                                        oom_occurred = True
                                    if oom_occurred:
                                        batch_buffer.clear()
                                        _clear_cuda_cache()
                                        next_batch = max(1, min(effective_pose_batch, len(items_chunk)) // 2)
                                        print(
                                            f"{phase_label}: CUDAメモリ不足（OOM）が発生したため、バッチサイズを {next_batch} に下げて続行します。",
                                            flush=True,
                                        )
                                        effective_pose_batch = next_batch
                                        out = []
                                        for start in range(0, len(items_chunk), next_batch):
                                            out.extend(_run_pose_chunk(items_chunk[start : start + next_batch]))
                                        return out
                                return [
                                    estimator.infer_single(frm, box, return_crop=True)
                                    for frm, box in items_chunk
                                ]

                            inferred = _run_pose_chunk(batch_items)
                        else:
                            inferred = [
                                estimator.infer_single(frm, box, return_crop=True)
                                for frm, box in batch_items
                            ]
                        for pos, pose_with_crop in zip(valid_positions, inferred):
                            pose_results[pos] = pose_with_crop

                    for (idx, frame, target_box), (
                        (restored_keypoints, pose_scores),
                        crop_info,
                    ) in zip(buffered, pose_results):
                        _emit_pose_frame(
                            idx,
                            frame,
                            target_box,
                            restored_keypoints,
                            pose_scores,
                            crop_info,
                        )
            except BaseException:
                aborted = True
                raise
            finally:
                try:
                    reader.close()
                finally:
                    try:
                        if writer_worker is not None:
                            writer_worker.close(drain=not aborted)
                    finally:
                        try:
                            if crop_writer_worker is not None:
                                crop_writer_worker.close(drain=not aborted)
                        finally:
                            try:
                                if crop_skeleton_writer_worker is not None:
                                    crop_skeleton_writer_worker.close(drain=not aborted)
                            finally:
                                capture.release()
                                for w in (writer, crop_writer, crop_skeleton_writer):
                                    if w is not None:
                                        w.release()

        pose_elapsed_seconds = pose_init_seconds + perf_counter() - pose_started_at
        pose_display_name = estimator.display_name
        print(f"PROGRESS:100:{phase_code}", flush=True)
    except BaseException:
        if model_cache is not None:
            model_cache.release_pose()
        raise
    finally:
        if model_cache is None:
            estimator.close()

    # Finalize NPZ + JSON + TXT metadata aligned strictly to actual frame count T = frame_count
    actual_t = frame_count
    frame_indices_arr = np.arange(actual_t, dtype=np.int32)
    timestamps_arr = frame_indices_arr.astype(np.float64) / float(effective_capture_fps)
    np.savez_compressed(
        output_npz,
        frame_indices=frame_indices_arr,
        timestamps_sec=timestamps_arr,
        keypoints_xy=(
            np.stack(npz_kpts_xy[:actual_t], axis=0).astype(np.float32)
            if actual_t > 0
            else np.empty((0, 17, 2), dtype=np.float32)
        ),
        keypoints_score=(
            np.stack(npz_kpts_score[:actual_t], axis=0).astype(np.float32)
            if actual_t > 0
            else np.empty((0, 17), dtype=np.float32)
        ),
        target_boxes=(
            np.asarray(npz_target_boxes[:actual_t], dtype=np.float32)
            if actual_t > 0
            else np.empty((0, 4), dtype=np.float32)
        ),
        box_state=(
            np.asarray(npz_box_states[:actual_t], dtype=np.int8)
            if actual_t > 0
            else np.empty((0,), dtype=np.int8)
        ),
        crop_centers=(
            np.asarray(npz_crop_centers[:actual_t], dtype=np.float32)
            if actual_t > 0
            else np.empty((0, 2), dtype=np.float32)
        ),
        crop_scales=(
            np.asarray(npz_crop_scales[:actual_t], dtype=np.float32)
            if actual_t > 0
            else np.empty((0, 2), dtype=np.float32)
        ),
        crop_size=np.asarray([crop_w, crop_h], dtype=np.int32),
        crop_keypoints_xy=(
            np.stack(npz_crop_kpts[:actual_t], axis=0).astype(np.float32)
            if actual_t > 0
            else np.empty((0, 17, 2), dtype=np.float32)
        ),
    )

    metadata_json_payload = {
        "schema_version": "1.0",
        "video": {
            "source_path": str(input_video.resolve()),
            "video_name": input_video.name,
            "width": int(width),
            "height": int(height),
            "actual_frame_count": int(actual_t),
            "container_frame_count": int(metadata_total_frames),
            "capture_fps": float(effective_capture_fps),
            "capture_fps_source": capture_fps_source,
            "playback_fps": float(effective_playback_fps),
            "is_vfr": bool(is_vfr),
            "duration_seconds": float(actual_t / effective_capture_fps if effective_capture_fps > 0 else 0.0),
        },
        "ai": {
            "person_detector": {
                "model": str(YOLO_MODEL),
                "tracker": str(YOLO_TRACKER),
                "image_size": int(YOLO_IMAGE_SIZE),
                "confidence": float(YOLO_CONFIDENCE),
                "iou": float(YOLO_IOU),
                "classes": [int(c) for c in YOLO_CLASSES],
            },
            "pose_estimator": {
                "engine": pose_engine,
                "display_name": pose_display_name,
                "crop_size": [int(crop_w), int(crop_h)],
                "keypoint_threshold": float(KEYPOINT_THRESHOLD),
                "keypoint_names": list(COCO_KEYPOINTS),
            },
            "target_stable_id": target_stable_id,
        },
        "outputs": {
            "video": output_video.name,
            "crop_video": output_crop_video.name,
            "crop_skeleton_video": output_crop_skeleton_video.name,
            "csv": output_csv.name,
            "metadata_txt": output_metadata.name,
            "metadata_json": output_metadata_json.name,
            "npz": output_npz.name,
        },
        "counts": {
            "target_boxes": int(target_box_count),
            "pose_calls": int(pose_call_count),
            "pose_accepted": int(pose_success_count),
        },
    }
    output_metadata_json.write_text(
        json.dumps(metadata_json_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_video_metadata(
        input_video,
        output_metadata,
        actual_t,
        width,
        height,
        effective_playback_fps,
        metadata_total_frames=metadata_total_frames,
        playback_fps=effective_playback_fps,
        capture_fps=effective_capture_fps,
        capture_fps_source=capture_fps_source,
        is_vfr=is_vfr,
        yolo_model=YOLO_MODEL,
        pose_engine_label=pose_display_name,
        target_stable_id=target_stable_id,
    )

    print(f"Finished: {frame_count} frames")
    if write_videos:
        print(f"Output: {output_video.resolve()}")
        print(f"Crop: {output_crop_video.resolve()}")
        print(f"Crop Skeleton: {output_crop_skeleton_video.resolve()}")
    else:
        print("Output Videos: skipped (data_only)")
    print(f"CSV: {output_csv.resolve()}")
    print(f"Metadata: {output_metadata.resolve()}")
    print(f"Metadata JSON: {output_metadata_json.resolve()}")
    print(f"NPZ: {output_npz.resolve()}")
    print(f"Target boxes: {target_box_count}/{frame_count}")
    print(f"{phase_label} calls: {pose_call_count}, accepted: {pose_success_count}")
    yolo_analysis_fps = len(target_boxes) / yolo_elapsed_seconds if yolo_elapsed_seconds > 0 else 0.0
    pose_analysis_fps = frame_count / pose_elapsed_seconds if pose_elapsed_seconds > 0 else 0.0
    print(f"YOLO分析時間: {yolo_elapsed_seconds:.2f} 秒", flush=True)
    print(f"YOLO分析速度: {yolo_analysis_fps:.2f} フレーム/秒", flush=True)
    print(f"{phase_label}分析時間: {pose_elapsed_seconds:.2f} 秒", flush=True)
    print(f"{phase_label}分析速度: {pose_analysis_fps:.2f} フレーム/秒", flush=True)


def render_videos_from_data(
    input_video: Path | str,
    output_directory: Path | str,
    settings: dict | None = None,
    *,
    cancel_check: Callable[[], bool] | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict[str, Path]:
    """Render full, crop, and crop-skeleton MP4 videos from raw video + saved NPZ/metadata."""
    import numpy as np

    if "cv2" not in globals():
        globals()["cv2"] = importlib.import_module("cv2")

    in_path = Path(input_video)
    out_dir = Path(output_directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = dict(settings or {})
    default_names = output_names(out_dir)

    output_video = out_dir / (cfg.get("OUTPUT_VIDEO_NAME") or default_names["OUTPUT_VIDEO_NAME"])
    output_crop_video = out_dir / (
        cfg.get("OUTPUT_CROP_VIDEO_NAME") or default_names["OUTPUT_CROP_VIDEO_NAME"]
    )
    output_crop_skeleton_video = out_dir / (
        cfg.get("OUTPUT_CROP_SKELETON_VIDEO_NAME")
        or default_names["OUTPUT_CROP_SKELETON_VIDEO_NAME"]
    )
    output_npz = out_dir / (cfg.get("OUTPUT_NPZ_NAME") or default_names["OUTPUT_NPZ_NAME"])
    output_metadata_json = out_dir / (
        cfg.get("OUTPUT_METADATA_JSON_NAME") or default_names["OUTPUT_METADATA_JSON_NAME"]
    )

    if not in_path.is_file():
        raise FileNotFoundError(f"Input video not found for local render: {in_path}")
    if not output_npz.is_file():
        raise FileNotFoundError(f"NPZ data file not found for local render: {output_npz}")

    with np.load(output_npz) as npz_data:
        frame_indices = np.asarray(npz_data["frame_indices"], dtype=np.int32)
        keypoints_xy = np.asarray(npz_data["keypoints_xy"], dtype=np.float32)
        keypoints_score = np.asarray(npz_data["keypoints_score"], dtype=np.float32)
        crop_centers = np.asarray(npz_data["crop_centers"], dtype=np.float32)
        crop_scales = np.asarray(npz_data["crop_scales"], dtype=np.float32)
        crop_size = np.asarray(npz_data["crop_size"], dtype=np.int32)
        crop_keypoints_xy = np.asarray(npz_data["crop_keypoints_xy"], dtype=np.float32)

    actual_t = int(len(frame_indices))
    if len(crop_size) < 2:
        raise ValueError(f"Invalid crop_size in NPZ: {crop_size!r}")
    crop_w, crop_h = max(1, int(crop_size[0])), max(1, int(crop_size[1]))

    playback_fps = 0.0
    if output_metadata_json.is_file():
        try:
            meta = json.loads(output_metadata_json.read_text(encoding="utf-8"))
            playback_fps = float(meta.get("video", {}).get("playback_fps") or 0.0)
        except Exception:
            playback_fps = 0.0

    capture = cv2.VideoCapture(str(in_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open input video for local render: {in_path.resolve()}")

    writer = None
    crop_writer = None
    crop_skeleton_writer = None
    writer_worker = None
    crop_writer_worker = None
    crop_skeleton_writer_worker = None
    aborted = False

    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width <= 0 or height <= 0:
            raise RuntimeError(f"Invalid video dimensions ({width}x{height}) for {in_path}")
        if playback_fps <= 0.0 or not math.isfinite(playback_fps):
            playback_fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)

        overlay = _compute_overlay_params(width, height, crop_w, crop_h, settings=cfg)
        kpt_thr = overlay["kpt_thr"]
        skel_line_w = overlay["skel_line_w"]
        kpt_rad = overlay["kpt_rad"]
        crop_line_w = overlay["crop_line_w"]
        crop_kpt_rad = overlay["crop_kpt_rad"]
        label_font_scale = overlay["label_font_scale"]
        label_thickness = overlay["label_thickness"]

        writer, _ = open_mp4v_writer(output_video, playback_fps, width, height)
        if not writer.isOpened():
            raise RuntimeError(f"Could not create output video: {output_video.resolve()}")
        crop_writer, _ = open_mp4v_writer(output_crop_video, playback_fps, crop_w, crop_h)
        if not crop_writer.isOpened():
            raise RuntimeError(f"Could not create crop output video: {output_crop_video.resolve()}")
        crop_skeleton_writer, _ = open_mp4v_writer(
            output_crop_skeleton_video, playback_fps, crop_w, crop_h
        )
        if not crop_skeleton_writer.isOpened():
            raise RuntimeError(
                f"Could not create crop skeleton output video: {output_crop_skeleton_video.resolve()}"
            )

        writer_worker = AsyncVideoWriter(writer, max_queue_size=16)
        crop_writer_worker = AsyncVideoWriter(crop_writer, max_queue_size=16)
        crop_skeleton_writer_worker = AsyncVideoWriter(crop_skeleton_writer, max_queue_size=16)
        black_crop = np.zeros((crop_h, crop_w, 3), dtype=np.uint8)
        last_reported_pct = -1

        for idx in range(actual_t):
            if (cancel_check is not None and cancel_check()) or _CANCEL_EVENT.is_set():
                raise AnalysisCancelledError("ローカル動画書き出しをキャンセルしました。")

            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError(
                    f"Input video ended early during local render at frame {idx}/{actual_t}: {in_path}"
                )

            has_kpts = (
                idx < len(keypoints_xy)
                and idx < len(keypoints_score)
                and not np.isnan(keypoints_xy[idx]).all()
                and not np.isnan(keypoints_score[idx]).all()
            )

            has_crop = (
                idx < len(crop_centers)
                and idx < len(crop_scales)
                and not np.isnan(crop_centers[idx]).any()
                and not np.isnan(crop_scales[idx]).any()
            )

            if has_crop:
                warp_mat = get_udp_warp_matrix(crop_centers[idx], crop_scales[idx], (crop_w, crop_h))
                crop_bgr = cv2.warpAffine(frame, warp_mat, (crop_w, crop_h), flags=cv2.INTER_LINEAR)
                crop_writer_worker.write(crop_bgr)

                has_crop_kpts = (
                    has_kpts
                    and idx < len(crop_keypoints_xy)
                    and not np.isnan(crop_keypoints_xy[idx]).all()
                )
                if has_crop_kpts:
                    crop_skeleton = draw_pose_skeleton(
                        crop_bgr.copy(),
                        crop_keypoints_xy[idx][None, :, :],
                        keypoints_score[idx][None, :],
                        kpt_thr=kpt_thr,
                        skeleton_line_width=crop_line_w,
                        keypoint_radius=crop_kpt_rad,
                    )
                else:
                    crop_skeleton = crop_bgr.copy()
                crop_skeleton_writer_worker.write(crop_skeleton)
            else:
                crop_writer_worker.write(black_crop)
                crop_skeleton_writer_worker.write(black_crop)

            if has_kpts:
                annotate_pose_on_frame(
                    frame,
                    None,
                    keypoints_xy[idx],
                    keypoints_score[idx],
                    keypoint_threshold=kpt_thr,
                    skeleton_line_width=skel_line_w,
                    keypoint_radius=kpt_rad,
                )
            _draw_frame_index_label(frame, idx, label_font_scale, label_thickness)
            writer_worker.write(frame)

            if progress_cb is not None and actual_t > 0:
                pct = int((idx + 1) * 100 / actual_t)
                if pct != last_reported_pct:
                    last_reported_pct = pct
                    progress_cb(float(pct), "LOCAL_RENDER")

    except BaseException:
        aborted = True
        raise
    finally:
        try:
            if writer_worker is not None:
                writer_worker.close(drain=not aborted)
        finally:
            try:
                if crop_writer_worker is not None:
                    crop_writer_worker.close(drain=not aborted)
            finally:
                try:
                    if crop_skeleton_writer_worker is not None:
                        crop_skeleton_writer_worker.close(drain=not aborted)
                finally:
                    capture.release()
                    for w in (writer, crop_writer, crop_skeleton_writer):
                        if w is not None:
                            w.release()
        if aborted:
            for partial in (output_video, output_crop_video, output_crop_skeleton_video):
                try:
                    if partial.exists():
                        partial.unlink()
                except OSError:
                    pass

    return {
        "video": output_video,
        "crop_video": output_crop_video,
        "crop_skeleton_video": output_crop_skeleton_video,
    }


_CANCEL_EVENT = threading.Event()
_CANCEL_FLAG_FILE: Path | None = None


class AnalysisCancelledError(Exception):
    """Raised when the current analysis job is cancelled cooperatively."""


def _is_cancel_requested() -> bool:
    if _CANCEL_EVENT.is_set():
        return True
    flag_file = _CANCEL_FLAG_FILE
    if flag_file is not None:
        try:
            if flag_file.exists():
                return True
        except OSError:
            pass
    return False


def _check_cancel_requested() -> None:
    if _is_cancel_requested():
        raise AnalysisCancelledError("解析がキャンセルされました。")


def _handle_cancel_signal(signum, frame) -> None:
    del signum, frame
    _CANCEL_EVENT.set()


def _init_worker_environment() -> None:
    """Initialize process-wide worker settings and reusable heavy modules once."""
    import importlib
    import os
    import warnings

    os.environ.setdefault("ORT_LOGGING_LEVEL", "3")
    os.environ.setdefault("YOLO_VERBOSE", "False")
    configure_hf_environment()
    warnings.filterwarnings("ignore", category=UserWarning, module=r"torch\.cuda")

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _handle_cancel_signal)
            except (ValueError, OSError):
                pass

    if "cv2" not in globals():
        globals()["cv2"] = importlib.import_module("cv2")
    if "YOLO" not in globals():
        globals()["YOLO"] = importlib.import_module("ultralytics").YOLO
    if "draw_skeleton" not in globals():
        try:
            rtmlib = importlib.import_module("rtmlib")
            globals()["draw_skeleton"] = rtmlib.draw_skeleton
        except ImportError:
            pass


def _apply_worker_config(config_path: Path) -> None:
    """Reset ENGINE_DEFAULTS globals completely, then apply config JSON overrides."""
    global _CANCEL_FLAG_FILE
    import importlib

    _CANCEL_EVENT.clear()
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    cancel_file_raw = raw_config.pop("__CANCEL_FLAG_FILE__", None)
    _CANCEL_FLAG_FILE = (
        Path(cancel_file_raw)
        if cancel_file_raw
        else config_path.with_suffix(".cancel")
    )
    raw_output_mode = raw_config.pop("__OUTPUT_MODE__", raw_config.pop("OUTPUT_MODE", None))

    settings = normalize_legacy_rtmlib_settings(raw_config)
    unknown = set(settings) - set(ENGINE_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")

    for key, default_val in ENGINE_DEFAULTS.items():
        globals()[key] = deepcopy(default_val)

    for key, value in settings.items():
        if key in PATH_SETTING_KEYS and value is not None:
            value = Path(value).expanduser()
        globals()[key] = value
    globals()["OUTPUT_MODE"] = normalize_output_mode(raw_output_mode)

    if "cv2" not in globals():
        globals()["cv2"] = importlib.import_module("cv2")
    if "YOLO" not in globals():
        globals()["YOLO"] = importlib.import_module("ultralytics").YOLO
    if normalize_pose_engine(globals().get("POSE_ENGINE")) == "rtmpose":
        if "RTMPose" not in globals() or "draw_skeleton" not in globals():
            rtmlib = importlib.import_module("rtmlib")
            globals()["RTMPose"] = rtmlib.RTMPose
            globals()["draw_skeleton"] = rtmlib.draw_skeleton
    elif "draw_skeleton" not in globals():
        try:
            rtmlib = importlib.import_module("rtmlib")
            globals()["draw_skeleton"] = rtmlib.draw_skeleton
        except ImportError:
            pass


def run_analysis_worker(config_path: Path) -> None:
    """同じgui.pyを解析ワーカーとして起動した場合のエントリーポイント。"""
    _init_worker_environment()
    _apply_worker_config(config_path)
    try:
        run_analysis()
    except AnalysisCancelledError as exc:
        print(str(exc), flush=True)
        sys.exit(1)


def run_persistent_worker(initial_config: Path | None = None) -> None:
    """常駐ワーカーとして複数ジョブを連続処理するエントリーポイント。"""
    del initial_config
    _init_worker_environment()
    cache = WorkerModelCache()
    try:
        print("WORKER_READY", flush=True)
        while True:
            raw_line = sys.stdin.readline()
            if not raw_line:
                break
            command = raw_line.strip()
            if not command:
                continue
            if command == "SHUTDOWN":
                break
            if command.startswith("RUN_JOB:"):
                job_config_path = Path(command[len("RUN_JOB:") :].strip())
                exit_code = 0
                try:
                    _apply_worker_config(job_config_path)
                    run_analysis(model_cache=cache)
                except AnalysisCancelledError as exc:
                    print(str(exc), flush=True)
                    exit_code = 1
                except Exception:
                    import traceback

                    traceback.print_exc(file=sys.stdout)
                    sys.stdout.flush()
                    exit_code = 1
                print(f"JOB_DONE:{exit_code}", flush=True)
            else:
                print(f"Unknown persistent worker command: {command}", flush=True)
    finally:
        cache.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="動画姿勢推定 GUI / 解析ワーカー")
    parser.add_argument("--analysis-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--persistent-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--debug", action="store_true", help="PyWebView デバッグモードを有効にする")
    parser.add_argument("--dev", action="store_true", help="Vite 開発サーバー (http://localhost:5173) に接続する")
    args = parser.parse_args()
    if args.persistent_worker:
        run_persistent_worker(args.config)
    elif args.analysis_worker:
        if args.config is None:
            parser.error("解析ワーカーには --config が必要です")
        run_analysis_worker(args.config)
    else:
        try:
            from pose_ui_webview import launch_webview_gui
        except ImportError as exc:
            print(
                f"PyWebView GUIの起動に失敗しました: {exc}\n"
                "必要なパッケージ（pywebview）がインストールされているか確認してください。",
                file=sys.stderr,
            )
            sys.exit(1)
        launch_webview_gui(debug=args.debug, dev_server=args.dev)
