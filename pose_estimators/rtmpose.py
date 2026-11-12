"""RTMPose (ONNX Runtime / rtmlib) estimator implementation."""
from __future__ import annotations

import contextlib
import io
import re
from typing import Any, Optional

import numpy as np

from .base import (
    BasePoseEstimator,
    clamped_target_box,
    draw_pose_skeleton,
    get_cuda_free_total_gb,
)

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


def resolve_rtmlib_selection(pose_model: str, pose_input_size: str) -> dict[str, Any]:
    """Resolve RTMLib model choices to downloadable models and input sizes."""
    if pose_model not in RTMLIB_POSE_ASSETS:
        raise ValueError(f"不明なRTMPoseモデルです: {pose_model}")

    pose_asset = RTMLIB_POSE_ASSETS[pose_model].get(pose_input_size)
    if pose_asset is None:
        available = " / ".join(RTMLIB_POSE_ASSETS[pose_model])
        raise ValueError(
            f"RTMPose-{pose_model.upper()} は {pose_input_size} に対応していません。"
            f"使用できる解像度: {available}。"
        )

    return {
        "pose_model": pose_model,
        "pose_resolution": pose_input_size,
        "pose_asset": pose_asset,
    }


def _ensure_pose_preprocess_ready(pose_model: Any) -> None:
    """Convert mean/std once so concurrent or repeated preprocess calls avoid re-allocation."""
    if getattr(pose_model, "mean", None) is not None and not isinstance(
        pose_model.mean, np.ndarray
    ):
        pose_model.mean = np.array(pose_model.mean)
    if getattr(pose_model, "std", None) is not None and not isinstance(
        pose_model.std, np.ndarray
    ):
        pose_model.std = np.array(pose_model.std)


def _write_chw_float32_into(preprocessed_img: Any, dest: np.ndarray) -> None:
    """Copy rtmlib RTMPose.preprocess output directly into a pre-allocated (3, H, W) float32 slice."""
    arr = np.asarray(preprocessed_img)
    if arr.ndim == 4 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.ndim == 3 and arr.shape[2] == 3:
        np.copyto(dest, np.transpose(arr, (2, 0, 1)), casting="unsafe")
    elif arr.ndim == 3 and arr.shape[0] == 3:
        np.copyto(dest, arr, casting="unsafe")
    else:
        raise ValueError(f"Unexpected preprocessed RTMPose shape: {arr.shape}")


def _extract_single_pose(keypoints: Any, scores: Any):
    """Extract 1-person (keypoints, scores) arrays from rtmlib RTMPose output."""
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


def _prepare_pose_crop(pose_model: Any, frame: np.ndarray, clamped_box: list[float]):
    """Affine-crop frame for RTMPose and return (preprocessed, crop_bgr, center, scale)."""
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


class RTMPoseEstimator(BasePoseEstimator):
    """Strategy wrapper around rtmlib.RTMPose (ONNX Runtime / OpenCV)."""

    def __init__(
        self,
        pose_model: str = "x",
        pose_input_size: str = "384x288",
        backend: str = "onnxruntime",
        device: str = "cpu",
        *,
        rtmpose_instance: Any = None,
    ) -> None:
        selection = resolve_rtmlib_selection(pose_model, pose_input_size)
        self._selection = selection
        self._backend = backend
        self._device = device
        self._model = rtmpose_instance if rtmpose_instance is not None else self._build_model()

    def _build_model(self) -> Any:
        from rtmlib import RTMPose

        pose_asset = self._selection["pose_asset"]
        init_stdout = io.StringIO()
        with contextlib.redirect_stdout(init_stdout):
            model = RTMPose(
                onnx_model=pose_asset["url"],
                model_input_size=pose_asset["input_size"],
                backend=self._backend,
                device=self._device,
            )
        for line in init_stdout.getvalue().splitlines():
            if line.strip() and not re.match(r"^load .+ with .+ backend$", line.strip()):
                print(line, flush=True)
        if self._backend == "onnxruntime":
            providers = model.session.get_providers()
            if str(self._device).startswith("cuda") and "CUDAExecutionProvider" not in providers:
                raise RuntimeError(
                    "RTMLIB pose_model のCUDA初期化に失敗しました。"
                    "CUDA/cuDNNのバージョンを確認するか、DEVICE=cpu を選択してください。"
                )
        return model

    @property
    def raw_model(self) -> Any:
        return self._model

    @property
    def model_input_size(self) -> tuple[int, int]:
        w, h = map(int, getattr(self._model, "model_input_size", self._selection["pose_asset"]["input_size"]))
        return (w, h)

    @property
    def display_name(self) -> str:
        return f"RTMPose-{self._selection['pose_model'].upper()} ({self._selection['pose_resolution']})"

    @property
    def progress_phase(self) -> str:
        return "RTMLIB"

    def supports_dynamic_batch(self) -> tuple[bool, object]:
        session = getattr(self._model, "session", None)
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

    def cap_batch_by_vram(self, requested: int, device: str) -> int:
        if requested <= 1 or not str(device).startswith("cuda"):
            return requested
        mem_info = get_cuda_free_total_gb(device)
        if mem_info is None:
            return requested
        free_gb, _ = mem_info
        crop_w, crop_h = self.model_input_size
        area_factor = max(1, crop_w * crop_h) / (192.0 * 256.0)
        usable_gb = max(0.4, free_gb * 0.85 - 0.4)
        est_gb_per_frame = 0.028 * area_factor
        safe_max = max(1, int(usable_gb / max(est_gb_per_frame, 1e-4)))
        if requested > safe_max:
            print(
                f"RTMPose: 利用可能VRAM ({free_gb:.1f}GB) に合わせて"
                f"バッチサイズを {requested} -> {safe_max} に自動調整しました。",
                flush=True,
            )
            return safe_max
        return requested

    def infer_single(
        self,
        frame: np.ndarray,
        target_box: Any,
        *,
        return_crop: bool = False,
    ) -> Any:
        height, width = frame.shape[:2]
        clamped = clamped_target_box(target_box, width, height)
        if clamped is None:
            return ((None, None), None) if return_crop else (None, None)
        if return_crop:
            preprocessed, crop_bgr, center, scale = _prepare_pose_crop(
                self._model, frame, clamped
            )
            outputs = self._model.inference(preprocessed)
            keypoints, scores = self._model.postprocess(outputs, center, scale)
            kpts, scs = _extract_single_pose(keypoints, scores)
            return (kpts, scs), (crop_bgr, center, scale)
        keypoints, scores = self._model(frame, bboxes=[clamped])
        return _extract_single_pose(keypoints, scores)

    def infer_batch(
        self,
        batch_items: list[tuple[np.ndarray, Any]],
        fixed_batch_size: Optional[int] = None,
        batch_buffer: Optional[dict] = None,
        *,
        return_crop: bool = False,
    ) -> list[Any]:
        if not batch_items:
            return []
        if len(batch_items) == 1 and (fixed_batch_size is None or fixed_batch_size <= 1):
            frame, target_box = batch_items[0]
            return [
                self.infer_single(frame, target_box, return_crop=return_crop)
            ]

        _ensure_pose_preprocess_ready(self._model)

        prepared = []
        valid_metas = []
        batch_tensor = None
        tensor_idx = 0
        target_cap = max(len(batch_items), fixed_batch_size or 0)

        def _ensure_buffer(sample_h: int, sample_w: int) -> None:
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
            clamped = clamped_target_box(target_box, width, height)
            if clamped is None:
                prepared.append(None)
                continue
            if return_crop:
                preprocessed, crop_bgr, center, scale = _prepare_pose_crop(
                    self._model, frame, clamped
                )
                crop_info = (crop_bgr, center, scale)
            else:
                preprocessed, center, scale = self._model.preprocess(frame, clamped)
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

        session = self._model.session
        input_name = session.get_inputs()[0].name
        output_names = [out.name for out in session.get_outputs()]
        raw_outputs = session.run(output_names, {input_name: feed_tensor})
        if run_count > valid_count:
            raw_outputs = [out[:valid_count] for out in raw_outputs]

        valid_results = None
        if len(raw_outputs) == 2 and valid_count > 1:
            try:
                centers = np.asarray([m[0] for m in valid_metas])[:, None, :]
                scales = np.asarray([m[1] for m in valid_metas])[:, None, :]
                kpts_batch, scores_batch = self._model.postprocess(raw_outputs, centers, scales)
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
                kpts, scs = self._model.postprocess(item_outputs, center, scale)
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

    def render_pose_on_crop(
        self,
        crop_bgr: Optional[np.ndarray],
        restored_keypoints: Any,
        pose_scores: Any,
        center: Any,
        scale: Any,
        keypoint_threshold: float = 0.45,
    ) -> Optional[np.ndarray]:
        if crop_bgr is None:
            return None
        annotated = crop_bgr.copy()
        if restored_keypoints is None or pose_scores is None:
            return annotated
        scale_arr = np.asarray(scale, dtype=np.float32)
        center_arr = np.asarray(center, dtype=np.float32)
        size_arr = np.asarray(self.model_input_size, dtype=np.float32)
        safe_scale = np.where(scale_arr == 0, 1.0, scale_arr)
        crop_kpts = (
            (np.asarray(restored_keypoints, dtype=np.float32) - (center_arr - scale_arr / 2.0))
            / safe_scale
            * size_arr
        )
        return draw_pose_skeleton(
            annotated,
            crop_kpts[None, :, :],
            np.asarray([pose_scores], dtype=np.float32),
            kpt_thr=keypoint_threshold,
        )

    def close(self) -> None:
        self._model = None
        super().close()
