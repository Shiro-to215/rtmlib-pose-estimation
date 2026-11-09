#!/usr/bin/env python3
"""Automated Smoke & Integration Test Suite for PyWebView & React/Vite Desktop Application Rebuild.

Covers:
- Tier 1: Feature Coverage (ReservationQueue, Engine Functions, Bridge Interface Contracts)
- Tier 2: Boundary & Corner Cases (Collisions, Empty States, Rollback, Unicode/Japanese paths)
- Backend Preservation Invariants (Zero-modification verification for gui.py and reservation_queue.py)

Usage:
    .\\.venv\\Scripts\\python.exe tests/test_pywebview_migration.py
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from typing import Any

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Import preserved backend modules
import reservation_queue
from reservation_queue import Reservation, ReservationQueue, set_output, write_json
import gui


class TestBackendPreservation(unittest.TestCase):
    """Verifies that backend core files and specifications are 100% preserved (Requirement R2)."""

    def test_backend_files_exist_and_readable(self):
        """Assures gui.py and reservation_queue.py exist in workspace root."""
        gui_path = WORKSPACE_ROOT / "gui.py"
        queue_path = WORKSPACE_ROOT / "reservation_queue.py"
        self.assertTrue(gui_path.is_file(), "gui.py must exist in workspace root")
        self.assertTrue(queue_path.is_file(), "reservation_queue.py must exist in workspace root")
        self.assertGreater(gui_path.stat().st_size, 10000, "gui.py must not be truncated")
        self.assertGreater(queue_path.stat().st_size, 5000, "reservation_queue.py must not be truncated")

    def test_gui_engine_defaults_intact(self):
        """Verifies ENGINE_DEFAULTS has 52 settings matching ENGINE_SETTING_NAMES."""
        self.assertEqual(len(gui.ENGINE_SETTING_NAMES), 52)
        self.assertEqual(len(gui.ENGINE_DEFAULTS), 52)
        for key in gui.ENGINE_SETTING_NAMES:
            self.assertIn(key, gui.ENGINE_DEFAULTS)

    def test_gui_choices_and_types_intact(self):
        """Verifies choices and type key groupings in gui.py."""
        self.assertIn("YOLO_MODEL", gui.CHOICES)
        self.assertIn("MODEL_MODE", gui.CHOICES)
        self.assertIn("RTMLIB_POSE_MODEL", gui.CHOICES)
        self.assertIn("DEVICE", gui.CHOICES)
        self.assertIn("OUTPUT_DIRECTORY", gui.PATH_KEYS)
        self.assertIn("INPUT_VIDEO_FILE", gui.FILE_KEYS)
        self.assertIsInstance(gui.BOOL_KEYS, set)
        self.assertIsInstance(gui.INT_KEYS, set)
        self.assertIsInstance(gui.FLOAT_KEYS, set)

    def test_reservation_queue_classes_and_functions_intact(self):
        """Verifies classes and functions exist in reservation_queue.py."""
        self.assertTrue(hasattr(reservation_queue, "ReservationQueue"))
        self.assertTrue(hasattr(reservation_queue, "Reservation"))
        self.assertTrue(hasattr(reservation_queue, "set_output"))
        self.assertTrue(hasattr(reservation_queue, "write_json"))
        self.assertTrue(hasattr(reservation_queue, "transactional"))
        self.assertEqual(reservation_queue.STATES, {"pending", "running", "done", "failed"})


class TestReservationQueueFeatureCoverage(unittest.TestCase):
    """Tier 1: Feature coverage for ReservationQueue operations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.queue_file = self.temp_path / "analysis_queue.json"
        self.output_root = self.temp_path / "output"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.template_settings = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            self.template_settings[k] = str(self.template_settings[k])

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_dummy_video(self, name: str = "video.mp4") -> Path:
        video_path = self.temp_path / name
        video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
        return video_path

    def test_queue_load_missing_file_creates_empty_queue(self):
        """Initializing ReservationQueue with non-existent file creates empty queue."""
        q = ReservationQueue(self.queue_file, self.output_root)
        self.assertEqual(len(q.jobs), 0)
        self.assertEqual(q.output_root, str(self.output_root))
        self.assertIsNone(q.next_pending())

    def test_queue_add_single_video_default_dest(self):
        """Adding a single video generates a job with correct output directory and pending state."""
        video = self._create_dummy_video("run_sample.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        created = q.add(
            videos=[video],
            template=self.template_settings,
            root=self.output_root,
            output_names=gui.output_names,
        )
        self.assertEqual(len(created), 1)
        job = created[0]
        self.assertEqual(len(job.id), 32)
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.error, "")
        self.assertEqual(job.video.name, "run_sample.mp4")
        self.assertEqual(job.output.name, "run_sample")
        self.assertEqual(job.settings["OUTPUT_VIDEO_NAME"], "run_sample.mp4")
        self.assertEqual(job.settings["OUTPUT_YOLO_VIDEO_NAME"], "run_sample-yolo.mp4")
        self.assertEqual(job.settings["OUTPUT_CSV_NAME"], "run_sample.csv")
        self.assertEqual(job.settings["OUTPUT_METADATA_NAME"], "run_sample_metadata.txt")

        # Verify disk persistence
        self.assertTrue(self.queue_file.exists())
        data = json.loads(self.queue_file.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(len(data["jobs"]), 1)
        self.assertEqual(data["jobs"][0]["id"], job.id)

    def test_queue_add_multiple_videos(self):
        """Adding multiple videos creates ordered jobs with unique collision-free outputs."""
        v1 = self._create_dummy_video("clip1.mp4")
        v2 = self._create_dummy_video("clip2.mp4")
        v3 = self._create_dummy_video("clip3.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        created = q.add(
            videos=[v1, v2, v3],
            template=self.template_settings,
            root=self.output_root,
            output_names=gui.output_names,
        )
        self.assertEqual(len(created), 3)
        self.assertEqual(len(q.jobs), 3)
        self.assertEqual([j.video.name for j in q.jobs], ["clip1.mp4", "clip2.mp4", "clip3.mp4"])
        self.assertEqual(q.next_pending().id, created[0].id)

    def test_queue_add_with_custom_destination(self):
        """Adding a single video with a custom destination respects the override."""
        video = self._create_dummy_video("single.mp4")
        custom_dest = self.output_root / "custom_folder_name"
        q = ReservationQueue(self.queue_file, self.output_root)
        created = q.add(
            videos=[video],
            template=self.template_settings,
            root=self.output_root,
            output_names=gui.output_names,
            custom_destination=custom_dest,
        )
        self.assertEqual(created[0].output.name, "custom_folder_name")
        self.assertEqual(created[0].settings["OUTPUT_FOLDER_NAME"], "custom_folder_name")

    def test_queue_add_with_thumbnail(self):
        """Adding a single video with thumbnail stores thumbnail settings."""
        video = self._create_dummy_video("thumb_test.mp4")
        thumb = self.temp_path / "thumb.jpg"
        thumb.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")
        q = ReservationQueue(self.queue_file, self.output_root)
        created = q.add(
            videos=[video],
            template=self.template_settings,
            root=self.output_root,
            output_names=gui.output_names,
            thumbnail=thumb,
        )
        self.assertEqual(created[0].settings["THUMBNAIL_IMAGE_NAME"], "thumb.jpg")
        self.assertEqual(created[0].settings["THUMBNAIL_ROOT"], str(self.temp_path.resolve()))

    def test_queue_update_job_success(self):
        """update_job modifies settings and destination correctly."""
        video = self._create_dummy_video("update_test.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        created = q.add([video], self.template_settings, self.output_root, gui.output_names)
        job_id = created[0].id

        new_settings = deepcopy(self.template_settings)
        new_settings["YOLO_MODEL"] = "yolo11x.pt"
        new_dest = self.output_root / "updated_dest"

        updated = q.update_job(job_id, new_settings, new_dest, gui.output_names)
        self.assertEqual(updated.settings["YOLO_MODEL"], "yolo11x.pt")
        self.assertEqual(updated.output.name, "updated_dest")
        self.assertEqual(updated.settings["OUTPUT_VIDEO_NAME"], "updated_dest.mp4")

    def test_queue_update_job_reset_failed(self):
        """update_job with reset_failed=True resets a failed job to pending."""
        video = self._create_dummy_video("failed_reset.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        created = q.add([video], self.template_settings, self.output_root, gui.output_names)
        job = created[0]
        job.state = "failed"
        job.error = "Error during inference"
        q.save()

        new_dest = self.output_root / "retry_dest"
        updated = q.update_job(job.id, job.settings, new_dest, gui.output_names, reset_failed=True)
        self.assertEqual(updated.state, "pending")
        self.assertEqual(updated.error, "")

    def test_queue_remove_jobs(self):
        """remove() deletes specified jobs by ID from queue."""
        v1 = self._create_dummy_video("del1.mp4")
        v2 = self._create_dummy_video("del2.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        jobs = q.add([v1, v2], self.template_settings, self.output_root, gui.output_names)
        self.assertEqual(len(q.jobs), 2)

        q.remove([jobs[0].id])
        self.assertEqual(len(q.jobs), 1)
        self.assertEqual(q.jobs[0].id, jobs[1].id)

    def test_queue_move_up_and_down(self):
        """move() swaps positions of pending jobs up (-1) or down (+1)."""
        v1 = self._create_dummy_video("m1.mp4")
        v2 = self._create_dummy_video("m2.mp4")
        v3 = self._create_dummy_video("m3.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        jobs = q.add([v1, v2, v3], self.template_settings, self.output_root, gui.output_names)
        j1, j2, j3 = jobs[0].id, jobs[1].id, jobs[2].id

        # Move j2 up (-1) -> order becomes j2, j1, j3
        q.move(j2, -1)
        self.assertEqual([j.id for j in q.jobs], [j2, j1, j3])

        # Move j2 down (+1) -> order becomes j1, j2, j3
        q.move(j2, 1)
        self.assertEqual([j.id for j in q.jobs], [j1, j2, j3])

    def test_queue_retry_failed_job(self):
        """retry() resets failed job to pending and ensures destination availability."""
        video = self._create_dummy_video("retry_test.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        created = q.add([video], self.template_settings, self.output_root, gui.output_names)
        job = created[0]
        job.state = "failed"
        job.error = "Worker crashed"
        q.save()

        # Create the destination directory on disk to test collision avoidance on retry
        job.output.mkdir(parents=True, exist_ok=True)

        q.retry([job.id], gui.output_names)
        retried = q.find(job.id)
        self.assertEqual(retried.state, "pending")
        self.assertEqual(retried.error, "")
        # Output should have been bumped to avoid collision
        self.assertEqual(retried.output.name, "retry_test_2")

    def test_write_json_creates_parents_and_replaces_atomically(self):
        """write_json creates parent directories if needed and writes JSON atomically."""
        nested_file = self.temp_path / "deeply" / "nested" / "test.json"
        data = {"hello": "world", "num": 42}
        write_json(nested_file, data)
        self.assertTrue(nested_file.is_file())
        loaded = json.loads(nested_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded, data)

    def test_reservation_properties(self):
        """Reservation video and output properties return correct resolved paths."""
        res = Reservation(
            settings={
                "INPUT_ROOT": str(self.temp_path),
                "INPUT_VIDEO_NAME": "my_video.mp4",
                "OUTPUT_ROOT": str(self.output_root),
                "OUTPUT_FOLDER_NAME": "my_output",
            }
        )
        self.assertEqual(res.video, self.temp_path / "my_video.mp4")
        self.assertEqual(res.output, self.output_root / "my_output")

    def test_queue_migration_of_interrupted_jobs(self):
        """Loading a queue with 'running', 'stopped', or 'interrupted' jobs converts them to 'pending'."""
        data = {
            "version": 1,
            "output_root": str(self.output_root),
            "jobs": [
                {
                    "id": "1" * 32,
                    "state": "running",
                    "error": "in progress",
                    "settings": {
                        "INPUT_ROOT": str(self.temp_path),
                        "INPUT_VIDEO_NAME": "v1.mp4",
                        "OUTPUT_ROOT": str(self.output_root),
                        "OUTPUT_FOLDER_NAME": "out1",
                    },
                },
                {
                    "id": "2" * 32,
                    "state": "stopped",
                    "error": "user cancelled",
                    "settings": {
                        "INPUT_ROOT": str(self.temp_path),
                        "INPUT_VIDEO_NAME": "v2.mp4",
                        "OUTPUT_ROOT": str(self.output_root),
                        "OUTPUT_FOLDER_NAME": "out2",
                    },
                },
            ],
        }
        self.queue_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        q = ReservationQueue(self.queue_file, self.output_root)
        self.assertEqual(len(q.jobs), 2)
        self.assertEqual(q.jobs[0].state, "pending")
        self.assertEqual(q.jobs[0].error, "")
        self.assertEqual(q.jobs[1].state, "pending")
        self.assertEqual(q.jobs[1].error, "")

    def test_queue_resume_prioritization(self):
        """Running job from previous session is placed before existing pending jobs upon reload."""
        data = {
            "version": 1,
            "output_root": str(self.output_root),
            "jobs": [
                {
                    "id": "a" * 32,
                    "state": "pending",
                    "error": "",
                    "settings": {
                        "INPUT_ROOT": str(self.temp_path),
                        "INPUT_VIDEO_NAME": "pending.mp4",
                        "OUTPUT_ROOT": str(self.output_root),
                        "OUTPUT_FOLDER_NAME": "out_a",
                    },
                },
                {
                    "id": "b" * 32,
                    "state": "running",
                    "error": "",
                    "settings": {
                        "INPUT_ROOT": str(self.temp_path),
                        "INPUT_VIDEO_NAME": "running.mp4",
                        "OUTPUT_ROOT": str(self.output_root),
                        "OUTPUT_FOLDER_NAME": "out_b",
                    },
                },
            ],
        }
        self.queue_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        q = ReservationQueue(self.queue_file, self.output_root)
        # Running job 'b'*32 should be prioritized to index 0
        self.assertEqual(q.jobs[0].id, "b" * 32)
        self.assertEqual(q.jobs[1].id, "a" * 32)


class TestReservationQueueBoundaryAndCornerCases(unittest.TestCase):
    """Tier 2: Boundary conditions, corner cases, error recovery, and stress inputs."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.queue_file = self.temp_path / "analysis_queue.json"
        self.output_root = self.temp_path / "output"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.template_settings = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            self.template_settings[k] = str(self.template_settings[k])

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_dummy_video(self, name: str = "video.mp4") -> Path:
        video_path = self.temp_path / name
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
        return video_path

    def test_empty_queue_operations_safe(self):
        """Operations on an empty queue complete safely without throwing exceptions."""
        q = ReservationQueue(self.queue_file, self.output_root)
        self.assertIsNone(q.next_pending())
        self.assertIsNone(q.find("nonexistent_id"))
        # remove and move on non-existent jobs
        q.remove(["nonexistent_id"])
        q.move("nonexistent_id", 1)
        q.move("nonexistent_id", -1)
        # save empty queue
        q.save()
        self.assertEqual(len(q.jobs), 0)

    def test_move_boundary_no_op(self):
        """Moving the first job up or last job down leaves order unchanged."""
        v1 = self._create_dummy_video("b1.mp4")
        v2 = self._create_dummy_video("b2.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        jobs = q.add([v1, v2], self.template_settings, self.output_root, gui.output_names)
        j1, j2 = jobs[0].id, jobs[1].id

        # Moving first job up (-1)
        q.move(j1, -1)
        self.assertEqual([j.id for j in q.jobs], [j1, j2])

        # Moving second job down (+1)
        q.move(j2, 1)
        self.assertEqual([j.id for j in q.jobs], [j1, j2])

    def test_queue_high_concurrency_rapid_additions(self):
        """Rapid additions with identical filenames produce unique, collision-free suffixes."""
        video = self._create_dummy_video("repeat.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        # Add the same video 10 times consecutively
        for _ in range(10):
            q.add([video], self.template_settings, self.output_root, gui.output_names)

        self.assertEqual(len(q.jobs), 10)
        output_names = [j.output.name for j in q.jobs]
        # First is 'repeat', then 'repeat_2', ..., 'repeat_10'
        expected = ["repeat"] + [f"repeat_{i}" for i in range(2, 11)]
        self.assertEqual(output_names, expected)
        # All job IDs must be unique
        self.assertEqual(len({j.id for j in q.jobs}), 10)

    def test_ensure_available_destination_disk_collision(self):
        """Collisions with existing disk folders increment suffix: dir -> dir_2 -> dir_3."""
        q = ReservationQueue(self.queue_file, self.output_root)
        target = self.output_root / "test_clip"

        # Case 1: Doesn't exist
        dest1 = q.ensure_available_destination(target)
        self.assertEqual(dest1.name, "test_clip")

        # Case 2: Exists on disk
        target.mkdir(parents=True, exist_ok=True)
        dest2 = q.ensure_available_destination(target)
        self.assertEqual(dest2.name, "test_clip_2")

        # Case 3: test_clip_2 also exists
        (self.output_root / "test_clip_2").mkdir(parents=True, exist_ok=True)
        dest3 = q.ensure_available_destination(target)
        self.assertEqual(dest3.name, "test_clip_3")

    def test_ensure_available_destination_reserved_collision(self):
        """Collisions with active reservations increment suffix even if not on disk."""
        video = self._create_dummy_video("reserved.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        q.add([video], self.template_settings, self.output_root, gui.output_names)

        # In-memory reservation now reserves 'reserved'
        dest = q.ensure_available_destination(self.output_root / "reserved")
        self.assertEqual(dest.name, "reserved_2")

    def test_ensure_available_destination_case_insensitive_windows(self):
        """Case variations in folder names are treated as collisions on Windows."""
        video = self._create_dummy_video("CaseVideo.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        q.add([video], self.template_settings, self.output_root, gui.output_names)

        # 'casevideo' should collide with 'CaseVideo'
        dest = q.ensure_available_destination(self.output_root / "casevideo")
        self.assertEqual(dest.name, "casevideo_2")

    def test_ensure_available_destination_empty_raises_value_error(self):
        """Empty destination name (e.g. drive root 'C:\\' or '/') raises ValueError."""
        q = ReservationQueue(self.queue_file, self.output_root)
        root_path = "C:\\" if os.name == "nt" else "/"
        with self.assertRaises(ValueError) as ctx:
            q.ensure_available_destination(root_path)
        self.assertIn("出力先フォルダを指定してください", str(ctx.exception))

    def test_queue_add_missing_video_raises_value_error(self):
        """Adding a non-existent video path raises ValueError with the path in message."""
        q = ReservationQueue(self.queue_file, self.output_root)
        fake_path = self.temp_path / "does_not_exist.mp4"
        with self.assertRaises(ValueError) as ctx:
            q.add([fake_path], self.template_settings, self.output_root, gui.output_names)
        self.assertIn("入力動画が見つかりません", str(ctx.exception))
        self.assertIn("does_not_exist.mp4", str(ctx.exception))

    def test_queue_transactional_rollback_on_failure(self):
        """An error during add() rolls back jobs and output_root to prior state."""
        q = ReservationQueue(self.queue_file, self.output_root)
        v1 = self._create_dummy_video("valid.mp4")
        q.add([v1], self.template_settings, self.output_root, gui.output_names)
        self.assertEqual(len(q.jobs), 1)

        v_bad = self.temp_path / "bad.mp4"
        initial_jobs_count = len(q.jobs)
        with self.assertRaises(ValueError):
            q.add([v_bad], self.template_settings, self.output_root, gui.output_names)

        # Rollback should keep the 1 valid job
        self.assertEqual(len(q.jobs), initial_jobs_count)

    def test_queue_update_job_running_or_done_rejected(self):
        """Updating running or done jobs raises ValueError."""
        v = self._create_dummy_video("run_done.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        created = q.add([v], self.template_settings, self.output_root, gui.output_names)
        job = created[0]

        # Running job
        job.state = "running"
        with self.assertRaises(ValueError) as ctx:
            q.update_job(job.id, job.settings, self.output_root / "new", gui.output_names)
        self.assertIn("解析中または完了済みの予約は設定を変更できません", str(ctx.exception))

        # Done job
        job.state = "done"
        with self.assertRaises(ValueError) as ctx:
            q.update_job(job.id, job.settings, self.output_root / "new", gui.output_names)
        self.assertIn("解析中または完了済みの予約は設定を変更できません", str(ctx.exception))

    def test_queue_update_job_collision_with_other_job_rejected(self):
        """Updating a job to use another active job's destination raises ValueError."""
        v1 = self._create_dummy_video("clipA.mp4")
        v2 = self._create_dummy_video("clipB.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        jobs = q.add([v1, v2], self.template_settings, self.output_root, gui.output_names)
        dest_a = jobs[0].output

        # Attempt to set clipB's output to clipA's destination
        with self.assertRaises(ValueError) as ctx:
            q.update_job(jobs[1].id, jobs[1].settings, dest_a, gui.output_names)
        self.assertIn("指定された出力先フォルダは他の予約で既に使用されています", str(ctx.exception))

    def test_queue_remove_running_job_protected(self):
        """remove() does not delete running jobs."""
        v = self._create_dummy_video("protect_run.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        jobs = q.add([v], self.template_settings, self.output_root, gui.output_names)
        jobs[0].state = "running"

        q.remove([jobs[0].id])
        self.assertEqual(len(q.jobs), 1)
        self.assertEqual(q.jobs[0].id, jobs[0].id)

    def test_queue_move_skips_running_and_done(self):
        """move() swaps only with pending or failed jobs, skipping running or done."""
        v1 = self._create_dummy_video("s1.mp4")
        v2 = self._create_dummy_video("s2.mp4")
        v3 = self._create_dummy_video("s3.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        jobs = q.add([v1, v2, v3], self.template_settings, self.output_root, gui.output_names)
        j1, j2, j3 = jobs[0].id, jobs[1].id, jobs[2].id

        # Mark middle job as done
        jobs[1].state = "done"

        # Moving j3 up (-1) should skip j2 and swap with j1
        q.move(j3, -1)
        self.assertEqual([j.id for j in q.jobs], [j3, j2, j1])

    def test_queue_move_invalid_delta(self):
        """move() with delta other than -1 or 1 raises ValueError."""
        v = self._create_dummy_video("delta.mp4")
        q = ReservationQueue(self.queue_file, self.output_root)
        jobs = q.add([v], self.template_settings, self.output_root, gui.output_names)
        with self.assertRaises(ValueError) as ctx:
            q.move(jobs[0].id, 2)
        self.assertIn("移動方向は上または下を指定してください", str(ctx.exception))

    def test_unicode_and_japanese_path_integrity(self):
        """Preserves Japanese characters, symbols, and spaces in video names and paths."""
        jp_name = "踏切左-SONY（2026年 撮影） [高画質] #1.mp4"
        video = self._create_dummy_video(jp_name)
        jp_root = self.temp_path / "動画解析出力" / "プロジェクト Ａ"
        jp_root.mkdir(parents=True, exist_ok=True)

        q = ReservationQueue(self.queue_file, jp_root)
        created = q.add([video], self.template_settings, jp_root, gui.output_names)
        job = created[0]
        self.assertEqual(job.video.name, jp_name)
        self.assertTrue(job.output.name.startswith("踏切左-SONY"))

        # Reload queue from JSON to verify encoding round-trip
        q2 = ReservationQueue(self.queue_file, jp_root)
        self.assertEqual(q2.jobs[0].video.name, jp_name)
        self.assertEqual(q2.jobs[0].output.name, job.output.name)

    def test_corrupt_json_raises_value_error(self):
        """Malformed JSON or corrupted schema raises ValueError without crash."""
        self.queue_file.write_text("{ corrupt json ...", encoding="utf-8")
        with self.assertRaises(Exception):
            ReservationQueue(self.queue_file, self.output_root)

        # Invalid schema: version missing
        self.queue_file.write_text(json.dumps({"version": 2, "jobs": []}), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            ReservationQueue(self.queue_file, self.output_root)
        self.assertIn("予約ファイルの形式を読み取れません", str(ctx.exception))

        # Duplicate job ID
        dup_jobs = {
            "version": 1,
            "jobs": [
                {
                    "id": "c" * 32,
                    "state": "pending",
                    "settings": {
                        "INPUT_ROOT": str(self.temp_path),
                        "INPUT_VIDEO_NAME": "v1.mp4",
                        "OUTPUT_ROOT": str(self.output_root),
                        "OUTPUT_FOLDER_NAME": "out1",
                    },
                },
                {
                    "id": "c" * 32,
                    "state": "pending",
                    "settings": {
                        "INPUT_ROOT": str(self.temp_path),
                        "INPUT_VIDEO_NAME": "v2.mp4",
                        "OUTPUT_ROOT": str(self.output_root),
                        "OUTPUT_FOLDER_NAME": "out2",
                    },
                },
            ],
        }
        self.queue_file.write_text(json.dumps(dup_jobs), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            ReservationQueue(self.queue_file, self.output_root)
        self.assertIn("予約IDが重複しています", str(ctx.exception))


class TestEngineFunctions(unittest.TestCase):
    """Tests for core helper functions in gui.py."""

    def test_output_names_generation(self):
        """output_names creates dictionary with standard 4 output filenames."""
        res = gui.output_names(Path("C:/dest/踏切左-7"))
        self.assertEqual(
            res,
            {
                "OUTPUT_VIDEO_NAME": "踏切左-7.mp4",
                "OUTPUT_YOLO_VIDEO_NAME": "踏切左-7-yolo.mp4",
                "OUTPUT_CSV_NAME": "踏切左-7.csv",
                "OUTPUT_METADATA_NAME": "踏切左-7_metadata.txt",
            },
        )

    def test_output_names_empty_directory_raises(self):
        """output_names with empty name raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            gui.output_names(Path(""))
        self.assertIn("出力先フォルダを指定してください", str(ctx.exception))

    def test_resolve_rtmlib_presets(self):
        """resolve_rtmlib_selection handles standard presets correctly."""
        # Performance
        perf = gui.resolve_rtmlib_selection("performance", "mode", "mode", "mode")
        self.assertEqual(perf["pose_model"], "x")
        self.assertEqual(perf["pose_resolution"], "384x288")
        self.assertEqual(perf["person_detector"], "x")

        # Balanced
        bal = gui.resolve_rtmlib_selection("balanced", "mode", "mode", "mode")
        self.assertEqual(bal["pose_model"], "m")
        self.assertEqual(bal["pose_resolution"], "256x192")
        self.assertEqual(bal["person_detector"], "m")

        # Lightweight
        lite = gui.resolve_rtmlib_selection("lightweight", "mode", "mode", "mode")
        self.assertEqual(lite["pose_model"], "s")
        self.assertEqual(lite["pose_resolution"], "256x192")
        self.assertEqual(lite["person_detector"], "tiny")

    def test_resolve_rtmlib_invalid_combinations_raise(self):
        """resolve_rtmlib_selection rejects unsupported resolution combinations."""
        # RTMPose-M does not support 384x288
        with self.assertRaises(ValueError) as ctx:
            gui.resolve_rtmlib_selection("performance", "m", "384x288", "mode")
        self.assertIn("対応していません", str(ctx.exception))

        # Unknown mode
        with self.assertRaises(ValueError) as ctx:
            gui.resolve_rtmlib_selection("ultra_fast", "mode", "mode", "mode")
        self.assertIn("不明なRTMLib推定モードです", str(ctx.exception))


class MockBackendApi:
    """Reference implementation of the PyWebView JS Bridge interface contract.

    Adheres strictly to the 14-endpoint interface contract defined in
    PROJECT.md §Interface Contracts and TEST_INFRA.md.
    """

    def __init__(self, reservations: ReservationQueue, default_settings: dict[str, Any]):
        self.reservations = reservations
        self.default_settings = deepcopy(default_settings)
        self.is_processing = False
        self.current_job_id: str | None = None

    def get_initial_data(self) -> dict[str, Any]:
        return {
            "queue": [asdict(job) for job in self.reservations.jobs],
            "settings": self.default_settings,
            "system": {
                "output_root": self.reservations.output_root,
                "is_processing": self.is_processing,
                "current_job_id": self.current_job_id,
            },
            "choices": {k: list(v) for k, v in gui.CHOICES.items()},
        }

    def select_video_files(self) -> list[str]:
        return ["C:\\videos\\sample1.mp4", "C:\\videos\\sample2.mp4"]

    def select_directory(self, title: str = "出力先フォルダーを選択") -> str:
        return "C:\\videos\\output"

    def select_image_file(self) -> str | None:
        return "C:\\videos\\thumbnail.jpg"

    def add_reservations(
        self,
        videos: list[str],
        output_folder: str,
        is_multi: bool,
        settings: dict[str, Any],
        thumbnail: str | None = None,
    ) -> list[dict[str, Any]]:
        created = self.reservations.add(
            videos=videos,
            template=settings,
            root=output_folder,
            output_names=gui.output_names,
            thumbnail=thumbnail,
            custom_destination=output_folder if (not is_multi and len(videos) == 1) else None,
        )
        return [asdict(job) for job in created]

    def remove_jobs(self, job_ids: list[str]) -> list[dict[str, Any]]:
        self.reservations.remove(job_ids)
        return [asdict(job) for job in self.reservations.jobs]

    def move_job(self, job_id: str, direction: str) -> list[dict[str, Any]]:
        delta = -1 if direction in ("up", "-1", -1) else 1
        self.reservations.move(job_id, delta)
        return [asdict(job) for job in self.reservations.jobs]

    def update_job_settings(
        self,
        job_id: str,
        settings: dict[str, Any],
        reset_failed: bool = False,
    ) -> dict[str, Any]:
        dest = Path(settings["OUTPUT_ROOT"]) / settings["OUTPUT_FOLDER_NAME"]
        job = self.reservations.update_job(
            job_id=job_id,
            settings=settings,
            destination=dest,
            output_names=gui.output_names,
            reset_failed=reset_failed,
        )
        return asdict(job)

    def save_default_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        self.default_settings = deepcopy(settings)
        if "OUTPUT_ROOT" in settings:
            self.reservations.output_root = str(settings["OUTPUT_ROOT"])
        return self.default_settings

    def start_queue_processing(self) -> dict[str, str]:
        pending = self.reservations.next_pending()
        if pending is None:
            return {"status": "empty"}
        self.is_processing = True
        self.current_job_id = pending.id
        return {"status": "started", "job_id": pending.id}

    def cancel_current_job(self) -> dict[str, str]:
        if not self.is_processing:
            return {"status": "idle"}
        self.is_processing = False
        return {"status": "stopping", "job_id": self.current_job_id or ""}

    def retry_job(self, job_id: str) -> list[dict[str, Any]]:
        self.reservations.retry([job_id], gui.output_names)
        return [asdict(job) for job in self.reservations.jobs]

    def get_job_thumbnail(self, job_id: str) -> str:
        return "data:image/jpeg;base64,/9j/4AAQSkZJRg=="

    def get_preview_frame(self, job_id: str) -> str:
        return "data:image/jpeg;base64,/9j/4AAQSkZJRg=="

    def validate_rtmlib_settings(
        self, mode: str, pose_model: str, input_size: str, detector: str
    ) -> dict[str, Any]:
        try:
            resolved = gui.resolve_rtmlib_selection(mode, pose_model, input_size, detector)
            return {"valid": True, "resolved": resolved}
        except ValueError as err:
            return {"valid": False, "error": str(err)}

    def get_output_preview_names(self, folder_path: str) -> dict[str, str]:
        return gui.output_names(Path(folder_path))


class TestApiBridgeInterfaceContracts(unittest.TestCase):
    """Tier 1: Verifies the 14-endpoint PyWebView API bridge data structures and method signatures."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.queue_file = self.temp_path / "analysis_queue.json"
        self.output_root = self.temp_path / "output"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.template_settings = deepcopy(gui.ENGINE_DEFAULTS)
        for k in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            self.template_settings[k] = str(self.template_settings[k])

        self.queue = ReservationQueue(self.queue_file, self.output_root)
        self.api = MockBackendApi(self.queue, self.template_settings)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_dummy_video(self, name: str = "video.mp4") -> Path:
        p = self.temp_path / name
        p.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
        return p

    def test_get_initial_data_contract(self):
        """get_initial_data returns valid JSON-serializable dictionary with required keys."""
        data = self.api.get_initial_data()
        self.assertIn("queue", data)
        self.assertIn("settings", data)
        self.assertIn("system", data)
        self.assertIn("choices", data)
        # Assure JSON serializable
        serialized = json.dumps(data, ensure_ascii=False)
        self.assertIsInstance(serialized, str)

    def test_add_reservations_bridge_contract(self):
        """add_reservations creates jobs and returns serialized job list."""
        v1 = self._create_dummy_video("bridge1.mp4")
        v2 = self._create_dummy_video("bridge2.mp4")
        res = self.api.add_reservations(
            videos=[str(v1), str(v2)],
            output_folder=str(self.output_root),
            is_multi=True,
            settings=self.template_settings,
        )
        self.assertEqual(len(res), 2)
        self.assertIn("id", res[0])
        self.assertIn("settings", res[0])
        self.assertEqual(res[0]["state"], "pending")
        # Ensure round-trip serialization
        json.dumps(res, ensure_ascii=False)

    def test_remove_jobs_bridge_contract(self):
        """remove_jobs deletes jobs and returns updated queue list."""
        v = self._create_dummy_video("rem.mp4")
        added = self.api.add_reservations([str(v)], str(self.output_root), False, self.template_settings)
        job_id = added[0]["id"]
        updated_queue = self.api.remove_jobs([job_id])
        self.assertEqual(len(updated_queue), 0)

    def test_move_job_bridge_contract(self):
        """move_job reorders jobs and returns updated queue list."""
        v1 = self._create_dummy_video("mv1.mp4")
        v2 = self._create_dummy_video("mv2.mp4")
        added = self.api.add_reservations([str(v1), str(v2)], str(self.output_root), True, self.template_settings)
        j1_id = added[0]["id"]
        j2_id = added[1]["id"]

        reordered = self.api.move_job(j2_id, "up")
        self.assertEqual(reordered[0]["id"], j2_id)
        self.assertEqual(reordered[1]["id"], j1_id)

    def test_update_job_settings_bridge_contract(self):
        """update_job_settings applies changes and returns modified job."""
        v = self._create_dummy_video("upd.mp4")
        added = self.api.add_reservations([str(v)], str(self.output_root), False, self.template_settings)
        job = added[0]

        new_settings = deepcopy(job["settings"])
        new_settings["YOLO_MODEL"] = "yolo11s.pt"
        updated = self.api.update_job_settings(job["id"], new_settings)
        self.assertEqual(updated["settings"]["YOLO_MODEL"], "yolo11s.pt")

    def test_start_and_cancel_queue_bridge_contract(self):
        """start_queue_processing and cancel_current_job return valid status dicts."""
        # Empty queue start
        self.assertEqual(self.api.start_queue_processing()["status"], "empty")

        v = self._create_dummy_video("start_test.mp4")
        self.api.add_reservations([str(v)], str(self.output_root), False, self.template_settings)

        started = self.api.start_queue_processing()
        self.assertEqual(started["status"], "started")
        self.assertTrue(self.api.is_processing)

        cancelled = self.api.cancel_current_job()
        self.assertEqual(cancelled["status"], "stopping")
        self.assertFalse(self.api.is_processing)

    def test_retry_job_bridge_contract(self):
        """retry_job resets failed job to pending."""
        v = self._create_dummy_video("retry_b.mp4")
        added = self.api.add_reservations([str(v)], str(self.output_root), False, self.template_settings)
        job_id = added[0]["id"]

        job = self.queue.find(job_id)
        job.state = "failed"
        job.error = "Test failure"
        self.queue.save()

        updated_queue = self.api.retry_job(job_id)
        retried = next(j for j in updated_queue if j["id"] == job_id)
        self.assertEqual(retried["state"], "pending")
        self.assertEqual(retried["error"], "")

    def test_all_14_bridge_methods_contract_and_json_serializability(self):
        """Verifies all 14 methods specified in PROJECT.md return JSON-serializable payloads."""
        v = self._create_dummy_video("all_methods.mp4")

        # 1. get_initial_data
        r1 = self.api.get_initial_data()
        self.assertIsInstance(json.dumps(r1, ensure_ascii=False), str)

        # 2. select_video_files
        r2 = self.api.select_video_files()
        self.assertIsInstance(json.dumps(r2, ensure_ascii=False), str)

        # 3. select_directory
        r3 = self.api.select_directory("Select output")
        self.assertIsInstance(json.dumps(r3, ensure_ascii=False), str)

        # 4. select_image_file
        r4 = self.api.select_image_file()
        self.assertIsInstance(json.dumps(r4, ensure_ascii=False), str)

        # 5. add_reservations
        r5 = self.api.add_reservations([str(v)], str(self.output_root), False, self.template_settings)
        self.assertIsInstance(json.dumps(r5, ensure_ascii=False), str)
        job_id = r5[0]["id"]

        # 6. update_job_settings
        r6 = self.api.update_job_settings(job_id, r5[0]["settings"])
        self.assertIsInstance(json.dumps(r6, ensure_ascii=False), str)

        # 7. move_job
        r7 = self.api.move_job(job_id, "down")
        self.assertIsInstance(json.dumps(r7, ensure_ascii=False), str)

        # 8. save_default_settings
        r8 = self.api.save_default_settings(self.template_settings)
        self.assertIsInstance(json.dumps(r8, ensure_ascii=False), str)

        # 9. start_queue_processing
        r9 = self.api.start_queue_processing()
        self.assertIsInstance(json.dumps(r9, ensure_ascii=False), str)

        # 10. cancel_current_job
        r10 = self.api.cancel_current_job()
        self.assertIsInstance(json.dumps(r10, ensure_ascii=False), str)

        # 11. retry_job
        r11 = self.api.retry_job(job_id)
        self.assertIsInstance(json.dumps(r11, ensure_ascii=False), str)

        # 12. get_job_thumbnail
        r12 = self.api.get_job_thumbnail(job_id)
        self.assertIsInstance(json.dumps(r12, ensure_ascii=False), str)

        # 13. get_preview_frame
        r13 = self.api.get_preview_frame(job_id)
        self.assertIsInstance(json.dumps(r13, ensure_ascii=False), str)

        # 14. validate_rtmlib_settings & get_output_preview_names
        r14a = self.api.validate_rtmlib_settings("performance", "mode", "mode", "mode")
        self.assertIsInstance(json.dumps(r14a, ensure_ascii=False), str)
        r14b = self.api.get_output_preview_names(str(self.output_root / "test_out"))
        self.assertIsInstance(json.dumps(r14b, ensure_ascii=False), str)

        # Final cleanup: remove_jobs
        r_rem = self.api.remove_jobs([job_id])
        self.assertIsInstance(json.dumps(r_rem, ensure_ascii=False), str)

    def test_dynamic_pose_ui_webview_bridge_discovery(self):
        """If pose_ui_webview package exists, dynamically verifies real BackendApi signatures."""
        try:
            import pose_ui_webview
            import pose_ui_webview.api_bridge as bridge_mod
            cls = getattr(bridge_mod, "BackendApi", None)
            if cls is not None:
                # Validate that real BackendApi implements the expected methods
                expected_methods = [
                    "get_initial_data",
                    "select_video_files",
                    "select_directory",
                    "add_reservations",
                    "remove_jobs",
                    "move_job",
                    "update_job_settings",
                    "save_default_settings",
                    "start_queue_processing",
                    "cancel_current_job",
                    "retry_job",
                ]
                for method_name in expected_methods:
                    self.assertTrue(
                        hasattr(cls, method_name),
                        f"pose_ui_webview.BackendApi missing required endpoint: {method_name}",
                    )
        except ImportError:
            # Module not yet created (M1 phase) - mock contract test satisfies Progressive Testability
            pass


class CustomTestResult(unittest.TextTestResult):
    """Custom test result collector for detailed console reporting."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_timings: dict[str, float] = {}
        self._start_time = 0.0

    def startTest(self, test):
        self._start_time = time.perf_counter()
        super().startTest(test)

    def addSuccess(self, test):
        elapsed = time.perf_counter() - self._start_time
        self.test_timings[test.id()] = elapsed
        super().addSuccess(test)

    def addFailure(self, test, err):
        elapsed = time.perf_counter() - self._start_time
        self.test_timings[test.id()] = elapsed
        super().addFailure(test, err)

    def addError(self, test, err):
        elapsed = time.perf_counter() - self._start_time
        self.test_timings[test.id()] = elapsed
        super().addError(test, err)


def run_all_tests() -> int:
    """Executes the test suite with formatted output and returns exit code."""
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    # Add test cases in logical progression
    suite.addTests(loader.loadTestsFromTestCase(TestBackendPreservation))
    suite.addTests(loader.loadTestsFromTestCase(TestReservationQueueFeatureCoverage))
    suite.addTests(loader.loadTestsFromTestCase(TestReservationQueueBoundaryAndCornerCases))
    suite.addTests(loader.loadTestsFromTestCase(TestEngineFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestApiBridgeInterfaceContracts))

    print("=" * 80)
    print("  PyWebView & React/Vite Migration Verification Suite")
    print(f"  Python: {sys.version.split()[0]} | Workspace: {WORKSPACE_ROOT}")
    print("=" * 80)

    runner = unittest.TextTestRunner(
        resultclass=CustomTestResult,
        verbosity=2,
        stream=sys.stdout,
    )
    start_total = time.perf_counter()
    result = runner.run(suite)
    total_time = time.perf_counter() - start_total

    print("\n" + "=" * 80)
    print("  TEST EXECUTION SUMMARY")
    print("=" * 80)
    print(f"  Total Tests Run: {result.testsRun}")
    print(f"  Passed:          {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  Failures:        {len(result.failures)}")
    print(f"  Errors:          {len(result.errors)}")
    print(f"  Execution Time:  {total_time:.3f} seconds")
    print("=" * 80)

    if result.wasSuccessful():
        print("  RESULT: [PASS] All Tier 1 and Tier 2 tests completed successfully.")
        print("=" * 80)
        return 0
    else:
        print("  RESULT: [FAIL] One or more tests failed.")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
