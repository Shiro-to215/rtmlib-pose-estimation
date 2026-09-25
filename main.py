from pathlib import Path
import csv
from datetime import datetime
import math
import subprocess

import cv2
from rtmlib import Body, draw_skeleton
from ultralytics import YOLO


# ここを書き換えて、動画を探す階層とファイル名を指定してください。
INPUT_ROOT = (
    Path.home()
    / "解析用動画ファイル"
    / "9-18-SMZ"
    / "空中左-SONY"
)
INPUT_VIDEO_NAME = "C0033.MP4"   # 解析ファイル名を正しく入力

# ここを書き換えて、出力先の階層、新規フォルダ名、ファイル名を指定してください。
OUTPUT_ROOT = (
    Path.home()
    / "動画解析出力"
    / "9-18-SMZ"
    / "空中左-SONY"
)
OUTPUT_FOLDER_NAME = "空中左-1"
OUTPUT_VIDEO_NAME = "空中左-1.mp4"
OUTPUT_YOLO_VIDEO_NAME = "空中左_yolo-1.mp4"  # 実験用: YOLO検出・追跡結果
OUTPUT_CSV_NAME = "空中左-1.csv"
OUTPUT_METADATA_NAME = "空中左-1_metadata.txt"

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


# 対象人物のクロップ設定。0.10は上下左右に10%相当の余白を追加します。
CROP_PADDING_RATIO = 0.10
TARGET_REACQUIRE_MAX_DISTANCE = 300.0
TARGET_REACQUIRE_MIN_IOU = 0.05

COCO_KEYPOINTS = [
    "鼻", "左目", "右目", "左耳", "右耳",
    "左肩", "右肩", "左肘", "右肘", "左手首", "右手首",
    "左股関節", "右股関節", "左膝", "右膝", "左足首", "右足首",
]

BACKEND = "onnxruntime"
DEVICE = "cpu"
#推定モデルを設定[performance , balanced , lightweight]
MODEL_MODE = "performance"

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
POSE_TRACK_MAX_COST = 1.25
POSE_TRACK_KEYPOINT_WEIGHT = 0.65
POSE_TRACK_CENTER_WEIGHT = 0.25
POSE_TRACK_SHAPE_WEIGHT = 0.10


def find_input_video() -> Path:
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
    duration_hours = int(duration_seconds // 3600)
    duration_minutes = int((duration_seconds % 3600) // 60)
    duration_remainder = duration_seconds % 60
    output_path.write_text(
        "元動画情報\n"
        "====================\n"
        f"元動画: {input_video.resolve()}\n"
        f"動画の撮影日時: {recorded_at}\n"
        f"総フレーム数: {total_frames}\n"
        f"解像度（横 x 縦）: {width} x {height}\n"
        f"FPS（1秒あたりのフレーム数）: {fps:.6f}\n"
        f"動画全体の長さ（秒）: {duration_seconds:.6f}\n"
        f"動画全体の長さ（時:分:秒）: {duration_hours:02d}:{duration_minutes:02d}:{duration_remainder:06.3f}\n",
        encoding="utf-8",
    )


def get_recorded_at(input_video: Path) -> str:
    # 1. まず ExifTool を使ってカメラ固有のオリジナル撮影日時の取得を試みる
    try:
        result = subprocess.run(
            [
                "exiftool",
                "-s3",
                "-DateTimeOriginal",
                "-CreateDate",
                str(input_video),
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
        pass

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
                str(input_video),
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
    target_center = box_center(target_box)
    local_target_center = (
        target_center[0] - crop_left,
        target_center[1] - crop_top,
    )
    local_previous_keypoints = None
    if previous_keypoints is not None:
        local_previous_keypoints = [
            (float(point[0]) - crop_left, float(point[1]) - crop_top)
            for point in previous_keypoints
        ]
    if previous_keypoints is None or previous_scores is None:
        pose_index = min(
            range(len(keypoints)),
            key=lambda index: math.dist(
                get_person_geometry(keypoints[index], scores[index])["center"],
                local_target_center,
            ),
        )
    else:
        pose_costs = [
            pose_match_cost(
                candidate_keypoints,
                candidate_scores,
                local_target_center,
                local_previous_keypoints,
                previous_scores,
            )
            for candidate_keypoints, candidate_scores in zip(keypoints, scores)
        ]
        pose_index = min(range(len(pose_costs)), key=pose_costs.__getitem__)
        if pose_costs[pose_index] > POSE_TRACK_MAX_COST:
            return None, None, (crop_left, crop_top, crop_right, crop_bottom)
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


def run_yolo_pass(input_video: Path, output_yolo_video: Path):
    capture = cv2.VideoCapture(str(input_video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open input video: {input_video.resolve()}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
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
    try:
        while True:
            success, frame = capture.read()
            if not success:
                break
            results = detector.track(
                frame,
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
    finally:
        capture.release()
        writer.release()
    if target_stable_id is None:
        target_stable_id = select_moving_target_id(
            frame_detections,
            len(frame_detections),
        )
    target_boxes = fill_target_box_gaps(frame_detections, target_stable_id)
    return frame_detections, target_boxes, target_stable_id, width, height, fps


def main() -> None:
    input_video = find_input_video()
    output_directory = OUTPUT_ROOT / OUTPUT_FOLDER_NAME
    output_video = output_directory / OUTPUT_VIDEO_NAME
    output_yolo_video = output_directory / OUTPUT_YOLO_VIDEO_NAME
    output_csv = output_directory / OUTPUT_CSV_NAME
    output_metadata = output_directory / OUTPUT_METADATA_NAME

    output_directory.mkdir(parents=True, exist_ok=True)
    _, target_boxes, target_stable_id, width, height, fps = run_yolo_pass(
        input_video,
        output_yolo_video,
    )
    pose_model = Body(
        mode=MODEL_MODE,
        backend=BACKEND,
        device=DEVICE,
    )

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

                writer.write(frame)
                frame_count += 1

                if frame_count % 30 == 0:
                    print(f"Processed {frame_count} frames", flush=True)
        finally:
            capture.release()
            writer.release()

    write_video_metadata(
        input_video,
        output_metadata,
        frame_count,
        width,
        height,
        fps,
    )

    print(f"Finished: {frame_count} frames")
    print(f"Output: {output_video.resolve()}")
    print(f"YOLO: {output_yolo_video.resolve()}")
    print(f"CSV: {output_csv.resolve()}")
    print(f"Metadata: {output_metadata.resolve()}")
    print(f"Target boxes: {target_box_count}/{frame_count}")
    print(f"rtmlib calls: {pose_call_count}, accepted: {pose_success_count}")


if __name__ == "__main__":
    main()
