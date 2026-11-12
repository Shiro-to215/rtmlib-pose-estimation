"""ViTPose++ (PyTorch / Hugging Face Transformers) estimator implementation."""
from __future__ import annotations

from typing import Any, Optional

import cv2
import numpy as np

from .base import (
    COCO_FLIP_INDEX,
    BasePoseEstimator,
    bbox_xyxy2cs,
    clamped_target_box,
    draw_pose_skeleton,
    get_cuda_free_total_gb,
    top_down_affine_udp,
)

# Official Hugging Face usyd-community ViTPose++ checkpoints (Classic decoder, 256x192, MoE COCO expert=0).
VITPOSE_ASSETS: dict[str, dict[str, dict[str, Any]]] = {
    "s": {
        "256x192": {
            "repo_id": "usyd-community/vitpose-plus-small",
            "input_size": (192, 256),
            "dataset_index": 0,
            "vram_weights_gb": 0.2,
            "vram_per_sample_gb": 0.04,
            "label": "ViTPose++-S (Small)",
        },
    },
    "b": {
        "256x192": {
            "repo_id": "usyd-community/vitpose-plus-base",
            "input_size": (192, 256),
            "dataset_index": 0,
            "vram_weights_gb": 0.4,
            "vram_per_sample_gb": 0.06,
            "label": "ViTPose++-B (Base)",
        },
    },
    "l": {
        "256x192": {
            "repo_id": "usyd-community/vitpose-plus-large",
            "input_size": (192, 256),
            "dataset_index": 0,
            "vram_weights_gb": 0.9,
            "vram_per_sample_gb": 0.11,
            "label": "ViTPose++-L (Large)",
        },
    },
    "h": {
        "256x192": {
            "repo_id": "usyd-community/vitpose-plus-huge",
            "input_size": (192, 256),
            "dataset_index": 0,
            "vram_weights_gb": 1.6,
            "vram_per_sample_gb": 0.18,
            "label": "ViTPose++-H (Huge)",
        },
    },
}

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def resolve_vitpose_selection(
    model_size: str,
    input_size: str = "256x192",
) -> dict[str, Any]:
    """Validate and resolve ViTPose++ model size and fixed 256x192 input resolution."""
    normalized_size = str(model_size or "h").strip().lower()
    normalized_res = str(input_size or "256x192").strip().lower()
    if normalized_size not in VITPOSE_ASSETS:
        raise ValueError(f"不明なViTPose++モデルサイズです: {model_size}")
    asset = VITPOSE_ASSETS[normalized_size].get(normalized_res)
    if asset is None:
        available = " / ".join(VITPOSE_ASSETS[normalized_size])
        raise ValueError(
            f"ViTPose++-{normalized_size.upper()} は {input_size} に対応していません。"
            f"使用できる解像度: {available}。"
        )
    return {
        "model_size": normalized_size,
        "resolution": normalized_res,
        "asset": asset,
    }


def _gaussian_blur_2d(heatmap: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    """Apply 2D Gaussian blur for DARK/UDP sub-pixel refinement."""
    try:
        from scipy.ndimage import gaussian_filter

        return gaussian_filter(heatmap, sigma=sigma)
    except Exception:
        ksize = max(3, int(2 * round(3 * sigma) + 1))
        if ksize % 2 == 0:
            ksize += 1
        return cv2.GaussianBlur(heatmap, (ksize, ksize), sigmaX=sigma, sigmaY=sigma)


def decode_heatmaps_udp(
    heatmaps: np.ndarray,
    centers: np.ndarray,
    scales: np.ndarray,
    *,
    blur_sigma: float = 1.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Decode (B, K, H, W) float32 heatmaps using UDP + DARK Taylor sub-pixel refinement.

    Args:
        heatmaps: Float32 numpy array of shape (B, K, H, W).
        centers: Array of shape (B, 2) containing bbox centers (cx, cy).
        scales: Array of shape (B, 2) containing bbox scales (sw, sh).
        blur_sigma: Gaussian smoothing sigma for log-heatmap Hessian stability.

    Returns:
        (coords, scores) with coords of shape (B, K, 2) and scores of shape (B, K).
    """
    hm_arr = np.asarray(heatmaps, dtype=np.float32)
    batch_size, num_joints, hm_h, hm_w = hm_arr.shape

    flat = hm_arr.reshape(batch_size, num_joints, -1)
    max_idx = np.argmax(flat, axis=-1)
    scores = np.take_along_axis(flat, max_idx[..., None], axis=-1)[..., 0].astype(np.float32)

    coords = np.zeros((batch_size, num_joints, 2), dtype=np.float32)
    coords[:, :, 0] = (max_idx % hm_w).astype(np.float32)
    coords[:, :, 1] = (max_idx // hm_w).astype(np.float32)

    for b in range(batch_size):
        for k in range(num_joints):
            if scores[b, k] <= 0.0:
                continue
            hm = hm_arr[b, k]
            blurred = _gaussian_blur_2d(hm, sigma=blur_sigma) if blur_sigma > 0 else hm
            max_val = float(np.max(blurred))
            if max_val <= 0.0:
                continue
            # Rescale peak magnitude to match raw heatmap peak, then compute log-heatmap Taylor step.
            blurred = np.maximum(blurred, 1e-10)
            log_hm = np.log(blurred)

            px = int(coords[b, k, 0])
            py = int(coords[b, k, 1])
            if 1 < px < hm_w - 2 and 1 < py < hm_h - 2:
                dx = 0.5 * (log_hm[py, px + 1] - log_hm[py, px - 1])
                dy = 0.5 * (log_hm[py + 1, px] - log_hm[py - 1, px])
                dxx = 0.25 * (log_hm[py, px + 2] - 2.0 * log_hm[py, px] + log_hm[py, px - 2])
                dyy = 0.25 * (log_hm[py + 2, px] - 2.0 * log_hm[py, px] + log_hm[py - 2, px])
                dxy = 0.25 * (
                    log_hm[py + 1, px + 1]
                    - log_hm[py - 1, px + 1]
                    - log_hm[py + 1, px - 1]
                    + log_hm[py - 1, px - 1]
                )
                hessian = np.array([[dxx, dxy], [dxy, dyy]], dtype=np.float32)
                det = float(hessian[0, 0] * hessian[1, 1] - hessian[0, 1] * hessian[1, 0])
                if abs(det) > 1e-6:
                    # Only apply second-order Newton step when local Hessian is negative-definite (concave peak).
                    if hessian[0, 0] < 0.0 and det > 0.0:
                        inv_h = np.array(
                            [[hessian[1, 1], -hessian[0, 1]], [-hessian[1, 0], hessian[0, 0]]],
                            dtype=np.float32,
                        ) / det
                        offset = -inv_h @ np.array([dx, dy], dtype=np.float32)
                        coords[b, k, 0] += float(np.clip(offset[0], -0.5, 0.5))
                        coords[b, k, 1] += float(np.clip(offset[1], -0.5, 0.5))
                    else:
                        coords[b, k, 0] += float(np.sign(dx) * 0.25)
                        coords[b, k, 1] += float(np.sign(dy) * 0.25)
            elif 0 < px < hm_w - 1 and 0 < py < hm_h - 1:
                dx = hm[py, px + 1] - hm[py, px - 1]
                dy = hm[py + 1, px] - hm[py - 1, px]
                coords[b, k, 0] += float(np.sign(dx) * 0.25)
                coords[b, k, 1] += float(np.sign(dy) * 0.25)

    # UDP unbiased inverse mapping: [0, hm_w - 1] <-> [center_x - scale_x/2, center_x + scale_x/2]
    denom_x = max(float(hm_w - 1), 1.0)
    denom_y = max(float(hm_h - 1), 1.0)
    restored = np.empty_like(coords, dtype=np.float32)
    restored[:, :, 0] = (coords[:, :, 0] / denom_x - 0.5) * scales[:, 0:1] + centers[:, 0:1]
    restored[:, :, 1] = (coords[:, :, 1] / denom_y - 0.5) * scales[:, 1:2] + centers[:, 1:2]
    return restored, scores


def normalize_crop_bgr_to_chw(crop_bgr: np.ndarray) -> np.ndarray:
    """Convert (H, W, 3) uint8 BGR crop to normalized (3, H, W) float32 RGB array without resizing."""
    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) * (1.0 / 255.0)
    rgb = (rgb - IMAGENET_MEAN) / IMAGENET_STD
    return np.transpose(rgb, (2, 0, 1))


def preimport_vitpose_dependencies() -> None:
    """Pre-import Hugging Face transformers ViTPose class into RAM (no weights or CUDA)."""
    try:
        import transformers

        transformers.utils.logging.disable_progress_bar()
        from transformers import VitPoseForPoseEstimation  # noqa: F401
    except Exception:
        pass


class ViTPoseEstimator(BasePoseEstimator):
    """High-accuracy PyTorch ViTPose++ estimator with UDP affine/decode, FP16 AMP, and Flip Test TTA."""

    def __init__(
        self,
        model_size: str = "h",
        input_size: str = "256x192",
        device: str = "cpu",
        *,
        flip_test: bool = True,
        pytorch_model: Any = None,
    ) -> None:
        self._selection = resolve_vitpose_selection(model_size, input_size)
        self._asset = self._selection["asset"]
        self._device = str(device)
        self._is_cuda = self._device.startswith("cuda")
        self._use_fp16 = self._is_cuda
        self._flip_test = bool(flip_test)
        self._dataset_index_value = int(self._asset.get("dataset_index", 0))
        self._model = pytorch_model if pytorch_model is not None else self._load_model()

    def _load_model(self) -> Any:
        import torch
        import transformers

        transformers.utils.logging.disable_progress_bar()
        from transformers import VitPoseForPoseEstimation

        dtype = torch.float16 if self._use_fp16 else torch.float32
        repo_id = self._asset["repo_id"]

        def _from_pretrained(*, local_files_only: bool) -> Any:
            try:
                return VitPoseForPoseEstimation.from_pretrained(
                    repo_id,
                    dtype=dtype,
                    local_files_only=local_files_only,
                )
            except TypeError:
                return VitPoseForPoseEstimation.from_pretrained(
                    repo_id,
                    torch_dtype=dtype,
                    local_files_only=local_files_only,
                )

        try:
            model = _from_pretrained(local_files_only=True)
        except OSError:
            # First-time download or incomplete local cache: fall back to Hugging Face Hub.
            print(f"初回モデルダウンロード中: {repo_id}", flush=True)
            model = _from_pretrained(local_files_only=False)
        model.to(self._device)
        model.eval()
        return model

    @property
    def model_input_size(self) -> tuple[int, int]:
        return tuple(self._asset["input_size"])

    @property
    def display_name(self) -> str:
        tta_tag = "Flip" if self._flip_test else "NoFlip"
        prec_tag = "FP16" if self._use_fp16 else "FP32"
        return (
            f"ViTPose++-{self._selection['model_size'].upper()} "
            f"({self._selection['resolution']}, {prec_tag}, {tta_tag})"
        )

    @property
    def progress_phase(self) -> str:
        return "VITPOSE"

    def cap_batch_by_vram(self, requested: int, device: str) -> int:
        if requested <= 1 or not str(device).startswith("cuda"):
            return requested
        mem_info = get_cuda_free_total_gb(device)
        if mem_info is None:
            return requested
        free_gb, _ = mem_info
        # Leave safe headroom for CUDA allocator / context and output video writers.
        usable_gb = max(0.25, (free_gb - 1.0) * 0.75)
        per_sample_gb = float(self._asset.get("vram_per_sample_gb", 0.15))
        safe_max = max(1, int(usable_gb / max(per_sample_gb, 0.02)))
        if requested > safe_max:
            print(
                f"ViTPose++: VRAM空き容量 {free_gb:.1f}GB に合わせて"
                f"バッチサイズを {requested} -> {safe_max} に制限します。",
                flush=True,
            )
            return safe_max
        return requested

    def _forward_heatmaps(self, pixel_tensor: Any) -> Any:
        """Run ViTPose++ forward pass (with FP16 autocast on CUDA) and return FP32 heatmaps."""
        import contextlib
        import torch

        batch_len = pixel_tensor.shape[0]
        dataset_idx = torch.full(
            (batch_len,),
            self._dataset_index_value,
            dtype=torch.long,
            device=pixel_tensor.device,
        )
        amp_ctx = (
            torch.amp.autocast("cuda", dtype=torch.float16)
            if self._use_fp16
            else contextlib.nullcontext()
        )
        with torch.inference_mode():
            with amp_ctx:
                outputs = self._model(pixel_values=pixel_tensor, dataset_index=dataset_idx)
                heatmaps = outputs.heatmaps.float()
                if self._flip_test:
                    flipped_inputs = torch.flip(pixel_tensor, dims=[-1])
                    flip_outputs = self._model(
                        pixel_values=flipped_inputs,
                        dataset_index=dataset_idx,
                    )
                    flip_heatmaps = torch.flip(flip_outputs.heatmaps.float(), dims=[-1])
                    flip_heatmaps = flip_heatmaps[:, list(COCO_FLIP_INDEX), :, :]
                    heatmaps = 0.5 * (heatmaps + flip_heatmaps)
        return heatmaps

    def infer_single(
        self,
        frame: np.ndarray,
        target_box: Any,
        *,
        return_crop: bool = False,
    ) -> Any:
        results = self.infer_batch(
            [(frame, target_box)],
            fixed_batch_size=None,
            batch_buffer=None,
            return_crop=return_crop,
        )
        return results[0]

    def infer_batch(
        self,
        batch_items: list[tuple[np.ndarray, Any]],
        fixed_batch_size: Optional[int] = None,
        batch_buffer: Optional[dict] = None,
        *,
        return_crop: bool = False,
    ) -> list[Any]:
        import torch

        if not batch_items:
            return []

        crop_w, crop_h = self.model_input_size
        prepared: list[Optional[tuple[np.ndarray, np.ndarray, Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]]]] = []
        valid_metas: list[tuple[np.ndarray, np.ndarray, Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]]] = []
        target_cap = len(batch_items)

        batch_array = None
        if batch_buffer is not None:
            buf = batch_buffer.get("vitpose_tensor")
            if buf is None or buf.shape != (target_cap, 3, crop_h, crop_w):
                buf = np.empty((target_cap, 3, crop_h, crop_w), dtype=np.float32)
                batch_buffer["vitpose_tensor"] = buf
            batch_array = buf
        else:
            batch_array = np.empty((target_cap, 3, crop_h, crop_w), dtype=np.float32)

        tensor_idx = 0
        for frame, target_box in batch_items:
            height, width = frame.shape[:2]
            clamped = clamped_target_box(target_box, width, height)
            if clamped is None:
                prepared.append(None)
                continue
            center, scale = bbox_xyxy2cs(clamped, padding=1.25)
            crop_bgr, adj_scale = top_down_affine_udp(
                (crop_w, crop_h),
                scale,
                center,
                frame,
            )
            batch_array[tensor_idx] = normalize_crop_bgr_to_chw(crop_bgr)
            tensor_idx += 1
            crop_info = (crop_bgr, center, adj_scale) if return_crop else None
            meta = (center, adj_scale, crop_info)
            valid_metas.append(meta)
            prepared.append(meta)

        valid_count = len(valid_metas)
        if valid_count == 0:
            empty_item = ((None, None), None) if return_crop else (None, None)
            return [empty_item for _ in batch_items]

        feed_np = np.ascontiguousarray(batch_array[:valid_count], dtype=np.float32)
        pixel_tensor = torch.from_numpy(feed_np).to(self._device, non_blocking=self._is_cuda)
        heatmaps_tensor = self._forward_heatmaps(pixel_tensor)
        heatmaps_np = heatmaps_tensor.detach().float().cpu().numpy()

        centers_np = np.asarray([m[0] for m in valid_metas], dtype=np.float32)
        scales_np = np.asarray([m[1] for m in valid_metas], dtype=np.float32)
        coords_np, scores_np = decode_heatmaps_udp(heatmaps_np, centers_np, scales_np)

        results: list[Any] = []
        valid_idx = 0
        for meta in prepared:
            if meta is None:
                results.append(((None, None), None) if return_crop else (None, None))
                continue
            kpts_list = [(float(pt[0]), float(pt[1])) for pt in coords_np[valid_idx]]
            scs_arr = scores_np[valid_idx]
            pose_pair = (kpts_list, scs_arr)
            if return_crop:
                results.append((pose_pair, meta[2]))
            else:
                results.append(pose_pair)
            valid_idx += 1
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
        crop_w, crop_h = self.model_input_size
        udp_span = np.array([max(crop_w - 1, 1), max(crop_h - 1, 1)], dtype=np.float32)
        safe_scale = np.where(scale_arr == 0, 1.0, scale_arr)
        crop_kpts = (
            ((np.asarray(restored_keypoints, dtype=np.float32) - center_arr) / safe_scale + 0.5)
            * udp_span
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
