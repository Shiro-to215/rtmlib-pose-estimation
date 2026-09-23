from pathlib import Path
import csv
import json
import math

import cv2
from rtmlib import Body, draw_skeleton


# ここを書き換えて、動画を探す階層とファイル名を指定してください。
INPUT_ROOT = (
    Path.home()
    / "解析用動画ファイル"
    / "9-18-SMZ"
    / "踏切右-GoPro"
)
INPUT_VIDEO_NAME = "GX010047.MP4"   # 解析ファイル名を正しく入力

# ここを書き換えて、出力先の階層、新規フォルダ名、ファイル名を指定してください。
OUTPUT_ROOT = (
    Path.home()
    / "動画解析出力"
    / "9-18-SMZ-分析用①"
    / "踏切右-GoPro"
)
OUTPUT_FOLDER_NAME = "踏切右"
OUTPUT_VIDEO_NAME = "踏切右.mp4"
OUTPUT_JSON_NAME = "踏切右.json"
OUTPUT_CSV_NAME = "踏切右.csv"

COCO_KEYPOINTS = [
    "鼻", "左目", "右目", "左耳", "右耳",
    "左肩", "右肩", "左肘", "右肘", "左手首", "右手首",
    "左股関節", "右股関節", "左膝", "右膝", "左足首", "右足首",
]

BACKEND = "onnxruntime"
DEVICE = "cpu"
#推定モデルを設定[performance , balanced , lightweight]
MODEL_MODE = "performance"
KEYPOINT_THRESHOLD = 0.45
TRACK_MAX_DISTANCE = 250.0
TRACK_MAX_MISSED_FRAMES = 30
CSV_MAX_PERSONS = 15
TRACK_MATCH_THRESHOLD = 2.0
TRACK_CENTER_WEIGHT = 0.35
TRACK_KEYPOINT_WEIGHT = 0.35
TRACK_POSE_WEIGHT = 0.20
TRACK_BBOX_WEIGHT = 0.10
TRACK_VELOCITY_SMOOTHING = 0.7


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
    persons_by_id = {
        person["person_id"]: person for person in frame_data["persons"]
    }
    for person_index in range(CSV_MAX_PERSONS):
        prefix = f"person_{person_index}"
        person = persons_by_id.get(person_index)
        row[f"{prefix}_id"] = "" if person is None else person["person_id"]
        for name in COCO_KEYPOINTS:
            keypoint = None if person is None else person[name]
            row[f"{prefix}_{name}_x"] = "" if keypoint is None else keypoint["x"]
            row[f"{prefix}_{name}_y"] = "" if keypoint is None else keypoint["y"]
            row[f"{prefix}_{name}_score"] = "" if keypoint is None else keypoint["score"]
    return row


def main() -> None:
    input_video = find_input_video()
    output_directory = OUTPUT_ROOT / OUTPUT_FOLDER_NAME
    output_video = output_directory / OUTPUT_VIDEO_NAME
    output_json = output_directory / OUTPUT_JSON_NAME
    output_csv = output_directory / OUTPUT_CSV_NAME

    output_directory.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(input_video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open input video: {input_video.resolve()}")

    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    writer = cv2.VideoWriter(
        str(output_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"Could not create output video: {output_video.resolve()}")

    body = Body(
        mode=MODEL_MODE,
        backend=BACKEND,
        device=DEVICE,
    )

    frame_count = 0
    tracks = {}
    next_person_id = 0
    with (
        output_json.open("w", encoding="utf-8") as json_file,
        output_csv.open("w", newline="", encoding="utf-8-sig") as csv_file,
    ):
        csv_writer = csv.DictWriter(csv_file, fieldnames=get_csv_fieldnames())
        csv_writer.writeheader()
        json_file.write("{\n")
        json_file.write('"input_video": ')
        json.dump(str(input_video.resolve()), json_file, ensure_ascii=False)
        json_file.write(f',\n"width": {width},\n"height": {height},\n"fps": {fps}')
        json_file.write(',\n"frames": [\n')

        try:
            while True:
                success, frame = capture.read()
                if not success:
                    break

                keypoints, scores = body(frame)
                person_ids, next_person_id = assign_person_ids(
                    keypoints,
                    scores,
                    tracks,
                    next_person_id,
                )
                frame_data = {
                    "frame": frame_count,
                    "time_seconds": frame_count / fps,
                    "persons": [],
                }
                for person_id, person_keypoints, person_scores in zip(
                    person_ids,
                    keypoints,
                    scores,
                ):
                    person = {"person_id": person_id}
                    for index, name in enumerate(COCO_KEYPOINTS):
                        x, y = person_keypoints[index]
                        person[name] = {
                            "x": float(x),
                            "y": float(y),
                            "score": float(person_scores[index]),
                        }
                    frame_data["persons"].append(person)

                if any(
                    person["person_id"] >= CSV_MAX_PERSONS
                    for person in frame_data["persons"]
                ):
                    raise RuntimeError(
                        "A person_id is outside the CSV range. Increase "
                        f"CSV_MAX_PERSONS (currently {CSV_MAX_PERSONS})."
                    )
                csv_writer.writerow(make_csv_row(frame_data))

                if frame_count > 0:
                    json_file.write(",\n")
                json.dump(frame_data, json_file, ensure_ascii=False)

                frame = draw_skeleton(
                    frame,
                    keypoints,
                    scores,
                    kpt_thr=KEYPOINT_THRESHOLD,
                )
                writer.write(frame)
                frame_count += 1

                if frame_count % 30 == 0:
                    print(f"Processed {frame_count} frames", flush=True)
        finally:
            json_file.write("\n]\n}\n")
            capture.release()
            writer.release()

    print(f"Finished: {frame_count} frames")
    print(f"Output: {output_video.resolve()}")
    print(f"JSON: {output_json.resolve()}")
    print(f"CSV: {output_csv.resolve()}")


if __name__ == "__main__":
    main()
