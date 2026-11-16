"""Common pose estimator interface and shared geometry/drawing utilities."""
from __future__ import annotations

from abc import ABC, abstractmethod
import contextlib
import gc
import io
from typing import Any, Optional

import cv2
import numpy as np

# Standard COCO-17 left/right symmetric keypoint index mapping used for Flip Test TTA.
COCO_FLIP_INDEX: tuple[int, ...] = (
    0,
    2, 1,
    4, 3,
    6, 5,
    8, 7,
    10, 9,
    12, 11,
    14, 13,
    16, 15,
)

# COCO-17 skeleton edges (0-indexed) for OpenCV fallback drawing when rtmlib is not loaded.
COCO_SKELETON_EDGES: tuple[tuple[int, int], ...] = (
    (15, 13), (13, 11), (16, 14), (14, 12), (11, 12),
    (5, 11), (6, 12), (5, 6), (5, 7), (6, 8),
    (7, 9), (8, 10), (1, 2), (0, 1), (0, 2),
    (1, 3), (2, 4), (3, 5), (4, 6),
)


def clear_cuda_cache() -> None:
    """Release cached PyTorch CUDA memory and force garbage collection."""
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def configure_onnxruntime_environment(
    ort_mod: Any = None,
    *,
    preload_cuda: bool = False,
) -> Any:
    """Set ONNX Runtime default severity to ERROR+ and quietly preload CUDA DLLs."""
    if ort_mod is None:
        import onnxruntime as ort_mod

    if hasattr(ort_mod, "set_default_logger_severity"):
        try:
            # 3 = ERROR; hides benign ORT C++ warnings such as plugin EP discovery misses.
            ort_mod.set_default_logger_severity(3)
        except Exception:
            pass

    if preload_cuda and hasattr(ort_mod, "preload_dlls"):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                ort_mod.preload_dlls()
        finally:
            for line in buf.getvalue().splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped == "Skip loading CUDA and cuDNN DLLs since torch is imported.":
                    continue
                print(line, flush=True)
    return ort_mod


def get_cuda_free_total_gb(device: str) -> tuple[float, float] | None:
    """Return (free_gb, total_gb) for a CUDA device, or None if unavailable."""
    if not str(device).startswith("cuda"):
        return None
    try:
        import torch
    except ImportError:
        return None
    try:
        index = int(str(device).split(":")[1]) if ":" in str(device) else 0
        free_bytes, total_bytes = torch.cuda.mem_get_info(index)
        gib = float(1024 ** 3)
        return free_bytes / gib, total_bytes / gib
    except Exception:
        return None


def clamp_box(box, width: int, height: int) -> tuple[int, int, int, int]:
    """Clamp an [x1, y1, x2, y2] box to image boundaries."""
    x1, y1, x2, y2 = map(int, box[:4])
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(width, x2)
    y2 = min(height, y2)
    return x1, y1, x2, y2


def clamped_target_box(target_box, width: int, height: int) -> list[float] | None:
    """Validate and clamp target_box; return None when degenerate or missing."""
    if target_box is None or len(target_box) < 4:
        return None
    raw_x1, raw_y1, raw_x2, raw_y2 = map(float, target_box[:4])
    if raw_x2 <= raw_x1 or raw_y2 <= raw_y1:
        return None
    clamped = clamp_box(target_box, width, height)
    if clamped[2] <= clamped[0] or clamped[3] <= clamped[1]:
        return None
    return [float(clamped[0]), float(clamped[1]), float(clamped[2]), float(clamped[3])]


def bbox_xyxy2cs(
    bbox: np.ndarray | list[float],
    padding: float = 1.25,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert xyxy bounding box into (center, scale) arrays of shape (2,)."""
    arr = np.asarray(bbox, dtype=np.float32)
    x1, y1, x2, y2 = arr[0], arr[1], arr[2], arr[3]
    center = np.array([(x1 + x2) * 0.5, (y1 + y2) * 0.5], dtype=np.float32)
    scale = np.array([max(1.0, x2 - x1) * padding, max(1.0, y2 - y1) * padding], dtype=np.float32)
    return center, scale


def fix_aspect_ratio_scale(scale: np.ndarray, aspect_ratio: float) -> np.ndarray:
    """Expand scale so width/height matches aspect_ratio without shrinking either axis."""
    w, h = float(scale[0]), float(scale[1])
    if w > h * aspect_ratio:
        h = w / aspect_ratio
    else:
        w = h * aspect_ratio
    return np.array([max(1.0, w), max(1.0, h)], dtype=np.float32)


def get_udp_warp_matrix(
    center: np.ndarray,
    scale: np.ndarray,
    output_size: tuple[int, int],
) -> np.ndarray:
    """Compute UDP-aligned 2x3 affine matrix mapping [center-scale/2, center+scale/2] to [0, w-1]x[0, h-1]."""
    dst_w, dst_h = int(output_size[0]), int(output_size[1])
    sx = float(dst_w - 1) / max(float(scale[0]), 1e-6)
    sy = float(dst_h - 1) / max(float(scale[1]), 1e-6)
    tx = (dst_w - 1) * 0.5 - sx * float(center[0])
    ty = (dst_h - 1) * 0.5 - sy * float(center[1])
    return np.array([[sx, 0.0, tx], [0.0, sy, ty]], dtype=np.float32)


def top_down_affine_udp(
    input_size: tuple[int, int],
    bbox_scale: np.ndarray,
    bbox_center: np.ndarray,
    img: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Crop and warp image using UDP coordinate conventions (single affine transform)."""
    w, h = int(input_size[0]), int(input_size[1])
    adjusted_scale = fix_aspect_ratio_scale(bbox_scale, w / float(h))
    warp_mat = get_udp_warp_matrix(bbox_center, adjusted_scale, (w, h))
    crop_bgr = cv2.warpAffine(img, warp_mat, (w, h), flags=cv2.INTER_LINEAR)
    return crop_bgr, adjusted_scale


def draw_pose_skeleton(
    image: np.ndarray,
    keypoints_batch: np.ndarray,
    scores_batch: np.ndarray,
    kpt_thr: float = 0.45,
    skeleton_line_width: int = 2,
    keypoint_radius: int = 4,
) -> np.ndarray:
    """Draw COCO-17 skeleton using rtmlib when available, with an OpenCV fallback."""
    try:
        from rtmlib import draw_skeleton

        return draw_skeleton(
            image,
            keypoints_batch,
            scores_batch,
            kpt_thr=kpt_thr,
            radius=max(1, int(keypoint_radius)),
            line_width=max(1, int(skeleton_line_width)),
        )
    except Exception:
        pass

    canvas = image.copy()
    kpts_arr = np.asarray(keypoints_batch, dtype=np.float32)
    scores_arr = np.asarray(scores_batch, dtype=np.float32)
    if kpts_arr.ndim == 2:
        kpts_arr = kpts_arr[None, :, :]
    if scores_arr.ndim == 1:
        scores_arr = scores_arr[None, :]

    for person_kpts, person_scores in zip(kpts_arr, scores_arr):
        for i, j in COCO_SKELETON_EDGES:
            if i < len(person_scores) and j < len(person_scores):
                if person_scores[i] >= kpt_thr and person_scores[j] >= kpt_thr:
                    pt1 = (int(round(person_kpts[i][0])), int(round(person_kpts[i][1])))
                    pt2 = (int(round(person_kpts[j][0])), int(round(person_kpts[j][1])))
                    cv2.line(
                        canvas,
                        pt1,
                        pt2,
                        (0, 255, 180),
                        max(1, int(skeleton_line_width)),
                        cv2.LINE_AA,
                    )
        for idx, (pt, sc) in enumerate(zip(person_kpts, person_scores)):
            if sc >= kpt_thr:
                color = (0, 200, 255) if idx < 5 else (0, 140, 255)
                cv2.circle(
                    canvas,
                    (int(round(pt[0])), int(round(pt[1]))),
                    max(1, int(keypoint_radius)),
                    color,
                    -1,
                    cv2.LINE_AA,
                )
    return canvas


class BasePoseEstimator(ABC):
    """Abstract Strategy interface for top-down 2D pose estimation engines."""

    @property
    @abstractmethod
    def model_input_size(self) -> tuple[int, int]:
        """Expected crop dimensions as (width, height)."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable model label for worker telemetry logs."""

    @property
    @abstractmethod
    def progress_phase(self) -> str:
        """Telemetry phase code emitted in PROGRESS:<pct>:<phase> lines."""

    def supports_dynamic_batch(self) -> tuple[bool, object]:
        """Return (is_dynamic, metadata) indicating whether batching >1 is supported."""
        return True, "dynamic"

    @abstractmethod
    def cap_batch_by_vram(self, requested: int, device: str) -> int:
        """Clamp requested batch size safely for available GPU VRAM."""

    @abstractmethod
    def infer_single(
        self,
        frame: np.ndarray,
        target_box: Any,
        *,
        return_crop: bool = False,
    ) -> Any:
        """Estimate pose for a single (frame, target_box) pair."""

    @abstractmethod
    def infer_batch(
        self,
        batch_items: list[tuple[np.ndarray, Any]],
        fixed_batch_size: Optional[int] = None,
        batch_buffer: Optional[dict] = None,
        *,
        return_crop: bool = False,
    ) -> list[Any]:
        """Estimate poses for a batch of (frame, target_box) pairs."""

    @abstractmethod
    def render_pose_on_crop(
        self,
        crop_bgr: Optional[np.ndarray],
        restored_keypoints: Any,
        pose_scores: Any,
        center: Any,
        scale: Any,
        keypoint_threshold: float = 0.45,
        skeleton_line_width: int = 2,
        keypoint_radius: int = 4,
    ) -> Optional[np.ndarray]:
        """Project restored frame keypoints onto crop_bgr and draw skeleton."""

    def close(self) -> None:
        """Release model weights and GPU memory."""
        clear_cuda_cache()
