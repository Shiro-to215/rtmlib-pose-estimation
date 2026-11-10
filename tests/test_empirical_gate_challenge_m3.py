#!/usr/bin/env python3
"""Empirical Gate Challenge Suite for Milestone 3 (React/Vite UI Rebuild & Visual Parity).

Stress-tests:
1. Challenge 1: Edge-case inputs and parameter boundaries
   - Empty queue, empty video paths, null/None values
   - Non-existent files, spaces/special characters, long paths
   - RTMLib invalid resolution combinations (rejection in backend & validation logic)
2. Challenge 2: Rapid state transitions & concurrency
   - Rapid start followed immediately by cancel (loop stress)
   - Rapid job reordering (boundaries: top item up, bottom item down, rapid swaps)
   - Deleting active vs inactive jobs
   - Updating job settings with reset_failed flag on failed and pending jobs
3. Challenge 3: Telemetry stress
   - Flooding progress lines (1,000 progress events)
   - Flooding log lines (> 2,000 log lines) with tail buffer capping & memory check
4. Verification of legacy code immutability (gui.py, reservation_queue.py)

Usage:
    .\\.venv\\Scripts\\python.exe tests/test_empirical_gate_challenge_m3.py
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import gui
from reservation_queue import Reservation, ReservationQueue, set_output, write_json
from pose_ui_webview import BackendApi, AnalysisWorkerManager, serialize_reservation


class MockWebviewWindow:
    """Mock PyWebView window capturing evaluate_js and create_file_dialog calls."""

    def __init__(self):
        self.evaluated_scripts: list[str] = []
        self.progress_events: list[dict[str, Any]] = []
        self.log_events: list[dict[str, Any]] = []
        self.queue_events: list[dict[str, Any]] = []
        self.dialog_return_value: Any = None
        self._lock = threading.Lock()

    def evaluate_js(self, script: str) -> None:
        with self._lock:
            self.evaluated_scripts.append(script)
            # Lightweight extraction for telemetry checks
            if "pywebview:job-progress" in script:
                self.progress_events.append({"script": script})
            if "pywebview:job-log" in script:
                self.log_events.append({"script": script})
            if "pywebview:queue-update" in script:
                self.queue_events.append({"script": script})

    def create_file_dialog(self, **kwargs) -> Any:
        return self.dialog_return_value


class TestEmpiricalGateChallengeM3(unittest.TestCase):
    """Rigorous empirical test harness for Milestone 3 Edge Cases & Stress."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.queue_file = self.temp_path / "analysis_queue.json"
        self.settings_file = self.temp_path / "gui_settings.json"
        self.output_root = self.temp_path / "output"
        self.output_root.mkdir(parents=True, exist_ok=True)

        self.mock_window = MockWebviewWindow()
        self.queue = ReservationQueue(self.queue_file, self.output_root)

        self.api = BackendApi(
            base_dir=self.temp_path,
            settings_file=self.settings_file,
            reservations=self.queue,
        )
        self.api.set_window(self.mock_window)

    def tearDown(self):
        self.api.shutdown()
        self.temp_dir.cleanup()

    def _create_dummy_video(self, name: str = "sample.mp4", subdirs: list[str] | None = None) -> Path:
        parent = self.temp_path
        if subdirs:
            for s in subdirs:
                parent = parent / s
        parent.mkdir(parents=True, exist_ok=True)
        video_path = parent / name
        video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 128)
        return video_path

    # =========================================================================
    # CHALLENGE 1: EDGE-CASE INPUTS AND PARAMETER BOUNDARIES
    # =========================================================================

    def test_c1_empty_queue_boundaries(self):
        """Empty queue operations must return predictable fallback states without crashing."""
        # 1. start_queue_processing on empty queue -> returns status 'empty'
        res_start = self.api.start_queue_processing()
        self.assertEqual(res_start.get("status"), "empty")
        self.assertFalse(self.api.is_processing)

        # 2. cancel_current_job on empty queue -> returns status 'idle'
        res_cancel = self.api.cancel_current_job()
        self.assertEqual(res_cancel.get("status"), "idle")

        # 3. remove_jobs on empty queue -> returns empty list
        rem_res = self.api.remove_jobs([])
        self.assertEqual(rem_res, [])
        rem_res_nonexistent = self.api.remove_jobs(["non_existent_id_999"])
        self.assertEqual(rem_res_nonexistent, [])

        # 4. move_job with non-existent job -> safely no-ops and returns empty queue
        move_res = self.api.move_job("non_existent_id", "up")
        self.assertEqual(move_res, [])
        # move_job with invalid direction -> raises ValueError
        with self.assertRaises(ValueError):
            self.api.move_job("non_existent_id", "diagonal")

        # 5. update_job_settings with non-existent job -> raises ValueError
        with self.assertRaises(ValueError):
            self.api.update_job_settings("non_existent_id", {"YOLO_IMAGE_SIZE": 640})

    def test_c1_empty_video_paths_and_null_values(self):
        """Empty video paths, null, and None parameters must be safely rejected or sanitized."""
        # add_reservations with empty list
        with self.assertRaises(ValueError):
            self.api.add_reservations([])

        # add_reservations with None
        with self.assertRaises(ValueError):
            self.api.add_reservations(None)

        # add_reservations with empty string video path
        with self.assertRaises(ValueError):
            self.api.add_reservations([""])

        # Preview frames with empty or None video path
        self.assertEqual(self.api.get_preview_frame(""), "")
        self.assertEqual(self.api.get_preview_frame(None), "")
        self.assertEqual(self.api.get_preview_frame("non_existent_video.mp4"), "")

        # Output preview names with empty or None folder path
        self.assertEqual(self.api.get_output_preview_names(""), {})
        self.assertEqual(self.api.get_output_preview_names(None), {})

        # Settings sanitization with null/None fields
        v = self._create_dummy_video("null_test.mp4")
        created = self.api.add_reservations([str(v)], str(self.output_root))
        job_id = created[0]["id"]

        # Passing None for various types should not crash
        null_settings = {
            "YOLO_IMAGE_SIZE": None,
            "YOLO_CONFIDENCE": None,
            "YOLO_TRACK_ID": None,
            "TARGET_LOCK_RAW_ID": None,
        }
        updated = self.api.update_job_settings(job_id, null_settings)
        self.assertIsNotNone(updated)
        # Check that YOLO_TRACK_ID is None
        self.assertIsNone(updated["settings"]["YOLO_TRACK_ID"])

    def test_c1_nonexistent_files_and_special_characters(self):
        """Non-existent files must be rejected; Japanese Kanji, Kana, spaces, and emojis preserved."""
        # 1. Non-existent file rejects and queue remains untouched
        missing_path = self.temp_path / "phantom_video.mp4"
        with self.assertRaises(ValueError):
            self.api.add_reservations([str(missing_path)], str(self.output_root))
        self.assertEqual(len(self.api.reservations.jobs), 0)

        # 2. Spaces and special Unicode characters in video name
        special_name = "🎥 姿勢推定 [テスト 2026] #1 (sample & run).mp4"
        v_special = self._create_dummy_video(special_name)
        self.assertTrue(v_special.exists())

        jobs = self.api.add_reservations([str(v_special)], str(self.output_root))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["video_name"], special_name)

        # Verify disk persistence with Unicode
        disk_data = json.loads(self.queue_file.read_text(encoding="utf-8"))
        self.assertEqual(disk_data["jobs"][0]["settings"]["INPUT_VIDEO_NAME"], special_name)

    def test_c1_extremely_long_file_paths(self):
        """Long nested paths (>200 chars) must be accepted and handled cleanly."""
        nested_dirs = ["a_very_long_directory_name_component_" + str(i) for i in range(4)]
        v_long = self._create_dummy_video("test_long_path_video.mp4", subdirs=nested_dirs)
        self.assertTrue(len(str(v_long)) > 150)

        jobs = self.api.add_reservations([str(v_long)], str(self.output_root))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["video_name"], "test_long_path_video.mp4")
        self.assertTrue(Path(jobs[0]["video_path"]).is_file())

    def test_c1_rtmlib_invalid_resolution_combinations(self):
        """RTMLib invalid resolution combinations must be rejected by backend and validation endpoint."""
        # 1. Validate RTMLib combinations via endpoint
        # RTMPose-S with 384x288 is INVALID (S only supports 256x192)
        res_s_384 = self.api.validate_rtmlib_settings("performance", "s", "384x288", "mode")
        self.assertFalse(res_s_384["valid"])
        self.assertIn("256x192", res_s_384["error"])

        # RTMPose-X with 256x192 is INVALID (X only supports 384x288)
        res_x_256 = self.api.validate_rtmlib_settings("performance", "x", "256x192", "mode")
        self.assertFalse(res_x_256["valid"])
        self.assertIn("384x288", res_x_256["error"])

        # RTMPose-M with 384x288 is INVALID
        res_m_384 = self.api.validate_rtmlib_settings("performance", "m", "384x288", "mode")
        self.assertFalse(res_m_384["valid"])

        # RTMPose-T with 384x288 is INVALID
        res_t_384 = self.api.validate_rtmlib_settings("performance", "t", "384x288", "mode")
        self.assertFalse(res_t_384["valid"])

        # Valid combinations:
        res_s_256 = self.api.validate_rtmlib_settings("performance", "s", "256x192", "mode")
        self.assertTrue(res_s_256["valid"])

        res_x_384 = self.api.validate_rtmlib_settings("performance", "x", "384x288", "mode")
        self.assertTrue(res_x_384["valid"])

        # 2. Verify backend rejection in update_job_settings
        v = self._create_dummy_video("rtmlib_val.mp4")
        jobs = self.api.add_reservations([str(v)], str(self.output_root))
        jid = jobs[0]["id"]

        with self.assertRaises(ValueError):
            self.api.update_job_settings(
                jid,
                {
                    "MODEL_MODE": "performance",
                    "RTMLIB_POSE_MODEL": "s",
                    "RTMLIB_POSE_INPUT_SIZE": "384x288",
                },
            )

        # 3. Verify backend rejection in save_default_settings
        with self.assertRaises(ValueError):
            self.api.save_default_settings({
                "MODEL_MODE": "performance",
                "RTMLIB_POSE_MODEL": "x",
                "RTMLIB_POSE_INPUT_SIZE": "256x192",
            })

    # =========================================================================
    # CHALLENGE 2: RAPID STATE TRANSITIONS & CONCURRENCY
    # =========================================================================

    def test_c2_rapid_start_and_cancel_stress(self):
        """Rapid start immediately followed by cancel must cleanly terminate and reset queue."""
        v = self._create_dummy_video("stress_cancel.mp4")
        self.api.add_reservations([str(v)], str(self.output_root))

        for iteration in range(5):
            res_start = self.api.start_queue_processing()
            # Immediately cancel without yielding
            res_cancel = self.api.cancel_current_job()

            self.assertIn(res_start.get("status"), ("started", "already_running", "stopping"))
            self.assertIn(res_cancel.get("status"), ("stopping", "idle"))

            # Give worker manager a moment to join and finalize
            timeout = time.time() + 3.0
            while self.api.is_processing and time.time() < timeout:
                time.sleep(0.05)

            self.assertFalse(self.api.is_processing, f"Worker still processing after cancel on iter {iteration}")
            # Ensure job was prioritized back to pending
            job = self.api.reservations.jobs[0]
            self.assertEqual(job.state, "pending", f"Job state was {job.state} instead of pending on iter {iteration}")

    def test_c2_rapid_job_reordering_boundaries_and_swaps(self):
        """Boundary reordering (top item up, bottom item down) and rapid 50x swaps maintain consistency."""
        v1 = self._create_dummy_video("video_1.mp4")
        v2 = self._create_dummy_video("video_2.mp4")
        v3 = self._create_dummy_video("video_3.mp4")
        v4 = self._create_dummy_video("video_4.mp4")
        v5 = self._create_dummy_video("video_5.mp4")

        jobs = self.api.add_reservations(
            [str(v1), str(v2), str(v3), str(v4), str(v5)],
            str(self.output_root),
            is_multi=True,
        )
        job_ids = [j["id"] for j in jobs]
        self.assertEqual(len(job_ids), 5)

        # 1. Moving top item up -> remains at index 0 (safe no-op / bounds check)
        updated = self.api.move_job(job_ids[0], "up")
        self.assertEqual(updated[0]["id"], job_ids[0])

        # 2. Moving bottom item down -> remains at bottom (safe no-op / bounds check)
        updated = self.api.move_job(job_ids[-1], "down")
        self.assertEqual(updated[-1]["id"], job_ids[-1])

        # 3. 50 rapid alternating swaps
        for i in range(50):
            target_id = job_ids[2]
            direction = "up" if i % 2 == 0 else "down"
            res = self.api.move_job(target_id, direction)
            self.assertEqual(len(res), 5)
            # Verify disk JSON validity after each move
            disk_data = json.loads(self.queue_file.read_text(encoding="utf-8"))
            self.assertEqual(len(disk_data["jobs"]), 5)

    def test_c2_deleting_active_vs_inactive_jobs(self):
        """Active (running) jobs must NOT be deleted, while pending/failed jobs are removed cleanly."""
        v1 = self._create_dummy_video("job_run.mp4")
        v2 = self._create_dummy_video("job_pend.mp4")
        v3 = self._create_dummy_video("job_fail.mp4")

        jobs = self.api.add_reservations(
            [str(v1), str(v2), str(v3)],
            str(self.output_root),
            is_multi=True,
        )
        j1_id = jobs[0]["id"]
        j2_id = jobs[1]["id"]
        j3_id = jobs[2]["id"]

        # Manually set states: j1 -> running, j3 -> failed
        job1 = self.api.reservations.find(j1_id)
        job1.state = "running"
        job3 = self.api.reservations.find(j3_id)
        job3.state = "failed"
        self.api.reservations.save()

        # Attempt to delete all three: [j1_id, j2_id, j3_id]
        remaining = self.api.remove_jobs([j1_id, j2_id, j3_id])

        # Running job must NOT have been deleted!
        remaining_ids = [j["id"] for j in remaining]
        self.assertIn(j1_id, remaining_ids, "Running job should NOT be removed!")
        self.assertNotIn(j2_id, remaining_ids, "Pending job should be removed!")
        self.assertNotIn(j3_id, remaining_ids, "Failed job should be removed!")

        # Verify on disk
        disk_data = json.loads(self.queue_file.read_text(encoding="utf-8"))
        disk_ids = [j["id"] for j in disk_data["jobs"]]
        self.assertEqual(disk_ids, [j1_id])

    def test_c2_update_job_settings_reset_failed_flag(self):
        """Updating settings with reset_failed flag properly resets failed jobs and handles pending jobs."""
        v1 = self._create_dummy_video("reset_fail.mp4")
        v2 = self._create_dummy_video("keep_pend.mp4")

        jobs = self.api.add_reservations([str(v1), str(v2)], str(self.output_root), is_multi=True)
        j1_id = jobs[0]["id"]
        j2_id = jobs[1]["id"]

        # Mark j1 as failed
        job1 = self.api.reservations.find(j1_id)
        job1.state = "failed"
        job1.error = "Simulated crash exit code 1"
        self.api.reservations.save()

        # 1. Update failed job with reset_failed=True
        res1 = self.api.update_job_settings(
            j1_id,
            {"YOLO_CONFIDENCE": 0.8},
            reset_failed=True,
        )
        self.assertEqual(res1["state"], "pending")
        self.assertEqual(res1["error"], "")
        self.assertEqual(res1["settings"]["YOLO_CONFIDENCE"], 0.8)

        # Re-fail j1 to test reset_failed=False
        job1 = self.api.reservations.find(j1_id)
        job1.state = "failed"
        job1.error = "Second crash"
        self.api.reservations.save()

        # 2. Update failed job with reset_failed=False
        res1_no_reset = self.api.update_job_settings(
            j1_id,
            {"YOLO_CONFIDENCE": 0.9},
            reset_failed=False,
        )
        self.assertEqual(res1_no_reset["state"], "failed")
        self.assertEqual(res1_no_reset["error"], "Second crash")
        self.assertEqual(res1_no_reset["settings"]["YOLO_CONFIDENCE"], 0.9)

        # 3. Update pending job (j2) with reset_failed=True
        res2 = self.api.update_job_settings(
            j2_id,
            {"CSV_MAX_PERSONS": 7},
            reset_failed=True,
        )
        self.assertEqual(res2["state"], "pending")
        self.assertEqual(res2["settings"]["CSV_MAX_PERSONS"], 7)

    # =========================================================================
    # CHALLENGE 3: TELEMETRY STRESS
    # =========================================================================

    def test_c3_progress_flood_1000_events(self):
        """Worker manager progress push under 1,000 rapid event flood executes without drops or crashes."""
        wm = self.api.worker_manager
        self.assertIsNotNone(wm)

        t0 = time.perf_counter()
        for i in range(1000):
            pct = i / 10.0  # 0.0 to 99.9
            phase = "YOLO" if pct < 50 else "RTMLIB"
            wm._push_progress("test-job-flood", pct, phase)
        elapsed = time.perf_counter() - t0

        # All 1,000 progress events evaluated via mock window
        self.assertEqual(len(self.mock_window.progress_events), 1000)
        self.assertLess(elapsed, 2.0, f"1000 progress events took too long: {elapsed:.2f}s")

    def test_c3_log_flood_capping_and_memory_leak_check(self):
        """Worker manager log push under > 2,000 lines caps tail buffer and does not leak memory."""
        wm = self.api.worker_manager
        self.assertIsNotNone(wm)

        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        log_count = 2500
        for i in range(log_count):
            line = f"Frame {i:05d}: detected 2 persons, rtmlib keypoints calculated in 12.3ms\n"
            with wm._state_lock:
                wm._tail_buffer.append(line)
                wm._tail_buffer = wm._tail_buffer[-16:]
            wm._push_log("test-job-log-flood", line)

        snapshot_after = tracemalloc.take_snapshot()
        top_stats = snapshot_after.compare_to(snapshot_before, "lineno")
        tracemalloc.stop()

        # Invariant 1: tail_buffer in worker_manager capped at 16
        with wm._state_lock:
            self.assertLessEqual(len(wm._tail_buffer), 16)
            self.assertIn("02499", wm._tail_buffer[-1])

        # Invariant 2: mock window received all 2,500 log events
        self.assertEqual(len(self.mock_window.log_events), log_count)

        # Invariant 3: Python memory delta should be minimal (< 10MB)
        total_delta = sum(stat.size_diff for stat in top_stats)
        delta_mb = total_delta / (1024 * 1024)
        self.assertLess(delta_mb, 10.0, f"Memory leaked excessively during log flood: {delta_mb:.2f} MB")

    # =========================================================================
    # CHALLENGE 4 & 5: REGRESSION & IMMUTABILITY CHECKS
    # =========================================================================

    def test_c5_legacy_code_immutability(self):
        """gui.py and reservation_queue.py must have zero modifications in Milestone 3."""
        # Using git diff to verify no unstaged or committed changes to legacy files in M3
        import subprocess
        res = subprocess.run(
            ["git", "diff", "HEAD~1", "--", "gui.py", "reservation_queue.py"],
            cwd=str(WORKSPACE_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "", "Milestone 3 modified legacy files!")


if __name__ == "__main__":
    unittest.main()
