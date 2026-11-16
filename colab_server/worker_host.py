"""Colab GPU persistent worker host, chunked video store, and ZIP result builder."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import importlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable
import uuid
import zipfile

import gui
from reservation_queue import write_json

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_FILENAME_STRIP_RE = re.compile(r'[\\/:*?"<>|\x00]+')
_STRIPPED_CLIENT_KEYS = {
    "INPUT_ROOT",
    "INPUT_VIDEO_NAME",
    "OUTPUT_ROOT",
    "OUTPUT_FOLDER_NAME",
    "__CANCEL_FLAG_FILE__",
    "__OUTPUT_MODE__",
    "OUTPUT_MODE",
}


def validate_sha256_hex(value: str) -> str:
    """Validate and normalize lowercase 64-char SHA-256 hex digest."""
    norm = str(value or "").strip().lower()
    if not _SHA256_RE.match(norm):
        raise ValueError(f"Invalid SHA-256 hex digest: {value!r}")
    return norm


def sanitize_filename(name: str, default: str = "file.bin") -> str:
    """Sanitize a client-provided basename so it cannot escape target directory."""
    raw = str(name or "").replace("\\", "/").split("/")[-1]
    cleaned = _SAFE_FILENAME_STRIP_RE.sub("_", raw).strip()
    if cleaned in ("", ".", ".."):
        return default
    return cleaned


@dataclass
class ColabJobRecord:
    """Runtime record for one inference job submitted to the Colab server."""

    job_id: str
    video_sha256: str
    video_path: Path
    root_dir: Path
    output_dir: Path
    config_path: Path
    cancel_flag_path: Path
    output_mode: str = "data_only"
    state: str = "queued"  # queued | running | done | failed | cancelled
    progress_pct: float = 0.0
    phase: str = "IDLE"
    exit_code: int | None = None
    error: str = ""
    cancel_requested: bool = False
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    tail_lines: list[str] = field(default_factory=list)
    next_seq: int = 1
    result_zip_path: Path | None = None
    notify_cond: threading.Condition = field(default_factory=threading.Condition)

    def append_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.notify_cond:
            event = dict(payload)
            event["seq"] = self.next_seq
            self.next_seq += 1
            self.events.append(event)
            self.notify_cond.notify_all()
            return event

    def snapshot_status(self) -> dict[str, Any]:
        with self.notify_cond:
            return {
                "job_id": self.job_id,
                "video_sha256": self.video_sha256,
                "output_mode": self.output_mode,
                "state": self.state,
                "progress_pct": self.progress_pct,
                "phase": self.phase,
                "last_seq": self.next_seq - 1,
                "exit_code": self.exit_code,
                "error": self.error,
            }


class ColabWorkerHost:
    """Manages uploaded videos, queued inference jobs, and persistent gui.py worker."""

    def __init__(
        self,
        work_dir: Path | str,
        *,
        base_dir: Path | None = None,
        worker_cmd: list[str] | None = None,
        on_job_finished: Callable[[ColabJobRecord], None] | None = None,
        max_video_cache_bytes: int = 8 * 1024 * 1024 * 1024,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.videos_dir = self.work_dir / "videos"
        self.chunks_dir = self.work_dir / "chunks"
        self.jobs_dir = self.work_dir / "jobs"
        for d in (self.videos_dir, self.chunks_dir, self.jobs_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.base_dir = Path(base_dir) if base_dir is not None else Path(gui.__file__).resolve().parent
        self.worker_cmd = worker_cmd
        self.on_job_finished = on_job_finished
        self.max_video_cache_bytes = max_video_cache_bytes

        self._lock = threading.RLock()
        self._jobs: dict[str, ColabJobRecord] = {}
        self._job_queue: queue.Queue[str] = queue.Queue()
        self._active_job_id: str | None = None

        self._proc: subprocess.Popen[str] | None = None
        self._worker_ready = False
        self._stop_event = threading.Event()
        self._dispatcher_thread: threading.Thread | None = None

    # ---- Video Store & Chunked Upload --------------------------------------

    def find_video_by_sha256(self, sha256: str) -> Path | None:
        digest = validate_sha256_hex(sha256)
        with self._lock:
            for p in sorted(self.videos_dir.glob(f"{digest}_*")):
                if p.is_file() and p.stat().st_size > 0:
                    return p
        return None

    def receive_chunk(
        self,
        sha256: str,
        filename: str,
        chunk_index: int,
        total_chunks: int,
        data: bytes,
    ) -> dict[str, Any]:
        digest = validate_sha256_hex(sha256)
        idx = int(chunk_index)
        total = int(total_chunks)
        if total < 1 or idx < 0 or idx >= total:
            raise ValueError(f"Invalid chunk index {idx}/{total}")

        existing = self.find_video_by_sha256(digest)
        if existing is not None:
            return {"status": "exists", "video_sha256": digest, "complete": True, "filename": existing.name}

        safe_name = sanitize_filename(filename, default="video.mp4")
        chunk_root = self.chunks_dir / digest
        chunk_root.mkdir(parents=True, exist_ok=True)
        meta_path = chunk_root / "meta.json"
        if not meta_path.exists():
            write_json(meta_path, {"filename": safe_name, "total_chunks": total})

        part_path = chunk_root / f"chunk_{idx:06d}.part"
        part_path.write_bytes(data)

        received_parts = sorted(chunk_root.glob("chunk_*.part"))
        if len(received_parts) < total:
            return {
                "status": "partial",
                "video_sha256": digest,
                "complete": False,
                "received_chunks": len(received_parts),
                "total_chunks": total,
            }

        expected_parts = [chunk_root / f"chunk_{i:06d}.part" for i in range(total)]
        if not all(p.is_file() for p in expected_parts):
            return {
                "status": "partial",
                "video_sha256": digest,
                "complete": False,
                "received_chunks": len(received_parts),
                "total_chunks": total,
            }

        tmp_assembled = self.videos_dir / f".{digest}.{uuid.uuid4().hex[:8]}.tmp"
        hasher = hashlib.sha256()
        try:
            with tmp_assembled.open("wb") as out_f:
                for part in expected_parts:
                    chunk_bytes = part.read_bytes()
                    hasher.update(chunk_bytes)
                    out_f.write(chunk_bytes)
            actual_digest = hasher.hexdigest().lower()
            if actual_digest != digest:
                shutil.rmtree(chunk_root, ignore_errors=True)
                raise ValueError(
                    f"SHA-256 verification failed for uploaded video: expected {digest}, got {actual_digest}"
                )
            final_path = self.videos_dir / f"{digest}_{safe_name}"
            os.replace(tmp_assembled, final_path)
            shutil.rmtree(chunk_root, ignore_errors=True)
        finally:
            if tmp_assembled.exists():
                try:
                    tmp_assembled.unlink()
                except OSError:
                    pass

        self._evict_old_videos_if_needed(keep_sha256=digest)
        return {
            "status": "stored",
            "video_sha256": digest,
            "complete": True,
            "filename": final_path.name,
            "size": final_path.stat().st_size,
        }

    def _evict_old_videos_if_needed(self, keep_sha256: str | None = None) -> None:
        if self.max_video_cache_bytes <= 0:
            return
        with self._lock:
            active_shas = {
                j.video_sha256
                for j in self._jobs.values()
                if j.state in ("queued", "running")
            }
            if keep_sha256:
                active_shas.add(keep_sha256)
            candidates = [p for p in self.videos_dir.iterdir() if p.is_file() and not p.name.startswith(".")]
            total_size = sum(p.stat().st_size for p in candidates)
            if total_size <= self.max_video_cache_bytes:
                return
            candidates.sort(key=lambda p: p.stat().st_mtime)
            for p in candidates:
                sha_prefix = p.name.split("_", 1)[0]
                if sha_prefix in active_shas:
                    continue
                try:
                    sz = p.stat().st_size
                    p.unlink()
                    total_size -= sz
                except OSError:
                    pass
                if total_size <= self.max_video_cache_bytes:
                    break

    # ---- Config & Job Submission -------------------------------------------

    def prepare_job_config(
        self,
        job_id: str,
        video_path: Path,
        raw_settings: dict[str, Any] | None,
        output_mode: str = "data_only",
    ) -> tuple[dict[str, Any], Path, Path]:
        """Sanitize client settings and rewrite all filesystem paths to Colab job directory."""
        job_root = self.jobs_dir / job_id
        output_folder_name = "output"
        job_output_dir = job_root / output_folder_name
        job_output_dir.mkdir(parents=True, exist_ok=True)
        cancel_flag_path = job_root / "cancel.flag"

        filtered = {
            k: deepcopy(v)
            for k, v in (raw_settings or {}).items()
            if k not in _STRIPPED_CLIENT_KEYS
        }
        normalized = gui.normalize_legacy_rtmlib_settings(filtered)
        engine_keys = set(getattr(gui, "ENGINE_DEFAULTS", {}))
        clean_settings: dict[str, Any] = {
            k: v for k, v in normalized.items() if k in engine_keys
        }

        default_out = gui.output_names(job_output_dir)
        for out_key, default_name in default_out.items():
            clean_settings[out_key] = sanitize_filename(
                str(clean_settings.get(out_key) or default_name),
                default=default_name,
            )

        clean_settings["INPUT_ROOT"] = str(video_path.parent)
        clean_settings["INPUT_VIDEO_NAME"] = video_path.name
        clean_settings["OUTPUT_ROOT"] = str(job_root)
        clean_settings["OUTPUT_FOLDER_NAME"] = output_folder_name
        if str(clean_settings.get("DEVICE", "auto")).strip().lower() == "cpu":
            clean_settings["DEVICE"] = "auto"

        norm_mode = gui.normalize_output_mode(output_mode)
        clean_settings["__OUTPUT_MODE__"] = norm_mode
        clean_settings["__CANCEL_FLAG_FILE__"] = str(cancel_flag_path)

        config_path = job_root / "job_config.json"
        write_json(config_path, clean_settings)
        return clean_settings, job_output_dir, cancel_flag_path

    def submit_job(
        self,
        video_sha256: str,
        settings: dict[str, Any] | None = None,
        output_mode: str = "data_only",
        *,
        auto_start: bool = True,
    ) -> ColabJobRecord:
        digest = validate_sha256_hex(video_sha256)
        video_path = self.find_video_by_sha256(digest)
        if video_path is None:
            raise FileNotFoundError(f"Video not uploaded on Colab server: {digest}")

        job_id = uuid.uuid4().hex
        norm_mode = gui.normalize_output_mode(output_mode)
        job_root = self.jobs_dir / job_id
        job_root.mkdir(parents=True, exist_ok=True)
        _, job_output_dir, cancel_flag_path = self.prepare_job_config(
            job_id,
            video_path,
            settings,
            output_mode=norm_mode,
        )
        config_path = job_root / "job_config.json"

        record = ColabJobRecord(
            job_id=job_id,
            video_sha256=digest,
            video_path=video_path,
            root_dir=job_root,
            output_dir=job_output_dir,
            config_path=config_path,
            cancel_flag_path=cancel_flag_path,
            output_mode=norm_mode,
        )
        with self._lock:
            self._jobs[job_id] = record
            self._job_queue.put(job_id)

        if auto_start:
            self.start()
        return record

    # ---- Worker Process & Dispatcher Lifecycle -----------------------------

    def start(self) -> None:
        with self._lock:
            if self._dispatcher_thread is None or not self._dispatcher_thread.is_alive():
                self._stop_event.clear()
                self._dispatcher_thread = threading.Thread(
                    target=self._dispatcher_loop,
                    daemon=True,
                    name="ColabWorkerDispatcher",
                )
                self._dispatcher_thread.start()

    def _default_worker_cmd(self) -> list[str]:
        return [
            sys.executable,
            "-u",
            "-X",
            "utf8",
            str(self.base_dir / "gui.py"),
            "--persistent-worker",
        ]

    def _spawn_worker(self) -> subprocess.Popen[str]:
        cmd = self.worker_cmd if self.worker_cmd is not None else self._default_worker_cmd()
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        return subprocess.Popen(
            cmd,
            cwd=str(self.base_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )

    def _ensure_worker_ready(self) -> subprocess.Popen[str]:
        with self._lock:
            proc = self._proc
            if proc is not None and proc.poll() is None and self._worker_ready and proc.stdin is not None:
                return proc

        self._terminate_worker()
        proc = self._spawn_worker()
        if proc.stdout is None:
            raise RuntimeError("Colab persistent worker stdout is unavailable")

        while True:
            line = proc.stdout.readline()
            if not line:
                rc = proc.wait()
                raise RuntimeError(f"Persistent worker exited before WORKER_READY (code={rc})")
            if line.strip() == "WORKER_READY":
                with self._lock:
                    self._proc = proc
                    self._worker_ready = True
                return proc

    def _terminate_worker(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            self._worker_ready = False
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin is not None:
                try:
                    proc.stdin.write("SHUTDOWN\n")
                    proc.stdin.flush()
                    proc.stdin.close()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
        finally:
            for stream in (proc.stdin, proc.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass

    def shutdown(self) -> None:
        self._stop_event.set()
        self._job_queue.put("")
        self._terminate_worker()
        thread = self._dispatcher_thread
        if thread is not None and thread.is_alive() and threading.current_thread() != thread:
            thread.join(timeout=3.0)

    def _dispatcher_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id = self._job_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if self._stop_event.is_set() or not job_id:
                    continue
                record = self.get_job(job_id)
                if record is None:
                    continue
                self._execute_job(record)
            finally:
                self._job_queue.task_done()

    def _execute_job(self, record: ColabJobRecord) -> None:
        with record.notify_cond:
            if record.cancel_requested or record.state == "cancelled":
                record.state = "cancelled"
                record.exit_code = 1
                record.finished_at = time.time()
                record.notify_cond.notify_all()
                return
            record.state = "running"
            record.phase = "STARTING"
            record.progress_pct = 0.0
            record.notify_cond.notify_all()

        with self._lock:
            self._active_job_id = record.job_id

        exit_code = 1
        try:
            proc = self._ensure_worker_ready()
            if proc.stdin is None or proc.stdout is None:
                raise RuntimeError("Worker pipes are unavailable")
            proc.stdin.write(f"RUN_JOB:{record.config_path}\n")
            proc.stdin.flush()

            job_done = False
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                stripped = line.strip()
                if stripped.startswith("JOB_DONE:"):
                    try:
                        exit_code = int(stripped.split(":", 1)[1])
                    except ValueError:
                        exit_code = 1
                    job_done = True
                    break
                if stripped.startswith("PROGRESS:"):
                    parts = stripped.split(":", 2)
                    if len(parts) == 3:
                        try:
                            pct = float(parts[1])
                            phase = parts[2].strip()
                            with record.notify_cond:
                                record.progress_pct = pct
                                record.phase = phase
                            record.append_event({"type": "progress", "pct": pct, "phase": phase})
                            continue
                        except ValueError:
                            pass
                with record.notify_cond:
                    record.tail_lines.append(line)
                    record.tail_lines = record.tail_lines[-24:]
                record.append_event({"type": "log", "line": line})

            if not job_done:
                rc = proc.wait()
                self._terminate_worker()
                exit_code = rc if rc != 0 else 1
        except Exception as exc:
            exit_code = 1
            msg = f"Colab worker error: {exc}\n"
            with record.notify_cond:
                record.tail_lines.append(msg)
            record.append_event({"type": "log", "line": msg})
            self._terminate_worker()
        finally:
            with self._lock:
                if self._active_job_id == record.job_id:
                    self._active_job_id = None

            with record.notify_cond:
                record.exit_code = exit_code
                record.finished_at = time.time()
                if record.cancel_requested:
                    record.state = "cancelled"
                    record.phase = "STOPPING"
                    record.error = "Cancelled by user"
                elif exit_code == 0:
                    record.state = "done"
                    record.progress_pct = 100.0
                    record.phase = "DONE"
                else:
                    record.state = "failed"
                    record.error = "".join(record.tail_lines)[-2000:].strip() or f"Exit code {exit_code}"
                status_payload = {
                    "type": "status",
                    "state": record.state,
                    "exit_code": record.exit_code,
                    "error": record.error,
                }
            record.append_event(status_payload)

            if record.state == "done" and self.on_job_finished is not None:
                try:
                    self.on_job_finished(record)
                except Exception:
                    pass

    # ---- Query, Cancel, Result ZIP & Cleanup -------------------------------

    def get_job(self, job_id: str) -> ColabJobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        record = self.get_job(job_id)
        if record is None:
            raise KeyError(f"Unknown job_id: {job_id}")
        return record.snapshot_status()

    def get_events_since(
        self,
        job_id: str,
        from_seq: int = 0,
        *,
        wait_timeout: float = 0.0,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Return (events_after_from_seq, is_terminal)."""
        record = self.get_job(job_id)
        if record is None:
            raise KeyError(f"Unknown job_id: {job_id}")
        terminal_states = ("done", "failed", "cancelled")
        with record.notify_cond:
            events = [e for e in record.events if int(e.get("seq", 0)) > from_seq]
            if not events and record.state not in terminal_states and wait_timeout > 0:
                record.notify_cond.wait(timeout=wait_timeout)
                events = [e for e in record.events if int(e.get("seq", 0)) > from_seq]
            is_terminal = record.state in terminal_states and (
                not events or int(record.events[-1].get("seq", 0)) <= int(events[-1].get("seq", 0))
            ) if record.events else (record.state in terminal_states)
            return events, is_terminal

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        record = self.get_job(job_id)
        if record is None:
            raise KeyError(f"Unknown job_id: {job_id}")
        with record.notify_cond:
            if record.state in ("done", "failed", "cancelled"):
                return record.snapshot_status()
            record.cancel_requested = True
            if record.state == "queued":
                record.state = "cancelled"
                record.exit_code = 1
                record.finished_at = time.time()
                record.error = "Cancelled while queued"
                record.notify_cond.notify_all()
        try:
            record.cancel_flag_path.parent.mkdir(parents=True, exist_ok=True)
            record.cancel_flag_path.write_text("cancel\n", encoding="utf-8")
        except OSError:
            pass
        if record.state == "cancelled":
            record.append_event(
                {"type": "status", "state": "cancelled", "exit_code": 1, "error": record.error}
            )
        return record.snapshot_status()

    def build_result_zip(self, job_id: str) -> Path:
        record = self.get_job(job_id)
        if record is None:
            raise KeyError(f"Unknown job_id: {job_id}")
        if record.state != "done":
            raise RuntimeError(f"Job {job_id} is not completed (state={record.state})")
        if record.result_zip_path is not None and record.result_zip_path.is_file():
            return record.result_zip_path

        allowed_suffixes = {".csv", ".npz", ".json", ".txt"}
        if record.output_mode == "web_video":
            allowed_suffixes.add(".mp4")

        zip_path = record.root_dir / "result.zip"
        tmp_zip = record.root_dir / f".result.{uuid.uuid4().hex[:8]}.zip.tmp"
        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as zf:
                for file_path in sorted(record.output_dir.iterdir()):
                    if not file_path.is_file():
                        continue
                    if file_path.suffix.lower() not in allowed_suffixes:
                        continue
                    zf.write(file_path, arcname=file_path.name)
            os.replace(tmp_zip, zip_path)
        finally:
            if tmp_zip.exists():
                try:
                    tmp_zip.unlink()
                except OSError:
                    pass

        with record.notify_cond:
            record.result_zip_path = zip_path
        return zip_path

    def cleanup_job(self, job_id: str) -> bool:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return False
            if record.state in ("queued", "running"):
                raise RuntimeError(f"Cannot delete active job {job_id}")
            shutil.rmtree(record.root_dir, ignore_errors=True)
            self._jobs.pop(job_id, None)
            return True

    def health_info(self) -> dict[str, Any]:
        gpu_name = None
        vram_free_gb = None
        vram_total_gb = None
        try:
            torch_mod = importlib.import_module("torch")
            if torch_mod.cuda.is_available():
                gpu_name = str(torch_mod.cuda.get_device_name(0))
                free_b, total_b = torch_mod.cuda.mem_get_info(0)
                vram_free_gb = round(free_b / (1024**3), 2)
                vram_total_gb = round(total_b / (1024**3), 2)
        except Exception:
            pass

        ram_total_gb = None
        ram_avail_gb = None
        try:
            psutil_mod = importlib.import_module("psutil")
            vm = psutil_mod.virtual_memory()
            ram_total_gb = round(vm.total / (1024**3), 2)
            ram_avail_gb = round(vm.available / (1024**3), 2)
        except Exception:
            avail_b = gui._get_available_system_ram_bytes()
            if avail_b is not None:
                ram_avail_gb = round(avail_b / (1024**3), 2)

        with self._lock:
            queued_count = sum(1 for j in self._jobs.values() if j.state == "queued")
            return {
                "status": "ok",
                "gpu_name": gpu_name,
                "vram_free_gb": vram_free_gb,
                "vram_total_gb": vram_total_gb,
                "ram_total_gb": ram_total_gb,
                "ram_available_gb": ram_avail_gb,
                "worker_ready": self._worker_ready,
                "active_job_id": self._active_job_id,
                "queued_count": queued_count,
                "capabilities": ["data_only", "web_video"],
            }
