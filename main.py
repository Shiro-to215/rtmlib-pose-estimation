from pathlib import Path
import json

import cv2
from rtmlib import Body, draw_skeleton


# ここを書き換えて、動画を探す階層とファイル名を指定してください。
INPUT_ROOT = (
    Path.home()
    / "解析用動画ファイル"
    / "9-18-SMZ"
    / "空中左-SONY"
)
INPUT_VIDEO_NAME = "C0036.MP4"   # 解析ファイル名を正しく入力

# ここを書き換えて、出力先の階層、新規フォルダ名、ファイル名を指定してください。
OUTPUT_ROOT = (
    Path.home()
    / "動画解析出力"
    / "9-18-SMZ"
    / "空中左-SONY"
)
OUTPUT_FOLDER_NAME = "空中左-4"
OUTPUT_VIDEO_NAME = "空中左-4.mp4"
OUTPUT_JSON_NAME = "空中左-4.json"

COCO_KEYPOINTS = [
    "鼻", "左目", "右目", "左耳", "右耳",
    "左肩", "右肩", "左肘", "右肘", "左手首", "右手首",
    "左股関節", "右股関節", "左膝", "右膝", "左足首", "右足首",
]

BACKEND = "onnxruntime"
DEVICE = "cpu"
MODEL_MODE = "balanced"
KEYPOINT_THRESHOLD = 0.45


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


def main() -> None:
    input_video = find_input_video()
    output_directory = OUTPUT_ROOT / OUTPUT_FOLDER_NAME
    output_video = output_directory / OUTPUT_VIDEO_NAME
    output_json = output_directory / OUTPUT_JSON_NAME

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
    with output_json.open("w", encoding="utf-8") as json_file:
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
                frame_data = {
                    "frame": frame_count,
                    "time_seconds": frame_count / fps,
                    "persons": [],
                }
                for person_keypoints, person_scores in zip(keypoints, scores):
                    person = {}
                    for index, name in enumerate(COCO_KEYPOINTS):
                        x, y = person_keypoints[index]
                        person[name] = {
                            "x": float(x),
                            "y": float(y),
                            "score": float(person_scores[index]),
                        }
                    frame_data["persons"].append(person)

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


if __name__ == "__main__":
    main()
