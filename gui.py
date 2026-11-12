from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import math
import queue
import subprocess
import sys
import threading
from pathlib import Path
from time import perf_counter

from pose_estimators import (
    BasePoseEstimator,
    RTMLIB_POSE_ASSETS,
    VITPOSE_ASSETS,
    clear_cuda_cache as _estimator_clear_cuda_cache,
    create_pose_estimator as _factory_create_pose_estimator,
    draw_pose_skeleton,
    resolve_rtmlib_selection,
    resolve_vitpose_selection,
    validate_pose_settings,
)
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

# 撮影日時を取得するサムネイル画像のフォルダとファイル名を指定してください。
THUMBNAIL_ROOT = (
    Path.home()
    / "解析用動画ファイル"
    / "9-18-SMZ"
    / "THMBNL"
)
THUMBNAIL_IMAGE_NAME = "H7.JPG"

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

# YOLO/ByteTrack設定。YOLO_MODELは初回実行時に自動ダウンロードされます。
# 高速なnではなく、精度優先のmを使用します。
YOLO_MODEL = "yolo11m.pt"
YOLO_TRACKER = "bytetrack.yaml"
YOLO_IMAGE_SIZE = 1280
YOLO_CONFIDENCE = 0.20
YOLO_IOU = 0.50
YOLO_CLASSES = [0]  # COCOのperson
YOLO_BATCH_SIZE = 1

# 対象選択。指定した場合だけ、そのYOLO追跡IDを対象にします。
# Noneの場合は、動画全体の移動量から対象IDを自動選択します。
YOLO_TRACK_ID = None



# 対象人物のクロップ設定。0.25は上下左右に25%相当の余白を追加します。
CROP_PADDING_RATIO = 0.25
TARGET_REACQUIRE_MAX_DISTANCE = 300.0
TARGET_REACQUIRE_MIN_IOU = 0.05

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

#各種設定
KEYPOINT_THRESHOLD = 0.45
TRACK_MAX_DISTANCE = 250.0
TRACK_MAX_MISSED_FRAMES = 8
CSV_MAX_PERSONS = 3
TRACK_MATCH_THRESHOLD = 2.0
TRACK_CENTER_WEIGHT = 0.35
TRACK_KEYPOINT_WEIGHT = 0.35
TRACK_POSE_WEIGHT = 0.20
TRACK_BBOX_WEIGHT = 0.10
TRACK_VELOCITY_SMOOTHING = 0.35
TRACK_RAW_ID_BONUS = 2.0
TRACK_PREDICTED_BOX_WEIGHT = 0.35
TRACK_PREDICTION_MAX_FRAMES = 2
TARGET_TRACK_MATCH_THRESHOLD = 0.75
TARGET_TRACK_MIN_IOU = 0.15
TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING = True
TARGET_LOCK_RAW_ID = True
TARGET_SELECTION_MIN_FRAMES = 15
TARGET_SELECTION_COVERAGE_WEIGHT = 0.5
TARGET_BOX_FILL_MAX_FRAMES = 60
POSE_TRACK_KEYPOINT_WEIGHT = 0.65
POSE_TRACK_CENTER_WEIGHT = 0.25
POSE_TRACK_SHAPE_WEIGHT = 0.10
POSE_BOX_IOU_WEIGHT = 2.0
POSE_BOX_CENTER_WEIGHT = 0.5
POSE_TEMPORAL_WEIGHT = 0.5


ENGINE_SETTING_NAMES = (
    "INPUT_ROOT", "INPUT_VIDEO_NAME", "THUMBNAIL_ROOT", "THUMBNAIL_IMAGE_NAME",
    "OUTPUT_ROOT", "OUTPUT_FOLDER_NAME", "OUTPUT_VIDEO_NAME", "OUTPUT_CROP_VIDEO_NAME",
    "OUTPUT_CROP_SKELETON_VIDEO_NAME", "OUTPUT_CSV_NAME", "OUTPUT_METADATA_NAME", "YOLO_MODEL", "YOLO_TRACKER",
    "YOLO_IMAGE_SIZE", "YOLO_CONFIDENCE", "YOLO_IOU", "YOLO_CLASSES", "YOLO_BATCH_SIZE", "YOLO_TRACK_ID",
    "CROP_PADDING_RATIO", "TARGET_REACQUIRE_MAX_DISTANCE", "TARGET_REACQUIRE_MIN_IOU",
    "POSE_ENGINE", "BACKEND", "DEVICE", "RTMLIB_POSE_MODEL", "RTMLIB_POSE_INPUT_SIZE",
    "RTMPOSE_BATCH_SIZE", "VITPOSE_MODEL", "VITPOSE_INPUT_SIZE",
    "VITPOSE_BATCH_SIZE", "VITPOSE_FLIP_TEST", "KEYPOINT_THRESHOLD", "TRACK_MAX_DISTANCE",
    "TRACK_MAX_MISSED_FRAMES", "CSV_MAX_PERSONS", "TRACK_MATCH_THRESHOLD",
    "TRACK_CENTER_WEIGHT", "TRACK_KEYPOINT_WEIGHT", "TRACK_POSE_WEIGHT", "TRACK_BBOX_WEIGHT",
    "TRACK_VELOCITY_SMOOTHING", "TRACK_RAW_ID_BONUS", "TRACK_PREDICTED_BOX_WEIGHT",
    "TRACK_PREDICTION_MAX_FRAMES", "TARGET_TRACK_MATCH_THRESHOLD", "TARGET_TRACK_MIN_IOU",
    "TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING", "TARGET_LOCK_RAW_ID", "TARGET_SELECTION_MIN_FRAMES",
    "TARGET_SELECTION_COVERAGE_WEIGHT", "TARGET_BOX_FILL_MAX_FRAMES", "POSE_TRACK_KEYPOINT_WEIGHT",
    "POSE_TRACK_CENTER_WEIGHT", "POSE_TRACK_SHAPE_WEIGHT", "POSE_BOX_IOU_WEIGHT",
    "POSE_BOX_CENTER_WEIGHT", "POSE_TEMPORAL_WEIGHT",
)
ENGINE_DEFAULTS = {key: globals()[key] for key in ENGINE_SETTING_NAMES}
PATH_SETTING_KEYS = {"INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"}
OUTPUT_NAME_KEYS = {
    "OUTPUT_VIDEO_NAME",
    "OUTPUT_CROP_VIDEO_NAME",
    "OUTPUT_CROP_SKELETON_VIDEO_NAME",
    "OUTPUT_CSV_NAME",
    "OUTPUT_METADATA_NAME",
}

DEFAULTS = {
    "INPUT_VIDEO_FILE": str(INPUT_ROOT / INPUT_VIDEO_NAME),
    "THUMBNAIL_FILE": str(THUMBNAIL_ROOT / THUMBNAIL_IMAGE_NAME),
    "OUTPUT_DIRECTORY": str(OUTPUT_ROOT / OUTPUT_FOLDER_NAME),
}
DEFAULTS.update({
    key: value for key, value in ENGINE_DEFAULTS.items()
    if key not in PATH_SETTING_KEYS and key not in OUTPUT_NAME_KEYS
})

GROUPS = [
    ("入力・出力", ["INPUT_VIDEO_FILE", "THUMBNAIL_FILE", "OUTPUT_DIRECTORY"]),
    ("YOLO・対象人物", ["YOLO_MODEL", "YOLO_TRACKER", "YOLO_IMAGE_SIZE", "YOLO_CONFIDENCE",
                    "YOLO_IOU", "YOLO_CLASSES", "YOLO_BATCH_SIZE", "YOLO_TRACK_ID", "CROP_PADDING_RATIO",
                    "TARGET_REACQUIRE_MAX_DISTANCE", "TARGET_REACQUIRE_MIN_IOU",
                    "TARGET_SELECTION_MIN_FRAMES", "TARGET_SELECTION_COVERAGE_WEIGHT",
                    "TARGET_BOX_FILL_MAX_FRAMES"]),
    ("姿勢推定・追跡", ["POSE_ENGINE", "RTMLIB_POSE_MODEL", "RTMLIB_POSE_INPUT_SIZE",
                     "RTMPOSE_BATCH_SIZE", "VITPOSE_MODEL", "VITPOSE_INPUT_SIZE",
                     "VITPOSE_BATCH_SIZE", "VITPOSE_FLIP_TEST", "BACKEND", "DEVICE",
                     "KEYPOINT_THRESHOLD", "CSV_MAX_PERSONS",
                     "TRACK_MAX_DISTANCE", "TRACK_MAX_MISSED_FRAMES", "TRACK_MATCH_THRESHOLD",
                     "TRACK_CENTER_WEIGHT", "TRACK_KEYPOINT_WEIGHT", "TRACK_POSE_WEIGHT",
                     "TRACK_BBOX_WEIGHT", "TRACK_VELOCITY_SMOOTHING", "TRACK_RAW_ID_BONUS",
                     "TRACK_PREDICTED_BOX_WEIGHT", "TRACK_PREDICTION_MAX_FRAMES",
                     "TARGET_TRACK_MATCH_THRESHOLD", "TARGET_TRACK_MIN_IOU",
                     "TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING", "TARGET_LOCK_RAW_ID",
                     "POSE_TRACK_KEYPOINT_WEIGHT", "POSE_TRACK_CENTER_WEIGHT", "POSE_TRACK_SHAPE_WEIGHT",
                     "POSE_BOX_IOU_WEIGHT", "POSE_BOX_CENTER_WEIGHT", "POSE_TEMPORAL_WEIGHT"]),
]
PATH_KEYS = {"OUTPUT_DIRECTORY"}
FILE_KEYS = {"INPUT_VIDEO_FILE", "THUMBNAIL_FILE"}
BOOL_KEYS = {key for key, value in DEFAULTS.items() if isinstance(value, bool)}
INT_KEYS = {key for key, value in DEFAULTS.items() if isinstance(value, int) and not isinstance(value, bool)}
FLOAT_KEYS = {key for key, value in DEFAULTS.items() if isinstance(value, float)}
LABELS = {
    "INPUT_VIDEO_FILE": "入力動画",
    "THUMBNAIL_FILE": "撮影日時用サムネイル（任意）",
    "OUTPUT_DIRECTORY": "出力先フォルダ",
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
    "DEVICE": "実行デバイス（YOLO・姿勢推定）",
}
CHOICES = {
    "YOLO_MODEL": ("n", "s", "m", "l", "x"),
    "POSE_ENGINE": ("rtmpose", "vitpose"),
    "RTMLIB_POSE_MODEL": ("t", "s", "m", "l", "x"),
    "RTMLIB_POSE_INPUT_SIZE": ("256x192", "384x288"),
    "VITPOSE_MODEL": ("s", "b", "l", "h"),
    "VITPOSE_INPUT_SIZE": ("256x192",),
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
    return out


def build_job_summary(settings: dict) -> dict:
    """Build UI summary fields for a serialized reservation job."""
    return {
        "pose_engine": normalize_pose_engine(settings.get("POSE_ENGINE", "rtmpose")),
        "pose_model": settings.get("RTMLIB_POSE_MODEL", "x"),
        "pose_input_size": settings.get("RTMLIB_POSE_INPUT_SIZE", "384x288"),
        "vitpose_model": str(settings.get("VITPOSE_MODEL", "h")).lower(),
        "vitpose_input_size": str(settings.get("VITPOSE_INPUT_SIZE", "256x192")),
        "vitpose_flip_test": bool(settings.get("VITPOSE_FLIP_TEST", True)),
        "yolo_model": settings.get("YOLO_MODEL", "yolo11m.pt"),
        "device": settings.get("DEVICE", "auto"),
        "track_id": settings.get("YOLO_TRACK_ID"),
        "csv_max_persons": settings.get("CSV_MAX_PERSONS", 3),
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


def write_video_metadata(
    input_video: Path,
    output_path: Path,
    total_frames: int,
    width: int,
    height: int,
    fps: float,
) -> None:
    recorded_at = get_recorded_at(input_video)
    duration_seconds = total_frames / fps if fps > 0 else 0.0
    
    output_path.write_text(
        "元動画情報\n"
        "====================\n"
        f"元動画: {input_video.resolve()}\n"
        f"動画の撮影日時: {recorded_at}\n"
        f"総フレーム数: {total_frames}\n"
        f"解像度（横 x 縦）: {width} x {height}\n"
        f"FPS（1秒あたりのフレーム数）: {fps:.6f}\n"
        f"動画全体の長さ（秒）: {duration_seconds:.3f}\n",
        encoding="utf-8",
    )


def get_recorded_at(input_video: Path) -> str:
    thumbnail_path = THUMBNAIL_ROOT / THUMBNAIL_IMAGE_NAME
    metadata_source = (
        thumbnail_path
        if thumbnail_path.is_file()
        else input_video
    )

    # DateTimeOriginalを優先し、記録がない場合だけCreateDateを使う。
    for date_tag in ("DateTimeOriginal", "CreateDate"):
        try:
            result = subprocess.run(
                [
                    "exiftool",
                    "-s3",
                    f"-{date_tag}",
                    str(metadata_source),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                value = line.strip()
                if value:
                    return value
        except FileNotFoundError:
            break

    # 2. ExifTool がない場合は ffprobe で全メタデータから撮影日時タグを優先検索する
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format_tags:stream_tags",
                "-of",
                "default=noprint_wrappers=1",
                str(metadata_source),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        tags = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                tags[k.lower()] = v.strip()

        # 編集日の可能性が高い creation_time より前に、オリジナルの撮影日時タグを検索
        priority_keys = [
            "tag:datetimeoriginal",
            "tag:date",
            "tag:com.sony.mxf.datetime",
            "tag:creation_time",
        ]
        for key in priority_keys:
            if key in tags:
                value = tags[key]
                try:
                    recorded_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return recorded_at.astimezone().isoformat(sep=" ", timespec="seconds")
                except ValueError:
                    return value
    except FileNotFoundError:
        return "取得不可（ffprobe/exiftoolがインストールされていません）"

    return "取得不可（動画内に撮影日時メタデータがありません）"


def clamp_box(box, width: int, height: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return (
        max(0, int(left)),
        max(0, int(top)),
        min(width, int(right)),
        min(height, int(bottom)),
    )


def padded_crop_box(box, width: int, height: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    box_width = right - left
    box_height = bottom - top
    return clamp_box(
        (
            left - box_width * CROP_PADDING_RATIO,
            top - box_height * CROP_PADDING_RATIO,
            right + box_width * CROP_PADDING_RATIO,
            bottom + box_height * CROP_PADDING_RATIO,
        ),
        width,
        height,
    )


def box_center(box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def choose_target_yolo_box(boxes, target_track_id, previous_box):
    candidates = []
    for index, box in enumerate(boxes):
        xyxy = tuple(float(value) for value in box.xyxy[0].tolist())
        track_id = None if box.id is None else int(box.id[0].item())
        candidates.append({"index": index, "xyxy": xyxy, "track_id": track_id})
    if target_track_id is not None:
        for candidate in candidates:
            if candidate["track_id"] == target_track_id:
                return candidate
    if previous_box is None:
        return None
    previous_center = box_center(previous_box)
    recovery_candidates = []
    for candidate in candidates:
        center_distance = math.dist(previous_center, box_center(candidate["xyxy"]))
        overlap = bbox_iou(previous_box, candidate["xyxy"])
        if (
            center_distance <= TARGET_REACQUIRE_MAX_DISTANCE
            or overlap >= TARGET_REACQUIRE_MIN_IOU
        ):
            recovery_candidates.append((overlap, -center_distance, candidate))
    if not recovery_candidates:
        return None
    return max(recovery_candidates, key=lambda item: (item[0], item[1]))[2]


def pose_match_cost(
    keypoints,
    scores,
    target_center,
    previous_keypoints,
    previous_scores,
) -> float:
    geometry = get_person_geometry(keypoints, scores)
    crop_scale = max(
        math.hypot(
            geometry["bbox"][2] - geometry["bbox"][0],
            geometry["bbox"][3] - geometry["bbox"][1],
        ),
        1.0,
    )
    center_cost = math.dist(geometry["center"], target_center) / crop_scale
    reliable_indices = [
        index
        for index, score in enumerate(scores)
        if float(score) >= KEYPOINT_THRESHOLD
        and float(previous_scores[index]) >= KEYPOINT_THRESHOLD
    ]
    if not reliable_indices:
        reliable_indices = list(range(min(len(keypoints), len(previous_keypoints))))
    keypoint_costs = []
    shape_costs = []
    current_center = geometry["center"]
    previous_geometry = get_person_geometry(previous_keypoints, previous_scores)
    for index in reliable_indices:
        current_point = (
            float(keypoints[index][0]),
            float(keypoints[index][1]),
        )
        previous_point = (
            float(previous_keypoints[index][0]),
            float(previous_keypoints[index][1]),
        )
        keypoint_costs.append(math.dist(current_point, previous_point) / crop_scale)
        current_relative = (
            current_point[0] - current_center[0],
            current_point[1] - current_center[1],
        )
        previous_relative = (
            previous_point[0] - previous_geometry["center"][0],
            previous_point[1] - previous_geometry["center"][1],
        )
        shape_costs.append(math.dist(current_relative, previous_relative) / crop_scale)
    return (
        POSE_TRACK_KEYPOINT_WEIGHT * (sum(keypoint_costs) / len(keypoint_costs))
        + POSE_TRACK_CENTER_WEIGHT * center_cost
        + POSE_TRACK_SHAPE_WEIGHT * (sum(shape_costs) / len(shape_costs))
    )


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


def cap_rtmpose_batch_by_vram(requested: int, device: str, pose_model) -> int:
    """Cap RTMPose batch size conservatively from remaining free VRAM."""
    if requested <= 1:
        return requested
    mem_info = _get_cuda_free_total_gb(device)
    if mem_info is None:
        return requested
    free_gb, _ = mem_info
    input_size = getattr(pose_model, "model_input_size", (192, 256))
    try:
        in_w, in_h = int(input_size[0]), int(input_size[1])
    except (TypeError, ValueError, IndexError):
        in_w, in_h = 192, 256
    usable_gb = max(0.4, free_gb * 0.85 - 0.4)
    area_factor = max(1, in_w * in_h) / (192.0 * 256.0)
    est_gb_per_frame = 0.028 * area_factor
    max_safe = max(1, int(usable_gb / max(est_gb_per_frame, 1e-4)))
    if requested > max_safe:
        print(
            f"RTMPose: 利用可能VRAM ({free_gb:.1f} GB) に合わせてバッチサイズを "
            f"{requested} -> {max_safe} に自動調整しました",
            flush=True,
        )
        return max_safe
    return requested


def supports_dynamic_batch(pose_model) -> tuple[bool, object]:
    """Check whether the loaded pose model ONNX session supports a dynamic batch axis."""
    session = getattr(pose_model, "session", None)
    if session is None:
        return False, "no-onnx-session"
    try:
        inputs = session.get_inputs()
    except Exception:
        return False, "unknown"
    if not inputs or not getattr(inputs[0], "shape", None):
        return False, "unknown"
    batch_dim = inputs[0].shape[0]
    if isinstance(batch_dim, int) and batch_dim > 0:
        return False, batch_dim
    return True, batch_dim


def _ensure_pose_preprocess_ready(pose_model) -> None:
    """Convert mean/std once so concurrent or repeated preprocess calls avoid re-allocation."""
    import numpy as np

    if getattr(pose_model, "mean", None) is not None and not isinstance(
        pose_model.mean, np.ndarray
    ):
        pose_model.mean = np.array(pose_model.mean)
    if getattr(pose_model, "std", None) is not None and not isinstance(
        pose_model.std, np.ndarray
    ):
        pose_model.std = np.array(pose_model.std)


def _write_chw_float32_into(preprocessed_img, dest) -> None:
    """Copy rtmlib RTMPose.preprocess output directly into a pre-allocated (3, H, W) float32 slice."""
    import numpy as np

    arr = np.asarray(preprocessed_img)
    if arr.ndim == 4 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.ndim == 3 and arr.shape[2] == 3:
        np.copyto(dest, np.transpose(arr, (2, 0, 1)), casting="unsafe")
    elif arr.ndim == 3 and arr.shape[0] == 3:
        np.copyto(dest, arr, casting="unsafe")
    else:
        raise ValueError(f"Unexpected preprocessed RTMPose shape: {arr.shape}")


def _to_chw_float32(preprocessed_img):
    """Normalize rtmlib RTMPose.preprocess image output to contiguous (3, H, W) float32."""
    import numpy as np

    arr = np.asarray(preprocessed_img, dtype=np.float32)
    if arr.ndim == 4 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.ndim == 3 and arr.shape[2] == 3:
        arr = np.transpose(arr, (2, 0, 1))
    elif arr.ndim != 3 or arr.shape[0] != 3:
        raise ValueError(f"Unexpected preprocessed RTMPose shape: {arr.shape}")
    return np.ascontiguousarray(arr, dtype=np.float32)


def _extract_single_pose(keypoints, scores):
    """Extract 1-person (keypoints, scores) arrays from rtmlib RTMPose output."""
    import numpy as np

    if keypoints is None or scores is None or len(keypoints) == 0:
        return None, None
    kpts_arr = np.asarray(keypoints, dtype=np.float32)
    scores_arr = np.asarray(scores, dtype=np.float32)
    if kpts_arr.ndim == 3:
        kpts_arr = kpts_arr[0]
    if scores_arr.ndim == 2:
        scores_arr = scores_arr[0]
    if len(kpts_arr) == 0:
        return None, None
    return [(float(pt[0]), float(pt[1])) for pt in kpts_arr], scores_arr


def _clamped_target_box(target_box, width: int, height: int):
    if target_box is None:
        return None
    clamped = clamp_box(target_box, width, height)
    if clamped[2] <= clamped[0] or clamped[3] <= clamped[1]:
        return None
    return [float(clamped[0]), float(clamped[1]), float(clamped[2]), float(clamped[3])]


def _prepare_pose_crop(pose_model, frame, clamped_box):
    """Affine-crop frame for RTMPose and return (preprocessed, crop_bgr, center, scale)."""
    import numpy as np
    from rtmlib.tools.pose_estimation.rtmpose import bbox_xyxy2cs, top_down_affine

    _ensure_pose_preprocess_ready(pose_model)
    center, scale = bbox_xyxy2cs(np.asarray(clamped_box, dtype=np.float32), padding=1.25)
    crop_bgr, scale = top_down_affine(pose_model.model_input_size, scale, center, frame)
    preprocessed = crop_bgr
    if (
        getattr(pose_model, "mean", None) is not None
        and getattr(pose_model, "std", None) is not None
    ):
        preprocessed = (crop_bgr - pose_model.mean) / pose_model.std
    return preprocessed, crop_bgr, center, scale


def render_pose_on_crop(
    crop_bgr,
    restored_keypoints,
    pose_scores,
    center,
    scale,
    model_input_size,
):
    """Draw skeleton only (no text overlays) onto the RTMPose input crop image."""
    import numpy as np

    if crop_bgr is None:
        return None
    annotated = crop_bgr.copy()
    if restored_keypoints is None or pose_scores is None:
        return annotated
    scale_arr = np.asarray(scale, dtype=np.float32)
    center_arr = np.asarray(center, dtype=np.float32)
    size_arr = np.asarray(model_input_size, dtype=np.float32)
    safe_scale = np.where(scale_arr == 0, 1.0, scale_arr)
    crop_kpts = (
        (np.asarray(restored_keypoints, dtype=np.float32) - (center_arr - scale_arr / 2.0))
        / safe_scale
        * size_arr
    )
    return draw_skeleton(
        annotated,
        crop_kpts[None, :, :],
        np.asarray([pose_scores], dtype=np.float32),
        kpt_thr=KEYPOINT_THRESHOLD,
    )


def infer_pose_single(pose_model, frame, target_box, *, return_crop: bool = False):
    """Run RTMPose directly on target_box for a single frame."""
    height, width = frame.shape[:2]
    clamped = _clamped_target_box(target_box, width, height)
    if clamped is None:
        return ((None, None), None) if return_crop else (None, None)
    if return_crop:
        preprocessed, crop_bgr, center, scale = _prepare_pose_crop(
            pose_model, frame, clamped
        )
        outputs = pose_model.inference(preprocessed)
        keypoints, scores = pose_model.postprocess(outputs, center, scale)
        kpts, scs = _extract_single_pose(keypoints, scores)
        return (kpts, scs), (crop_bgr, center, scale)
    keypoints, scores = pose_model(frame, bboxes=[clamped])
    return _extract_single_pose(keypoints, scores)


def infer_pose_batch(
    pose_model,
    batch_items,
    fixed_batch_size: int | None = None,
    batch_buffer: dict | None = None,
    *,
    return_crop: bool = False,
):
    """Run batched RTMPose inference via ONNX Runtime for [(frame, target_box), ...].

    When ``fixed_batch_size`` is set above ``len(valid)``, the tensor is padded to
    ``fixed_batch_size`` so ONNX Runtime always sees a constant input shape.
    """
    import numpy as np

    if not batch_items:
        return []
    if len(batch_items) == 1 and (fixed_batch_size is None or fixed_batch_size <= 1):
        frame, target_box = batch_items[0]
        return [
            infer_pose_single(
                pose_model, frame, target_box, return_crop=return_crop
            )
        ]

    _ensure_pose_preprocess_ready(pose_model)

    prepared = []
    valid_metas = []
    batch_tensor = None
    tensor_idx = 0
    target_cap = max(len(batch_items), fixed_batch_size or 0)

    def _ensure_buffer(sample_h: int, sample_w: int):
        nonlocal batch_tensor
        if batch_buffer is not None:
            buf = batch_buffer.get("tensor")
            if buf is None or buf.shape != (target_cap, 3, sample_h, sample_w):
                buf = np.empty((target_cap, 3, sample_h, sample_w), dtype=np.float32)
                batch_buffer["tensor"] = buf
            batch_tensor = buf
        else:
            batch_tensor = np.empty((target_cap, 3, sample_h, sample_w), dtype=np.float32)

    for frame, target_box in batch_items:
        height, width = frame.shape[:2]
        clamped = _clamped_target_box(target_box, width, height)
        if clamped is None:
            prepared.append(None)
            continue
        if return_crop:
            preprocessed, crop_bgr, center, scale = _prepare_pose_crop(
                pose_model, frame, clamped
            )
            crop_info = (crop_bgr, center, scale)
        else:
            preprocessed, center, scale = pose_model.preprocess(frame, clamped)
            crop_info = None
        arr = np.asarray(preprocessed)
        if arr.ndim == 4 and arr.shape[0] == 1:
            arr = arr[0]
        if arr.ndim == 3 and arr.shape[2] == 3:
            sample_h, sample_w = arr.shape[0], arr.shape[1]
        elif arr.ndim == 3 and arr.shape[0] == 3:
            sample_h, sample_w = arr.shape[1], arr.shape[2]
        else:
            raise ValueError(f"Unexpected preprocessed RTMPose shape: {arr.shape}")

        if batch_tensor is None:
            _ensure_buffer(sample_h, sample_w)
        _write_chw_float32_into(arr, batch_tensor[tensor_idx])
        tensor_idx += 1
        meta = (center, scale, crop_info)
        valid_metas.append(meta)
        prepared.append(meta)

    valid_count = len(valid_metas)
    if valid_count == 0 or batch_tensor is None:
        empty_item = ((None, None), None) if return_crop else (None, None)
        return [empty_item for _ in batch_items]

    run_count = fixed_batch_size if (fixed_batch_size and fixed_batch_size >= valid_count) else valid_count
    if run_count > valid_count:
        batch_tensor[valid_count:run_count] = batch_tensor[0]
    feed_tensor = batch_tensor if run_count == batch_tensor.shape[0] else batch_tensor[:run_count]

    session = pose_model.session
    input_name = session.get_inputs()[0].name
    output_names = [out.name for out in session.get_outputs()]
    raw_outputs = session.run(output_names, {input_name: feed_tensor})
    if run_count > valid_count:
        raw_outputs = [out[:valid_count] for out in raw_outputs]

    # Try vectorized batch postprocessing across all valid items at once.
    valid_results = None
    if len(raw_outputs) == 2 and valid_count > 1:
        try:
            centers = np.asarray([m[0] for m in valid_metas])[:, None, :]
            scales = np.asarray([m[1] for m in valid_metas])[:, None, :]
            kpts_batch, scores_batch = pose_model.postprocess(raw_outputs, centers, scales)
            kpts_arr = np.asarray(kpts_batch, dtype=np.float32)
            scores_arr = np.asarray(scores_batch, dtype=np.float32)
            if kpts_arr.ndim == 3 and kpts_arr.shape[0] == valid_count:
                valid_results = [
                    ([(float(pt[0]), float(pt[1])) for pt in kpts_arr[i]], scores_arr[i])
                    for i in range(valid_count)
                ]
        except Exception:
            valid_results = None

    if valid_results is None:
        valid_results = []
        for idx, (center, scale, _crop_info) in enumerate(valid_metas):
            item_outputs = [out[idx : idx + 1] for out in raw_outputs]
            kpts, scs = pose_model.postprocess(item_outputs, center, scale)
            valid_results.append(_extract_single_pose(kpts, scs))

    results = []
    valid_iter = iter(valid_results)
    for meta in prepared:
        if meta is None:
            results.append(((None, None), None) if return_crop else (None, None))
        else:
            pose_pair = next(valid_iter)
            if return_crop:
                results.append((pose_pair, meta[2]))
            else:
                results.append(pose_pair)
    return results


def annotate_pose_on_frame(frame, target_box, restored_keypoints, pose_scores) -> None:
    """Draw skeleton on the padded crop region of frame in-place."""
    import numpy as np

    if restored_keypoints is None or pose_scores is None or target_box is None:
        return
    height, width = frame.shape[:2]
    crop_left, crop_top, crop_right, crop_bottom = padded_crop_box(
        target_box, width, height
    )
    crop = frame[crop_top:crop_bottom, crop_left:crop_right]
    if crop.size == 0:
        return
    local_kpts = np.asarray(
        [[(float(x) - crop_left, float(y) - crop_top) for x, y in restored_keypoints]],
        dtype=np.float32,
    )
    local_scores = np.asarray([pose_scores], dtype=np.float32)
    annotated_crop = draw_pose_skeleton(
        crop.copy(),
        local_kpts,
        local_scores,
        kpt_thr=KEYPOINT_THRESHOLD,
    )
    frame[crop_top:crop_bottom, crop_left:crop_right] = annotated_crop


def pose_from_crop(pose_model, frame, target_box, previous_keypoints=None, previous_scores=None):
    """Run RTMPose directly on YOLO target_box and draw skeleton onto frame."""
    restored_keypoints, pose_scores = infer_pose_single(pose_model, frame, target_box)
    if restored_keypoints is None:
        return None, None, None
    annotate_pose_on_frame(frame, target_box, restored_keypoints, pose_scores)
    height, width = frame.shape[:2]
    return restored_keypoints, pose_scores, padded_crop_box(target_box, width, height)


def get_person_geometry(person_keypoints, person_scores) -> dict:
    points = [
        (float(point[0]), float(point[1]))
        for point, score in zip(person_keypoints, person_scores)
        if float(score) >= KEYPOINT_THRESHOLD
    ]
    if len(points) < 3:
        points = [(float(point[0]), float(point[1])) for point in person_keypoints]
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    return {
        "center": (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        ),
        "bbox": (min_x, min_y, max_x, max_y),
    }


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


def get_match_cost(track, keypoints, scores, geometry) -> float:
    elapsed_frames = track["missed_frames"] + 1
    predicted_center = (
        track["center"][0] + track["velocity"][0] * elapsed_frames,
        track["center"][1] + track["velocity"][1] * elapsed_frames,
    )
    center_scale = max(
        math.hypot(
            track["bbox"][2] - track["bbox"][0],
            track["bbox"][3] - track["bbox"][1],
        ),
        1.0,
    )
    center_cost = math.dist(predicted_center, geometry["center"]) / center_scale

    reliable_indices = [
        index for index, score in enumerate(scores)
        if float(score) >= KEYPOINT_THRESHOLD
    ]
    if not reliable_indices:
        reliable_indices = list(range(len(keypoints)))
    keypoint_distances = []
    pose_distances = []
    for index in reliable_indices:
        current = (float(keypoints[index][0]), float(keypoints[index][1]))
        previous = track["keypoints"][index]
        predicted = (
            previous[0] + track["velocity"][0] * elapsed_frames,
            previous[1] + track["velocity"][1] * elapsed_frames,
        )
        keypoint_distances.append(math.dist(current, predicted) / center_scale)
        current_relative = (
            current[0] - geometry["center"][0],
            current[1] - geometry["center"][1],
        )
        previous_relative = (
            previous[0] - track["center"][0],
            previous[1] - track["center"][1],
        )
        pose_distances.append(math.dist(current_relative, previous_relative) / center_scale)
    keypoint_cost = sum(keypoint_distances) / len(keypoint_distances)
    pose_cost = sum(pose_distances) / len(pose_distances)
    bbox_cost = 1.0 - bbox_iou(track["bbox"], geometry["bbox"])
    return (
        TRACK_CENTER_WEIGHT * center_cost
        + TRACK_KEYPOINT_WEIGHT * keypoint_cost
        + TRACK_POSE_WEIGHT * pose_cost
        + TRACK_BBOX_WEIGHT * bbox_cost
    )


def assign_person_ids(keypoints, scores, tracks, next_person_id):
    geometries = [
        get_person_geometry(person_keypoints, person_scores)
        for person_keypoints, person_scores in zip(keypoints, scores)
    ]
    for track in tracks.values():
        track["missed_frames"] += 1

    possible_matches = []
    for detection_index, (person_keypoints, person_scores, geometry) in enumerate(
        zip(keypoints, scores, geometries)
    ):
        for person_id, track in tracks.items():
            center_distance = math.dist(
                geometry["center"],
                (
                    track["center"][0] + track["velocity"][0],
                    track["center"][1] + track["velocity"][1],
                ),
            )
            if center_distance <= TRACK_MAX_DISTANCE * (track["missed_frames"] + 1):
                cost = get_match_cost(track, person_keypoints, person_scores, geometry)
                if cost <= TRACK_MATCH_THRESHOLD:
                    possible_matches.append((cost, detection_index, person_id))

    assigned_detections = set()
    assigned_ids = set()
    detection_ids = [None] * len(geometries)
    for _, detection_index, person_id in sorted(possible_matches):
        if detection_index in assigned_detections or person_id in assigned_ids:
            continue
        detection_ids[detection_index] = person_id
        assigned_detections.add(detection_index)
        assigned_ids.add(person_id)

    for detection_index, geometry in enumerate(geometries):
        person_id = detection_ids[detection_index]
        if person_id is None:
            person_id = next_person_id
            next_person_id += 1
            detection_ids[detection_index] = person_id
        center = geometry["center"]
        previous_track = tracks.get(person_id)
        velocity = (0.0, 0.0)
        if previous_track is not None and previous_track["missed_frames"] == 1:
            measured_velocity = (
                center[0] - previous_track["center"][0],
                center[1] - previous_track["center"][1],
            )
            velocity = (
                TRACK_VELOCITY_SMOOTHING * previous_track["velocity"][0]
                + (1 - TRACK_VELOCITY_SMOOTHING) * measured_velocity[0],
                TRACK_VELOCITY_SMOOTHING * previous_track["velocity"][1]
                + (1 - TRACK_VELOCITY_SMOOTHING) * measured_velocity[1],
            )
        tracks[person_id] = {
            "center": center,
            "bbox": geometry["bbox"],
            "keypoints": [
                (float(point[0]), float(point[1])) for point in keypoints[detection_index]
            ],
            "velocity": velocity,
            "missed_frames": 0,
        }

    expired_ids = [
        person_id
        for person_id, track in tracks.items()
        if track["missed_frames"] > TRACK_MAX_MISSED_FRAMES
    ]
    for person_id in expired_ids:
        del tracks[person_id]

    return detection_ids, next_person_id


def get_csv_fieldnames() -> list[str]:
    fieldnames = ["frame", "time_seconds"]
    for person_index in range(CSV_MAX_PERSONS):
        prefix = f"person_{person_index}"
        fieldnames.append(f"{prefix}_id")
        for name in COCO_KEYPOINTS:
            fieldnames.extend([
                f"{prefix}_{name}_x",
                f"{prefix}_{name}_y",
                f"{prefix}_{name}_score",
            ])
    return fieldnames


def make_csv_row(frame_data: dict) -> dict:
    row = {
        "frame": frame_data["frame"],
        "time_seconds": frame_data["time_seconds"],
    }
    for person_index in range(CSV_MAX_PERSONS):
        prefix = f"person_{person_index}"
        person = (
            frame_data["persons"][person_index]
            if person_index < len(frame_data["persons"])
            else None
        )
        row[f"{prefix}_id"] = "" if person is None else person["person_id"]
        for name in COCO_KEYPOINTS:
            keypoint = None if person is None else person[name]
            row[f"{prefix}_{name}_x"] = "" if keypoint is None else keypoint["x"]
            row[f"{prefix}_{name}_y"] = "" if keypoint is None else keypoint["y"]
            row[f"{prefix}_{name}_score"] = "" if keypoint is None else keypoint["score"]
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
        - (TRACK_RAW_ID_BONUS if raw_track_id == track["raw_track_id"] else 0.0)
    )


def stabilize_yolo_ids(
    boxes,
    tracks: dict,
    next_id: int,
    protected_stable_id: int | None = None,
):
    detections = [
        {
            "bbox": tuple(float(value) for value in box.xyxy[0].tolist()),
            "raw_track_id": None if box.id is None else int(box.id[0].item()),
        }
        for box in boxes
    ]
    for track in tracks.values():
        track["missed_frames"] += 1

    matches = []
    for detection_index, detection in enumerate(detections):
        for stable_id, track in tracks.items():
            if track["missed_frames"] <= TRACK_MAX_MISSED_FRAMES + 1:
                cost = yolo_box_cost(
                    track,
                    detection["bbox"],
                    detection["raw_track_id"],
                )
                if stable_id == protected_stable_id:
                    predicted_box = predict_track_box(track)
                    if (
                        TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING
                        and track["missed_frames"] > 0
                        and detection["raw_track_id"] != track["raw_track_id"]
                    ):
                        continue
                    protected_match = (
                        cost <= TARGET_TRACK_MATCH_THRESHOLD
                        and bbox_iou(predicted_box, detection["bbox"])
                        >= TARGET_TRACK_MIN_IOU
                    )
                    if not protected_match and (
                        detection["raw_track_id"] != track["raw_track_id"]
                    ):
                        continue
                if (
                    cost <= TRACK_MATCH_THRESHOLD
                    or detection["raw_track_id"] == track["raw_track_id"]
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
        velocity = (0.0, 0.0)
        if previous is not None and previous["missed_frames"] == 1:
            measured = (
                center[0] - previous["center"][0],
                center[1] - previous["center"][1],
            )
            velocity = (
                TRACK_VELOCITY_SMOOTHING * previous["velocity"][0]
                + (1.0 - TRACK_VELOCITY_SMOOTHING) * measured[0],
                TRACK_VELOCITY_SMOOTHING * previous["velocity"][1]
                + (1.0 - TRACK_VELOCITY_SMOOTHING) * measured[1],
            )
        tracks[stable_id] = {
            "center": center,
            "bbox": detection_box,
            "raw_track_id": detection["raw_track_id"],
            "velocity": velocity,
            "missed_frames": 0,
        }
        stable_ids[detection_index] = stable_id

    for stable_id in [
        stable_id
        for stable_id, track in tracks.items()
        if track["missed_frames"] > TRACK_MAX_MISSED_FRAMES
    ]:
        del tracks[stable_id]

    return [
        {
            "stable_id": stable_id,
            "bbox": detection["bbox"],
            "raw_track_id": detection["raw_track_id"],
        }
        for stable_id, detection in zip(stable_ids, detections)
    ], next_id


def select_moving_target_id(frame_detections, total_frames):
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

    first = observed[0]
    last = observed[-1]
    for index in range(max(0, first - TARGET_BOX_FILL_MAX_FRAMES), first):
        target_boxes[index] = target_boxes[first]
    for index in range(
        last + 1,
        min(len(target_boxes), last + TARGET_BOX_FILL_MAX_FRAMES + 1),
    ):
        target_boxes[index] = target_boxes[last]

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
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
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
    }


def create_pose_estimator_from_globals(device: str) -> BasePoseEstimator:
    """Build the configured BasePoseEstimator (RTMPose or ViTPose++) for Pass 2."""
    settings = _active_pose_settings_from_globals()
    estimator = _factory_create_pose_estimator(settings, device)
    print(f"姿勢モデル: {estimator.display_name}", flush=True)
    return estimator


def create_pose_model(device: str):
    """Backward-compatible helper returning the underlying rtmlib RTMPose instance."""
    from pose_estimators.rtmpose import RTMPoseEstimator

    estimator = RTMPoseEstimator(
        pose_model=RTMLIB_POSE_MODEL,
        pose_input_size=RTMLIB_POSE_INPUT_SIZE,
        backend=BACKEND,
        device=device,
    )
    print(f"姿勢モデル: {estimator.display_name}", flush=True)
    return estimator.raw_model


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


def run_yolo_pass(input_video: Path, progress_total_frames=0, device="cpu"):
    capture = cv2.VideoCapture(str(input_video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open input video: {input_video.resolve()}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = progress_total_frames or int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    configure_cuda_memory_fraction(device)
    detector = YOLO(YOLO_MODEL)
    effective_batch = resolve_effective_batch_size(YOLO_BATCH_SIZE, device, "YOLO")
    effective_batch = cap_yolo_batch_by_vram(
        effective_batch, device, YOLO_MODEL, YOLO_IMAGE_SIZE
    )
    print(f"YOLOバッチサイズ: {effective_batch}", flush=True)
    tracks = {}
    next_id = 0
    target_stable_id = YOLO_TRACK_ID
    frame_detections = []
    processed_frames = 0
    last_progress = -1
    print("PROGRESS:0:YOLO", flush=True)

    def _track_single(single_frame):
        return detector.track(
            single_frame,
            device=device,
            persist=True,
            tracker=YOLO_TRACKER,
            imgsz=YOLO_IMAGE_SIZE,
            conf=YOLO_CONFIDENCE,
            iou=YOLO_IOU,
            classes=YOLO_CLASSES,
            max_det=30,
            verbose=False,
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
                    tracker=YOLO_TRACKER,
                    imgsz=YOLO_IMAGE_SIZE,
                    conf=YOLO_CONFIDENCE,
                    iou=YOLO_IOU,
                    classes=YOLO_CLASSES,
                    max_det=30,
                    batch=len(frames_chunk),
                    verbose=False,
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
    try:
        while True:
            batch_frames = reader.read_batch(effective_batch)
            if not batch_frames:
                break
            _run_yolo_chunk(batch_frames)
    finally:
        try:
            reader.close()
        finally:
            capture.release()
            del detector
            _clear_cuda_cache()
    print(f"YOLO処理フレーム数: {processed_frames}（動画情報の値: {total_frames}）", flush=True)
    print("PROGRESS:50:YOLO", flush=True)
    if target_stable_id is None:
        target_stable_id = select_moving_target_id(
            frame_detections,
            len(frame_detections),
        )
    target_boxes = fill_target_box_gaps(frame_detections, target_stable_id)
    return frame_detections, target_boxes, target_stable_id, width, height, fps


def run_analysis() -> None:
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

    output_directory.mkdir(parents=True, exist_ok=True)

    metadata_capture = cv2.VideoCapture(str(input_video))
    if not metadata_capture.isOpened():
        raise RuntimeError(f"Could not open input video: {input_video.resolve()}")
    metadata_total_frames = int(metadata_capture.get(cv2.CAP_PROP_FRAME_COUNT))
    metadata_width = int(metadata_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    metadata_height = int(metadata_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    metadata_fps = metadata_capture.get(cv2.CAP_PROP_FPS) or 30.0
    metadata_capture.release()

    write_video_metadata(
        input_video,
        output_metadata,
        metadata_total_frames,
        metadata_width,
        metadata_height,
        metadata_fps,
    )

    yolo_started_at = perf_counter()
    _, target_boxes, target_stable_id, width, height, fps = run_yolo_pass(
        input_video,
        metadata_total_frames,
        device=yolo_device,
    )
    yolo_elapsed_seconds = perf_counter() - yolo_started_at

    # Pass 1 (YOLO) が解放された後にのみ Pass 2 の姿勢推定モデルをロードする（12GB VRAM競合防止）
    pose_init_started_at = perf_counter()
    estimator = create_pose_estimator_from_globals(pose_device)
    pose_init_seconds = perf_counter() - pose_init_started_at

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

        black_crop = np.zeros((crop_h, crop_w, 3), dtype=np.uint8)

        with output_csv.open("w", newline="", encoding="utf-8-sig") as csv_file:
            csv_writer = csv.DictWriter(csv_file, fieldnames=get_csv_fieldnames())
            csv_writer.writeheader()

            reader = AsyncFrameReader(
                capture,
                max_queue_size=max(8, min(48, effective_pose_batch + 8)),
                max_frames=len(target_boxes),
            )
            writer_queue_size = max(8, min(32, effective_pose_batch + 8))
            writer_worker = AsyncVideoWriter(writer, max_queue_size=writer_queue_size)
            crop_writer_worker = AsyncVideoWriter(
                crop_writer, max_queue_size=writer_queue_size
            )
            crop_skeleton_writer_worker = AsyncVideoWriter(
                crop_skeleton_writer, max_queue_size=writer_queue_size
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

            def _emit_pose_frame(
                idx, frame, target_box, restored_keypoints, pose_scores, crop_info=None
            ) -> None:
                nonlocal frame_count, target_box_count, pose_success_count, last_progress
                if target_box is not None:
                    target_box_count += 1
                if restored_keypoints is not None:
                    pose_success_count += 1
                    annotate_pose_on_frame(frame, target_box, restored_keypoints, pose_scores)

                if crop_info is not None:
                    crop_bgr, crop_center, crop_scale = crop_info
                    crop_writer_worker.write(crop_bgr)
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
                    crop_writer_worker.write(black_crop)
                    crop_skeleton_writer_worker.write(black_crop)

                frame_data = {
                    "frame": idx,
                    "time_seconds": idx / fps,
                    "persons": [],
                }
                if restored_keypoints is not None:
                    person = {
                        "person_id": target_stable_id,
                        "yolo_track_id": target_stable_id,
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

                if restored_keypoints is not None and target_box is not None:
                    label_x, label_y = map(int, target_box[:2])
                    cv2.putText(
                        frame,
                        f"YOLO stable_id: {target_stable_id}",
                        (label_x, max(25, label_y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )

                cv2.putText(
                    frame,
                    f"Frame: {idx + 1}",
                    (40, 80),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )

                writer_worker.write(frame)
                frame_count += 1

                if total_pose_frames > 0:
                    progress = 50 + int(frame_count * 50 / total_pose_frames)
                    if progress > last_progress:
                        print(f"PROGRESS:{progress}:{phase_code}", flush=True)
                        last_progress = progress

                if frame_count % 30 == 0:
                    print(f"Processed {frame_count} frames", flush=True)

            try:
                print(f"PROGRESS:50:{phase_code}", flush=True)
                next_read_idx = 0
                eof = False
                while next_read_idx < total_pose_frames and not eof:
                    buffered = []
                    valid_positions = []
                    max_buffered = min(
                        effective_pose_batch + 64,
                        max(effective_pose_batch * 2, 16),
                    )
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
                            _clamped_target_box(target_box, frame.shape[1], frame.shape[0])
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
                                        fixed_bs = (
                                            effective_pose_batch
                                            if pose_engine == "rtmpose"
                                            else None
                                        )
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
                        writer_worker.close(drain=not aborted)
                    finally:
                        try:
                            crop_writer_worker.close(drain=not aborted)
                        finally:
                            try:
                                crop_skeleton_writer_worker.close(drain=not aborted)
                            finally:
                                capture.release()
                                writer.release()
                                crop_writer.release()
                                crop_skeleton_writer.release()

        pose_elapsed_seconds = pose_init_seconds + perf_counter() - pose_started_at
        print(f"PROGRESS:100:{phase_code}", flush=True)
    finally:
        estimator.close()

    print(f"Finished: {frame_count} frames")
    print(f"Output: {output_video.resolve()}")
    print(f"Crop: {output_crop_video.resolve()}")
    print(f"Crop Skeleton: {output_crop_skeleton_video.resolve()}")
    print(f"CSV: {output_csv.resolve()}")
    print(f"Metadata: {output_metadata.resolve()}")
    print(f"Target boxes: {target_box_count}/{frame_count}")
    print(f"{phase_label} calls: {pose_call_count}, accepted: {pose_success_count}")
    yolo_analysis_fps = len(target_boxes) / yolo_elapsed_seconds if yolo_elapsed_seconds > 0 else 0.0
    pose_analysis_fps = frame_count / pose_elapsed_seconds if pose_elapsed_seconds > 0 else 0.0
    print(f"YOLO分析時間: {yolo_elapsed_seconds:.2f} 秒", flush=True)
    print(f"YOLO分析速度: {yolo_analysis_fps:.2f} フレーム/秒", flush=True)
    print(f"{phase_label}分析時間: {pose_elapsed_seconds:.2f} 秒", flush=True)
    print(f"{phase_label}分析速度: {pose_analysis_fps:.2f} フレーム/秒", flush=True)


def run_analysis_worker(config_path: Path) -> None:
    """同じgui.pyを解析ワーカーとして起動した場合のエントリーポイント。"""
    import importlib
    import os
    import warnings

    os.environ.setdefault("ORT_LOGGING_LEVEL", "3")
    os.environ.setdefault("YOLO_VERBOSE", "False")
    warnings.filterwarnings("ignore", category=UserWarning, module=r"torch\.cuda")

    settings = normalize_legacy_rtmlib_settings(
        json.loads(config_path.read_text(encoding="utf-8"))
    )
    unknown = set(settings) - set(ENGINE_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
    for key, value in settings.items():
        if key in PATH_SETTING_KEYS:
            value = Path(value).expanduser()
        globals()[key] = value

    globals()["cv2"] = importlib.import_module("cv2")
    globals()["YOLO"] = importlib.import_module("ultralytics").YOLO
    if normalize_pose_engine(globals().get("POSE_ENGINE")) == "rtmpose":
        rtmlib = importlib.import_module("rtmlib")
        globals()["RTMPose"] = rtmlib.RTMPose
        globals()["draw_skeleton"] = rtmlib.draw_skeleton
    else:
        try:
            rtmlib = importlib.import_module("rtmlib")
            globals()["draw_skeleton"] = rtmlib.draw_skeleton
        except ImportError:
            pass

    run_analysis()


def _start_gui() -> None:
    try:
        from pose_ui import launch_gui
    except ImportError as exc:
        msg = (
            f"GUI表示に必要なパッケージが見つかりません ({exc})。\n\n"
            "新規環境では:\n"
            "  python -m pip install -r requirements.txt\n\n"
            "既存のGPU環境（.venv）に追加する場合は:\n"
            "  python -m pip install customtkinter tkinterdnd2 Pillow\n"
            "を実行してください。"
        )
        print(msg, file=sys.stderr, flush=True)
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("必要なパッケージが不足しています", msg)
            root.destroy()
        except Exception:
            pass
        sys.exit(1)

    launch_gui(
        base_dir=BASE_DIR,
        settings_file=SETTINGS_FILE,
        engine_defaults=ENGINE_DEFAULTS,
        choices=CHOICES,
        bool_keys=BOOL_KEYS,
        int_keys=INT_KEYS,
        float_keys=FLOAT_KEYS,
        resolve_rtmlib_fn=resolve_rtmlib_selection,
        output_names_fn=output_names,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="動画姿勢推定 GUI / 解析ワーカー")
    parser.add_argument("--analysis-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--legacy", action="store_true", help="従来版 CustomTkinter GUI を起動する")
    parser.add_argument("--debug", action="store_true", help="PyWebView デバッグモードを有効にする")
    parser.add_argument("--dev", action="store_true", help="Vite 開発サーバー (http://localhost:5173) に接続する")
    args = parser.parse_args()
    if args.analysis_worker:
        if args.config is None:
            parser.error("解析ワーカーには --config が必要です")
        run_analysis_worker(args.config)
    elif args.legacy:
        _start_gui()
    else:
        try:
            from pose_ui_webview import launch_webview_gui
        except ImportError as exc:
            print(f"PyWebView GUIの起動に失敗しました: {exc}\n--legacy オプションで従来版GUIを起動できます。", file=sys.stderr)
            sys.exit(1)
        launch_webview_gui(debug=args.debug, dev_server=args.dev)
