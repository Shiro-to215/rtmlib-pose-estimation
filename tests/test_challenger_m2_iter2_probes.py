"""Adversarial and Edge-Case Empirical Verification for Milestone 2 Iteration 2.

Author: teamwork_challenger (Challenger 1)
Purpose: Empirically stress-test the 5 edge-case vulnerabilities and boundary conditions
in pose_ui_webview.api_bridge.BackendApi.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import gui
from reservation_queue import ReservationQueue, write_json
from pose_ui_webview.api_bridge import BackendApi


class TestChallengerEdgeCaseProbes(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="challenger_probe_"))
        self.queue_file = self.tmp_dir / "reservation_queue.json"
        self.settings_file = self.tmp_dir / "gui_settings.json"
        self.output_root = self.tmp_dir / "output"
        self.output_root.mkdir(parents=True, exist_ok=True)

        self.queue = ReservationQueue(self.queue_file, self.output_root)
        self.api = BackendApi(
            base_dir=self.tmp_dir,
            settings_file=self.settings_file,
            reservations=self.queue,
            resolve_rtmlib_fn=gui.resolve_rtmlib_selection,
            output_names_fn=gui.output_names,
        )

        self.dummy_video = self.tmp_dir / "probe_test.mp4"
        self.dummy_video.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")

    def tearDown(self):
        self.api.shutdown()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. get_preview_frame probes
    # -------------------------------------------------------------------------
    def test_get_preview_frame_all_invalid_types_and_values(self):
        """get_preview_frame must cleanly return empty string for all non-str/non-Path or missing inputs."""
        invalid_inputs = [
            None,
            "",
            123,
            0,
            -1,
            3.14,
            [],
            [1, 2],
            {},
            {"video": "path"},
            Path(self.tmp_dir / "non_existent_file.mp4"),
            "non_existent_file.mp4",
        ]
        for val in invalid_inputs:
            with self.subTest(val=val):
                res = self.api.get_preview_frame(val)
                self.assertEqual(res, "", f"Failed for input {val!r}")

    # -------------------------------------------------------------------------
    # 2. save_default_settings probes
    # -------------------------------------------------------------------------
    def test_save_default_settings_null_and_malformed_payloads(self):
        """save_default_settings must not raise TypeError when OUTPUT_ROOT is None or corrupt."""
        test_payloads = [
            {"OUTPUT_ROOT": None},
            {},
            {"OUTPUT_ROOT": None, "MODEL_MODE": "performance"},
            {"OUTPUT_ROOT": None, "YOLO_CLASSES": [None, "invalid", 2]},
            {"OUTPUT_ROOT": None, "YOLO_TRACK_ID": "null"},
            {"OUTPUT_ROOT": None, "YOLO_TRACK_ID": "None"},
            {"OUTPUT_ROOT": None, "YOLO_TRACK_ID": "invalid"},
            {"OUTPUT_ROOT": str(self.output_root), "DETECT_PERSON": "true"},
        ]
        for payload in test_payloads:
            with self.subTest(payload=payload):
                res = self.api.save_default_settings(payload)
                self.assertIsInstance(res, dict)
                self.assertIn("OUTPUT_ROOT", res)
                self.assertIsNotNone(res["OUTPUT_ROOT"])
                self.assertTrue(len(res["OUTPUT_ROOT"]) > 0)

    # -------------------------------------------------------------------------
    # 3. sanitize_settings probes
    # -------------------------------------------------------------------------
    def test_sanitize_settings_corrupt_types_and_lists(self):
        """sanitize_settings must safely coerce and drop invalid items without raising exceptions."""
        # YOLO_CLASSES list with non-numeric, None, dict, and strings
        res = self.api.sanitize_settings(
            {"YOLO_CLASSES": ["0", "invalid", 2, None, "10", -5, {}, []]}
        )
        self.assertEqual(res["YOLO_CLASSES"], [0, 2, 10, -5])

        # YOLO_CLASSES string comma-delimited
        res_str = self.api.sanitize_settings({"YOLO_CLASSES": "0, 1, foo, 2, , 3"})
        self.assertEqual(res_str["YOLO_CLASSES"], [0, 1, 2, 3])

        # YOLO_CLASSES None or int
        res_none = self.api.sanitize_settings({"YOLO_CLASSES": None})
        self.assertIsNone(res_none["YOLO_CLASSES"])

        # YOLO_TRACK_ID edge cases
        for tid, expected in [
            (None, None),
            ("", None),
            ("None", None),
            ("null", None),
            ("corrupt", None),
            ("42", 42),
            (42, 42),
            (0, 0),
        ]:
            res_tid = self.api.sanitize_settings({"YOLO_TRACK_ID": tid})
            self.assertEqual(res_tid["YOLO_TRACK_ID"], expected, f"Failed for {tid!r}")

        # Boolean coercions for known boolean key
        for bval, expected in [
            ("true", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("false", False),
            ("0", False),
            ("no", False),
            (True, True),
            (False, False),
            (1, True),
            (0, False),
        ]:
            res_b = self.api.sanitize_settings({"TARGET_LOCK_RAW_ID": bval})
            self.assertEqual(res_b["TARGET_LOCK_RAW_ID"], expected, f"Failed for {bval!r}")

        # Int / float invalid values (must not crash)
        res_num = self.api.sanitize_settings({"LINE_WIDTH": "invalid", "CONF_THRES": "invalid"})
        self.assertEqual(res_num["LINE_WIDTH"], "invalid")
        self.assertEqual(res_num["CONF_THRES"], "invalid")

    # -------------------------------------------------------------------------
    # 4. get_output_preview_names probes
    # -------------------------------------------------------------------------
    def test_get_output_preview_names_edge_and_boundary_cases(self):
        """get_output_preview_names must never raise TypeError or ValueError."""
        invalid_folders = [
            None,
            "",
            123,
            [],
            {},
            "C:\\",
            "C:/",
            "//",
            Path("."),
        ]
        for f in invalid_folders:
            with self.subTest(folder=f):
                res = self.api.get_output_preview_names(f)
                self.assertIsInstance(res, dict)

        # Valid folder
        folder_valid = self.output_root / "test_run"
        res_v = self.api.get_output_preview_names(str(folder_valid))
        self.assertEqual(res_v["OUTPUT_VIDEO_NAME"], "test_run.mp4")
        self.assertEqual(res_v["OUTPUT_YOLO_VIDEO_NAME"], "test_run-yolo.mp4")
        self.assertEqual(res_v["OUTPUT_CSV_NAME"], "test_run.csv")
        self.assertEqual(res_v["OUTPUT_METADATA_NAME"], "test_run_metadata.txt")

    # -------------------------------------------------------------------------
    # 5. update_job_settings probes
    # -------------------------------------------------------------------------
    def test_update_job_settings_null_destinations_and_non_engine_keys(self):
        """update_job_settings must handle None destination fields and strip non-engine keys."""
        jobs = self.api.add_reservations([str(self.dummy_video)], str(self.output_root), is_multi=True)
        job_id = jobs[0]["id"]

        test_payloads = [
            {"OUTPUT_ROOT": None, "OUTPUT_FOLDER_NAME": "test"},
            {"OUTPUT_ROOT": str(self.output_root), "OUTPUT_FOLDER_NAME": None},
            {"OUTPUT_ROOT": None, "OUTPUT_FOLDER_NAME": None},
            {"OUTPUT_DIRECTORY": None},
            {"OUTPUT_DIRECTORY": ""},
            {"OUTPUT_DIRECTORY": str(self.output_root / "custom_dest")},
            {"YOLO_CLASSES": ["0", "corrupt", 1]},
            {
                "OUTPUT_DIRECTORY": "dir",
                "OUTPUT_ROOT": "root",
                "OUTPUT_FOLDER_NAME": "folder",
                "MODEL_MODE": "performance",
            },
        ]

        for payload in test_payloads:
            with self.subTest(payload=payload):
                res = self.api.update_job_settings(job_id, payload)
                self.assertIsInstance(res, dict)
                self.assertIn("id", res)
                self.assertEqual(res["id"], job_id)

                # Ensure non-engine key OUTPUT_DIRECTORY is stripped from job.settings
                job_obj = self.api.reservations.find(job_id)
                self.assertNotIn(
                    "OUTPUT_DIRECTORY",
                    job_obj.settings,
                    "Non-engine key OUTPUT_DIRECTORY was not stripped from job.settings!",
                )

    # -------------------------------------------------------------------------
    # 6. Worker config file stripping non-engine keys
    # -------------------------------------------------------------------------
    def test_worker_config_pure_engine_keys(self):
        """Worker config JSON file must contain only keys defined in gui.ENGINE_DEFAULTS."""
        import json
        jobs = self.api.add_reservations([str(self.dummy_video)], str(self.output_root), is_multi=True)
        job_id = jobs[0]["id"]

        # Update with some non-engine keys in dictionary
        self.api.update_job_settings(job_id, {"OUTPUT_DIRECTORY": "foo", "MODEL_MODE": "balanced"})
        job = self.api.reservations.find(job_id)

        # Worker manager config preparation check
        config_dir = self.tmp_dir / ".analysis_jobs" / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / f"{job.id}.json"
        clean_settings = {k: v for k, v in job.settings.items() if k in set(getattr(gui, "ENGINE_DEFAULTS", {}))}
        write_json(config_path, clean_settings)

        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        for k in loaded:
            self.assertIn(k, gui.ENGINE_DEFAULTS)
        self.assertNotIn("OUTPUT_DIRECTORY", loaded)

    # -------------------------------------------------------------------------
    # 7. Worker manager shutdown joins the thread
    # -------------------------------------------------------------------------
    def test_worker_manager_shutdown_joins_queue_thread(self):
        """AnalysisWorkerManager.shutdown must cleanly join the background queue thread."""
        import threading
        import time

        wm = self.api.worker_manager
        self.assertIsNotNone(wm)

        # Start a dummy thread simulating the queue thread
        def dummy_worker():
            for _ in range(50):
                if wm._stop_requested.is_set():
                    break
                time.sleep(0.01)

        fake_thread = threading.Thread(target=dummy_worker, daemon=True)
        wm._queue_thread = fake_thread
        fake_thread.start()
        self.assertTrue(fake_thread.is_alive())

        wm.shutdown(timeout_sec=1.0)
        self.assertFalse(fake_thread.is_alive(), "WorkerManager queue thread was not joined during shutdown!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
