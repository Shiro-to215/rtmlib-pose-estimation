from pathlib import Path
import json

import cv2
from rtmlib import Body, draw_skeleton


INPUT_VIDEO = Path("2.7K240fps-ex.MP4")
OUTPUT_VIDEO = Path("output_pose.mp4")
OUTPUT_JSON = Path("output_pose.json")

COCO_KEYPOINTS = [
    "鼻", "左目", "右目", "左耳", "右耳",
    "左肩", "右肩", "左肘", "右肘", "左手首", "右手首",
    "左股関節", "右股関節", "左膝", "右膝", "左足首", "右足首",
]

BACKEND = "onnxruntime"
DEVICE = "cpu"
MODEL_MODE = "balanced"
KEYPOINT_THRESHOLD = 0.45


def main() -> None:
    if not INPUT_VIDEO.is_file():
        raise FileNotFoundError(
            f"Input video was not found: {INPUT_VIDEO.resolve()}"
        )

    OUTPUT_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(INPUT_VIDEO))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open input video: {INPUT_VIDEO.resolve()}")

    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    writer = cv2.VideoWriter(
        str(OUTPUT_VIDEO),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"Could not create output video: {OUTPUT_VIDEO.resolve()}")

    body = Body(
        mode=MODEL_MODE,
        backend=BACKEND,
        device=DEVICE,
    )

    frame_count = 0
    with OUTPUT_JSON.open("w", encoding="utf-8") as json_file:
        json_file.write("{\n")
        json_file.write('"input_video": ')
        json.dump(str(INPUT_VIDEO.resolve()), json_file, ensure_ascii=False)
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
    print(f"Output: {OUTPUT_VIDEO.resolve()}")
    print(f"JSON: {OUTPUT_JSON.resolve()}")


if __name__ == "__main__":
    main()
