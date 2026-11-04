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
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from time import perf_counter

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
OUTPUT_YOLO_VIDEO_NAME = "踏切左-7-yolo.mp4"
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

BACKEND = "onnxruntime"
DEVICE = "auto"
#推定モデルを設定[performance , balanced , lightweight]
MODEL_MODE = "performance"
RTMLIB_POSE_MODEL = "mode"
RTMLIB_POSE_INPUT_SIZE = "mode"
RTMLIB_PERSON_DETECTOR = "mode"

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
    "OUTPUT_ROOT", "OUTPUT_FOLDER_NAME", "OUTPUT_VIDEO_NAME", "OUTPUT_YOLO_VIDEO_NAME",
    "OUTPUT_CSV_NAME", "OUTPUT_METADATA_NAME", "YOLO_MODEL", "YOLO_TRACKER",
    "YOLO_IMAGE_SIZE", "YOLO_CONFIDENCE", "YOLO_IOU", "YOLO_CLASSES", "YOLO_TRACK_ID",
    "CROP_PADDING_RATIO", "TARGET_REACQUIRE_MAX_DISTANCE", "TARGET_REACQUIRE_MIN_IOU",
    "BACKEND", "DEVICE", "MODEL_MODE", "RTMLIB_POSE_MODEL", "RTMLIB_POSE_INPUT_SIZE",
    "RTMLIB_PERSON_DETECTOR", "KEYPOINT_THRESHOLD", "TRACK_MAX_DISTANCE",
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
    "OUTPUT_VIDEO_NAME", "OUTPUT_YOLO_VIDEO_NAME", "OUTPUT_CSV_NAME", "OUTPUT_METADATA_NAME"
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
                    "YOLO_IOU", "YOLO_CLASSES", "YOLO_TRACK_ID", "CROP_PADDING_RATIO",
                    "TARGET_REACQUIRE_MAX_DISTANCE", "TARGET_REACQUIRE_MIN_IOU",
                    "TARGET_SELECTION_MIN_FRAMES", "TARGET_SELECTION_COVERAGE_WEIGHT",
                    "TARGET_BOX_FILL_MAX_FRAMES"]),
    ("姿勢推定・追跡", ["MODEL_MODE", "RTMLIB_POSE_MODEL", "RTMLIB_POSE_INPUT_SIZE",
                     "RTMLIB_PERSON_DETECTOR", "BACKEND", "DEVICE", "KEYPOINT_THRESHOLD", "CSV_MAX_PERSONS",
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
    "MODEL_MODE": "姿勢推定モデル",
    "RTMLIB_POSE_MODEL": "RTMPoseモデル（mode=既存モード）",
    "RTMLIB_POSE_INPUT_SIZE": "RTMPose入力解像度（mode=モードに合わせる）",
    "RTMLIB_PERSON_DETECTOR": "RTMLib人物検出器 YOLOX（mode=既存モード）",
    "DEVICE": "実行デバイス（YOLO・姿勢推定）",
}
CHOICES = {
    "YOLO_MODEL": ("n", "s", "m", "l", "x"),
    "MODEL_MODE": ("performance", "balanced", "lightweight"),
    "RTMLIB_POSE_MODEL": ("mode", "t", "s", "m", "l", "x"),
    "RTMLIB_POSE_INPUT_SIZE": ("mode", "256x192", "384x288"),
    "RTMLIB_PERSON_DETECTOR": ("mode", "nano", "tiny", "s", "m", "l", "x"),
    "DEVICE": ("auto", "cpu", "cuda"),
}

RTMLIB_MODE_POSE = {
    "performance": ("x", "384x288"),
    "balanced": ("m", "256x192"),
    "lightweight": ("s", "256x192"),
}
RTMLIB_MODE_DETECTOR = {
    "performance": "x",
    "balanced": "m",
    "lightweight": "tiny",
}
RTMLIB_POSE_ASSETS = {
    "t": {
        "256x192": {
            "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-t_simcc-body7_pt-body7_420e-256x192-026a1439_20230504.zip",
            "input_size": (192, 256),
        },
    },
    "s": {
        "256x192": {
            "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-s_simcc-body7_pt-body7_420e-256x192-acd4a1ef_20230504.zip",
            "input_size": (192, 256),
        },
    },
    "m": {
        "256x192": {
            "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.zip",
            "input_size": (192, 256),
        },
    },
    "l": {
        "256x192": {
            "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-l_simcc-body7_pt-body7_420e-256x192-4dba18fc_20230504.zip",
            "input_size": (192, 256),
        },
        "384x288": {
            "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-l_simcc-body7_pt-body7_420e-384x288-3f5a1437_20230504.zip",
            "input_size": (288, 384),
        },
    },
    "x": {
        "384x288": {
            "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-x_simcc-body7_pt-body7_700e-384x288-71d7b7e9_20230629.zip",
            "input_size": (288, 384),
        },
    },
}
RTMLIB_PERSON_DETECTOR_ASSETS = {
    "nano": {
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_nano_8xb8-300e_humanart-40f6f0d0.zip",
        "input_size": (416, 416),
    },
    "tiny": {
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_tiny_8xb8-300e_humanart-6f3252f9.zip",
        "input_size": (416, 416),
    },
    "s": {
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_s_8xb8-300e_humanart-3ef259a7.zip",
        "input_size": (640, 640),
    },
    "m": {
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_m_8xb8-300e_humanart-c2c7a14a.zip",
        "input_size": (640, 640),
    },
    "l": {
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_l_8xb8-300e_humanart-ce1d7a62.zip",
        "input_size": (640, 640),
    },
    "x": {
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_x_8xb8-300e_humanart-a39d44ed.zip",
        "input_size": (640, 640),
    },
}
RTMLIB_DETECTOR_SCORE_THRESHOLD = 0.7
RTMLIB_DETECTOR_NMS_THRESHOLD = 0.45


def resolve_rtmlib_selection(mode: str, pose_model: str, pose_input_size: str, person_detector: str) -> dict:
    """Resolve preset/manual RTMLib model choices to downloadable models and input sizes."""
    if mode not in RTMLIB_MODE_POSE:
        raise ValueError(f"不明なRTMLib推定モードです: {mode}")

    mode_pose, mode_resolution = RTMLIB_MODE_POSE[mode]
    selected_pose = mode_pose if pose_model == "mode" else pose_model
    if selected_pose not in RTMLIB_POSE_ASSETS:
        raise ValueError(f"不明なRTMPoseモデルです: {pose_model}")

    if pose_input_size == "mode":
        if pose_model == "mode":
            selected_resolution = mode_resolution
        elif mode_resolution in RTMLIB_POSE_ASSETS[selected_pose]:
            selected_resolution = mode_resolution
        else:
            selected_resolution = next(iter(RTMLIB_POSE_ASSETS[selected_pose]))
    else:
        selected_resolution = pose_input_size

    pose_asset = RTMLIB_POSE_ASSETS[selected_pose].get(selected_resolution)
    if pose_asset is None:
        available = " / ".join(RTMLIB_POSE_ASSETS[selected_pose])
        raise ValueError(
            f"RTMPose-{selected_pose.upper()} は {selected_resolution} に対応していません。"
            f"使用できる解像度: {available}。"
        )

    selected_detector = (
        RTMLIB_MODE_DETECTOR[mode] if person_detector == "mode" else person_detector
    )
    detector_asset = RTMLIB_PERSON_DETECTOR_ASSETS.get(selected_detector)
    if detector_asset is None:
        raise ValueError(f"不明なRTMLib人物検出器です: {person_detector}")

    return {
        "pose_model": selected_pose,
        "pose_resolution": selected_resolution,
        "pose_asset": pose_asset,
        "person_detector": selected_detector,
        "detector_asset": detector_asset,
    }


def output_names(output_directory: Path) -> dict[str, str]:
    """選択された出力フォルダ名から出力ファイル名を作ります。"""
    name = output_directory.name
    if not name:
        raise ValueError("出力先フォルダを指定してください。")
    return {
        "OUTPUT_VIDEO_NAME": f"{name}.mp4",
        "OUTPUT_YOLO_VIDEO_NAME": f"{name}-yolo.mp4",
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


def pose_from_crop(body, frame, target_box, previous_keypoints=None, previous_scores=None):
    height, width = frame.shape[:2]
    crop_left, crop_top, crop_right, crop_bottom = padded_crop_box(
        target_box, width, height
    )
    crop = frame[crop_top:crop_bottom, crop_left:crop_right]
    if crop.size == 0:
        return None, None, None
    keypoints, scores = body(crop)
    if len(keypoints) == 0:
        return None, None, (crop_left, crop_top, crop_right, crop_bottom)
    local_target_box = (
        float(target_box[0]) - crop_left,
        float(target_box[1]) - crop_top,
        float(target_box[2]) - crop_left,
        float(target_box[3]) - crop_top,
    )
    local_target_center = box_center(local_target_box)
    target_scale = max(
        math.hypot(
            local_target_box[2] - local_target_box[0],
            local_target_box[3] - local_target_box[1],
        ),
        1.0,
    )
    local_previous_keypoints = None
    if previous_keypoints is not None:
        local_previous_keypoints = [
            (float(point[0]) - crop_left, float(point[1]) - crop_top)
            for point in previous_keypoints
        ]
    candidate_costs = []
    for candidate_keypoints, candidate_scores in zip(keypoints, scores):
        geometry = get_person_geometry(candidate_keypoints, candidate_scores)
        iou_cost = 1.0 - bbox_iou(local_target_box, geometry["bbox"])
        center_cost = math.dist(geometry["center"], local_target_center) / target_scale
        temporal_cost = 0.0
        if local_previous_keypoints is not None and previous_scores is not None:
            temporal_cost = pose_match_cost(
                candidate_keypoints,
                candidate_scores,
                local_target_center,
                local_previous_keypoints,
                previous_scores,
            )
        candidate_costs.append(
            POSE_BOX_IOU_WEIGHT * iou_cost
            + POSE_BOX_CENTER_WEIGHT * center_cost
            + POSE_TEMPORAL_WEIGHT * temporal_cost
        )
    pose_index = min(range(len(candidate_costs)), key=candidate_costs.__getitem__)
    local_keypoints = keypoints[pose_index]
    local_scores = scores[pose_index]
    restored_keypoints = [
        (float(point[0]) + crop_left, float(point[1]) + crop_top)
        for point in local_keypoints
    ]
    annotated_crop = draw_skeleton(
        crop.copy(),
        keypoints[pose_index:pose_index + 1],
        scores[pose_index:pose_index + 1],
        kpt_thr=KEYPOINT_THRESHOLD,
    )
    frame[crop_top:crop_bottom, crop_left:crop_right] = annotated_crop
    return restored_keypoints, local_scores, (crop_left, crop_top, crop_right, crop_bottom)


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


def draw_stable_yolo_tracks(frame, detections):
    annotated = frame.copy()
    for detection in detections:
        left, top, right, bottom = map(int, detection["bbox"])
        stable_id = detection["stable_id"]
        cv2.rectangle(annotated, (left, top), (right, bottom), (0, 255, 255), 2)
        cv2.putText(
            annotated,
            f"person_id: {stable_id}",
            (left, max(25, top - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return annotated


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


def prepare_runtime(backend: str, device: str) -> tuple[str, str]:
    """両方の推論エンジンで使えるデバイスを選び、CUDA DLLを読み込みます。"""
    import torch

    device = device.strip().lower()
    if device not in {"auto", "cpu", "cuda"} and not (
        device.startswith("cuda:") and device[5:].isdigit()
    ):
        raise ValueError("DEVICE は auto / cpu / cuda / cuda:番号 を指定してください。")
    if device == "cpu":
        print("実行デバイス: CPU（YOLO・姿勢推定）", flush=True)
        return "cpu", "cpu"

    reason = None
    if backend != "onnxruntime":
        reason = "GPU実行には BACKEND=onnxruntime を指定してください。"
    elif not torch.cuda.is_available():
        reason = "PyTorchでCUDAを利用できません。GPU版PyTorchとNVIDIAドライバーを確認してください。"
    else:
        import onnxruntime as ort

        # PyTorchと同じCUDA/cuDNN DLLを使います（特にWindowsで必要）。
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            reason = "ONNX RuntimeでCUDAを利用できません。onnxruntime-gpuを導入してください。"
    if reason is not None:
        if device != "auto":
            raise RuntimeError(reason)
        print(f"{reason}\n実行デバイス: CPU（YOLO・姿勢推定）", flush=True)
        return "cpu", "cpu"

    index = int(device.split(":")[1]) if ":" in device else 0
    if index >= torch.cuda.device_count():
        raise ValueError(f"GPU番号 {index} は存在しません。")
    print(f"実行デバイス: CUDA:{index} / {torch.cuda.get_device_name(index)}（YOLO・姿勢推定）", flush=True)
    return f"cuda:{index}", f"cuda:{index}"


def create_pose_model(device: str):
    selection = resolve_rtmlib_selection(
        MODEL_MODE,
        RTMLIB_POSE_MODEL,
        RTMLIB_POSE_INPUT_SIZE,
        RTMLIB_PERSON_DETECTOR,
    )
    pose_asset = selection["pose_asset"]
    detector_asset = selection["detector_asset"]
    print(
        f"RTMLIB姿勢モデル: RTMPose-{selection['pose_model'].upper()} "
        f"({selection['pose_resolution']})",
        flush=True,
    )
    detector_size = detector_asset["input_size"]
    print(
        f"RTMLIB人物検出器: YOLOX-{selection['person_detector'].upper()} "
        f"({detector_size[1]}x{detector_size[0]}), "
        f"score_thr={RTMLIB_DETECTOR_SCORE_THRESHOLD:.2f}, "
        f"nms_thr={RTMLIB_DETECTOR_NMS_THRESHOLD:.2f}",
        flush=True,
    )
    model = Body(
        det=detector_asset["url"],
        det_input_size=detector_asset["input_size"],
        pose=pose_asset["url"],
        pose_input_size=pose_asset["input_size"],
        mode=MODEL_MODE,
        backend=BACKEND,
        device=device,
    )
    model.det_model.score_thr = RTMLIB_DETECTOR_SCORE_THRESHOLD
    model.det_model.nms_thr = RTMLIB_DETECTOR_NMS_THRESHOLD
    if BACKEND == "onnxruntime":
        for name in ("det_model", "pose_model"):
            providers = getattr(model, name).session.get_providers()
            print(f"RTMLIB {name}: {', '.join(providers)}", flush=True)
            if device.startswith("cuda") and "CUDAExecutionProvider" not in providers:
                raise RuntimeError(
                    f"RTMLIB {name} のCUDA初期化に失敗しました。"
                    "CUDA/cuDNNのバージョンを確認するか、DEVICE=cpu を選択してください。"
                )
    return model


def run_yolo_pass(input_video: Path, output_yolo_video: Path, progress_total_frames=0, device="cpu"):
    capture = cv2.VideoCapture(str(input_video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open input video: {input_video.resolve()}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = progress_total_frames or int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    writer = cv2.VideoWriter(
        str(output_yolo_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(
            f"Could not create YOLO output video: {output_yolo_video.resolve()}"
        )

    detector = YOLO(YOLO_MODEL)
    tracks = {}
    next_id = 0
    target_stable_id = YOLO_TRACK_ID
    frame_detections = []
    processed_frames = 0
    last_progress = -1
    print("PROGRESS:0:YOLO", flush=True)
    try:
        while True:
            success, frame = capture.read()
            if not success:
                break
            results = detector.track(
                frame,
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
            detections, next_id = stabilize_yolo_ids(
                results[0].boxes,
                tracks,
                next_id,
            )
            frame_detections.append(detections)
            writer.write(draw_stable_yolo_tracks(frame, detections))
            processed_frames += 1
            if total_frames > 0:
                progress = min(49, int(processed_frames * 50 / total_frames))
                if progress > last_progress:
                    print(f"PROGRESS:{progress}:YOLO", flush=True)
                    last_progress = progress
    finally:
        capture.release()
        writer.release()
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
    yolo_device, pose_device = prepare_runtime(BACKEND, DEVICE)
    # 長いYOLO処理を始める前に、姿勢推定のCUDA初期化も確認します。
    rtmlib_initialization_started_at = perf_counter()
    pose_model = create_pose_model(pose_device)
    rtmlib_initialization_seconds = perf_counter() - rtmlib_initialization_started_at
    input_video = find_input_video()
    output_directory = OUTPUT_ROOT / OUTPUT_FOLDER_NAME
    output_video = output_directory / OUTPUT_VIDEO_NAME
    output_yolo_video = output_directory / OUTPUT_YOLO_VIDEO_NAME
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
        output_yolo_video,
        metadata_total_frames,
        device=yolo_device,
    )
    yolo_elapsed_seconds = perf_counter() - yolo_started_at

    rtmlib_started_at = perf_counter()
    capture = cv2.VideoCapture(str(input_video))
    writer = cv2.VideoWriter(
        str(output_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not capture.isOpened():
        raise RuntimeError(f"Could not reopen input video: {input_video.resolve()}")
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"Could not create output video: {output_video.resolve()}")

    with output_csv.open("w", newline="", encoding="utf-8-sig") as csv_file:
        csv_writer = csv.DictWriter(csv_file, fieldnames=get_csv_fieldnames())
        csv_writer.writeheader()

        try:
            frame_count = 0
            target_box_count = 0
            pose_call_count = 0
            pose_success_count = 0
            previous_target_keypoints = None
            previous_target_scores = None
            last_progress = 50
            total_pose_frames = len(target_boxes)
            print("PROGRESS:50:RTMLIB", flush=True)
            while frame_count < len(target_boxes):
                success, frame = capture.read()
                if not success:
                    break
                target_box = target_boxes[frame_count]
                restored_keypoints = None
                pose_scores = None
                if target_box is not None:
                    target_box_count += 1
                    pose_call_count += 1
                    restored_keypoints, pose_scores, crop_box = pose_from_crop(
                        pose_model,
                        frame,
                        target_box,
                        previous_target_keypoints,
                        previous_target_scores,
                    )
                    if restored_keypoints is not None:
                        pose_success_count += 1
                        previous_target_keypoints = restored_keypoints
                        previous_target_scores = pose_scores
                frame_data = {
                    "frame": frame_count,
                    "time_seconds": frame_count / fps,
                    "persons": [],
                }
                if restored_keypoints is not None:
                    person = {
                        "person_id": target_stable_id,
                        "yolo_track_id": target_stable_id,
                    }
                    for index, name in enumerate(COCO_KEYPOINTS):
                        x, y = restored_keypoints[index]
                        person[name] = {
                            "x": x,
                            "y": y,
                            "score": float(pose_scores[index]),
                        }
                    frame_data["persons"].append(person)

                csv_writer.writerow(make_csv_row(frame_data))

                if restored_keypoints is not None:
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
                    f"Frame: {frame_count + 1}",
                    (40, 80),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )

                writer.write(frame)
                frame_count += 1

                if total_pose_frames > 0:
                    progress = 50 + int(frame_count * 50 / total_pose_frames)
                    if progress > last_progress:
                        print(f"PROGRESS:{progress}:RTMLIB", flush=True)
                        last_progress = progress

                if frame_count % 30 == 0:
                    print(f"Processed {frame_count} frames", flush=True)
        finally:
            capture.release()
            writer.release()

    rtmlib_elapsed_seconds = rtmlib_initialization_seconds + perf_counter() - rtmlib_started_at
    print("PROGRESS:100:RTMLIB", flush=True)

    print(f"Finished: {frame_count} frames")
    print(f"Output: {output_video.resolve()}")
    print(f"YOLO: {output_yolo_video.resolve()}")
    print(f"CSV: {output_csv.resolve()}")
    print(f"Metadata: {output_metadata.resolve()}")
    print(f"Target boxes: {target_box_count}/{frame_count}")
    print(f"rtmlib calls: {pose_call_count}, accepted: {pose_success_count}")
    yolo_analysis_fps = len(target_boxes) / yolo_elapsed_seconds if yolo_elapsed_seconds > 0 else 0.0
    rtmlib_analysis_fps = frame_count / rtmlib_elapsed_seconds if rtmlib_elapsed_seconds > 0 else 0.0
    print(f"YOLO分析時間: {yolo_elapsed_seconds:.2f} 秒", flush=True)
    print(f"YOLO分析速度: {yolo_analysis_fps:.2f} フレーム/秒", flush=True)
    print(f"RTMLIB分析時間: {rtmlib_elapsed_seconds:.2f} 秒", flush=True)
    print(f"RTMLIB分析速度: {rtmlib_analysis_fps:.2f} フレーム/秒", flush=True)


class PoseGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("動画姿勢推定")
        self.geometry("1150x820")
        self.minsize(900, 600)
        self.values = dict(DEFAULTS)
        if SETTINGS_FILE.exists():
            try:
                saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                self.values.update({key: value for key, value in saved.items() if key in DEFAULTS})
                # 旧GUIの保存設定（親フォルダとファイル名）も新しいファイル選択欄へ引き継ぎます。
                if "INPUT_VIDEO_FILE" not in saved and "INPUT_ROOT" in saved:
                    self.values["INPUT_VIDEO_FILE"] = str(Path(saved["INPUT_ROOT"]) / saved.get("INPUT_VIDEO_NAME", ""))
                if "THUMBNAIL_FILE" not in saved and "THUMBNAIL_ROOT" in saved:
                    self.values["THUMBNAIL_FILE"] = str(Path(saved["THUMBNAIL_ROOT"]) / saved.get("THUMBNAIL_IMAGE_NAME", ""))
                if "OUTPUT_DIRECTORY" not in saved and "OUTPUT_ROOT" in saved:
                    self.values["OUTPUT_DIRECTORY"] = str(Path(saved["OUTPUT_ROOT"]) / saved.get("OUTPUT_FOLDER_NAME", ""))
            except (OSError, json.JSONDecodeError) as exc:
                messagebox.showwarning("設定ファイル", f"保存済み設定を読み込めませんでした。初期設定で起動します。\n{exc}")
        self.vars = {}
        self.process = None
        self.cancel_requested = False
        self.log_queue = queue.Queue()
        self._build()

    def _build(self):
        top = ttk.Frame(self, padding=(12, 10))
        top.pack(fill="x")
        ttk.Label(top, text="入力動画、出力先、推定・追跡の設定を指定して実行します。", wraplength=850).pack(anchor="w")
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=12)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.form = ttk.Frame(canvas, padding=(4, 4, 12, 12))
        self.output_preview = tk.StringVar()
        self.form.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        form_window = canvas.create_window((0, 0), window=self.form, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(form_window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for title, keys in GROUPS:
            group = ttk.LabelFrame(self.form, text=title, padding=10)
            group.pack(fill="x", pady=(0, 10))
            group.columnconfigure(1, weight=1)
            for row, key in enumerate(keys):
                ttk.Label(group, text=LABELS.get(key, key)).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
                if key in BOOL_KEYS:
                    variable = tk.BooleanVar(value=self.values[key])
                    widget = ttk.Checkbutton(group, variable=variable)
                    widget.grid(row=row, column=1, sticky="w", pady=3)
                elif key in CHOICES:
                    current = str(self.values[key])
                    if key == "YOLO_MODEL":
                        current = current.removeprefix("yolo11").removesuffix(".pt")
                    variable = tk.StringVar(value=current)
                    widget = ttk.Combobox(group, textvariable=variable, values=CHOICES[key], state="readonly", width=8)
                    widget.grid(row=row, column=1, sticky="w", pady=3)
                else:
                    value = self.values[key]
                    if key == "YOLO_TRACK_ID" and value is None:
                        value = ""
                    variable = tk.StringVar(value=self._format(value))
                    widget = ttk.Entry(group, textvariable=variable)
                    widget.grid(row=row, column=1, sticky="ew", pady=3)
                    if key in PATH_KEYS:
                        ttk.Button(group, text="参照…", command=lambda k=key: self._choose_dir(k)).grid(row=row, column=2, padx=(6, 0))
                    elif key in FILE_KEYS:
                        ttk.Button(group, text="参照…", command=lambda k=key: self._choose_file(k)).grid(row=row, column=2, padx=(6, 0))
                self.vars[key] = variable
                if key == "OUTPUT_DIRECTORY":
                    variable.trace_add("write", self._update_output_preview)
                    ttk.Label(group, textvariable=self.output_preview, wraplength=850).grid(
                        row=row + 1, column=1, columnspan=2, sticky="w", pady=(4, 2)
                    )
                    self._update_output_preview()
        actions = ttk.Frame(self, padding=12)
        actions.pack(fill="x")
        self.status = ttk.Label(actions, text="待機中")
        self.status.pack(side="left", fill="x", expand=True)
        self.progress_value = tk.IntVar(value=0)
        self.progress_label = ttk.Label(actions, text="0%")
        self.progress_label.pack(side="right", padx=(6, 12))
        self.progress_bar = ttk.Progressbar(actions, maximum=100, variable=self.progress_value, length=220)
        self.progress_bar.pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="初期設定に戻す", command=self._reset).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="設定を保存", command=self._save).pack(side="right", padx=(6, 0))
        self.cancel_button = ttk.Button(actions, text="解析を中断", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="right", padx=(6, 0))
        self.start_button = ttk.Button(actions, text="解析を開始", command=self._start)
        self.start_button.pack(side="right")
        log_frame = ttk.LabelFrame(self, text="実行ログ", padding=8)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log = tk.Text(log_frame, height=9, wrap="word", state="disabled")
        log_scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        self.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    @staticmethod
    def _format(value):
        if isinstance(value, list):
            return ", ".join(map(str, value))
        return str(value)

    def _choose_dir(self, key):
        selected = filedialog.askdirectory(initialdir=self.vars[key].get() or str(HOME))
        if selected:
            self.vars[key].set(selected)

    def _update_output_preview(self, *_args):
        try:
            names = output_names(Path(self.vars["OUTPUT_DIRECTORY"].get().strip()))
            self.output_preview.set("生成ファイル: " + " / ".join(names.values()))
        except ValueError:
            self.output_preview.set("出力先フォルダ名からファイル名を自動生成します")

    def _choose_file(self, key):
        is_video = key == "INPUT_VIDEO_FILE"
        initial = self.vars[key].get() or str(HOME)
        initial_path = Path(initial).expanduser()
        selected = filedialog.askopenfilename(initialdir=str(initial_path.parent),
            filetypes=[("動画ファイル", "*.mp4 *.MP4 *.mov *.MOV *.avi *.mkv") , ("画像ファイル", "*.jpg *.JPG *.jpeg *.png")] if not is_video else [("動画ファイル", "*.mp4 *.MP4 *.mov *.MOV *.avi *.mkv"), ("すべてのファイル", "*.*")])
        if selected:
            self.vars[key].set(str(Path(selected).expanduser()))

    def _collect(self):
        settings = {}
        for key, variable in self.vars.items():
            if key in BOOL_KEYS:
                settings[key] = bool(variable.get())
                continue
            value = variable.get().strip()
            if key == "YOLO_MODEL":
                if value not in CHOICES[key]:
                    raise ValueError("YOLOモデルサイズは n / s / m / l / x から選択してください。")
                settings[key] = f"yolo11{value}.pt"
            elif key == "MODEL_MODE":
                if value not in CHOICES[key]:
                    raise ValueError("姿勢推定モデルを選択してください。")
                settings[key] = value
            elif key in {
                "RTMLIB_POSE_MODEL", "RTMLIB_POSE_INPUT_SIZE", "RTMLIB_PERSON_DETECTOR"
            }:
                if value not in CHOICES[key]:
                    raise ValueError(f"{LABELS[key]} の値を選択してください。")
                settings[key] = value
            elif key in PATH_KEYS or key in FILE_KEYS or key in {"YOLO_TRACKER", "MODEL_MODE", "BACKEND", "DEVICE"} or key.startswith("OUTPUT_"):
                settings[key] = value
            elif key == "YOLO_TRACK_ID":
                settings[key] = None if not value else int(value)
            elif key == "YOLO_CLASSES":
                settings[key] = [int(part.strip()) for part in value.split(",") if part.strip()]
            elif key in INT_KEYS:
                settings[key] = int(value)
            elif key in FLOAT_KEYS:
                settings[key] = float(value)
            else:
                settings[key] = value
        video_path = Path(settings.pop("INPUT_VIDEO_FILE")).expanduser()
        thumbnail_value = settings.pop("THUMBNAIL_FILE").strip()
        output_directory = Path(settings.pop("OUTPUT_DIRECTORY")).expanduser()
        settings.update({
            "INPUT_ROOT": str(video_path.parent),
            "INPUT_VIDEO_NAME": video_path.name,
            "THUMBNAIL_ROOT": str(Path(thumbnail_value).parent) if thumbnail_value else "",
            "THUMBNAIL_IMAGE_NAME": Path(thumbnail_value).name if thumbnail_value else "",
            "OUTPUT_ROOT": str(output_directory.parent),
            "OUTPUT_FOLDER_NAME": output_directory.name,
        })
        settings.update(output_names(output_directory))
        resolve_rtmlib_selection(
            settings["MODEL_MODE"],
            settings["RTMLIB_POSE_MODEL"],
            settings["RTMLIB_POSE_INPUT_SIZE"],
            settings["RTMLIB_PERSON_DETECTOR"],
        )
        return settings

    def _save(self, show_message=True):
        try:
            settings = self._collect()
            SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if show_message:
                self.status.configure(text=f"設定を保存しました: {SETTINGS_FILE.name}")
            return settings
        except (ValueError, OSError) as exc:
            messagebox.showerror("設定エラー", f"設定値を確認してください。\n{exc}")
            return None

    def _reset(self):
        for key, variable in self.vars.items():
            if key in BOOL_KEYS:
                variable.set(DEFAULTS[key])
            else:
                value = "" if key == "YOLO_TRACK_ID" else self._format(DEFAULTS[key])
                variable.set(value)
        self._save(show_message=False)
        self.status.configure(text="現在の設定を初期値に戻しました")

    def _start(self):
        settings = self._save(show_message=False)
        if settings is None:
            return
        if not settings["INPUT_VIDEO_NAME"]:
            messagebox.showerror("入力エラー", "入力動画を指定してください。")
            return
        video = Path(settings["INPUT_ROOT"]).expanduser() / settings["INPUT_VIDEO_NAME"]
        if not video.is_file():
            messagebox.showerror("入力エラー", f"入力動画が見つかりません。\n{video}")
            return
        config = SETTINGS_FILE
        self.cancel_requested = False
        self.process = None
        self.progress_value.set(0)
        self.progress_label.configure(text="0%")
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status.configure(text="解析を実行中…")
        self._append(f"設定を保存しました: {config}\n解析を開始します: {video}\n")
        threading.Thread(target=self._run_process, args=(config,), daemon=True).start()

    def _cancel(self):
        self.cancel_requested = True
        self.cancel_button.configure(state="disabled")
        self.status.configure(text="解析を中断しています…")
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()

    def _run_process(self, config):
        try:
            self.process = subprocess.Popen([sys.executable, "-u", "-X", "utf8", str(BASE_DIR / "gui.py"), "--analysis-worker", "--config", str(config)],
                cwd=BASE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
            if self.cancel_requested:
                self.process.terminate()
            for line in self.process.stdout:
                self.log_queue.put(line)
            code = self.process.wait()
            self.log_queue.put(("__FINISHED__", code))
        except Exception as exc:
            self.log_queue.put(f"起動エラー: {exc}\n")
            self.log_queue.put(("__FINISHED__", -1))

    def _append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__FINISHED__":
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    if self.cancel_requested:
                        self.status.configure(text="解析を中断しました")
                    else:
                        self.status.configure(text="解析が完了しました" if item[1] == 0 else f"解析が終了しました（終了コード {item[1]}）")
                    if item[1] == 0:
                        self.progress_value.set(100)
                        self.progress_label.configure(text="100%")
                    self._append(f"\n--- 終了コード: {item[1]} ---\n")
                elif isinstance(item, str) and item.startswith("PROGRESS:"):
                    try:
                        percent, phase = item.strip().split(":", 2)[1:]
                        self.progress_value.set(int(percent))
                        self.progress_label.configure(text=f"{int(percent)}%")
                        self.status.configure(text="YOLO処理中…" if phase == "YOLO" else "RTMLIB処理中…")
                    except (ValueError, IndexError):
                        self._append(item)
                else:
                    self._append(item)
        except queue.Empty:
            pass
        self.after(150, self._poll)


def run_analysis_worker(config_path: Path) -> None:
    """同じgui.pyを解析ワーカーとして起動した場合のエントリーポイント。"""
    import importlib

    globals()["cv2"] = importlib.import_module("cv2")
    rtmlib = importlib.import_module("rtmlib")
    globals()["Body"] = rtmlib.Body
    globals()["draw_skeleton"] = rtmlib.draw_skeleton
    globals()["YOLO"] = importlib.import_module("ultralytics").YOLO

    settings = json.loads(config_path.read_text(encoding="utf-8"))
    unknown = set(settings) - set(ENGINE_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
    for key, value in settings.items():
        if key in PATH_SETTING_KEYS:
            value = Path(value).expanduser()
        globals()[key] = value
    run_analysis()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="動画姿勢推定 GUI / 解析ワーカー")
    parser.add_argument("--analysis-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.analysis_worker:
        if args.config is None:
            parser.error("解析ワーカーには --config が必要です")
        run_analysis_worker(args.config)
    else:
        app = PoseGui()
        app.after(150, app._poll)
        app.mainloop()
