#!/usr/bin/env python3
"""Empirical Adversarial Challenge Suite for pose_ui_webview.BackendApi.

Adversarially tests pose_ui_webview.BackendApi against:
1. Input boundary & type coercion (valid/invalid bool, int, float, and YOLO parameters)
2. Non-existent video files & transactional rollback verification
3. Empty queue edge cases (start, cancel, move, retry, remove)
4. Duplicate destinations & collision resolution (_2, _3 suffixes)
5. Full Unicode, Japanese Kanji/Kana, emojis, and space preservation in paths
6. Invalid directions and out-of-range deltas in move_job
7. Multi-threaded rapid concurrent calls & race condition stress test
8. JSON serializability verification of all endpoint outputs
9. Subprocess telemetry & queue cancellation rollback
10. Robustness against null/None/corrupt inputs from JavaScript runtime

Usage:
    .\\.venv\\Scripts\\python.exe tests/test_backend_api_adversarial.py
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
        self.dialog_return_value: Any = None
        self._lock = threading.Lock()

    def evaluate_js(self, script: str) -> None:
        with self._lock:
            self.evaluated_scripts.append(script)

    def create_file_dialog(self, **kwargs) -> Any:
        return self.dialog_return_value


class TestBackendApiAdversarial(unittest.TestCase):
    """Adversarial challenge test harness for pose_ui_webview.BackendApi."""

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

    def _create_dummy_video(self, name: str = "sample.mp4") -> Path:
        video_path = self.temp_path / name
        video_path.parent.mkdir(parents=True, exist_ok=True)
        # Minimal MP4 container header
        video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
        return video_path

    def _assert_json_serializable(self, payload: Any, context_msg: str = "") -> None:
        """Verifies that an object is 100% JSON-serializable without raising TypeError or ValueError."""
        try:
            dumped = json.dumps(payload, ensure_ascii=False)
            self.assertIsInstance(dumped, str)
            reloaded = json.loads(dumped)
            self.assertIsNotNone(reloaded)
        except Exception as exc:
            self.fail(f"JSON serialization failure for {context_msg}: {exc}")

    # =========================================================================
    # 1. Handshake & Initial Data Edge Cases
    # =========================================================================

    def test_get_initial_data_empty_queue(self):
        """get_initial_data returns complete schema on fresh empty queue."""
        data = self.api.get_initial_data()
        self._assert_json_serializable(data, "get_initial_data empty queue")
        self.assertIn("queue", data)
        self.assertEqual(len(data["queue"]), 0)
        self.assertIn("settings", data)
        self.assertIn("system", data)
        self.assertIn("choices", data)
        self.assertEqual(data["system"]["is_processing"], False)
        self.assertIsNone(data["system"]["current_job_id"])

    def test_get_initial_data_populated_queue(self):
        """get_initial_data returns serialized queue items with correct summary metadata."""
        v = self._create_dummy_video("test_init.mp4")
        self.api.add_reservations([str(v)], str(self.output_root))

        data = self.api.get_initial_data()
        self._assert_json_serializable(data, "get_initial_data populated queue")
        self.assertEqual(len(data["queue"]), 1)
        job = data["queue"][0]
        self.assertEqual(job["video_name"], "test_init.mp4")
        self.assertIn("summary", job)
        self.assertEqual(job["summary"]["model_mode"], "performance")

    # =========================================================================
    # 2. Input Boundary & Transactional Rollback
    # =========================================================================

    def test_add_reservations_empty_or_none_raises_value_error(self):
        """add_reservations rejects empty list or None with clean ValueError."""
        with self.assertRaises(ValueError):
            self.api.add_reservations([])
        with self.assertRaises(ValueError):
            self.api.add_reservations(None)

    def test_add_reservations_non_existent_video_raises_and_rolls_back(self):
        """add_reservations with missing file raises ValueError and cleanly rolls back disk/RAM queue."""
        missing = self.temp_path / "does_not_exist.mp4"
        with self.assertRaises(ValueError):
            self.api.add_reservations([str(missing)], str(self.output_root))

        # Check queue in RAM
        self.assertEqual(len(self.api.reservations.jobs), 0)

        # Check queue on disk
        if self.queue_file.exists():
            disk_data = json.loads(self.queue_file.read_text(encoding="utf-8"))
            self.assertEqual(len(disk_data.get("jobs", [])), 0)

    def test_add_reservations_partial_failure_transactional_rollback(self):
        """Batch of [valid, missing, valid] must completely roll back — zero jobs registered."""
        v1 = self._create_dummy_video("valid1.mp4")
        v_missing = self.temp_path / "missing2.mp4"
        v3 = self._create_dummy_video("valid3.mp4")

        with self.assertRaises(ValueError):
            self.api.add_reservations([str(v1), str(v_missing), str(v3)], str(self.output_root))

        # In-memory must be empty
        self.assertEqual(len(self.api.reservations.jobs), 0)
        # Disk queue must have 0 jobs
        if self.queue_file.exists():
            disk_data = json.loads(self.queue_file.read_text(encoding="utf-8"))
            self.assertEqual(len(disk_data.get("jobs", [])), 0)

    def test_add_reservations_sanitizes_valid_string_coercions(self):
        """Settings with strings for booleans, ints, floats, and bad YOLO_TRACK_ID are coerced safely."""
        v = self._create_dummy_video("sanitize_test.mp4")
        adversarial_settings = {
            "TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING": "True",  # bool string
            "TARGET_LOCK_RAW_ID": "0",                          # bool falsy string
            "YOLO_CONFIDENCE": "0.75",                          # float string
            "CSV_MAX_PERSONS": "5",                             # int string
            "YOLO_TRACK_ID": "None",                            # track id "None" string -> None
            "YOLO_CLASSES": "0, 1, invalid",                    # classes string -> [0, 1]
            "YOLO_MODEL": "s",                                  # short model code -> yolo11s.pt
        }
        jobs = self.api.add_reservations(
            [str(v)], str(self.output_root), False, adversarial_settings
        )
        self.assertEqual(len(jobs), 1)
        job_settings = jobs[0]["settings"]
        self.assertIs(job_settings["TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING"], True)
        self.assertIs(job_settings["TARGET_LOCK_RAW_ID"], False)
        self.assertEqual(job_settings["YOLO_CONFIDENCE"], 0.75)
        self.assertEqual(job_settings["CSV_MAX_PERSONS"], 5)
        self.assertIsNone(job_settings["YOLO_TRACK_ID"])
        self.assertEqual(job_settings["YOLO_CLASSES"], [0, 1])
        self.assertEqual(job_settings["YOLO_MODEL"], "yolo11s.pt")
        self._assert_json_serializable(jobs, "sanitized job serialization")

    # =========================================================================
    # 3. Unicode, Japanese, Emojis, and Space Preservation
    # =========================================================================

    def test_unicode_japanese_and_special_paths(self):
        """Preserves Japanese characters (Kanji/Hiragana/Katakana), symbols, spaces, and punctuation."""
        complex_name = "【2026年 動作解析】_走高跳 (男子) #01 [テスト] ★.mp4"
        v = self._create_dummy_video(complex_name)
        custom_out = self.output_root / "出力フォルダ＿２０２６" / "詳細 データ (最終)"

        jobs = self.api.add_reservations(
            videos=[str(v)],
            output_folder=str(custom_out),
            is_multi=False,
            settings=None,
        )
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["video_name"], complex_name)
        self.assertTrue(complex_name in job["video_path"])
        self.assertTrue("出力フォルダ＿２０２６" in job["output_path"])

        # Check round-trip JSON serialization
        self._assert_json_serializable(job, "unicode job serialization")

        # Verify disk persistence intact
        disk_data = json.loads(self.queue_file.read_text(encoding="utf-8"))
        self.assertEqual(disk_data["jobs"][0]["settings"]["INPUT_VIDEO_NAME"], complex_name)

    # =========================================================================
    # 4. Duplicate Destinations and Collisions
    # =========================================================================

    def test_duplicate_destinations_increment_suffix_safely(self):
        """Adding duplicate videos in multi-mode creates collision-free folders with _2, _3 suffixes."""
        v1 = self._create_dummy_video("run.mp4")
        # Add multiple jobs with same video name
        j1 = self.api.add_reservations([str(v1)], str(self.output_root), is_multi=True)[0]
        j2 = self.api.add_reservations([str(v1)], str(self.output_root), is_multi=True)[0]
        j3 = self.api.add_reservations([str(v1)], str(self.output_root), is_multi=True)[0]

        self.assertEqual(j1["output_folder"], "run")
        self.assertEqual(j2["output_folder"], "run_2")
        self.assertEqual(j3["output_folder"], "run_3")

        # In-memory and disk consistency
        self.assertEqual(len(self.api.reservations.jobs), 3)

        # Update destination collision rejection
        with self.assertRaises(ValueError):
            self.api.update_job_settings(
                job_id=j3["id"],
                settings={"OUTPUT_ROOT": str(self.output_root), "OUTPUT_FOLDER_NAME": "run"},
            )

    # =========================================================================
    # 5. Job Reordering (move_job) Edge Cases & Invalid Directions
    # =========================================================================

    def test_move_job_valid_and_boundary(self):
        """move_job correctly moves up and down and handles boundary without error."""
        v1 = self._create_dummy_video("m1.mp4")
        v2 = self._create_dummy_video("m2.mp4")
        v3 = self._create_dummy_video("m3.mp4")
        jobs = self.api.add_reservations([str(v1), str(v2), str(v3)], str(self.output_root), is_multi=True)
        j1_id, j2_id, j3_id = jobs[0]["id"], jobs[1]["id"], jobs[2]["id"]

        # Move top job up -> boundary no-op
        q = self.api.move_job(j1_id, "up")
        self.assertEqual([j["id"] for j in q], [j1_id, j2_id, j3_id])

        # Move bottom job down -> boundary no-op
        q = self.api.move_job(j3_id, "down")
        self.assertEqual([j["id"] for j in q], [j1_id, j2_id, j3_id])

        # Move j2 up
        q = self.api.move_job(j2_id, -1)
        self.assertEqual([j["id"] for j in q], [j2_id, j1_id, j3_id])

        # Move j2 down via string "1"
        q = self.api.move_job(j2_id, "1")
        self.assertEqual([j["id"] for j in q], [j1_id, j2_id, j3_id])

    def test_move_job_invalid_direction_raises_value_error(self):
        """move_job rejects invalid directions like 'left', 0, 5, or None with clean ValueError."""
        v = self._create_dummy_video("m_inv.mp4")
        jobs = self.api.add_reservations([str(v)], str(self.output_root))
        jid = jobs[0]["id"]

        for bad_dir in ("left", "right", "horizontal", None, "forward"):
            with self.assertRaises(ValueError):
                self.api.move_job(jid, bad_dir)

        # Delta not -1 or 1 raises ValueError
        for bad_int in (0, 2, -2, 100):
            with self.assertRaises(ValueError):
                self.api.move_job(jid, bad_int)

    def test_move_job_non_existent_id_handled_safely(self):
        """move_job with unknown job_id returns queue safely without crashing."""
        q = self.api.move_job("non-existent-id", "up")
        self.assertIsInstance(q, list)

    # =========================================================================
    # 6. Job Removal & Running Job Protection
    # =========================================================================

    def test_remove_jobs_empty_or_unknown_safe(self):
        """remove_jobs with empty list or unknown IDs returns queue safely."""
        q = self.api.remove_jobs([])
        self.assertEqual(len(q), 0)
        q = self.api.remove_jobs(["unknown_1", "unknown_2"])
        self.assertEqual(len(q), 0)

    def test_remove_jobs_running_job_protected(self):
        """remove_jobs refuses to delete a job currently in 'running' state."""
        v = self._create_dummy_video("run_prot.mp4")
        jobs = self.api.add_reservations([str(v)], str(self.output_root))
        jid = jobs[0]["id"]

        # Simulate job running
        job = self.queue.find(jid)
        job.state = "running"
        self.queue.save()

        # Attempt to remove
        updated = self.api.remove_jobs([jid])
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["id"], jid)

    # =========================================================================
    # 7. Job Update & RTMLib Validation
    # =========================================================================

    def test_update_job_settings_unknown_job_raises_value_error(self):
        """update_job_settings on non-existent job ID raises ValueError."""
        with self.assertRaises(ValueError):
            self.api.update_job_settings("fake_id", {"YOLO_MODEL": "yolo11s.pt"})

    def test_update_job_settings_invalid_rtmlib_rejected(self):
        """update_job_settings with invalid RTMLib combination raises ValueError and does not corrupt job."""
        v = self._create_dummy_video("rtm_val.mp4")
        jobs = self.api.add_reservations([str(v)], str(self.output_root))
        jid = jobs[0]["id"]

        bad_settings = {
            "MODEL_MODE": "lightweight",
            "RTMLIB_POSE_MODEL": "rtmpose-l",  # Incompatible with lightweight
        }
        with self.assertRaises(ValueError):
            self.api.update_job_settings(jid, bad_settings)

        # Job settings must remain untouched
        job = self.queue.find(jid)
        self.assertEqual(job.settings["MODEL_MODE"], "performance")

    def test_validate_rtmlib_settings_returns_clean_dict(self):
        """validate_rtmlib_settings returns valid JSON dict without raising exceptions."""
        valid_res = self.api.validate_rtmlib_settings("performance", "mode", "mode", "mode")
        self._assert_json_serializable(valid_res, "valid RTMLib resolution")
        self.assertTrue(valid_res["valid"])
        self.assertIn("resolved", valid_res)

        invalid_res = self.api.validate_rtmlib_settings("lightweight", "rtmpose-l", "mode", "mode")
        self._assert_json_serializable(invalid_res, "invalid RTMLib resolution")
        self.assertFalse(invalid_res["valid"])
        self.assertIn("error", invalid_res)

    # =========================================================================
    # 8. Settings Persistence (save_default_settings)
    # =========================================================================

    def test_save_default_settings_persists_and_updates_root(self):
        """save_default_settings validates, updates default settings file, and updates queue root."""
        new_root = self.temp_path / "new_default_output"
        new_settings = {
            "MODEL_MODE": "balanced",
            "YOLO_MODEL": "yolo11l.pt",
            "DEVICE": "cpu",
            "OUTPUT_ROOT": str(new_root),
        }
        saved = self.api.save_default_settings(new_settings)
        self._assert_json_serializable(saved, "saved default settings")
        self.assertEqual(saved["MODEL_MODE"], "balanced")
        self.assertEqual(saved["YOLO_MODEL"], "yolo11l.pt")
        self.assertEqual(self.api.reservations.output_root, str(new_root.resolve()))

        # Verify disk persistence
        self.assertTrue(self.settings_file.exists())
        persisted = json.loads(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(persisted["MODEL_MODE"], "balanced")

    # =========================================================================
    # 9. Queue Processing & Cancellation Lifecycle
    # =========================================================================

    def test_queue_processing_empty_queue_safe(self):
        """start_queue_processing on empty queue returns {'status': 'empty'} without error."""
        res = self.api.start_queue_processing()
        self._assert_json_serializable(res, "start_queue_processing empty")
        self.assertEqual(res["status"], "empty")
        self.assertFalse(self.api.is_processing)

    def test_cancel_current_job_when_idle_safe(self):
        """cancel_current_job when no job is running returns {'status': 'idle'} without error."""
        res = self.api.cancel_current_job()
        self._assert_json_serializable(res, "cancel_current_job idle")
        self.assertEqual(res["status"], "idle")

    # =========================================================================
    # 10. Native Dialog Endpoints Without Window
    # =========================================================================

    def test_native_dialogs_without_window_return_safe_defaults(self):
        """Calling dialog methods without window attached returns safe empty defaults."""
        api_no_win = BackendApi(base_dir=self.temp_path)
        self.assertEqual(api_no_win.select_video_files(), [])
        self.assertEqual(api_no_win.select_directory(), "")
        self.assertIsNone(api_no_win.select_image_file())

    def test_native_dialogs_with_exception_return_safe_defaults(self):
        """If create_file_dialog raises unexpected exception, methods catch and return defaults."""
        class CrashingWindow:
            def create_file_dialog(self, **kwargs):
                raise RuntimeError("Native COM / Win32 Dialog Crash")

        self.api.set_window(CrashingWindow())
        self.assertEqual(self.api.select_video_files(), [])
        self.assertEqual(self.api.select_directory(), "")
        self.assertIsNone(self.api.select_image_file())

    # =========================================================================
    # 11. Multi-Threaded Concurrency & Rapid Stress Test
    # =========================================================================

    def test_rapid_consecutive_concurrent_calls(self):
        """Stress tests BackendApi with 20 concurrent threads performing queue mutations and reads."""
        videos = [self._create_dummy_video(f"rapid_{i}.mp4") for i in range(10)]
        exceptions: list[Exception] = []

        def worker_task(thread_id: int):
            try:
                for step in range(5):
                    # Reader
                    init = self.api.get_initial_data()
                    self._assert_json_serializable(init)

                    # Writer
                    vid = videos[thread_id % len(videos)]
                    created = self.api.add_reservations([str(vid)], str(self.output_root), is_multi=True)
                    if created:
                        jid = created[0]["id"]
                        self.api.move_job(jid, "up")
                        self.api.update_job_settings(jid, {"YOLO_MODEL": "yolo11s.pt"})
                        # Random delete
                        if step % 2 == 0:
                            self.api.remove_jobs([jid])
            except Exception as exc:
                exceptions.append(exc)

        threads = [
            threading.Thread(target=worker_task, args=(i,), name=f"StressWorker-{i}")
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        # No uncaught exceptions allowed
        self.assertEqual(
            len(exceptions), 0, f"Concurrent execution produced exceptions: {exceptions}"
        )

        # Final queue on disk must be valid JSON
        self.assertTrue(self.queue_file.exists())
        final_disk = json.loads(self.queue_file.read_text(encoding="utf-8"))
        self.assertIn("jobs", final_disk)

    # =========================================================================
    # 12. Vulnerability Probes: Null/None and Corrupt JS Payloads
    # =========================================================================

    def test_get_preview_frame_null_path_safe(self):
        """get_preview_frame(None) must return empty string without raising TypeError."""
        res = self.api.get_preview_frame(None)
        self.assertEqual(res, "")

    def test_save_default_settings_null_output_root_safe(self):
        """save_default_settings with OUTPUT_ROOT: None must fall back safely without raising TypeError."""
        res = self.api.save_default_settings({"OUTPUT_ROOT": None})
        self.assertIn("OUTPUT_ROOT", res)
        self.assertIsNotNone(res["OUTPUT_ROOT"])

    def test_sanitize_settings_corrupt_yolo_classes_list_safe(self):
        """sanitize_settings with non-numeric strings in YOLO_CLASSES list must not raise ValueError."""
        res = self.api.sanitize_settings({"YOLO_CLASSES": ["0", "invalid", 2]})
        self.assertEqual(res["YOLO_CLASSES"], [0, 2])

    def test_get_output_preview_names_null_and_empty_safe(self):
        """get_output_preview_names(None) or empty string must not raise TypeError or ValueError."""
        res_none = self.api.get_output_preview_names(None)
        self.assertIsInstance(res_none, dict)
        res_empty = self.api.get_output_preview_names("")
        self.assertIsInstance(res_empty, dict)

    def test_update_job_settings_null_destination_fields_safe(self):
        """update_job_settings when OUTPUT_ROOT or OUTPUT_FOLDER_NAME is None must not raise TypeError."""
        v = self._create_dummy_video("null_dest.mp4")
        job = self.api.add_reservations([str(v)], str(self.output_root), is_multi=True)[0]
        res1 = self.api.update_job_settings(job["id"], {"OUTPUT_ROOT": None, "OUTPUT_FOLDER_NAME": "test"})
        self.assertIsNotNone(res1)
        res2 = self.api.update_job_settings(job["id"], {"OUTPUT_ROOT": str(self.output_root), "OUTPUT_FOLDER_NAME": None})
        self.assertIsNotNone(res2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
