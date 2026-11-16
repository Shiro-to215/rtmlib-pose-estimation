"""Atomic cache synchronization between Google Drive and Colab local SSD (/content/.cache)."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import shutil
import uuid

from pose_estimators.vitpose import verify_onnx_external_data


def is_valid_onnx_pair(onnx_path: Path) -> bool:
    """Return True if onnx_path and any external weight files exist and are valid."""
    return verify_onnx_external_data(Path(onnx_path))


def find_onnx_companion_files(onnx_path: Path) -> list[Path]:
    """Return existing external data companion paths referenced by onnx_path."""
    onnx_path = Path(onnx_path)
    base_dir = onnx_path.parent.resolve()
    companions: list[Path] = []
    seen: set[Path] = set()

    companion_default = Path(f"{onnx_path}.data")
    if companion_default.is_file():
        resolved = companion_default.resolve()
        if resolved.is_relative_to(base_dir):
            seen.add(resolved)
            companions.append(resolved)

    try:
        onnx_mod = importlib.import_module("onnx")
        model = onnx_mod.load(str(onnx_path), load_external_data=False)
        external_loc_enum = getattr(getattr(onnx_mod, "TensorProto", None), "EXTERNAL", 1)
        for init in getattr(getattr(model, "graph", None), "initializer", ()):
            if getattr(init, "data_location", 0) != external_loc_enum:
                continue
            for entry in getattr(init, "external_data", ()):
                if getattr(entry, "key", "") == "location":
                    rel = str(getattr(entry, "value", "")).strip()
                    if rel:
                        candidate = (base_dir / rel).resolve()
                        if candidate.is_relative_to(base_dir) and candidate.is_file() and candidate not in seen:
                            seen.add(candidate)
                            companions.append(candidate)
                    break
    except Exception:
        pass
    return companions


def _atomic_copy_file(src: Path, dst: Path) -> bool:
    """Atomically copy src to dst via temporary file + os.replace. Returns True if copied."""
    if not src.is_file():
        return False
    src_stat = src.stat()
    if dst.is_file():
        dst_stat = dst.stat()
        if dst_stat.st_size == src_stat.st_size and src_stat.st_size > 0:
            return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dst.parent / f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        shutil.copy2(src, tmp_path)
        os.replace(tmp_path, dst)
        return True
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _sync_vitpose_onnx_dir(src_dir: Path, dst_dir: Path) -> dict[str, int]:
    """Sync valid (.onnx + external data) sets atomically; external files copied before .onnx."""
    stats = {"copied": 0, "skipped": 0, "invalid_onnx": 0}
    if not src_dir.is_dir():
        return stats

    for onnx_file in sorted(src_dir.glob("*.onnx")):
        if not is_valid_onnx_pair(onnx_file):
            stats["invalid_onnx"] += 1
            continue
        companions = find_onnx_companion_files(onnx_file)
        # Copy external weights BEFORE the .onnx descriptor so partial interruption never creates an orphan .onnx.
        for ext_src in companions:
            rel = ext_src.relative_to(src_dir.resolve())
            if _atomic_copy_file(ext_src, dst_dir / rel):
                stats["copied"] += 1
            else:
                stats["skipped"] += 1
        if _atomic_copy_file(onnx_file, dst_dir / onnx_file.name):
            stats["copied"] += 1
        else:
            stats["skipped"] += 1
    return stats


def _sync_tree_files(src_dir: Path, dst_dir: Path, *, max_file_bytes: int | None = None) -> dict[str, int]:
    """Recursively sync regular files from src_dir to dst_dir using atomic copies."""
    stats = {"copied": 0, "skipped": 0}
    if not src_dir.is_dir():
        return stats
    for item in sorted(src_dir.rglob("*")):
        if not item.is_file():
            continue
        if item.name.endswith(".tmp") or ".locks" in item.parts:
            continue
        if max_file_bytes is not None and item.stat().st_size > max_file_bytes:
            stats["skipped"] += 1
            continue
        rel = item.relative_to(src_dir)
        if _atomic_copy_file(item, dst_dir / rel):
            stats["copied"] += 1
        else:
            stats["skipped"] += 1
    return stats


def _sync_cache_pair(src_root: Path, dst_root: Path) -> dict[str, int]:
    """Synchronize vitpose_onnx, ultralytics, and huggingface caches from src_root to dst_root."""
    src_root = Path(src_root)
    dst_root = Path(dst_root)
    total = {"copied": 0, "skipped": 0, "invalid_onnx": 0}
    if not src_root.is_dir():
        return total

    onnx_stats = _sync_vitpose_onnx_dir(src_root / "vitpose_onnx", dst_root / "vitpose_onnx")
    for k, v in onnx_stats.items():
        total[k] += v

    for sub in ("ultralytics", "huggingface"):
        tree_stats = _sync_tree_files(src_root / sub, dst_root / sub)
        total["copied"] += tree_stats["copied"]
        total["skipped"] += tree_stats["skipped"]
    return total


def sync_drive_to_local(drive_dir: Path | str, local_dir: Path | str) -> dict[str, int]:
    """Copy verified cached models from Google Drive into Colab fast local SSD cache."""
    return _sync_cache_pair(Path(drive_dir), Path(local_dir))


def sync_local_to_drive(local_dir: Path | str, drive_dir: Path | str) -> dict[str, int]:
    """Copy verified newly exported models from Colab local cache back to Google Drive."""
    return _sync_cache_pair(Path(local_dir), Path(drive_dir))
