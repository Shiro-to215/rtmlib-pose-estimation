"""Empirical Challenger Verification Harness for Milestone 2:
AnalysisWorkerManager, Subprocess Lifecycle, Cancellation, and ThumbnailDaemon.

Executes real subprocesses, validates stdout parsing, process termination,
no-orphan guarantees, queue state rollback, and OpenCV thumbnail extraction.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from typing import Any, List, Tuple

import cv2
import numpy as np

# Workspace imports
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import gui
from reservation_queue import Reservation, ReservationQueue, set_output, write_json
from pose_ui_webview.worker_manager import AnalysisWorkerManager
from pose_ui_webview.app import ThumbnailDaemon
from pose_ui_webview.api_bridge import BackendApi, serialize_reservation


class MockPyWebViewWindow:
    """Mock pywebview Window capturing evaluate_js and event dispatches."""

    def __init__(self):
        self.evaluated_scripts: list[str] = []
        self.progress_events: list[tuple[str, float, str]] = []
        self.log_events: list[tuple[str, str]] = []
        self.finished_events: list[tuple[str, int]] = []
        self.thumbnail_events: list[tuple[str, str, str]] = []
        self.queue_status_events: list[tuple[bool, str | None]] = []
        self._lock = threading.Lock()

    def evaluate_js(self, script: str) -> None:
        with self._lock:
            self.evaluated_scripts.append(script)
            # Parse progress
            if "onJobProgress" in script:
                # e.g., window.onJobProgress("job_id", 50.0, "YOLO");
                try:
                    call = script.split("window.onJobProgress(")[1].split(");")[0]
                    parts = [p.strip() for p in call.split(",")]
                    jid = json.loads(parts[0])
                    pct = float(parts[1])
                    phase = json.loads(parts[2])
                    self.progress_events.append((jid, pct, phase))
                except Exception:
                    pass
            # Parse log
            if "onJobLog" in script:
                try:
                    call = script.split("window.onJobLog(")[1].split(");")[0]
                    parts = call.split(",", 1)
                    jid = json.loads(parts[0].strip())
                    msg = json.loads(parts[1].strip())
                    self.log_events.append((jid, msg))
                except Exception:
                    pass
            # Parse finished
            if "onJobFinished" in script:
                try:
                    call = script.split("window.onJobFinished(")[1].split(");")[0]
                    parts = [p.strip() for p in call.split(",")]
                    jid = json.loads(parts[0])
                    code = int(parts[1])
                    self.finished_events.append((jid, code))
                except Exception:
                    pass
            # Parse thumbnail
            if "__onBackendEvent('thumbnail'" in script:
                try:
                    payload_str = script.split("__onBackendEvent('thumbnail', ")[1].split(");")[0]
                    data = json.loads(payload_str)
                    self.thumbnail_events.append((data["job_id"], data["data_url"], data["info"]))
                except Exception:
                    pass
            elif "onJobThumbnail" in script:
                try:
                    # Fallback
                    prefix = "window.onJobThumbnail("
                    body = script[script.index(prefix) + len(prefix):]
                    body = body[:body.index(");")]
                    # Wrap in array to parse as valid JSON array
                    arr = json.loads(f"[{body}]")
                    self.thumbnail_events.append((arr[0], arr[1], arr[2]))
                except Exception:
                    pass
            # Parse queue status
            if "onQueueStatusChanged" in script:
                try:
                    call = script.split("window.onQueueStatusChanged(")[1].split(");")[0]
                    parts = [p.strip() for p in call.split(",")]
                    active = parts[0].lower() == "true"
                    jid = json.loads(parts[1]) if parts[1] != "null" else None
                    self.queue_status_events.append((active, jid))
                except Exception:
                    pass


def create_synthetic_mp4(
    file_path: Path,
    width: int = 640,
    height: int = 360,
    fps: float = 30.0,
    num_frames: int = 15,
) -> Path:
    """Generates a valid MP4 file with colored frames using OpenCV VideoWriter."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(file_path), fourcc, fps, (width, height))
    for i in range(num_frames):
        # Draw gradient frame with text
        frame = np.full((height, width, 3), (i * 15 % 255, 128, 200), dtype=np.uint8)
        cv2.putText(
            frame,
            f"Frame {i}",
            (50, height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
        )
        writer.write(frame)
    writer.release()
    return file_path


class TestEmpiricalWorkerSubprocess(unittest.TestCase):
    """Empirical tests for AnalysisWorkerManager subprocess lifecycle and stdout parsing."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.queue_file = self.temp_path / "analysis_queue.json"
        self.output_root = self.temp_path / "output"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.queue = ReservationQueue(self.queue_file, self.output_root)
        self.mock_window = MockPyWebViewWindow()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_mock_gui_script(self, behavior: str = "normal") -> Path:
        """Creates a mock gui.py script inside self.temp_path for worker testing."""
        gui_script = self.temp_path / "gui.py"
        if behavior == "normal":
            code = """import sys, time, json
print("Worker started", flush=True)
time.sleep(0.05)
print("PROGRESS:10:YOLO", flush=True)
time.sleep(0.05)
print("PROGRESS:25:YOLO", flush=True)
time.sleep(0.05)
print("PROGRESS:50:YOLO", flush=True)
time.sleep(0.05)
print("PROGRESS:50:RTMLIB", flush=True)
time.sleep(0.05)
print("PROGRESS:75:RTMLIB", flush=True)
time.sleep(0.05)
print("PROGRESS:100:RTMLIB", flush=True)
print("Worker finished successfully", flush=True)
sys.exit(0)
"""
        elif behavior == "slow":
            # Sleeps in a loop printing progress, allows testing cancel
            code = """import sys, time
print("Slow worker started", flush=True)
for i in range(1, 100):
    print(f"PROGRESS:{i}:YOLO", flush=True)
    time.sleep(0.1)
print("Slow worker finished", flush=True)
sys.exit(0)
"""
        elif behavior == "error":
            code = """import sys, time
print("Worker starting before crash...", flush=True)
time.sleep(0.05)
print("PROGRESS:20:YOLO", flush=True)
print("CRITICAL: CUDA out of memory in line 42", file=sys.stderr, flush=True)
print("Fatal processing exception", flush=True)
sys.exit(42)
"""
        gui_script.write_text(code, encoding="utf-8")
        return gui_script

    def test_worker_launch_and_stdout_progress_parsing(self):
        """Worker manager successfully spawns worker, parses PROGRESS: lines, and reaches done state."""
        self._create_mock_gui_script("normal")
        video = create_synthetic_mp4(self.temp_path / "input.mp4")
        template = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            template[k] = str(template[k])

        jobs = self.queue.add([video], template, self.output_root, gui.output_names)
        job_id = jobs[0].id

        manager = AnalysisWorkerManager(
            base_dir=self.temp_path,
            reservations=self.queue,
            output_names_fn=gui.output_names,
            window_provider=lambda: self.mock_window,
        )

        res = manager.start_queue()
        self.assertEqual(res["status"], "started")
        self.assertEqual(res["job_id"], job_id)

        # Wait for queue execution thread to finish
        assert manager._queue_thread is not None
        manager._queue_thread.join(timeout=10.0)
        self.assertFalse(manager._queue_thread.is_alive(), "Worker thread should terminate")
        self.assertFalse(manager.is_running)

        # Verify job state on queue and in file
        reloaded_queue = ReservationQueue(self.queue_file, self.output_root)
        finished_job = reloaded_queue.find(job_id)
        self.assertIsNotNone(finished_job)
        self.assertEqual(finished_job.state, "done")
        self.assertEqual(finished_job.error, "")

        # Verify progress events pushed to frontend
        progress_records = [(pct, phase) for jid, pct, phase in self.mock_window.progress_events if jid == job_id]
        self.assertIn((10.0, "YOLO"), progress_records)
        self.assertIn((25.0, "YOLO"), progress_records)
        self.assertIn((50.0, "YOLO"), progress_records)
        self.assertIn((50.0, "RTMLIB"), progress_records)
        self.assertIn((75.0, "RTMLIB"), progress_records)
        self.assertIn((100.0, "完了"), progress_records)

        # Verify logs were mirrored to .analysis_jobs/logs/{job_id}.log
        log_file = self.temp_path / ".analysis_jobs" / "logs" / f"{job_id}.log"
        self.assertTrue(log_file.is_file())
        log_content = log_file.read_text(encoding="utf-8")
        self.assertIn("Worker started", log_content)
        self.assertIn("Worker finished successfully", log_content)

        # Verify config JSON was generated
        config_file = self.temp_path / ".analysis_jobs" / "configs" / f"{job_id}.json"
        self.assertTrue(config_file.is_file())
        config_data = json.loads(config_file.read_text(encoding="utf-8"))
        self.assertEqual(config_data["INPUT_VIDEO_NAME"], video.name)

    def test_worker_cancellation_and_immediate_termination(self):
        """Cancelling active worker terminates subprocess immediately and prioritizes job at queue head."""
        self._create_mock_gui_script("slow")
        v1 = create_synthetic_mp4(self.temp_path / "v1.mp4")
        v2 = create_synthetic_mp4(self.temp_path / "v2.mp4")
        template = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            template[k] = str(template[k])

        jobs = self.queue.add([v1, v2], template, self.output_root, gui.output_names)
        j1_id = jobs[0].id
        j2_id = jobs[1].id

        manager = AnalysisWorkerManager(
            base_dir=self.temp_path,
            reservations=self.queue,
            output_names_fn=gui.output_names,
            window_provider=lambda: self.mock_window,
        )

        start_res = manager.start_queue()
        self.assertEqual(start_res["status"], "started")

        # Wait until process is actively spawned and running
        t0 = time.time()
        proc = None
        while time.time() - t0 < 5.0:
            with manager._state_lock:
                proc = manager._current_process
            if proc is not None and proc.poll() is None:
                break
            time.sleep(0.05)

        self.assertIsNotNone(proc, "Subprocess must be spawned")
        self.assertIsNone(proc.poll(), "Subprocess must be running prior to cancel")
        proc_pid = proc.pid

        # Trigger cancellation
        cancel_res = manager.cancel_current_job()
        self.assertEqual(cancel_res["status"], "stopping")
        self.assertEqual(cancel_res["job_id"], j1_id)

        # Check process terminated immediately
        t_term_start = time.perf_counter()
        terminated = False
        while time.perf_counter() - t_term_start < 2.0:
            if proc.poll() is not None:
                terminated = True
                break
            time.sleep(0.02)
        self.assertTrue(terminated, f"Subprocess {proc_pid} must be terminated immediately on cancel")

        # Verify no orphan process remains
        self.assertIsNotNone(proc.poll(), f"Subprocess {proc_pid} must report finished code via poll()")
        if os.name == "nt":
            import ctypes
            SYNCHRONIZE = 0x00100000
            # Open process handle with query/synchronize
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, proc_pid)
            if handle:
                # Wait 0 ms to check if signaled (terminated)
                wait_val = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
                ctypes.windll.kernel32.CloseHandle(handle)
                # WAIT_OBJECT_0 = 0 means signaled (process terminated)
                self.assertEqual(wait_val, 0, f"Process {proc_pid} should be terminated/signaled")

        # Wait for queue thread to finish
        assert manager._queue_thread is not None
        manager._queue_thread.join(timeout=5.0)
        self.assertFalse(manager._queue_thread.is_alive())
        self.assertFalse(manager.is_running)

        # Verify job 1 is reverted to 'pending' with no error
        reloaded_queue = ReservationQueue(self.queue_file, self.output_root)
        j1_after = reloaded_queue.find(j1_id)
        j2_after = reloaded_queue.find(j2_id)
        self.assertEqual(j1_after.state, "pending")
        self.assertEqual(j1_after.error, "")
        self.assertEqual(j2_after.state, "pending")

        # Verify job 1 is prioritized at the front of pending jobs (position 0)
        self.assertEqual(reloaded_queue.jobs[0].id, j1_id)
        self.assertEqual(reloaded_queue.jobs[1].id, j2_id)

        # Verify stopping progress was pushed
        stopping_events = [p for p in self.mock_window.progress_events if p[2] == "STOPPING"]
        self.assertGreaterEqual(len(stopping_events), 1)

    def test_start_queue_while_stopping_rejected(self):
        """Calling start_queue while worker is stopping returns status: stopping."""
        self._create_mock_gui_script("slow")
        v = create_synthetic_mp4(self.temp_path / "stop_rej.mp4")
        template = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            template[k] = str(template[k])

        jobs = self.queue.add([v], template, self.output_root, gui.output_names)
        manager = AnalysisWorkerManager(
            base_dir=self.temp_path,
            reservations=self.queue,
            output_names_fn=gui.output_names,
            window_provider=lambda: self.mock_window,
        )

        manager.start_queue()
        t0 = time.time()
        while time.time() - t0 < 5.0:
            if manager._current_process is not None:
                break
            time.sleep(0.05)

        manager.cancel_current_job()
        res = manager.start_queue()
        self.assertEqual(res["status"], "stopping")

        # Cleanup
        assert manager._queue_thread is not None
        manager._queue_thread.join(timeout=5.0)

    def test_empty_queue_start(self):
        """Calling start_queue on empty queue returns status: empty."""
        manager = AnalysisWorkerManager(
            base_dir=self.temp_path,
            reservations=self.queue,
            output_names_fn=gui.output_names,
            window_provider=lambda: self.mock_window,
        )
        res = manager.start_queue()
        self.assertEqual(res["status"], "empty")

    def test_cancel_when_idle(self):
        """Calling cancel_current_job when idle returns status: idle."""
        manager = AnalysisWorkerManager(
            base_dir=self.temp_path,
            reservations=self.queue,
            output_names_fn=gui.output_names,
            window_provider=lambda: self.mock_window,
        )
        res = manager.cancel_current_job()
        self.assertEqual(res["status"], "idle")

    def test_worker_error_and_tail_buffer_diagnostics(self):
        """Worker failure captures non-zero exit code and tail buffer into job.error."""
        self._create_mock_gui_script("error")
        v = create_synthetic_mp4(self.temp_path / "crash.mp4")
        template = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            template[k] = str(template[k])

        jobs = self.queue.add([v], template, self.output_root, gui.output_names)
        job_id = jobs[0].id

        manager = AnalysisWorkerManager(
            base_dir=self.temp_path,
            reservations=self.queue,
            output_names_fn=gui.output_names,
            window_provider=lambda: self.mock_window,
        )

        manager.start_queue()
        assert manager._queue_thread is not None
        manager._queue_thread.join(timeout=5.0)

        reloaded_queue = ReservationQueue(self.queue_file, self.output_root)
        failed_job = reloaded_queue.find(job_id)
        self.assertEqual(failed_job.state, "failed")
        self.assertIn("終了コード 42", failed_job.error)
        self.assertIn("CRITICAL: CUDA out of memory", failed_job.error)

    def test_missing_input_video_fails_safely(self):
        """If input video is deleted prior to execution, job is marked as failed safely without crash."""
        self._create_mock_gui_script("normal")
        v = self.temp_path / "missing.mp4"
        v.write_bytes(b"dummy")
        template = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            template[k] = str(template[k])

        jobs = self.queue.add([v], template, self.output_root, gui.output_names)
        job_id = jobs[0].id
        v.unlink()  # Delete before running

        manager = AnalysisWorkerManager(
            base_dir=self.temp_path,
            reservations=self.queue,
            output_names_fn=gui.output_names,
            window_provider=lambda: self.mock_window,
        )

        manager.start_queue()
        assert manager._queue_thread is not None
        manager._queue_thread.join(timeout=5.0)

        reloaded = ReservationQueue(self.queue_file, self.output_root)
        job = reloaded.find(job_id)
        self.assertEqual(job.state, "failed")
        self.assertIn("入力動画が見つかりません", job.error)

    def test_shutdown_with_running_subprocess(self):
        """shutdown() terminates active process and reverts state to pending."""
        self._create_mock_gui_script("slow")
        v = create_synthetic_mp4(self.temp_path / "shut.mp4")
        template = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            template[k] = str(template[k])

        jobs = self.queue.add([v], template, self.output_root, gui.output_names)
        job_id = jobs[0].id

        manager = AnalysisWorkerManager(
            base_dir=self.temp_path,
            reservations=self.queue,
            output_names_fn=gui.output_names,
            window_provider=lambda: self.mock_window,
        )

        manager.start_queue()

        # Wait until process runs
        t0 = time.time()
        while time.time() - t0 < 5.0:
            if manager._current_process is not None:
                break
            time.sleep(0.05)

        manager.shutdown(timeout_sec=2.0)
        self.assertFalse(manager.is_running)

        reloaded = ReservationQueue(self.queue_file, self.output_root)
        job = reloaded.find(job_id)
        self.assertEqual(job.state, "pending")


class TestEmpiricalThumbnailDaemon(unittest.TestCase):
    """Empirical tests for ThumbnailDaemon OpenCV frame 0 extraction and caching."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.mock_window = MockPyWebViewWindow()
        self.daemon = ThumbnailDaemon(lambda: self.mock_window)

    def tearDown(self):
        self.daemon.stop()
        self.temp_dir.cleanup()

    def test_thumbnail_extraction_from_real_video(self):
        """Extracts frame 0 from real MP4 video, produces valid base64 JPEG URI and dimensions."""
        video_path = create_synthetic_mp4(self.temp_path / "valid_clip.mp4", width=1280, height=720)
        job_id = "test_job_101"

        self.daemon.enqueue(job_id, str(video_path))

        # Wait for daemon to process
        t0 = time.time()
        uri = ""
        while time.time() - t0 < 5.0:
            uri = self.daemon.get_thumbnail(job_id)
            if uri:
                break
            time.sleep(0.05)

        self.assertTrue(uri.startswith("data:image/jpeg;base64,"), f"Expected data URI, got: {uri[:40]}")
        info = self.daemon.get_info(job_id)
        self.assertEqual(info, "1280×720 px")

        # Decode base64 and verify image
        b64_data = uri.split("data:image/jpeg;base64,")[1]
        img_bytes = base64.b64decode(b64_data)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        decoded_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        self.assertIsNotNone(decoded_img, "Base64 payload must decode into valid JPEG image")
        # Aspect ratio should match 16:9, scaled to target max 640x360
        dh, dw = decoded_img.shape[:2]
        self.assertEqual(dw, 640)
        self.assertEqual(dh, 360)

        # Verify window event was dispatched
        self.assertGreaterEqual(len(self.mock_window.thumbnail_events), 1)
        dispatched_id, dispatched_uri, dispatched_info = self.mock_window.thumbnail_events[0]
        self.assertEqual(dispatched_id, job_id)
        self.assertEqual(dispatched_info, "1280×720 px")

    def test_thumbnail_missing_video_handling(self):
        """Missing video produces empty URI and descriptive info message."""
        job_id = "missing_job"
        self.daemon.enqueue(job_id, str(self.temp_path / "not_existing.mp4"))

        t0 = time.time()
        while time.time() - t0 < 3.0:
            info = self.daemon.get_info(job_id)
            if info:
                break
            time.sleep(0.05)

        self.assertEqual(self.daemon.get_thumbnail(job_id), "")
        self.assertEqual(self.daemon.get_info(job_id), "動画が見つかりません")

    def test_thumbnail_prune_cleans_memory(self):
        """Pruning keeps active jobs and removes deleted jobs from memory."""
        v1 = create_synthetic_mp4(self.temp_path / "c1.mp4", width=320, height=240)
        v2 = create_synthetic_mp4(self.temp_path / "c2.mp4", width=320, height=240)

        self.daemon.enqueue("job1", str(v1))
        self.daemon.enqueue("job2", str(v2))

        t0 = time.time()
        while time.time() - t0 < 5.0:
            if self.daemon.get_thumbnail("job1") and self.daemon.get_thumbnail("job2"):
                break
            time.sleep(0.05)

        self.daemon.prune(active_job_ids={"job1"})
        self.assertNotEqual(self.daemon.get_thumbnail("job1"), "")
        self.assertEqual(self.daemon.get_thumbnail("job2"), "")


class TestEmpiricalBackendApiIntegration(unittest.TestCase):
    """End-to-end integration tests between BackendApi, ReservationQueue, and AnalysisWorkerManager."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.queue_file = self.temp_path / "analysis_queue.json"
        self.output_root = self.temp_path / "output"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.queue = ReservationQueue(self.queue_file, self.output_root)
        self.mock_window = MockPyWebViewWindow()

        # Mock gui.py
        gui_script = self.temp_path / "gui.py"
        gui_script.write_text("import sys\nprint('PROGRESS:100:RTMLIB', flush=True)\nsys.exit(0)\n", encoding="utf-8")

        self.api = BackendApi(
            base_dir=self.temp_path,
            reservations=self.queue,
            output_names_fn=gui.output_names,
            resolve_rtmlib_fn=gui.resolve_rtmlib_selection,
        )
        self.api.set_window(self.mock_window)

    def tearDown(self):
        if self.api.worker_manager:
            self.api.worker_manager.shutdown()
        self.temp_dir.cleanup()

    def test_api_add_and_process_queue(self):
        """API adds reservation, starts processing, worker runs to completion."""
        video = create_synthetic_mp4(self.temp_path / "test.mp4")
        template = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            template[k] = str(template[k])

        added = self.api.add_reservations([str(video)], str(self.output_root), False, template)
        self.assertEqual(len(added), 1)
        job_id = added[0]["id"]

        start_res = self.api.start_queue_processing()
        self.assertEqual(start_res["status"], "started")

        # Wait for completion
        assert self.api.worker_manager._queue_thread is not None
        self.api.worker_manager._queue_thread.join(timeout=5.0)

        initial = self.api.get_initial_data()
        job = next(j for j in initial["queue"] if j["id"] == job_id)
        self.assertEqual(job["state"], "done")


if __name__ == "__main__":
    unittest.main(verbosity=2)
