"""PyWebView JavaScript-Python API Bridge.

Exposes the 14-endpoint interface contract to the browser UI, coordinating:
- Queue operations (ReservationQueue)
- Parameter sanitization and validation
- Subprocess worker execution and telemetry streaming (AnalysisWorkerManager)
- Native file and directory dialogs
- In-memory thumbnail and frame preview decoding
"""
from __future__ import annotations

import base64
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Callable, Optional, Sequence

import webview

import gui
from pose_estimators import validate_pose_settings as _validate_pose_settings
from pose_estimators.factory import normalize_pose_engine
from reservation_queue import Reservation, ReservationQueue, set_output, write_json
from .worker_manager import AnalysisWorkerManager

logger = logging.getLogger(__name__)

# Keys belonging strictly to an individual reservation job, never persisted as global defaults
JOB_SCOPED_SETTING_KEYS: frozenset[str] = frozenset({
    "INPUT_ROOT",
    "INPUT_VIDEO_NAME",
    "THUMBNAIL_ROOT",
    "THUMBNAIL_IMAGE_NAME",
    "OUTPUT_FOLDER_NAME",
    "OUTPUT_VIDEO_NAME",
    "OUTPUT_CROP_VIDEO_NAME",
    "OUTPUT_CROP_SKELETON_VIDEO_NAME",
    "OUTPUT_CSV_NAME",
    "OUTPUT_METADATA_NAME",
    "OUTPUT_METADATA_JSON_NAME",
    "OUTPUT_NPZ_NAME",
})

# Keys that must never be overwritten via update_job_settings() payload dict
IMMUTABLE_JOB_SETTING_KEYS: frozenset[str] = frozenset({
    "INPUT_ROOT",
    "INPUT_VIDEO_NAME",
    "OUTPUT_DIRECTORY",
    "OUTPUT_ROOT",
    "OUTPUT_FOLDER_NAME",
    "OUTPUT_VIDEO_NAME",
    "OUTPUT_CROP_VIDEO_NAME",
    "OUTPUT_CROP_SKELETON_VIDEO_NAME",
    "OUTPUT_CSV_NAME",
    "OUTPUT_METADATA_NAME",
    "OUTPUT_METADATA_JSON_NAME",
    "OUTPUT_NPZ_NAME",
})


def serialize_reservation(
    job: Reservation | dict[str, Any],
    thumbnail: str = "",
    thumbnail_info: str = "",
) -> dict[str, Any]:
    """Converts a Reservation dataclass (or dict) into a JSON-serializable dictionary for JavaScript."""
    if isinstance(job, dict):
        settings = deepcopy(job.get("settings", {}))
        job_id = job.get("id", "")
        state = job.get("state", "pending")
        error = job.get("error", "")
        created_at = job.get("created_at", "")
        v_root = settings.get("INPUT_ROOT", "")
        v_name = settings.get("INPUT_VIDEO_NAME", "")
        o_root = settings.get("OUTPUT_ROOT", "")
        o_name = settings.get("OUTPUT_FOLDER_NAME", "")
        video_path = str(Path(v_root) / v_name) if v_root and v_name else ""
        video_name = v_name
        output_path = str(Path(o_root) / o_name) if o_root and o_name else ""
        output_folder = o_name
    else:
        settings = deepcopy(job.settings)
        job_id = job.id
        state = job.state
        error = job.error or ""
        created_at = job.created_at
        video_path = str(job.video)
        video_name = job.video.name
        output_path = str(job.output)
        output_folder = job.output.name

    settings = gui.normalize_legacy_rtmlib_settings(settings)

    for pk in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
        if pk in settings:
            settings[pk] = str(settings[pk])

    return {
        "id": job_id,
        "state": state,
        "error": error,
        "created_at": created_at,
        "video_path": video_path,
        "video_name": video_name,
        "output_path": output_path,
        "output_folder": output_folder,
        "thumbnail": thumbnail,
        "thumbnail_info": thumbnail_info,
        "settings": settings,
        "summary": gui.build_job_summary(settings),
    }


class BackendApi:
    """Sole bidirectional gateway between the Edge WebView2 React UI and Python desktop backend."""

    def __init__(
        self,
        base_dir_or_reservations: Any = None,
        settings_or_reservations: Any = None,
        base_dir: Path | str | None = None,
        settings_file: Path | str | None = None,
        reservations: Optional[ReservationQueue] = None,
        worker_manager: Optional[AnalysisWorkerManager] = None,
        engine_defaults: dict[str, Any] | None = None,
        choices: dict[str, Any] | None = None,
        bool_keys: set[str] | None = None,
        int_keys: set[str] | None = None,
        float_keys: set[str] | None = None,
        resolve_rtmlib_fn: Optional[Callable] = None,
        output_names_fn: Optional[Callable] = None,
        thumbnail_provider: Any = None,
    ) -> None:
        self._lock = threading.RLock()

        # Flexible argument detection supporting positional MockBackendApi(queue, template_settings)
        if isinstance(base_dir_or_reservations, ReservationQueue):
            reservations = base_dir_or_reservations
            if isinstance(settings_or_reservations, dict):
                engine_defaults = deepcopy(settings_or_reservations)
        elif isinstance(base_dir_or_reservations, (str, Path)):
            base_dir = Path(base_dir_or_reservations)

        self.base_dir = (
            Path(base_dir).resolve()
            if base_dir
            else Path.cwd().resolve()
        )
        self.settings_file = (
            Path(settings_file).resolve()
            if settings_file
            else (self.base_dir / "gui_settings.json")
        )
        self.queue_file = self.base_dir / "analysis_queue.json"

        # Engine defaults & choice specifications
        raw_defaults = engine_defaults if engine_defaults is not None else getattr(gui, "ENGINE_DEFAULTS", {})
        self.engine_defaults = deepcopy(raw_defaults)
        for pk in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            if pk in self.engine_defaults:
                self.engine_defaults[pk] = str(self.engine_defaults[pk])

        self.choices = choices if choices is not None else deepcopy(getattr(gui, "CHOICES", {}))
        self.bool_keys = set(bool_keys) if bool_keys is not None else set(getattr(gui, "BOOL_KEYS", set()))
        self.int_keys = set(int_keys) if int_keys is not None else set(getattr(gui, "INT_KEYS", set()))
        self.float_keys = set(float_keys) if float_keys is not None else set(getattr(gui, "FLOAT_KEYS", set()))
        self._resolve_rtmlib_fn = resolve_rtmlib_fn or getattr(gui, "resolve_rtmlib_selection", None)
        self._output_names_fn = output_names_fn or getattr(gui, "output_names", None)

        # Load persisted settings or fallback
        self.default_settings = self._load_default_settings()

        # ReservationQueue initialization
        if reservations is not None:
            self.reservations = reservations
        else:
            default_out = str(self.default_settings.get("OUTPUT_ROOT", self.base_dir / "output"))
            self.reservations = ReservationQueue(self.queue_file, default_out)

        # Worker Manager & Window hooks
        self._window: Optional[webview.Window] = None
        self.thumbnail_provider = thumbnail_provider
        self.worker_manager = worker_manager
        if self.worker_manager is None:
            self.worker_manager = AnalysisWorkerManager(
                base_dir=self.base_dir,
                reservations=self.reservations,
                output_names_fn=self._output_names_fn,
                window_provider=lambda: self._window,
                job_serializer=self.serialize_job,
            )
        elif getattr(self.worker_manager, "_job_serializer", None) is None:
            self.worker_manager._job_serializer = self.serialize_job

        # Fallback state flags if worker_manager not used directly
        self._is_processing = False
        self._current_job_id: Optional[str] = None

        # In-memory thumbnail caches & allowed video path whitelist
        self._thumbnails: dict[str, str] = {}
        self._thumb_info: dict[str, str] = {}
        self._allowed_video_paths: set[str] = set()
        self._last_video_dir: str = ""
        self._last_output_dir: str = ""

    @staticmethod
    def _normalize_video_key(path: str | Path) -> str:
        try:
            return os.path.normcase(str(Path(path).expanduser().resolve()))
        except Exception:
            return os.path.normcase(str(path))

    def register_allowed_videos(self, paths: Sequence[str | Path]) -> None:
        """Adds user-selected or dropped video paths to the preview whitelist."""
        if not paths:
            return
        with self._lock:
            for p in paths:
                if p:
                    self._allowed_video_paths.add(self._normalize_video_key(p))

    def set_window(self, window: webview.Window) -> None:
        """Attaches the PyWebView Window instance to the bridge."""
        self._window = window
        if self.worker_manager:
            self.worker_manager.set_window_provider(lambda: self._window)

    @property
    def is_processing(self) -> bool:
        if self.worker_manager:
            return self.worker_manager.is_running
        return self._is_processing

    @is_processing.setter
    def is_processing(self, val: bool) -> None:
        self._is_processing = val

    @property
    def queue_active(self) -> bool:
        return self.is_processing

    @property
    def current_job_id(self) -> Optional[str]:
        if self.worker_manager:
            return self.worker_manager.current_job_id
        return self._current_job_id

    @current_job_id.setter
    def current_job_id(self, val: Optional[str]) -> None:
        self._current_job_id = val

    # ---- 1. Initial Handshake Endpoint ---------------------------------------

    def get_initial_data(self) -> dict[str, Any]:
        """Handshake payload returning current queue, settings, choices, and system metadata."""
        with self._lock:
            queue_data = [self.serialize_job(job) for job in self.reservations.snapshot_jobs()]
            choices_data = {k: list(v) for k, v in self.choices.items()}
            labels_data = deepcopy(getattr(gui, "LABELS", {}))
            groups_data = [
                {"title": title, "keys": list(keys)}
                for title, keys in getattr(gui, "GROUPS", [])
            ]
            return {
                "settings": {
                    k: v
                    for k, v in deepcopy(self.default_settings).items()
                    if k not in JOB_SCOPED_SETTING_KEYS and k != "OUTPUT_DIRECTORY"
                },
                "queue": queue_data,
                "system": {
                    "output_root": str(self.reservations.output_root),
                    "is_processing": self.is_processing,
                    "current_job_id": self.current_job_id,
                    "queue_active": self.is_processing,
                    "active_job_id": self.current_job_id,
                    "choices": choices_data,
                    "labels": labels_data,
                    "groups": groups_data,
                },
                "choices": choices_data,
            }

    # ---- 2-4. Native Windows Dialog Endpoints --------------------------------

    def select_video_files(self) -> list[str]:
        """Opens native multi-file video selection dialog and returns resolved paths."""
        if self._window is None:
            return []
        dialog_type = getattr(webview.FileDialog, "OPEN", webview.OPEN_DIALOG)
        file_types = (
            "Video Files (*.mp4;*.mov;*.avi;*.mkv;*.m4v;*.wmv;*.webm)",
            "All Files (*.*)",
        )
        initial_dir = (
            self._last_video_dir
            if (self._last_video_dir and Path(self._last_video_dir).exists())
            else ""
        )
        try:
            res = self._window.create_file_dialog(
                dialog_type=dialog_type,
                directory=initial_dir,
                allow_multiple=True,
                file_types=file_types,
            )
            if not res:
                return []
            resolved = [str(Path(p).resolve()) for p in res]
            if resolved:
                self._last_video_dir = str(Path(resolved[0]).parent)
                self.register_allowed_videos(resolved)
            return resolved
        except Exception as exc:
            logger.warning("select_video_files dialog error: %s", exc)
            return []

    def select_directory(self, title: str = "出力先フォルダーを選択") -> str:
        """Opens native folder selection dialog and returns resolved directory path."""
        if self._window is None:
            return ""
        dialog_type = getattr(webview.FileDialog, "FOLDER", webview.FOLDER_DIALOG)
        initial_dir = (
            self._last_output_dir
            if (self._last_output_dir and Path(self._last_output_dir).exists())
            else ""
        )
        try:
            res = self._window.create_file_dialog(
                dialog_type=dialog_type,
                directory=initial_dir,
                allow_multiple=False,
            )
            if res and len(res) > 0:
                folder = str(Path(res[0]).resolve())
                self._last_output_dir = folder
                return folder
            return ""
        except Exception as exc:
            logger.warning("select_directory dialog error: %s", exc)
            return ""

    def select_image_file(self, title: str = "撮影日時取得用のサムネイル画像を選択") -> str | None:
        """Opens native single image file selection dialog (e.g. SONY THMBNL)."""
        if self._window is None:
            return None
        dialog_type = getattr(webview.FileDialog, "OPEN", webview.OPEN_DIALOG)
        file_types = (
            "Image Files (*.jpg;*.jpeg;*.png;*.thm;*.bmp)",
            "All Files (*.*)",
        )
        initial_dir = (
            self._last_video_dir
            if (self._last_video_dir and Path(self._last_video_dir).exists())
            else ""
        )
        try:
            res = self._window.create_file_dialog(
                dialog_type=dialog_type,
                directory=initial_dir,
                allow_multiple=False,
                file_types=file_types,
            )
            if res and len(res) > 0:
                return str(Path(res[0]).resolve())
            return None
        except Exception as exc:
            logger.warning("select_image_file dialog error: %s", exc)
            return None

    # ---- 5-8. Reservation Queue Mutation Endpoints ---------------------------

    def add_reservations(
        self,
        videos: list[str],
        output_folder: str | None = None,
        is_multi: bool = False,
        settings: dict[str, Any] | None = None,
        thumbnail: str | None = None,
    ) -> list[dict[str, Any]]:
        """Registers video files into the ReservationQueue and returns serialized created jobs."""
        if not videos:
            raise ValueError("動画ファイルを選択してください。")

        with self._lock:
            template = deepcopy(self.default_settings)
            if settings:
                template.update(self.sanitize_settings(settings))

            # Destination resolution
            if not is_multi and len(videos) == 1 and output_folder:
                custom_dest: Any = Path(output_folder)
                parent_root: Any = self.reservations.output_root
            else:
                custom_dest = None
                parent_root = output_folder or self.reservations.output_root

            created = self.reservations.add(
                videos=[Path(v) for v in videos],
                template=template,
                root=parent_root,
                output_names=self._output_names_fn,
                thumbnail=Path(thumbnail) if thumbnail else None,
                custom_destination=custom_dest,
            )

            for job in created:
                self._allowed_video_paths.add(self._normalize_video_key(job.video))

            # Trigger background thumbnail generation
            if self.thumbnail_provider and hasattr(self.thumbnail_provider, "enqueue_jobs"):
                self.thumbnail_provider.enqueue_jobs(created)

            result = [self.serialize_job(job) for job in created]

        self._push_queue_update()
        return result

    def remove_jobs(self, job_ids: list[str]) -> list[dict[str, Any]]:
        """Removes non-running jobs by ID and returns the updated queue."""
        with self._lock:
            to_remove = []
            for jid in job_ids:
                job = self.reservations.find(jid)
                if job and job.state != "running":
                    to_remove.append(jid)

            self.reservations.remove(to_remove)
            if self.thumbnail_provider and hasattr(self.thumbnail_provider, "prune"):
                self.thumbnail_provider.prune({j.id for j in self.reservations.snapshot_jobs()})
            for jid in to_remove:
                self._thumbnails.pop(jid, None)
                self._thumb_info.pop(jid, None)

            result = [self.serialize_job(j) for j in self.reservations.snapshot_jobs()]

        self._push_queue_update()
        return result

    def move_job(self, job_id: str, direction: str | int) -> list[dict[str, Any]]:
        """Moves a job up or down in the pending queue and returns updated list."""
        with self._lock:
            if isinstance(direction, int):
                delta = direction
            elif str(direction).lower() in ("up", "-1"):
                delta = -1
            elif str(direction).lower() in ("down", "1"):
                delta = 1
            else:
                raise ValueError("移動方向は上または下を指定してください")

            self.reservations.move(job_id, delta)
            result = [self.serialize_job(j) for j in self.reservations.snapshot_jobs()]

        self._push_queue_update()
        return result

    def reorder_job(self, job_id: str, target_index: int) -> list[dict[str, Any]]:
        """Moves a pending/failed job directly to target_index in the visible queue."""
        with self._lock:
            self.reservations.reorder_job(job_id, target_index)
            result = [self.serialize_job(j) for j in self.reservations.snapshot_jobs()]

        self._push_queue_update()
        return result

    def update_job_settings(
        self,
        job_id: str,
        settings: dict[str, Any],
        reset_failed: bool = False,
        destination: str | None = None,
    ) -> dict[str, Any]:
        """Updates parameters or destination for a pending/failed reservation."""
        with self._lock:
            job = self.reservations.find(job_id)
            if job is None:
                raise ValueError(f"予約が見つかりません: {job_id}")

            # Destination determination
            if destination:
                dest = Path(destination)
            elif settings.get("OUTPUT_DIRECTORY"):
                dest = Path(settings["OUTPUT_DIRECTORY"])
            elif settings.get("OUTPUT_ROOT") and settings.get("OUTPUT_FOLDER_NAME"):
                dest = Path(settings["OUTPUT_ROOT"]) / str(settings["OUTPUT_FOLDER_NAME"])
            else:
                dest = job.output

            sanitized = self.sanitize_settings(settings)
            for protected_key in IMMUTABLE_JOB_SETTING_KEYS:
                sanitized.pop(protected_key, None)

            merged = deepcopy(job.settings)
            for non_engine_key in ("OUTPUT_DIRECTORY", "OUTPUT_ROOT", "OUTPUT_FOLDER_NAME"):
                merged.pop(non_engine_key, None)
            merged.update(sanitized)
            merged = gui.normalize_legacy_rtmlib_settings(merged)

            # Validate active pose engine settings
            self._validate_active_pose_engine(merged)

            updated = self.reservations.update_job(
                job_id=job_id,
                settings=merged,
                destination=dest,
                output_names=self._output_names_fn,
                reset_failed=reset_failed,
            )
            result = self.serialize_job(updated)

        self._push_queue_update()
        return result

    def retry_job(self, job_id: str) -> list[dict[str, Any]]:
        """Resets failed job to pending and returns the updated queue."""
        with self._lock:
            self.reservations.retry([job_id], self._output_names_fn)
            result = [self.serialize_job(j) for j in self.reservations.snapshot_jobs()]

        self._push_queue_update()
        return result

    # ---- 9. Settings Persistence Endpoint ------------------------------------

    def save_default_settings(
        self, settings: dict[str, Any], default_root: str | None = None
    ) -> dict[str, Any]:
        """Validates, sanitizes, and persists defaults to gui_settings.json."""
        with self._lock:
            root = default_root or (settings.get("OUTPUT_ROOT") if isinstance(settings, dict) else None) or self.reservations.output_root
            resolved_root = str(Path(root).expanduser().resolve())

            sanitized = self.sanitize_settings(settings)
            for job_key in JOB_SCOPED_SETTING_KEYS:
                sanitized.pop(job_key, None)
            sanitized.pop("OUTPUT_DIRECTORY", None)
            sanitized["OUTPUT_ROOT"] = resolved_root

            merged_defaults = gui.normalize_legacy_rtmlib_settings({**self.default_settings, **sanitized})
            self._validate_active_pose_engine(merged_defaults)

            self.default_settings = merged_defaults
            for job_key in JOB_SCOPED_SETTING_KEYS:
                self.default_settings.pop(job_key, None)
            self.default_settings.pop("OUTPUT_DIRECTORY", None)
            write_json(self.settings_file, self.default_settings)

            self.reservations.set_output_root(resolved_root)

            return deepcopy(self.default_settings)

    # ---- 10-11. Queue Execution Control Endpoints ----------------------------

    def start_queue_processing(self) -> dict[str, Any]:
        """Begins processing pending jobs sequentially."""
        with self._lock:
            pending = self.reservations.next_pending()
            if pending is None:
                return {"status": "empty"}

            if self.worker_manager:
                return self.worker_manager.start_queue()

            self._is_processing = True
            self._current_job_id = pending.id
            return {"status": "started", "job_id": pending.id}

    def cancel_current_job(self) -> dict[str, Any]:
        """Interrupts currently running job and stops queue execution."""
        with self._lock:
            wm = self.worker_manager
            if wm is None:
                if not self.is_processing:
                    return {"status": "idle"}
                self._is_processing = False
                job_id = self._current_job_id or ""
                return {"status": "stopping", "job_id": job_id}
        return wm.cancel_current_job()

    # ---- 12-14. Thumbnail & Preview Decoders ---------------------------------

    def get_job_thumbnail(self, job_id: str) -> str:
        """Returns base64 JPEG data URI for specified job ID (extracts outside lock)."""
        video_path: Optional[str] = None
        with self._lock:
            if self.thumbnail_provider and hasattr(self.thumbnail_provider, "get_thumbnail"):
                thumb = self.thumbnail_provider.get_thumbnail(job_id)
                if thumb:
                    return thumb
            if job_id in self._thumbnails:
                return self._thumbnails[job_id]

            job = self.reservations.find(job_id)
            if job and job.video.is_file():
                video_path = str(job.video)

        if not video_path:
            return ""

        thumb, info = self._extract_thumbnail_sync(video_path)
        if thumb:
            with self._lock:
                self._thumbnails[job_id] = thumb
                self._thumb_info[job_id] = info
        return thumb

    def get_preview_frame(
        self, video_path_or_job_id: str, frame_idx_or_time: int | float = 0
    ) -> str:
        """Extracts high-resolution frame ONLY for whitelisted session/registered videos."""
        if not video_path_or_job_id or not isinstance(video_path_or_job_id, (str, Path)):
            return ""
        video_str = str(video_path_or_job_id)
        target_path: Optional[str] = None

        with self._lock:
            job = self.reservations.find(video_str)
            if job and job.video.is_file():
                target_path = str(job.video)
            else:
                candidate_key = self._normalize_video_key(video_str)
                registered_keys = {
                    self._normalize_video_key(j.video)
                    for j in self.reservations.snapshot_jobs()
                }
                if candidate_key in self._allowed_video_paths or candidate_key in registered_keys:
                    target_path = video_str

        if not target_path or not os.path.exists(target_path):
            return ""

        return self._extract_frame_sync(target_path, frame_idx_or_time)

    # ---- 15-16. Helper Utilities ---------------------------------------------

    def validate_rtmlib_settings(
        self, pose_model: str, input_size: str
    ) -> dict[str, Any]:
        """Validates RTMLib combination without modifying settings."""
        if self._resolve_rtmlib_fn is None:
            return {"valid": True, "resolved": {}}
        try:
            resolved = self._resolve_rtmlib_fn(pose_model, input_size)
            return {"valid": True, "resolved": resolved}
        except ValueError as err:
            return {"valid": False, "error": str(err)}

    def validate_pose_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Validates active pose engine combination without modifying settings."""
        try:
            resolved = self._validate_active_pose_engine(settings)
            return {"valid": True, "resolved": resolved}
        except ValueError as err:
            return {"valid": False, "error": str(err)}

    def _validate_active_pose_engine(self, settings: dict[str, Any]) -> dict[str, Any]:
        engine = normalize_pose_engine(settings.get("POSE_ENGINE", "rtmpose"))
        if engine == "rtmpose":
            pose_model = settings.get("RTMLIB_POSE_MODEL", "x")
            input_size = settings.get("RTMLIB_POSE_INPUT_SIZE", "384x288")
            if self._resolve_rtmlib_fn is not None:
                return self._resolve_rtmlib_fn(pose_model, input_size)
        return _validate_pose_settings(settings)

    def get_output_preview_names(self, folder_path: str) -> dict[str, str]:
        """Returns the 7 standard output filenames for destination folder preview."""
        if not folder_path or not isinstance(folder_path, (str, Path)):
            return {}
        p = Path(folder_path)
        if not p.name:
            return {}
        try:
            if self._output_names_fn is None:
                return {
                    "OUTPUT_VIDEO_NAME": f"{p.name}.mp4",
                    "OUTPUT_CROP_VIDEO_NAME": f"{p.name}-crop.mp4",
                    "OUTPUT_CROP_SKELETON_VIDEO_NAME": f"{p.name}-crop-skeleton.mp4",
                    "OUTPUT_CSV_NAME": f"{p.name}.csv",
                    "OUTPUT_METADATA_NAME": f"{p.name}_metadata.txt",
                    "OUTPUT_METADATA_JSON_NAME": f"{p.name}_metadata.json",
                    "OUTPUT_NPZ_NAME": f"{p.name}.npz",
                }
            return self._output_names_fn(p)
        except (ValueError, OSError):
            return {}

    # ---- Internal Sanitization & Serialization Helpers -----------------------

    def sanitize_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Enforces type coercion on parameter dictionary from frontend."""
        sanitized = deepcopy(settings)

        # Boolean keys
        for k in self.bool_keys:
            if k in sanitized:
                val = sanitized[k]
                if isinstance(val, str):
                    sanitized[k] = val.strip().lower() in ("true", "1", "yes")
                else:
                    sanitized[k] = bool(val)

        # Integer keys
        for k in self.int_keys:
            if k in sanitized and sanitized[k] is not None and sanitized[k] != "":
                try:
                    sanitized[k] = int(sanitized[k])
                except (ValueError, TypeError):
                    pass

        # Clamp batch size settings
        max_batch = int(getattr(gui, "MAX_BATCH_SIZE", 512))
        for batch_key in ("YOLO_BATCH_SIZE", "RTMPOSE_BATCH_SIZE"):
            if batch_key in sanitized:
                try:
                    val = int(float(sanitized[batch_key]))
                except (ValueError, TypeError):
                    val = 1
                sanitized[batch_key] = max(1, min(max_batch, val))

        if "VITPOSE_BATCH_SIZE" in sanitized:
            try:
                val = int(float(sanitized["VITPOSE_BATCH_SIZE"]))
            except (ValueError, TypeError):
                val = 4
            sanitized["VITPOSE_BATCH_SIZE"] = max(1, min(8, val))

        if "POSE_ENGINE" in sanitized:
            sanitized["POSE_ENGINE"] = normalize_pose_engine(sanitized["POSE_ENGINE"])

        if "VITPOSE_MODEL" in sanitized:
            sanitized["VITPOSE_MODEL"] = str(sanitized["VITPOSE_MODEL"] or "h").strip().lower()

        if "VITPOSE_INPUT_SIZE" in sanitized:
            sanitized["VITPOSE_INPUT_SIZE"] = str(sanitized["VITPOSE_INPUT_SIZE"] or "256x192").strip().lower()

        if "VITPOSE_PRECISION" in sanitized:
            prec = str(sanitized["VITPOSE_PRECISION"] or "fp16").strip().lower()
            sanitized["VITPOSE_PRECISION"] = prec if prec in ("fp16", "fp32") else "fp16"

        # Float keys
        for k in self.float_keys:
            if k in sanitized and sanitized[k] is not None and sanitized[k] != "":
                try:
                    sanitized[k] = float(sanitized[k])
                except (ValueError, TypeError):
                    pass

        # Nullable float keys (CAPTURE_FPS: empty/auto -> None, else positive finite float)
        nullable_float_keys = set(getattr(gui, "NULLABLE_FLOAT_KEYS", {"CAPTURE_FPS"}))
        for k in nullable_float_keys:
            if k in sanitized:
                raw_val = sanitized[k]
                if raw_val in (None, "", "None", "null", "auto"):
                    sanitized[k] = None
                else:
                    try:
                        parsed = float(raw_val)
                        import math as _math
                        sanitized[k] = parsed if (_math.isfinite(parsed) and parsed > 0) else None
                    except (ValueError, TypeError):
                        sanitized[k] = None

        # Special handling: YOLO_CLASSES
        if "YOLO_CLASSES" in sanitized:
            classes = sanitized["YOLO_CLASSES"]
            if isinstance(classes, str):
                parts = [p.strip() for p in classes.split(",") if p.strip()]
                sanitized["YOLO_CLASSES"] = [int(p) for p in parts if p.isdigit() and int(p) >= 0]
            elif isinstance(classes, (list, tuple)):
                coerced = []
                for p in classes:
                    try:
                        val = int(p)
                        if val >= 0:
                            coerced.append(val)
                    except (ValueError, TypeError):
                        pass
                sanitized["YOLO_CLASSES"] = coerced

        # Special handling: YOLO_MODEL
        if "YOLO_MODEL" in sanitized:
            ym = str(sanitized["YOLO_MODEL"]).strip()
            if ym in ("n", "s", "m", "l", "x"):
                sanitized["YOLO_MODEL"] = f"yolo11{ym}.pt"
            elif ym.startswith("yolo11") and ym.endswith(".pt"):
                sanitized["YOLO_MODEL"] = ym

        return gui.normalize_legacy_rtmlib_settings(sanitized)

    def serialize_job(self, job: Reservation) -> dict[str, Any]:
        """Serializes a single job with cached thumbnail data."""
        thumb = ""
        info = ""
        if self.thumbnail_provider and hasattr(self.thumbnail_provider, "get_thumbnail"):
            thumb = self.thumbnail_provider.get_thumbnail(job.id)
            info = getattr(self.thumbnail_provider, "get_info", lambda _: "")(job.id)
        if not thumb:
            thumb = self._thumbnails.get(job.id, "")
            info = self._thumb_info.get(job.id, "")
        return serialize_reservation(job, thumbnail=thumb, thumbnail_info=info)

    def _load_default_settings(self) -> dict[str, Any]:
        """Loads global default settings (excluding per-job I/O keys) from JSON or engine defaults."""
        clean_defaults = {
            k: v
            for k, v in deepcopy(self.engine_defaults).items()
            if k not in JOB_SCOPED_SETTING_KEYS and k != "OUTPUT_DIRECTORY"
        }
        if self.settings_file.is_file():
            try:
                data = json.loads(self.settings_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k, v in data.items():
                        if k not in JOB_SCOPED_SETTING_KEYS and k != "OUTPUT_DIRECTORY":
                            clean_defaults[k] = v
                return gui.normalize_legacy_rtmlib_settings(clean_defaults)
            except Exception as exc:
                logger.warning("Could not read settings from %s (%s); using defaults", self.settings_file, exc)
        return gui.normalize_legacy_rtmlib_settings(clean_defaults)

    def _push_queue_update(self) -> None:
        """Pushes queue snapshot update event to webview window outside locks."""
        with self._lock:
            window = self._window
            if window is None:
                return
            jobs_payload = [self.serialize_job(j) for j in self.reservations.snapshot_jobs()]
            active_id = self.current_job_id
            queue_active = self.is_processing
        payload = {
            "jobs": jobs_payload,
            "active_job_id": active_id,
            "queue_active": queue_active,
        }
        escaped_payload = json.dumps(payload, ensure_ascii=False)
        escaped_jobs = json.dumps(jobs_payload, ensure_ascii=False)
        js = (
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
        try:
            window.evaluate_js(js)
        except Exception:
            pass

    def shutdown(self) -> None:
        """Gracefully halts worker manager and thumbnail providers."""
        if self.worker_manager:
            self.worker_manager.shutdown()
        if self.thumbnail_provider and hasattr(self.thumbnail_provider, "stop"):
            self.thumbnail_provider.stop()

    def _extract_thumbnail_sync(self, video_path: str) -> tuple[str, str]:
        """Extracts frame 0 synchronously as base64 JPEG data URI."""
        if not os.path.exists(video_path):
            return "", ""
        try:
            import cv2
            cap = cv2.VideoCapture(str(video_path))
            try:
                ok, frame = cap.read()
                if not ok or frame is None:
                    return "", ""
                h, w = frame.shape[:2]
                scale = min(640 / max(1, w), 360 / max(1, h), 1.0)
                target_w = max(1, int(w * scale))
                target_h = max(1, int(h * scale))
                resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if not ok:
                    return "", f"{w}×{h} px"
                b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                return f"data:image/jpeg;base64,{b64}", f"{w}×{h} px"
            finally:
                cap.release()
        except Exception:
            return "", ""

    def _extract_frame_sync(self, video_path: str, frame_idx_or_time: int | float = 0) -> str:
        """Extracts single frame at specified frame index/timestamp as base64 JPEG."""
        if not os.path.exists(video_path):
            return ""
        try:
            import cv2
            cap = cv2.VideoCapture(str(video_path))
            try:
                if isinstance(frame_idx_or_time, float) and frame_idx_or_time > 0:
                    cap.set(cv2.CAP_PROP_POS_MSEC, frame_idx_or_time * 1000.0)
                elif isinstance(frame_idx_or_time, int) and frame_idx_or_time > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx_or_time)

                ok, frame = cap.read()
                if not ok or frame is None:
                    return ""
                h, w = frame.shape[:2]
                scale = min(640 / max(1, w), 360 / max(1, h), 1.0)
                target_w = max(1, int(w * scale))
                target_h = max(1, int(h * scale))
                resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if not ok:
                    return ""
                b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                return f"data:image/jpeg;base64,{b64}"
            finally:
                cap.release()
        except Exception:
            return ""
