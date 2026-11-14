"""ViTPose++ (ONNX Runtime / PyTorch / Hugging Face Transformers) estimator implementation."""
from __future__ import annotations

from contextlib import contextmanager
import importlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from typing import Any, Iterator, Optional

import cv2
import numpy as np

from .base import (
    COCO_FLIP_INDEX,
    BasePoseEstimator,
    bbox_xyxy2cs,
    clamped_target_box,
    clear_cuda_cache,
    draw_pose_skeleton,
    get_cuda_free_total_gb,
    top_down_affine_udp,
)

try:
    from scipy.ndimage import gaussian_filter as _SCIPY_GAUSSIAN_FILTER
except Exception:
    _SCIPY_GAUSSIAN_FILTER = None

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
    if _SCIPY_GAUSSIAN_FILTER is not None:
        return _SCIPY_GAUSSIAN_FILTER(heatmap, sigma=sigma)
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

    px_grid = (max_idx % hm_w).astype(np.intp)
    py_grid = (max_idx // hm_w).astype(np.intp)
    coords = np.stack((px_grid.astype(np.float32), py_grid.astype(np.float32)), axis=-1)

    valid_mask = scores > 0.0
    if np.any(valid_mask):
        vb, vk = np.nonzero(valid_mask)
        valid_hms = hm_arr[vb, vk]
        if blur_sigma > 0.0:
            if _SCIPY_GAUSSIAN_FILTER is not None:
                blurred_valid = _SCIPY_GAUSSIAN_FILTER(
                    valid_hms, sigma=(0.0, blur_sigma, blur_sigma)
                )
            else:
                ksize = max(3, int(2 * round(3 * blur_sigma) + 1))
                if ksize % 2 == 0:
                    ksize += 1
                blurred_valid = np.stack(
                    [
                        cv2.GaussianBlur(h, (ksize, ksize), sigmaX=blur_sigma, sigmaY=blur_sigma)
                        for h in valid_hms
                    ],
                    axis=0,
                )
        else:
            blurred_valid = valid_hms

        max_vals = blurred_valid.reshape(len(vb), -1).max(axis=1)
        active = max_vals > 0.0
        if np.any(active):
            vb = vb[active]
            vk = vk[active]
            v_blurred = blurred_valid[active]
            px_v = px_grid[vb, vk]
            py_v = py_grid[vb, vk]

            interior = (px_v > 1) & (px_v < hm_w - 2) & (py_v > 1) & (py_v < hm_h - 2)
            if np.any(interior):
                i_idx = np.nonzero(interior)[0]
                ib = vb[i_idx]
                ik = vk[i_idx]
                ipx = px_v[i_idx]
                ipy = py_v[i_idx]
                hb = v_blurred[i_idx]
                m_idx = np.arange(len(i_idx))

                def _log_stencil(dy_off: int, dx_off: int) -> np.ndarray:
                    vals = np.maximum(hb[m_idx, ipy + dy_off, ipx + dx_off], np.float32(1e-10))
                    return np.log(vals).astype(np.float32, copy=False)

                c00 = _log_stencil(0, 0)
                dx = np.float32(0.5) * (_log_stencil(0, 1) - _log_stencil(0, -1))
                dy = np.float32(0.5) * (_log_stencil(1, 0) - _log_stencil(-1, 0))
                dxx = np.float32(0.25) * (_log_stencil(0, 2) - np.float32(2.0) * c00 + _log_stencil(0, -2))
                dyy = np.float32(0.25) * (_log_stencil(2, 0) - np.float32(2.0) * c00 + _log_stencil(-2, 0))
                dxy = np.float32(0.25) * (
                    _log_stencil(1, 1) - _log_stencil(-1, 1) - _log_stencil(1, -1) + _log_stencil(-1, -1)
                )
                det = dxx * dyy - dxy * dxy
                valid_det = np.abs(det) > 1e-6
                concave = valid_det & (dxx < 0.0) & (det > 0.0)
                non_concave = valid_det & (~concave)

                if np.any(concave):
                    c_det = det[concave]
                    ox = -(dyy[concave] * dx[concave] - dxy[concave] * dy[concave]) / c_det
                    oy = -(-dxy[concave] * dx[concave] + dxx[concave] * dy[concave]) / c_det
                    coords[ib[concave], ik[concave], 0] += np.clip(ox, -0.5, 0.5)
                    coords[ib[concave], ik[concave], 1] += np.clip(oy, -0.5, 0.5)
                if np.any(non_concave):
                    coords[ib[non_concave], ik[non_concave], 0] += np.sign(dx[non_concave]) * np.float32(0.25)
                    coords[ib[non_concave], ik[non_concave], 1] += np.sign(dy[non_concave]) * np.float32(0.25)

            edge = (~interior) & (px_v > 0) & (px_v < hm_w - 1) & (py_v > 0) & (py_v < hm_h - 1)
            if np.any(edge):
                e_idx = np.nonzero(edge)[0]
                eb = vb[e_idx]
                ek = vk[e_idx]
                epx = px_v[e_idx]
                epy = py_v[e_idx]
                edx = hm_arr[eb, ek, epy, epx + 1] - hm_arr[eb, ek, epy, epx - 1]
                edy = hm_arr[eb, ek, epy + 1, epx] - hm_arr[eb, ek, epy - 1, epx]
                coords[eb, ek, 0] += np.sign(edx) * np.float32(0.25)
                coords[eb, ek, 1] += np.sign(edy) * np.float32(0.25)

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


_HF_TRUE_VALUES = frozenset({"1", "ON", "YES", "TRUE"})
_MIN_LOG_DOWNLOAD_BYTES = 1024 * 1024  # Skip small metadata files (< 1 MiB)
_PROGRESS_STEP_PCT = 5
_PROGRESS_INTERVAL_SEC = 5.0


def configure_hf_environment() -> None:
    """Apply safe Hugging Face defaults before huggingface_hub is imported."""
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _format_bytes(num_bytes: float) -> str:
    """Format a byte count into a human-readable IEC-scaled string."""
    size = max(0.0, float(num_bytes))
    if size < 1024.0:
        return f"{size:.0f} B"
    if size < 1024.0 ** 2:
        return f"{size / 1024.0:.1f} KB"
    if size < 1024.0 ** 3:
        return f"{size / (1024.0 ** 2):.1f} MB"
    return f"{size / (1024.0 ** 3):.2f} GB"


class _DownloadProgressLogger:
    """Lightweight tqdm-compatible progress reporter emitting throttled stdout lines."""

    _class_lock = threading.RLock()

    def __init__(
        self,
        *args: Any,
        total: int | float | None = None,
        initial: int | float = 0,
        desc: str | None = None,
        unit: str | None = None,
        disable: bool | None = False,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        del args, kwargs
        self._lock = threading.Lock()
        self.total = int(total) if total is not None else None
        self.n = max(0, int(initial or 0))
        self._start_n = self.n
        self.desc = str(desc or "").strip()
        self._unit = str(unit or "")
        self._name = str(name or "")
        env_disabled = (os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS") or "").strip().upper() in _HF_TRUE_VALUES
        self._enabled = (
            not bool(disable)
            and not env_disabled
            and self._unit == "B"
            and self._name != "huggingface_hub.snapshot_download.transfer"
        )
        now = time.monotonic()
        self._start_time = now
        self._last_log_time = now
        self._last_log_pct = -1
        self._last_log_bytes = self.n
        self._completed_logged = False

    @classmethod
    def get_lock(cls) -> threading.RLock:
        return cls._class_lock

    @classmethod
    def set_lock(cls, lock: Any) -> None:
        cls._class_lock = lock

    def __enter__(self) -> "_DownloadProgressLogger":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _emit_progress(self, pct: int, now: float) -> None:
        total = self.total or 0
        elapsed = max(now - self._start_time, 1e-6)
        transferred = max(0, self.n - self._start_n)
        rate_str = _format_bytes(transferred / elapsed)
        label = f" [{self.desc}]" if self.desc else ""
        print(
            f"ダウンロード進捗{label}: {pct}% ({_format_bytes(self.n)} / {_format_bytes(total)}, {rate_str}/s)",
            flush=True,
        )
        self._last_log_time = now
        self._last_log_pct = pct
        self._last_log_bytes = self.n
        if pct >= 100:
            self._completed_logged = True

    def update(self, n: int | float | None = 1) -> None:
        if n is None:
            return
        with self._lock:
            self.n = max(0, self.n + int(n))
            if not self._enabled or self.total is None or self.total < _MIN_LOG_DOWNLOAD_BYTES:
                return
            pct = min(100, int((self.n * 100) // self.total))
            now = time.monotonic()
            if pct >= 100:
                if not self._completed_logged:
                    self._emit_progress(100, now)
                return
            pct_reached = self._last_log_pct < 0 and pct >= _PROGRESS_STEP_PCT
            step_reached = self._last_log_pct >= 0 and pct >= self._last_log_pct + _PROGRESS_STEP_PCT
            interval_reached = (now - self._last_log_time) >= _PROGRESS_INTERVAL_SEC and self.n > self._last_log_bytes
            if pct_reached or step_reached or interval_reached:
                self._emit_progress(pct, now)

    def refresh(self) -> None:
        pass

    def set_description(self, desc: str | None = None, refresh: bool = True) -> None:
        del refresh
        if desc is not None:
            self.desc = str(desc).strip()

    def set_description_str(self, desc: str | None = None, refresh: bool = True) -> None:
        self.set_description(desc, refresh=refresh)

    def set_postfix_str(self, s: str = "", refresh: bool = True) -> None:
        del s, refresh

    def set_transfer_postfix_str(self, s: str = "", refresh: bool = True) -> None:
        del s, refresh

    def close(self) -> None:
        with self._lock:
            if (
                self._enabled
                and self.total is not None
                and self.total >= _MIN_LOG_DOWNLOAD_BYTES
                and self.n >= self.total
                and not self._completed_logged
            ):
                self._emit_progress(100, time.monotonic())


@contextmanager
def _hf_download_progress_logging() -> Iterator[None]:
    """Temporarily route huggingface_hub download progress bars to throttled stdout logs."""
    hf_tqdm_mod = importlib.import_module("huggingface_hub.utils.tqdm")

    try:
        hf_snap_mod = importlib.import_module("huggingface_hub._snapshot_download")
    except Exception:
        hf_snap_mod = None

    orig_utils_tqdm = getattr(hf_tqdm_mod, "tqdm", None)
    orig_snap_tqdm = getattr(hf_snap_mod, "hf_tqdm", None) if hf_snap_mod is not None else None
    hf_tqdm_mod.tqdm = _DownloadProgressLogger  # type: ignore[assignment]
    if hf_snap_mod is not None and orig_snap_tqdm is not None:
        hf_snap_mod.hf_tqdm = _DownloadProgressLogger  # type: ignore[assignment]
    try:
        yield
    finally:
        if orig_utils_tqdm is not None:
            hf_tqdm_mod.tqdm = orig_utils_tqdm
        if hf_snap_mod is not None and orig_snap_tqdm is not None:
            hf_snap_mod.hf_tqdm = orig_snap_tqdm


VITPOSE_ONNX_OPSET = 17


def get_vitpose_onnx_cache_dir() -> Path:
    """Return directory path for cached ViTPose++ ONNX models."""
    override = os.environ.get("VITPOSE_ONNX_CACHE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "rtmlib_pose_estimation" / "vitpose_onnx"


def get_vitpose_onnx_path(
    model_size: str,
    input_size: str = "256x192",
    *,
    fp16: bool = False,
) -> Path:
    """Return canonical ONNX cache file path for a ViTPose++ configuration."""
    selection = resolve_vitpose_selection(model_size, input_size)
    ds_idx = int(selection["asset"].get("dataset_index", 0))
    prec = "fp16" if fp16 else "fp32"
    filename = (
        f"vitpose-plus-{selection['model_size']}_{selection['resolution']}"
        f"_ds{ds_idx}_{prec}_op{VITPOSE_ONNX_OPSET}.onnx"
    )
    return get_vitpose_onnx_cache_dir() / filename


def has_cached_vitpose_onnx(
    model_size: str,
    input_size: str = "256x192",
    *,
    fp16: bool = False,
) -> bool:
    """Return True if a non-empty cached ViTPose++ ONNX file exists."""
    try:
        onnx_path = get_vitpose_onnx_path(model_size, input_size, fp16=fp16)
    except ValueError:
        return False
    return onnx_path.is_file() and onnx_path.stat().st_size > 0


def _is_vitpose_from_pretrained_mocked() -> bool:
    """Detect patched VitPoseForPoseEstimation.from_pretrained in unit tests without importing transformers."""
    transformers_mod = sys.modules.get("transformers")
    if transformers_mod is None:
        return False
    cls = getattr(transformers_mod, "VitPoseForPoseEstimation", None)
    if cls is None:
        return False
    fn = getattr(cls, "from_pretrained", None)
    return fn is not None and (hasattr(fn, "assert_called") or hasattr(fn, "_mock_name"))


def fuse_vitpose_moe_expert(model: Any, dataset_index: int = 0) -> Any:
    """Fuse fc2 + experts[dataset_index] in ViTPose++ MoE MLP layers into a single Linear layer.

    Removes unused MoE expert branches while preserving exact numeric output for dataset_index.
    """
    import torch
    import torch.nn as nn

    class _FusedVitPoseMLP(nn.Module):
        def __init__(
            self,
            fc1: nn.Module,
            act: Any,
            fused_fc2: nn.Linear,
        ) -> None:
            super().__init__()
            self.fc1 = fc1
            self.act = act
            self.fc2 = fused_fc2

        def forward(
            self,
            hidden_state: torch.Tensor,
            indices: torch.Tensor | None = None,
        ) -> torch.Tensor:
            del indices
            return self.fc2(self.act(self.fc1(hidden_state)))

    layers = getattr(getattr(getattr(model, "backbone", None), "encoder", None), "layer", None)
    if layers is None:
        return model

    for layer in layers:
        mlp = getattr(layer, "mlp", None)
        if mlp is None:
            continue
        fc1 = getattr(mlp, "fc1", None)
        fc2 = getattr(mlp, "fc2", None)
        act = getattr(mlp, "act", None)
        experts = getattr(mlp, "experts", None)
        if (
            fc1 is None
            or fc2 is None
            or act is None
            or experts is None
            or not (0 <= dataset_index < len(experts))
        ):
            continue
        expert = experts[dataset_index]
        has_bias = (fc2.bias is not None) or (expert.bias is not None)
        fused_fc2 = nn.Linear(
            fc2.in_features,
            fc2.out_features + expert.out_features,
            bias=has_bias,
            dtype=fc2.weight.dtype,
            device=fc2.weight.device,
        )
        with torch.no_grad():
            fused_fc2.weight.copy_(torch.cat([fc2.weight.data, expert.weight.data], dim=0))
            if has_bias:
                b_fc2 = (
                    fc2.bias.data
                    if fc2.bias is not None
                    else torch.zeros(fc2.out_features, dtype=fc2.weight.dtype, device=fc2.weight.device)
                )
                b_exp = (
                    expert.bias.data
                    if expert.bias is not None
                    else torch.zeros(expert.out_features, dtype=expert.weight.dtype, device=expert.weight.device)
                )
                fused_fc2.bias.copy_(torch.cat([b_fc2, b_exp], dim=0))
        layer.mlp = _FusedVitPoseMLP(fc1, act, fused_fc2)
    return model


def _build_vitpose_export_wrapper(model: Any, dataset_index: int) -> Any:
    """Wrap ViTPose model so ONNX graph takes only pixel_values and returns heatmaps."""
    import torch

    class _VitPoseOnnxExportWrapper(torch.nn.Module):
        def __init__(self, inner: Any, ds_index: int) -> None:
            super().__init__()
            self.model = inner
            self.dataset_index = int(ds_index)

        def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
            ds = torch.full(
                (pixel_values.shape[0],),
                self.dataset_index,
                dtype=torch.long,
                device=pixel_values.device,
            )
            outputs = self.model(pixel_values=pixel_values, dataset_index=ds)
            return outputs.heatmaps

    return _VitPoseOnnxExportWrapper(model, dataset_index)


def export_vitpose_to_onnx(
    pytorch_model: Any,
    onnx_path: Path,
    input_size: tuple[int, int],
    *,
    dataset_index: int = 0,
    fp16: bool = False,
    export_device: str = "cpu",
) -> Path:
    """Export a ViTPose++ PyTorch model (with MoE Expert fusion) to an ONNX file atomically."""
    import warnings
    import onnx
    import torch

    onnx_path = Path(onnx_path)
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    crop_w, crop_h = int(input_size[0]), int(input_size[1])
    dtype = torch.float16 if fp16 else torch.float32

    pytorch_model.eval()
    pytorch_model = fuse_vitpose_moe_expert(pytorch_model, dataset_index=dataset_index)
    pytorch_model.to(device=export_device, dtype=dtype)
    wrapper = _build_vitpose_export_wrapper(pytorch_model, dataset_index)
    wrapper.eval()

    dummy_input = torch.zeros((1, 3, crop_h, crop_w), dtype=dtype, device=export_device)
    tmp_dir = Path(tempfile.mkdtemp(dir=onnx_path.parent, prefix=".tmp_export_"))
    stage_dir = Path(tempfile.mkdtemp(dir=onnx_path.parent, prefix=".tmp_stage_"))
    try:
        tmp_onnx = tmp_dir / onnx_path.name
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            warnings.filterwarnings("ignore", message=r".*Converting a tensor to a Python boolean.*")
            with torch.no_grad():
                torch.onnx.export(
                    wrapper,
                    (dummy_input,),
                    str(tmp_onnx),
                    dynamo=False,
                    opset_version=VITPOSE_ONNX_OPSET,
                    input_names=["pixel_values"],
                    output_names=["heatmaps"],
                    dynamic_axes={"pixel_values": {0: "batch"}, "heatmaps": {0: "batch"}},
                )

        exported_files = list(tmp_dir.iterdir())
        data_dest = onnx_path.with_name(f"{onnx_path.name}.data")
        if len(exported_files) == 1:
            if data_dest.exists():
                data_dest.unlink()
            os.replace(tmp_onnx, onnx_path)
        else:
            proto = onnx.load(str(tmp_onnx), load_external_data=True)
            stage_onnx = stage_dir / onnx_path.name
            data_name = f"{onnx_path.name}.data"
            onnx.save_model(
                proto,
                str(stage_onnx),
                save_as_external_data=True,
                all_tensors_to_one_file=True,
                location=data_name,
            )
            stage_data = stage_dir / data_name
            if stage_data.is_file():
                os.replace(stage_data, data_dest)
            os.replace(stage_onnx, onnx_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(stage_dir, ignore_errors=True)
    return onnx_path


def preimport_vitpose_dependencies() -> None:
    """Pre-import Hugging Face transformers ViTPose class into RAM (no weights or CUDA)."""
    try:
        configure_hf_environment()
        import transformers

        transformers.utils.logging.disable_progress_bar()
        from transformers import VitPoseForPoseEstimation  # noqa: F401
    except Exception:
        pass


class ViTPoseEstimator(BasePoseEstimator):
    """High-accuracy ViTPose++ estimator using ONNX Runtime (with PyTorch fallback), UDP, and Flip Test TTA."""

    def __init__(
        self,
        model_size: str = "h",
        input_size: str = "256x192",
        device: str = "cpu",
        *,
        flip_test: bool = True,
        pytorch_model: Any = None,
        ort_session: Any = None,
        use_onnx: bool = True,
    ) -> None:
        self._selection = resolve_vitpose_selection(model_size, input_size)
        self._asset = self._selection["asset"]
        self._device = str(device)
        self._is_cuda = self._device.startswith("cuda")
        self._use_fp16 = self._is_cuda
        self._flip_test = bool(flip_test)
        self._dataset_index_value = int(self._asset.get("dataset_index", 0))
        self._model: Any = None
        self._ort_session: Any = None

        if pytorch_model is not None:
            self._model = pytorch_model
        elif ort_session is not None:
            self._ort_session = ort_session
        elif use_onnx and not _is_vitpose_from_pretrained_mocked():
            self._init_ort_or_fallback()
        else:
            self._model = self._load_model()

    def _init_ort_or_fallback(self) -> None:
        onnx_path = get_vitpose_onnx_path(
            self._selection["model_size"],
            self._selection["resolution"],
            fp16=self._use_fp16,
        )
        try:
            if not has_cached_vitpose_onnx(
                self._selection["model_size"],
                self._selection["resolution"],
                fp16=self._use_fp16,
            ):
                print(
                    f"ViTPose++ ONNX変換・キャッシュ生成中: {self._selection['model_size'].upper()} "
                    f"({'FP16' if self._use_fp16 else 'FP32'})",
                    flush=True,
                )
                pt_model = self._load_model(target_device="cpu")
                try:
                    try:
                        export_vitpose_to_onnx(
                            pt_model,
                            onnx_path,
                            self.model_input_size,
                            dataset_index=self._dataset_index_value,
                            fp16=self._use_fp16,
                            export_device="cpu",
                        )
                    except Exception:
                        if not self._is_cuda:
                            raise
                        export_vitpose_to_onnx(
                            pt_model,
                            onnx_path,
                            self.model_input_size,
                            dataset_index=self._dataset_index_value,
                            fp16=self._use_fp16,
                            export_device=self._device,
                        )
                finally:
                    del pt_model
                    clear_cuda_cache()

            self._ort_session = self._create_ort_session(onnx_path)
            return
        except Exception as exc:
            print(
                f"ViTPose++ ONNX初期化をスキップし、PyTorch推論へフォールバックします: {exc}",
                flush=True,
            )
            self._ort_session = None
            self._model = self._load_model()

    def _create_ort_session(self, onnx_path: Path) -> Any:
        import onnxruntime as ort

        if self._is_cuda and hasattr(ort, "preload_dlls"):
            ort.preload_dlls()

        if self._is_cuda:
            cuda_idx = int(self._device.split(":")[1]) if ":" in self._device else 0
            providers: list[Any] = [
                (
                    "CUDAExecutionProvider",
                    {
                        "device_id": cuda_idx,
                        "arena_extend_strategy": "kSameAsRequested",
                    },
                ),
                "CPUExecutionProvider",
            ]
        else:
            providers = ["CPUExecutionProvider"]

        session = ort.InferenceSession(str(onnx_path), providers=providers)
        if self._is_cuda and "CUDAExecutionProvider" not in session.get_providers():
            raise RuntimeError("ONNX Runtime で CUDAExecutionProvider を利用できません。")
        return session

    def _load_model(self, target_device: Optional[str] = None) -> Any:
        configure_hf_environment()
        import torch
        import transformers

        transformers.utils.logging.disable_progress_bar()
        from transformers import VitPoseForPoseEstimation

        dtype = torch.float16 if self._use_fp16 else torch.float32
        repo_id = self._asset["repo_id"]
        dest_device = self._device if target_device is None else target_device

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
            with _hf_download_progress_logging():
                model = _from_pretrained(local_files_only=False)
        model.to(dest_device)
        model.eval()
        return model

    @property
    def model_input_size(self) -> tuple[int, int]:
        return tuple(self._asset["input_size"])

    @property
    def display_name(self) -> str:
        tta_tag = "Flip" if self._flip_test else "NoFlip"
        prec_tag = "FP16" if self._use_fp16 else "FP32"
        backend_tag = "ONNX, " if self._ort_session is not None else ""
        return (
            f"ViTPose++-{self._selection['model_size'].upper()} "
            f"({self._selection['resolution']}, {backend_tag}{prec_tag}, {tta_tag})"
        )

    @property
    def progress_phase(self) -> str:
        return "VITPOSE"

    def supports_dynamic_batch(self) -> tuple[bool, object]:
        if self._ort_session is not None:
            try:
                inputs = self._ort_session.get_inputs()
                if inputs and getattr(inputs[0], "shape", None):
                    batch_dim = inputs[0].shape[0]
                    if isinstance(batch_dim, int) and batch_dim > 0:
                        return False, batch_dim
                    return True, batch_dim
            except Exception:
                return True, "dynamic"
        return True, "dynamic"

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

    def _forward_heatmaps_ort(self, feed_np: np.ndarray) -> np.ndarray:
        """Run ViTPose++ ONNX Runtime session (with optional Flip Test TTA) and return FP32 heatmaps."""
        session = self._ort_session
        input_meta = session.get_inputs()[0]
        input_name = input_meta.name
        output_name = session.get_outputs()[0].name
        expected_type = str(getattr(input_meta, "type", "") or "").lower()
        target_dtype = np.float16 if "float16" in expected_type else np.float32
        feed_input = np.ascontiguousarray(feed_np, dtype=target_dtype)

        heatmaps = np.asarray(
            session.run([output_name], {input_name: feed_input})[0],
            dtype=np.float32,
        )
        if self._flip_test:
            flipped_input = np.ascontiguousarray(feed_input[:, :, :, ::-1])
            flip_heatmaps = np.asarray(
                session.run([output_name], {input_name: flipped_input})[0],
                dtype=np.float32,
            )
            flip_heatmaps = flip_heatmaps[:, list(COCO_FLIP_INDEX), :, ::-1]
            heatmaps = np.float32(0.5) * (heatmaps + flip_heatmaps)
        return heatmaps

    def _forward_heatmaps(self, pixel_tensor: Any) -> Any:
        """Run ViTPose++ PyTorch forward pass (with FP16 autocast on CUDA) and return FP32 heatmaps."""
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
        if not batch_items:
            return []

        crop_w, crop_h = self.model_input_size
        prepared: list[Optional[tuple[np.ndarray, np.ndarray, Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]]]] = []
        valid_metas: list[tuple[np.ndarray, np.ndarray, Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]]] = []
        target_cap = max(len(batch_items), fixed_batch_size or 0)

        batch_array = None
        if batch_buffer is not None:
            buf = batch_buffer.get("vitpose_tensor")
            if buf is None or buf.shape[0] < target_cap or buf.shape[1:] != (3, crop_h, crop_w):
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

        if self._ort_session is not None:
            run_count = (
                fixed_batch_size
                if (fixed_batch_size and fixed_batch_size >= valid_count)
                else valid_count
            )
            if run_count > valid_count:
                batch_array[valid_count:run_count] = batch_array[0]
            feed_np = np.ascontiguousarray(batch_array[:run_count], dtype=np.float32)
            heatmaps_np = self._forward_heatmaps_ort(feed_np)
            if run_count > valid_count:
                heatmaps_np = heatmaps_np[:valid_count]
        else:
            import torch

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
        self._ort_session = None
        self._model = None
        super().close()
