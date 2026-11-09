"""Worker Subprocess Executor & Telemetry Stream Manager for PyWebView.

Manages sequential execution of analysis worker subprocesses (`gui.py --analysis-worker --config ...`),
captures unbuffered stdout/stderr telemetry, parses progress lines, mirrors logs to disk,
and pushes real-time events to the PyWebView React frontend.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Optional

from reservation_queue import Reservation, ReservationQueue, set_output, write_json

logger = logging.getLogger(__name__)


class AnalysisWorkerManager:
    """Manages sequential execution of analysis worker subprocesses,
    captures stdout telemetry, and pushes progress and logs to the PyWebView frontend.
    """

    def __init__(
        self,
        base_dir: Path | str,
        reservations: ReservationQueue,
        output_names_fn: Callable[[Path], dict[str, str]],
        window_provider: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.reservations = reservations
        self._output_names_fn = output_names_fn
        self._window_provider = window_provider

        # Concurrency & state controls
        self._state_lock = threading.Lock()
        self._is_running = False
        self._stop_requested = threading.Event()
        self._current_job_id: Optional[str] = None
        self._current_process: Optional[subprocess.Popen[str]] = None
        self._tail_buffer: list[str] = []
        self._queue_thread: Optional[threading.Thread] = None

    def set_window_provider(self, provider: Callable[[], Any]) -> None:
        """Sets the provider callable returning the active pywebview.Window."""
        self._window_provider = provider

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._is_running

    @property
    def current_job_id(self) -> Optional[str]:
        with self._state_lock:
            return self._current_job_id

    def start_queue(self) -> dict[str, Any]:
        """Starts processing pending jobs sequentially in a background thread."""
        with self._state_lock:
            if self._is_running:
                if self._stop_requested.is_set():
                    return {"status": "stopping", "message": "前回の解析の中断処理中です。"}
                return {"status": "already_running"}

            pending = self.reservations.next_pending()
            if pending is None:
                return {"status": "empty"}

            self._is_running = True
            self._stop_requested.clear()
            self._queue_thread = threading.Thread(
                target=self._run_queue_loop,
                daemon=True,
                name="AnalysisQueueWorker",
            )
            self._queue_thread.start()
            return {"status": "started", "job_id": pending.id}

    def cancel_current_job(self) -> dict[str, Any]:
        """Gracefully interrupts the currently running worker subprocess,
        marks the job as pending at the front of the queue, and stops queue execution.
        """
        with self._state_lock:
            if not self._is_running:
                return {"status": "idle"}
            self._stop_requested.set()
            proc = self._current_process
            job_id = self._current_job_id or ""

        # Emit stopping notifications
        self._push_progress(job_id, 0.0, "STOPPING")
        self._push_log(job_id, "解析を中断しています。現在の動画を待機リストの先頭へ戻します…\n")

        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

        return {"status": "stopping", "job_id": job_id}

    def shutdown(self, timeout_sec: float = 3.0) -> None:
        """Terminates any running subprocess and cleans up background threads on app exit."""
        self.cancel_current_job()
        proc = self._current_process
        if proc is not None and proc.poll() is None:
            try:
                proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            except OSError:
                pass

        # Ensure active job is safely reverted to pending
        with self._state_lock:
            if self._current_job_id:
                job = self.reservations.find(self._current_job_id)
                if job and job.state == "running":
                    job.state, job.error = "pending", ""
                    self.reservations.prioritize_pending(job.id)
                    try:
                        self.reservations.save()
                    except Exception:
                        pass

    # ---- Internal Queue Loop & Worker Execution ------------------------------

    def _run_queue_loop(self) -> None:
        try:
            while True:
                with self._state_lock:
                    if not self._is_running or self._stop_requested.is_set():
                        break
                    job = self.reservations.next_pending()
                    if job is None:
                        break

                self._execute_single_job(job)
        finally:
            with self._state_lock:
                self._is_running = False
                was_stopped = self._stop_requested.is_set()
                self._stop_requested.clear()
                self._current_job_id = None
                self._current_process = None

            self._push_queue_status(False, None)
            self._push_queue_update()
            if was_stopped:
                self._push_log("", "解析を中断しました。「解析開始」で先頭の動画から再開できます。\n")
            else:
                self._push_log("", "すべての待機予約の解析が終了しました。\n")

    def _execute_single_job(self, job: Reservation) -> None:
        with self._state_lock:
            self._current_job_id = job.id
            self._tail_buffer = []

        # Validate input video existence
        if not job.video.is_file():
            job.state, job.error = "failed", f"入力動画が見つかりません: {job.video}"
            self.reservations.save()
            self._push_log(job.id, f"エラー ({job.video.name}): 入力動画が見つかりません\n")
            self._push_finished(job.id, -1)
            self._push_queue_update()
            return

        # Collision avoidance for output destination
        if job.output.exists():
            safe_dest = self.reservations.ensure_available_destination(job.output, exclude_id=job.id)
            set_output(job.settings, safe_dest, self._output_names_fn)

        # Write config JSON
        config_dir = self.base_dir / ".analysis_jobs" / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / f"{job.id}.json"
        write_json(config_path, job.settings)

        # Ensure logs directory
        log_dir = self.base_dir / ".analysis_jobs" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{job.id}.log"

        # Update state to running
        job.state, job.error = "running", ""
        self.reservations.save()

        # Telemetry: announce job start
        self._push_started(job.id, job.video.name, str(job.output))
        self._push_queue_status(True, job.id)
        self._push_queue_update()
        self._push_log(job.id, f"\n--- 解析開始: {job.video.name} ---\n入力: {job.video}\n出力: {job.output}\n")

        # Check cancellation before launching process
        if self._stop_requested.is_set():
            job.state, job.error = "pending", ""
            self.reservations.prioritize_pending(job.id)
            self.reservations.save()
            self._push_finished(job.id, -1)
            self._push_queue_update()
            return

        # Build worker command
        cmd = [
            sys.executable,
            "-u",
            "-X", "utf8",
            str(self.base_dir / "gui.py"),
            "--analysis-worker",
            "--config",
            str(config_path),
        ]

        proc: Optional[subprocess.Popen[str]] = None
        code = -1
        try:
            with open(log_path, "w", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.base_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                with self._state_lock:
                    self._current_process = proc

                if self._stop_requested.is_set() and proc.poll() is None:
                    proc.terminate()

                assert proc.stdout is not None
                for line in proc.stdout:
                    log_file.write(line)
                    log_file.flush()

                    with self._state_lock:
                        self._tail_buffer.append(line)
                        self._tail_buffer = self._tail_buffer[-16:]

                    # Parse progress vs log
                    if line.startswith("PROGRESS:"):
                        parts = line.strip().split(":", 2)
                        if len(parts) == 3:
                            try:
                                pct = float(parts[1])
                                phase = parts[2].strip()
                                self._push_progress(job.id, pct, phase)
                                continue
                            except ValueError:
                                pass
                    self._push_log(job.id, line)

                code = proc.wait()
                if proc.stdout is not None:
                    proc.stdout.close()
        except Exception as exc:
            logger.exception("Worker execution exception for job %s: %s", job.id, exc)
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                except OSError:
                    pass
            self._push_log(job.id, f"起動/実行エラー: {exc}\n")
            code = -1
        finally:
            with self._state_lock:
                self._current_process = None

        # Finalize job outcome
        self._finalize_job_state(job, code)

    def _finalize_job_state(self, job: Reservation, exit_code: int) -> None:
        with self._state_lock:
            tail_lines = list(self._tail_buffer)
            was_stopped = self._stop_requested.is_set()

        if exit_code == 0:
            job.state, job.error = "done", ""
            self._push_progress(job.id, 100.0, "完了")
            self._push_log(job.id, f"--- 解析完了: {job.video.name} ---\n")
        elif was_stopped:
            job.state, job.error = "pending", ""
            self.reservations.prioritize_pending(job.id)
            self._push_log(job.id, f"--- 中断: {job.video.name} を予約リストの先頭へ戻しました ---\n")
        else:
            job.state = "failed"
            tail_text = "".join(tail_lines)[-2000:].strip()
            job.error = f"終了コード {exit_code}\n{tail_text}".strip()
            self._push_log(job.id, f"--- 解析失敗 ({job.video.name}, 終了コード: {exit_code}) ---\n")

        self.reservations.save()
        self._push_finished(job.id, exit_code)
        self._push_queue_update()

    # ---- PyWebView Push Helpers ----------------------------------------------

    def _get_window(self) -> Any:
        if callable(self._window_provider):
            return self._window_provider()
        return self._window_provider

    def _evaluate_js(self, js_code: str) -> None:
        window = self._get_window()
        if window is None:
            return
        try:
            window.evaluate_js(js_code)
        except Exception as exc:
            logger.debug("window.evaluate_js suppressed: %s", exc)

    def _push_progress(self, job_id: str, progress: float, phase: str) -> None:
        escaped_id = json.dumps(job_id)
        escaped_phase = json.dumps(phase)
        code = (
            f"if (typeof window.onJobProgress === 'function') {{ "
            f"  window.onJobProgress({escaped_id}, {progress}, {escaped_phase}); "
            f"}} "
            f"if (typeof window.__onBackendEvent === 'function') {{ "
            f"  window.__onBackendEvent('progress', {{jobId: {escaped_id}, progressPct: {progress}, phase: {escaped_phase}}}); "
            f"}} "
            f"window.dispatchEvent(new CustomEvent('pywebview:job-progress', {{ "
            f"  detail: {{ jobId: {escaped_id}, progress: {progress}, phase: {escaped_phase} }} "
            f"}}));"
        )
        self._evaluate_js(code)

    def _push_log(self, job_id: str, line: str) -> None:
        escaped_id = json.dumps(job_id)
        escaped_line = json.dumps(line)
        code = (
            f"if (typeof window.onJobLog === 'function') {{ "
            f"  window.onJobLog({escaped_id}, {escaped_line}); "
            f"}} "
            f"if (typeof window.__onBackendEvent === 'function') {{ "
            f"  window.__onBackendEvent('log', {{jobId: {escaped_id}, logLine: {escaped_line}}}); "
            f"}} "
            f"window.dispatchEvent(new CustomEvent('pywebview:job-log', {{ "
            f"  detail: {{ jobId: {escaped_id}, logLine: {escaped_line} }} "
            f"}}));"
        )
        self._evaluate_js(code)

    def _push_finished(self, job_id: str, code: int) -> None:
        escaped_id = json.dumps(job_id)
        js_code = (
            f"if (typeof window.onJobFinished === 'function') {{ "
            f"  window.onJobFinished({escaped_id}, {int(code)}); "
            f"}} "
            f"if (typeof window.__onBackendEvent === 'function') {{ "
            f"  window.__onBackendEvent('finished', {{jobId: {escaped_id}, returnCode: {int(code)}}}); "
            f"}} "
            f"window.dispatchEvent(new CustomEvent('pywebview:job-finished', {{ "
            f"  detail: {{ jobId: {escaped_id}, returnCode: {int(code)} }} "
            f"}}));"
        )
        self._evaluate_js(js_code)

    def _push_started(self, job_id: str, video_name: str, output_path: str) -> None:
        escaped_id = json.dumps(job_id)
        escaped_name = json.dumps(video_name)
        escaped_out = json.dumps(output_path)
        js_code = (
            f"if (typeof window.onJobStarted === 'function') {{ "
            f"  window.onJobStarted({escaped_id}, {escaped_name}, {escaped_out}); "
            f"}} "
            f"if (typeof window.__onBackendEvent === 'function') {{ "
            f"  window.__onBackendEvent('started', {{jobId: {escaped_id}, videoName: {escaped_name}, outputPath: {escaped_out}}}); "
            f"}} "
            f"window.dispatchEvent(new CustomEvent('pywebview:job-started', {{ "
            f"  detail: {{ jobId: {escaped_id}, videoName: {escaped_name}, outputPath: {escaped_out} }} "
            f"}}));"
        )
        self._evaluate_js(js_code)

    def _push_queue_status(self, is_active: bool, active_job_id: Optional[str]) -> None:
        js_active = "true" if is_active else "false"
        escaped_id = json.dumps(active_job_id)
        js_code = (
            f"if (typeof window.onQueueStatusChanged === 'function') {{ "
            f"  window.onQueueStatusChanged({js_active}, {escaped_id}); "
            f"}} "
            f"if (typeof window.__onBackendEvent === 'function') {{ "
            f"  window.__onBackendEvent('queue_status', {{isActive: {js_active}, activeJobId: {escaped_id}}}); "
            f"}} "
            f"window.dispatchEvent(new CustomEvent('pywebview:queue-status', {{ "
            f"  detail: {{ isActive: {js_active}, activeJobId: {escaped_id} }} "
            f"}}));"
        )
        self._evaluate_js(js_code)

    def _push_queue_update(self) -> None:
        """Pushes serialized jobs snapshot to frontend."""
        window = self._get_window()
        if window is None:
            return
        jobs_payload = []
        for j in self.reservations.jobs:
            settings = dict(j.settings)
            for pk in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
                if pk in settings:
                    settings[pk] = str(settings[pk])
            jobs_payload.append({
                "id": j.id,
                "state": j.state,
                "error": j.error or "",
                "created_at": j.created_at,
                "video_path": str(j.video),
                "video_name": j.video.name,
                "output_path": str(j.output),
                "output_folder": j.output.name,
                "thumbnail": "",
                "thumbnail_info": "",
                "settings": settings,
                "summary": {
                    "model_mode": settings.get("MODEL_MODE", "performance"),
                    "yolo_model": settings.get("YOLO_MODEL", "yolo11m.pt"),
                    "device": settings.get("DEVICE", "auto"),
                    "track_id": settings.get("YOLO_TRACK_ID"),
                    "csv_max_persons": settings.get("CSV_MAX_PERSONS", 3),
                },
            })

        payload = {
            "jobs": jobs_payload,
            "active_job_id": self._current_job_id,
            "queue_active": self._is_running,
        }
        escaped_payload = json.dumps(payload, ensure_ascii=False)
        escaped_jobs = json.dumps(jobs_payload, ensure_ascii=False)
        js_code = (
            f"if (typeof window.onQueueUpdated === 'function') {{ "
            f"  window.onQueueUpdated({escaped_jobs}); "
            f"}} "
            f"if (typeof window.__onBackendEvent === 'function') {{ "
            f"  window.__onBackendEvent('queue_update', {escaped_payload}); "
            f"}} "
            f"window.dispatchEvent(new CustomEvent('pywebview:queue-update', {{ "
            f"  detail: {escaped_payload} "
            f"}}));"
        )
        self._evaluate_js(js_code)
