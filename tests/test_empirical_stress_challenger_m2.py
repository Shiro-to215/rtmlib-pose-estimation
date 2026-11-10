"""Empirical Stress Test Suite for Milestone 2 Iteration 2 Gate Verification.

Adversarial stress-testing covering:
1. Subprocess Cancellation: rapid cycles, cancellation during active YOLO/RTMLIB phases,
   Win32 process handle teardown, queue lock safety, pending prioritization.
2. stdout PROGRESS Parsing: 0-50% YOLO and 50-100% RTMLIB full sequences, malformed/NaN/Infinity/
   negative/overflow progress lines, extra colons, unicode, and large log lines.
3. OpenCV Thumbnail Extraction: diverse aspect ratios (vertical 720x1280, tiny 64x64, 1080p),
   corrupt video headers, concurrent multi-job enqueues, and pruning during extraction.
"""

import base64
import json
import os
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np

import gui
from pose_ui_webview.app import ThumbnailDaemon
from pose_ui_webview.worker_manager import AnalysisWorkerManager
from reservation_queue import ReservationQueue


def create_synthetic_video(path: Path, width: int = 640, height: int = 360, num_frames: int = 15, fps: int = 30) -> Path:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    for i in range(num_frames):
        frame = np.full((height, width, 3), ((i * 15) % 256, (i * 30) % 256, 180), dtype=np.uint8)
        cv2.putText(frame, f"Frame {i}", (20, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        out.write(frame)
    out.release()
    return path


class MockPyWebViewWindow:
    def __init__(self):
        self.progress_events: list[tuple[str, float, str]] = []
        self.log_events: list[tuple[str, str]] = []
        self.thumbnail_events: list[tuple[str, str, str]] = []
        self.js_calls: list[str] = []

    def evaluate_js(self, js_code: str) -> None:
        self.js_calls.append(js_code)
        # Capture onJobProgress calls
        if "onJobProgress" in js_code:
            try:
                # Extract args from onJobProgress("id", pct, "phase")
                prefix = "onJobProgress("
                start = js_code.index(prefix) + len(prefix)
                end = js_code.index(");", start)
                args_str = js_code[start:end]
                # parse JSON array format
                raw_args = json.loads(f"[{args_str}]")
                self.progress_events.append((raw_args[0], float(raw_args[1]), raw_args[2]))
            except Exception:
                pass

        # Capture onJobLog calls
        if "onJobLog" in js_code:
            try:
                prefix = "onJobLog("
                start = js_code.index(prefix) + len(prefix)
                end = js_code.index(");", start)
                args_str = js_code[start:end]
                raw_args = json.loads(f"[{args_str}]")
                self.log_events.append((raw_args[0], raw_args[1]))
            except Exception:
                pass

        # Capture onJobThumbnail calls
        if "onJobThumbnail" in js_code:
            try:
                prefix = "onJobThumbnail("
                start = js_code.index(prefix) + len(prefix)
                end = js_code.index(");", start)
                args_str = js_code[start:end]
                raw_args = json.loads(f"[{args_str}]")
                self.thumbnail_events.append((raw_args[0], raw_args[1], raw_args[2]))
            except Exception:
                pass


class TestEmpiricalChallengerM2Stress(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.queue_file = self.temp_path / "queue.json"
        self.output_root = self.temp_path / "output"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.queue = ReservationQueue(self.queue_file, self.output_root)
        self.mock_window = MockPyWebViewWindow()

    def tearDown(self):
        self.temp_dir.cleanup()

    # =========================================================================
    # Task 3 Area 1: Subprocess Cancellation & Rapid Lifecycle Stress
    # =========================================================================

    def test_rapid_cancellation_cycles(self):
        """Rapid sequential start -> cancel -> start -> cancel cycles must remain deadlock-free and clean."""
        # Create a mock worker script that sleeps in a loop
        mock_script = self.temp_path / "gui.py"
        mock_script.write_text(
            "import sys, time\n"
            "print('PROGRESS:0:YOLO', flush=True)\n"
            "for i in range(100):\n"
            "    time.sleep(0.1)\n"
            "sys.exit(0)\n",
            encoding="utf-8"
        )

        video = create_synthetic_video(self.temp_path / "rapid.mp4")
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

        for cycle in range(3):
            # Start queue
            start_res = manager.start_queue()
            self.assertIn(start_res["status"], ("started", "already_running"))

            # Wait for process to spawn
            t0 = time.time()
            proc = None
            while time.time() - t0 < 3.0:
                with manager._state_lock:
                    proc = manager._current_process
                if proc is not None and proc.poll() is None:
                    break
                time.sleep(0.02)

            self.assertIsNotNone(proc, f"Cycle {cycle}: Subprocess must spawn")

            # Cancel immediately
            cancel_res = manager.cancel_current_job()
            self.assertEqual(cancel_res["status"], "stopping")

            # Wait for process to terminate
            t_term = time.time()
            while time.time() - t_term < 3.0:
                if proc.poll() is not None:
                    break
                time.sleep(0.02)
            self.assertIsNotNone(proc.poll(), f"Cycle {cycle}: Process must terminate after cancel")

            # Wait for worker manager thread to settle
            t_settle = time.time()
            while time.time() - t_settle < 3.0:
                if not manager.is_running:
                    break
                time.sleep(0.02)
            self.assertFalse(manager.is_running, f"Cycle {cycle}: Worker manager should settle to idle")

            # Verify queue state is restored to pending
            reloaded = ReservationQueue(self.queue_file, self.output_root)
            job = reloaded.find(job_id)
            self.assertIsNotNone(job)
            self.assertEqual(job.state, "pending")
            self.assertEqual(job.error, "")

    def test_shutdown_with_join_guarantee(self):
        """Verifies AnalysisWorkerManager.shutdown() joins queue thread and frees resources cleanly."""
        mock_script = self.temp_path / "gui.py"
        mock_script.write_text(
            "import sys, time\n"
            "print('PROGRESS:25:YOLO', flush=True)\n"
            "time.sleep(10)\n"
            "sys.exit(0)\n",
            encoding="utf-8"
        )

        video = create_synthetic_video(self.temp_path / "shut_guarantee.mp4")
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

        manager.start_queue()
        q_thread = manager._queue_thread
        self.assertIsNotNone(q_thread)

        # Wait until process runs
        t0 = time.time()
        while time.time() - t0 < 3.0:
            if manager._current_process is not None:
                break
            time.sleep(0.02)

        # Execute shutdown
        t_shut = time.perf_counter()
        manager.shutdown(timeout_sec=3.0)
        t_elapsed = time.perf_counter() - t_shut

        # Queue thread MUST NOT be alive
        self.assertFalse(q_thread.is_alive(), "Queue thread must be joined and terminated")
        self.assertFalse(manager.is_running, "Manager must be marked not running")
        self.assertLess(t_elapsed, 4.0, "Shutdown should complete promptly within timeout")

        # Job state safely reverted
        reloaded = ReservationQueue(self.queue_file, self.output_root)
        job = reloaded.find(job_id)
        self.assertEqual(job.state, "pending")

    # =========================================================================
    # Task 3 Area 2: stdout PROGRESS Parsing (0-50% YOLO, 50-100% RTMLIB)
    # =========================================================================

    def test_progress_full_pipeline_and_adversarial_lines(self):
        """Empirically tests complete 0-50% YOLO and 50-100% RTMLIB sequence alongside adversarial malformed lines."""
        mock_script = self.temp_path / "gui.py"
        script_code = (
            "import sys, time\n"
            "# 1. YOLO phase: 0 -> 25 -> 50\n"
            "print('PROGRESS:0:YOLO', flush=True)\n"
            "print('Regular log message 1', flush=True)\n"
            "print('PROGRESS:25:YOLO', flush=True)\n"
            "print('PROGRESS:50:YOLO', flush=True)\n"
            "\n"
            "# 2. RTMLIB phase: 50 -> 75.5 -> 100\n"
            "print('PROGRESS:50:RTMLIB', flush=True)\n"
            "print('PROGRESS:75.5:RTMLIB', flush=True)\n"
            "print('PROGRESS:100:RTMLIB', flush=True)\n"
            "\n"
            "# 3. Adversarial and malformed lines (must NOT crash worker)\n"
            "print('PROGRESS:', flush=True)\n"
            "print('PROGRESS:notanumber:YOLO', flush=True)\n"
            "print('PROGRESS:NaN:YOLO', flush=True)\n"
            "print('PROGRESS:Infinity:YOLO', flush=True)\n"
            "print('PROGRESS:-15.0:YOLO', flush=True)\n"
            "print('PROGRESS:150.0:RTMLIB', flush=True)\n"
            "print('PROGRESS:99:EXTRA:PARTS:HERE', flush=True)\n"
            "print('PROGRESS:70:日本語フェーズ名テスト', flush=True)\n"
            "print('LOG LINE WITH NO PREFIX', flush=True)\n"
            "print('X' * 5000, flush=True)\n"
            "sys.exit(0)\n"
        )
        mock_script.write_text(script_code, encoding="utf-8")

        video = create_synthetic_video(self.temp_path / "prog_test.mp4")
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

        manager.start_queue()
        assert manager._queue_thread is not None
        manager._queue_thread.join(timeout=10.0)
        self.assertFalse(manager._queue_thread.is_alive())

        # Verify job finished successfully
        reloaded = ReservationQueue(self.queue_file, self.output_root)
        job = reloaded.find(job_id)
        self.assertEqual(job.state, "done")
        self.assertEqual(job.error, "")

        # Verify extracted progress events
        p_events = [(pct, phase) for jid, pct, phase in self.mock_window.progress_events if jid == job_id]

        # YOLO milestones
        self.assertIn((0.0, "YOLO"), p_events)
        self.assertIn((25.0, "YOLO"), p_events)
        self.assertIn((50.0, "YOLO"), p_events)

        # RTMLIB milestones
        self.assertIn((50.0, "RTMLIB"), p_events)
        self.assertIn((75.5, "RTMLIB"), p_events)
        self.assertIn((100.0, "RTMLIB"), p_events)

        # Unicode phase name test
        self.assertIn((70.0, "日本語フェーズ名テスト"), p_events)

        # Completion event from worker manager
        self.assertIn((100.0, "完了"), p_events)

        # Verify log events received regular logs and malformed lines were not dropped
        logs = [msg for jid, msg in self.mock_window.log_events if jid == job_id]
        log_text = "".join(logs)
        self.assertIn("Regular log message 1", log_text)
        self.assertIn("LOG LINE WITH NO PREFIX", log_text)
        self.assertIn("PROGRESS:notanumber:YOLO", log_text)

    # =========================================================================
    # Task 3 Area 3: OpenCV Thumbnail Extraction Stress
    # =========================================================================

    def test_thumbnail_multi_format_and_adversarial_extraction(self):
        """Stress-tests ThumbnailDaemon across extreme resolutions, corrupt videos, and concurrency."""
        daemon = ThumbnailDaemon(lambda: self.mock_window)

        try:
            # 1. 1080p standard 16:9
            v_1080p = create_synthetic_video(self.temp_path / "1080p.mp4", width=1920, height=1080, num_frames=5)
            # 2. Vertical video (e.g. mobile 9:16) 720x1280
            v_vert = create_synthetic_video(self.temp_path / "vert.mp4", width=720, height=1280, num_frames=5)
            # 3. Tiny square video 64x64
            v_tiny = create_synthetic_video(self.temp_path / "tiny.mp4", width=64, height=64, num_frames=5)
            # 4. Corrupt video (random bytes)
            v_corrupt = self.temp_path / "corrupt.mp4"
            v_corrupt.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00trashdataandcorruptbits")
            # 5. Zero-byte video
            v_empty = self.temp_path / "empty.mp4"
            v_empty.write_bytes(b"")

            daemon.enqueue("job_1080p", str(v_1080p))
            daemon.enqueue("job_vert", str(v_vert))
            daemon.enqueue("job_tiny", str(v_tiny))
            daemon.enqueue("job_corrupt", str(v_corrupt))
            daemon.enqueue("job_empty", str(v_empty))

            # Wait for all 5 to be processed
            t0 = time.time()
            while time.time() - t0 < 8.0:
                info_count = sum(1 for j in ("job_1080p", "job_vert", "job_tiny", "job_corrupt", "job_empty") if daemon.get_info(j))
                if info_count == 5:
                    break
                time.sleep(0.05)

            # Verify 1080p thumbnail
            uri_1080p = daemon.get_thumbnail("job_1080p")
            self.assertTrue(uri_1080p.startswith("data:image/jpeg;base64,"))
            self.assertEqual(daemon.get_info("job_1080p"), "1920×1080 px")
            # Verify decoded size: max 640x360 scaled down
            img_bytes = base64.b64decode(uri_1080p.split(",", 1)[1])
            img_1080p = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            self.assertIsNotNone(img_1080p)
            self.assertEqual(img_1080p.shape[1], 640)
            self.assertEqual(img_1080p.shape[0], 360)

            # Verify vertical 720x1280 thumbnail
            uri_vert = daemon.get_thumbnail("job_vert")
            self.assertTrue(uri_vert.startswith("data:image/jpeg;base64,"))
            self.assertEqual(daemon.get_info("job_vert"), "720×1280 px")
            img_vert = cv2.imdecode(np.frombuffer(base64.b64decode(uri_vert.split(",", 1)[1]), dtype=np.uint8), cv2.IMREAD_COLOR)
            self.assertIsNotNone(img_vert)
            # scale min(640/720, 360/1280, 1.0) = 360/1280 = 0.28125 -> w=202, h=360
            self.assertEqual(img_vert.shape[0], 360)
            self.assertAlmostEqual(img_vert.shape[1], 202, delta=2)

            # Verify tiny 64x64 (scale <= 1.0, so remains 64x64)
            uri_tiny = daemon.get_thumbnail("job_tiny")
            self.assertTrue(uri_tiny.startswith("data:image/jpeg;base64,"))
            self.assertEqual(daemon.get_info("job_tiny"), "64×64 px")
            img_tiny = cv2.imdecode(np.frombuffer(base64.b64decode(uri_tiny.split(",", 1)[1]), dtype=np.uint8), cv2.IMREAD_COLOR)
            self.assertIsNotNone(img_tiny)
            self.assertEqual(img_tiny.shape[0], 64)
            self.assertEqual(img_tiny.shape[1], 64)

            # Verify corrupt video handled gracefully
            self.assertEqual(daemon.get_thumbnail("job_corrupt"), "")
            self.assertEqual(daemon.get_info("job_corrupt"), "プレビュー取得不可")

            # Verify empty video handled gracefully
            self.assertEqual(daemon.get_thumbnail("job_empty"), "")
            self.assertEqual(daemon.get_info("job_empty"), "プレビュー取得不可")

            # Verify prune functionality
            daemon.prune({"job_1080p"})
            self.assertNotEqual(daemon.get_thumbnail("job_1080p"), "")
            self.assertEqual(daemon.get_thumbnail("job_vert"), "")
            self.assertEqual(daemon.get_thumbnail("job_tiny"), "")

        finally:
            daemon.stop()


if __name__ == "__main__":
    unittest.main()
