"""Main application controller for the 2-pane RTMPose GUI."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk
from PIL import Image

from reservation_queue import ReservationQueue, set_output, write_json
from . import theme as t
from .add_reservation_view import AddReservationView
from .left_monitor import LeftMonitorPane
from .queue_view import QueueListView
from .settings_view import SettingsView


def _create_root() -> ctk.CTk:
    """Create a CustomTkinter root window with optional TkinterDnD2 drag-and-drop support."""
    ctk.set_appearance_mode("light")
    try:
        from tkinterdnd2 import TkinterDnD

        class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                try:
                    self.TkdndVersion = TkinterDnD._require(self)
                except tk.TclError:
                    self.TkdndVersion = None

        return DnDCTk(fg_color=t.BG_WINDOW)
    except Exception:
        return ctk.CTk(fg_color=t.BG_WINDOW)


class PoseApp:
    """Coordinator for LeftMonitorPane + Right Workspace (QueueList / Add / Settings)."""

    def __init__(
        self,
        *,
        base_dir: Path,
        settings_file: Path,
        engine_defaults: dict[str, Any],
        choices: dict[str, tuple[str, ...]],
        bool_keys: set[str],
        int_keys: set[str],
        float_keys: set[str],
        resolve_rtmlib_fn: Callable[[str, str, str, str], dict],
        output_names_fn: Callable[[Path], dict[str, str]],
        root: ctk.CTk | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.settings_file = Path(settings_file)
        self.engine_defaults = deepcopy(engine_defaults)
        self._output_names_fn = output_names_fn
        self._resolve_rtmlib_fn = resolve_rtmlib_fn

        self.root = root if root is not None else _create_root()
        f = t.init_theme(self.root)
        self.root.title("動画姿勢推定 — YOLO + RTMPose")
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = min(1460, max(1240, int(screen_w * 0.92)))
        win_h = min(860, max(760, int(screen_h * 0.86)))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(1200, 720)
        try:
            self.root.configure(fg_color=t.BG_WINDOW)
        except tk.TclError:
            self.root.configure(bg=t.BG_WINDOW)

        # Load persisted default settings (gui_settings.json)
        self.default_settings = self._load_default_settings()
        initial_output_root = str(Path(self.default_settings["OUTPUT_ROOT"]).expanduser())

        # Load reservation queue (analysis_queue.json)
        try:
            self.reservations = ReservationQueue(
                self.base_dir / "analysis_queue.json",
                initial_output_root,
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror(
                "予約ファイルを読み込めません",
                f"{exc}\n予約ファイルを上書きせず終了します。",
                parent=self.root,
            )
            self.root.destroy()
            raise

        # Runtime & worker state
        self.event_queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.queue_active = False
        self.current_job_id: str | None = None
        self.process: subprocess.Popen[str] | None = None
        self._queue_stop = threading.Event()
        self._close_after_stop = False
        self._job_tail: list[str] = []
        self._thumbnails: dict[str, Image.Image] = {}
        self._thumb_info: dict[str, str] = {}
        self._preview_started: set[str] = set()
        self._poll_token: str | None = None
        self._next_token: str | None = None
        self._active_view_name: str = "queue"

        # ---- Main 2-Pane Layout (Strict 1 : 3 Lock Across All Views) -------
        self.root.columnconfigure(0, weight=1, uniform="main_split")
        self.root.columnconfigure(1, weight=3, uniform="main_split")
        self.root.rowconfigure(0, weight=1)

        # Left Pane: Always-visible Analysis Monitor (25% width)
        self.left_monitor = LeftMonitorPane(self.root)
        self.left_monitor.configure(width=100, height=100)
        self.left_monitor.grid(row=0, column=0, sticky="nsew", padx=(14, 7), pady=14)
        self.left_monitor.grid_propagate(False)

        # Right Column: Top Control Bar + Switchable Workspace (75% width)
        self.right_shell = ctk.CTkFrame(self.root, fg_color="transparent", width=100, height=100)
        self.right_shell.grid(row=0, column=1, sticky="nsew", padx=(7, 14), pady=14)
        self.right_shell.grid_propagate(False)
        self.right_shell.columnconfigure(0, weight=1)
        self.right_shell.rowconfigure(1, weight=1)

        # Top Action Bar ([解析開始] [解析中断])
        top_bar = ctk.CTkFrame(
            self.right_shell,
            fg_color=t.BG_PANEL,
            corner_radius=t.RADIUS_PANEL,
            border_width=1,
            border_color=t.BORDER,
            height=64,
        )
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top_bar.grid_propagate(False)
        top_bar.columnconfigure(1, weight=1)

        btn_group = ctk.CTkFrame(top_bar, fg_color="transparent")
        btn_group.grid(row=0, column=0, padx=(16, 12), pady=11, sticky="w")

        self.start_btn = t.make_button(
            btn_group,
            "▶  解析開始",
            self.start_queue,
            kind="primary",
            width=168,
            height=42,
            large=True,
        )
        self.start_btn.pack(side="left", padx=(0, 10))

        self.cancel_btn = t.make_button(
            btn_group,
            "■  解析中断",
            self.cancel_queue,
            kind="danger",
            width=148,
            height=42,
            large=True,
        )
        self.cancel_btn.pack(side="left")
        t.set_btn_state(self.cancel_btn, False)

        self.banner_var = tk.StringVar(value="待機中の予約を上から順番に解析します。")
        self.banner_label = tk.Label(
            top_bar,
            textvariable=self.banner_var,
            font=(f.family, 11),
            fg=t.TEXT_SECONDARY,
            bg=t.BG_PANEL,
            anchor="e",
        )
        self.banner_label.grid(row=0, column=1, sticky="ew", padx=(16, 20))

        # Workspace Stack Container (grid_propagate=False keeps 1:3 ratio invariant on view switch)
        self.workspace = ctk.CTkFrame(self.right_shell, fg_color="transparent", width=100, height=100)
        self.workspace.grid(row=1, column=0, sticky="nsew")
        self.workspace.grid_propagate(False)
        self.workspace.columnconfigure(0, weight=1)
        self.workspace.rowconfigure(0, weight=1)

        self.queue_view = QueueListView(
            self.workspace,
            on_open_add=self.show_add_reservation,
            on_open_basic_settings=self.show_basic_settings,
            on_open_job_settings=self.show_job_settings,
            on_delete_jobs=self._delete_jobs,
            on_move_job=self._move_job,
            on_retry_job=self._retry_job,
        )

        self.add_view = AddReservationView(
            self.workspace,
            output_names_fn=output_names_fn,
            on_cancel=self.show_queue_list,
            on_submit=self._submit_new_reservations,
            on_open_basic_settings=self.show_basic_settings,
        )

        self.settings_view = SettingsView(
            self.workspace,
            engine_defaults=self.engine_defaults,
            choices=choices,
            bool_keys=bool_keys,
            int_keys=int_keys,
            float_keys=float_keys,
            resolve_rtmlib_fn=resolve_rtmlib_fn,
            output_names_fn=output_names_fn,
            on_back=self.show_queue_list,
            on_save_default=self._save_basic_settings,
            on_save_job=self._save_job_settings,
            get_current_defaults=lambda: deepcopy(self.default_settings),
        )

        for v in (self.queue_view, self.add_view, self.settings_view):
            v.grid_propagate(False)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self.show_queue_list()
        self._refresh_ui()
        self._start_thumbnail_worker(self.reservations.jobs)
        self._poll_token = self.root.after(120, self._poll_events)

    # ---- Settings Persistence --------------------------------------------

    def _load_default_settings(self) -> dict[str, Any]:
        values = deepcopy(self.engine_defaults)
        # Ensure string representations for path keys in settings dict
        for pk in ("INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"):
            values[pk] = str(values[pk])
        if self.settings_file.exists():
            try:
                saved = json.loads(self.settings_file.read_text(encoding="utf-8"))
                for key, val in saved.items():
                    if key in values:
                        values[key] = str(val) if key in {"INPUT_ROOT", "THUMBNAIL_ROOT", "OUTPUT_ROOT"} else val
            except (OSError, json.JSONDecodeError) as exc:
                messagebox.showwarning(
                    "設定ファイル",
                    f"保存済みの基本設定を読み込めませんでした。初期値で起動します。\n{exc}",
                    parent=self.root,
                )
        return values

    def _persist_default_settings(self) -> None:
        write_json(self.settings_file, self.default_settings)

    # ---- Right-Pane Navigation -------------------------------------------

    def _switch_right_view(self, target_name: str, widget: ctk.CTkFrame) -> None:
        for view in (self.queue_view, self.add_view, self.settings_view):
            if view is not widget:
                view.grid_remove()
        widget.grid(row=0, column=0, sticky="nsew")
        self._active_view_name = target_name

    def show_queue_list(self) -> None:
        self._switch_right_view("queue", self.queue_view)
        self._refresh_ui()

    def show_add_reservation(self, initial_videos: list[Path] | None = None) -> None:
        self.add_view.prepare(
            default_output_root=self.reservations.output_root,
            default_settings=self.default_settings,
            initial_videos=initial_videos,
        )
        self._switch_right_view("add", self.add_view)

    def show_basic_settings(self) -> None:
        self.settings_view.open_for_default(
            current_settings=self.default_settings,
            default_output_root=self.reservations.output_root,
        )
        self._switch_right_view("basic_settings", self.settings_view)

    def show_job_settings(self, job_id: str) -> None:
        job = self.reservations.find(job_id)
        if job is None:
            return
        if job.state == "running":
            messagebox.showinfo(
                "解析中の予約",
                "現在解析中の動画の設定は変更できません。中断してから変更してください。",
                parent=self.root,
            )
            return
        self.settings_view.open_for_job(job)
        self._switch_right_view("job_settings", self.settings_view)

    # ---- Reservation Mutations -------------------------------------------

    def _submit_new_reservations(
        self,
        videos: list[Path],
        parent_root: Path,
        custom_dest: Path | None,
        thumbnail: str | None,
    ) -> bool:
        try:
            if parent_root.exists() and not parent_root.is_dir():
                raise ValueError("出力親フォルダーにはフォルダーパスを指定してください。")
            created = self.reservations.add(
                videos,
                self.default_settings,
                parent_root,
                self._output_names_fn,
                thumbnail=thumbnail,
                custom_destination=custom_dest,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("登録できません", str(exc), parent=self.root)
            return False

        self._start_thumbnail_worker(created)
        self.show_queue_list()
        self.queue_view.select_only([j.id for j in created])
        self.left_monitor.append_log(f"予約を追加しました: {len(created)}件\n")
        self.banner_var.set(f"{len(created)}件の動画を予約リストに追加しました。")
        return True

    def _save_basic_settings(self, params: dict[str, Any], default_root: str) -> None:
        try:
            root_resolved = str(Path(default_root).expanduser().resolve())
            self.default_settings.update(params)
            self.default_settings["OUTPUT_ROOT"] = root_resolved
            self._persist_default_settings()
            self.reservations.output_root = root_resolved
            self._save_reservations_safe()
        except OSError as exc:
            messagebox.showerror("保存エラー", f"基本設定を保存できませんでした。\n{exc}", parent=self.root)
            return

        self.banner_var.set("基本設定を保存しました（今後の新規予約から適用されます）。")
        self.left_monitor.append_log("基本設定を更新しました。\n")
        self.show_queue_list()

    def _save_job_settings(
        self,
        job_id: str,
        merged_settings: dict[str, Any],
        destination: Path,
        reset_failed: bool,
    ) -> None:
        try:
            updated = self.reservations.update_job(
                job_id,
                merged_settings,
                destination,
                self._output_names_fn,
                reset_failed=reset_failed,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("設定を保存できません", str(exc), parent=self.root)
            return

        self.banner_var.set(f"「{updated.video.name}」の個別設定を保存しました。")
        self.left_monitor.append_log(f"予約設定を更新: {updated.video.name} -> 出力先 {updated.output}\n")
        self.show_queue_list()
        self.queue_view.select_only([job_id])

    def _delete_jobs(self, job_ids: list[str]) -> None:
        if not job_ids:
            return
        try:
            self.reservations.remove(job_ids)
        except OSError as exc:
            messagebox.showerror("削除エラー", str(exc), parent=self.root)
            return
        self._refresh_ui()
        self.banner_var.set(f"{len(job_ids)}件の予約をリストから削除しました。")

    def _move_job(self, job_id: str, delta: int) -> None:
        try:
            self.reservations.move(job_id, delta)
        except OSError as exc:
            messagebox.showerror("並べ替えエラー", str(exc), parent=self.root)
            return
        self._refresh_ui()
        self.queue_view.select_only([job_id])

    def _retry_job(self, job_id: str) -> None:
        try:
            self.reservations.retry([job_id], self._output_names_fn)
        except OSError as exc:
            messagebox.showerror("再試行エラー", str(exc), parent=self.root)
            return
        self._refresh_ui()
        self.queue_view.select_only([job_id])
        self.banner_var.set("失敗した予約を待機中に戻しました。「解析開始」で再実行できます。")

    def _save_reservations_safe(self) -> bool:
        try:
            self.reservations.save()
            return True
        except OSError as exc:
            self._queue_stop.set()
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.terminate()
                except OSError:
                    pass
            messagebox.showerror("予約を保存できません", str(exc), parent=self.root)
            return False

    # ---- Thumbnail Worker ------------------------------------------------

    def _start_thumbnail_worker(self, jobs: list[ Any ]) -> None:
        targets = [
            (job.id, str(job.video))
            for job in jobs
            if job.state != "done" and job.id not in self._preview_started
        ]
        if not targets:
            return
        self._preview_started.update(jid for jid, _ in targets)

        def _worker() -> None:
            try:
                import cv2
            except ImportError:
                return
            for job_id, video_path in targets:
                cap = cv2.VideoCapture(video_path)
                try:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        self.event_queue.put(("__PREVIEW__", job_id, None, "プレビュー取得不可"))
                        continue
                    h, w = frame.shape[:2]
                    scale = min(640 / max(1, w), 360 / max(1, h), 1.0)
                    resized = cv2.resize(
                        frame,
                        (max(1, int(w * scale)), max(1, int(h * scale))),
                    )
                    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb)
                    self.event_queue.put(("__PREVIEW__", job_id, pil_img, f"{w}×{h} px"))
                except Exception:
                    self.event_queue.put(("__PREVIEW__", job_id, None, ""))
                finally:
                    cap.release()

        threading.Thread(target=_worker, daemon=True).start()

    # ---- Queue Execution Engine ------------------------------------------

    def start_queue(self) -> None:
        if self.queue_active:
            return
        if self.reservations.next_pending() is None:
            messagebox.showinfo(
                "待機中の予約がありません",
                "「＋ 予約を追加」から動画を追加するか、失敗した動画の「再試行」を押してください。",
                parent=self.root,
            )
            return
        self._queue_stop.clear()
        self.queue_active = True
        t.set_btn_state(self.start_btn, False)
        t.set_btn_state(self.cancel_btn, True)
        self._launch_next_job()

    def cancel_queue(self) -> None:
        if not self.queue_active:
            return
        self._queue_stop.set()
        t.set_btn_state(self.cancel_btn, False)
        self.banner_var.set("解析を中断しています。現在の動画を待機リストの先頭へ戻します…")
        self.left_monitor.show_stopping()
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass

    def _launch_next_job(self) -> None:
        self._next_token = None
        if not self.queue_active or self._queue_stop.is_set():
            self._finish_queue_run()
            return
        job = self.reservations.next_pending()
        if job is None:
            self._finish_queue_run()
            return

        self.current_job_id = job.id
        self.process = None
        self._job_tail = []

        try:
            if not job.video.is_file():
                raise ValueError(f"入力動画が見つかりません: {job.video}")
            if job.output.exists():
                safe_dest = self.reservations.ensure_available_destination(job.output, exclude_id=job.id)
                set_output(job.settings, safe_dest, self._output_names_fn)
            config_path = self.base_dir / ".analysis_jobs" / "configs" / f"{job.id}.json"
            write_json(config_path, job.settings)
            (self.base_dir / ".analysis_jobs" / "logs").mkdir(parents=True, exist_ok=True)
            job.state, job.error = "running", ""
            if not self._save_reservations_safe():
                job.state = "pending"
                self._finish_queue_run()
                return
        except (OSError, ValueError) as exc:
            job.state, job.error = "failed", str(exc)
            self.left_monitor.append_log(f"エラー ({job.video.name}): {exc}\n", tag="error")
            if self._save_reservations_safe():
                self._next_token = self.root.after(0, self._launch_next_job)
            else:
                self._finish_queue_run()
            self._refresh_ui()
            return

        # Move job visually to Left Monitor Pane & remove from Right QueueListView
        self._start_thumbnail_worker([job])
        self.left_monitor.show_running_job(
            video_name=job.video.name,
            output_folder=str(job.output),
            pil_image=self._thumbnails.get(job.id),
            info_text=self._thumb_info.get(job.id, ""),
        )
        self.banner_var.set(f"解析実行中: {job.video.name}")
        self.left_monitor.append_log(
            f"\n--- 解析開始: {job.video.name} ---\n入力: {job.video}\n出力: {job.output}\n",
            tag="heading",
        )
        self._refresh_ui()

        threading.Thread(
            target=self._worker_subprocess_thread,
            args=(job.id, config_path),
            daemon=True,
        ).start()

    def _worker_command(self, config_path: Path) -> list[str]:
        return [
            sys.executable,
            "-u",
            "-X",
            "utf8",
            str(self.base_dir / "gui.py"),
            "--analysis-worker",
            "--config",
            str(config_path),
        ]

    def _worker_subprocess_thread(self, job_id: str, config_path: Path) -> None:
        proc: subprocess.Popen[str] | None = None
        try:
            log_path = self.base_dir / ".analysis_jobs" / "logs" / f"{job_id}.log"
            with log_path.open("w", encoding="utf-8") as log_file:
                if self._queue_stop.is_set():
                    self.event_queue.put(("__JOB_FINISHED__", job_id, -1))
                    return
                proc = subprocess.Popen(
                    self._worker_command(config_path),
                    cwd=self.base_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                self.process = proc
                if self._queue_stop.is_set() and proc.poll() is None:
                    proc.terminate()
                assert proc.stdout is not None
                for line in proc.stdout:
                    log_file.write(line)
                    log_file.flush()
                    self.event_queue.put(("__JOB_LOG__", job_id, line))
                code = proc.wait()
                proc.stdout.close()
                self.event_queue.put(("__JOB_FINISHED__", job_id, code))
        except Exception as exc:
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                except OSError:
                    pass
            self.event_queue.put(("__JOB_LOG__", job_id, f"起動エラー: {exc}\n"))
            self.event_queue.put(("__JOB_FINISHED__", job_id, -1))
        finally:
            if proc is not None and proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

    def _on_job_finished(self, job_id: str, exit_code: int) -> None:
        if job_id != self.current_job_id:
            return
        job = self.reservations.find(job_id)
        if job is not None:
            if exit_code == 0:
                job.state, job.error = "done", ""
                self.left_monitor.ring.set_done()
                self.left_monitor.append_log(f"--- 解析完了: {job.video.name} ---\n", tag="heading")
            elif self._queue_stop.is_set():
                job.state, job.error = "pending", ""
                self.reservations.prioritize_pending(job.id)
                self.left_monitor.append_log(
                    f"--- 中断: {job.video.name} を予約リストの先頭へ戻しました ---\n"
                )
            else:
                job.state = "failed"
                job.error = f"終了コード {exit_code}\n" + "".join(self._job_tail)[-2000:]
                self.left_monitor.append_log(
                    f"--- 解析失敗 ({job.video.name}, 終了コード: {exit_code}) ---\n",
                    tag="error",
                )

        self.process = None
        self.current_job_id = None
        self._save_reservations_safe()
        self._refresh_ui()

        if self.queue_active and not self._queue_stop.is_set():
            self._next_token = self.root.after(0, self._launch_next_job)
        else:
            self._finish_queue_run()

    def _finish_queue_run(self) -> None:
        self.queue_active = False
        self.current_job_id = None
        t.set_btn_state(self.start_btn, True)
        t.set_btn_state(self.cancel_btn, False)
        if self._queue_stop.is_set():
            msg = "解析を中断しました。「解析開始」で先頭の動画から再開できます。"
        else:
            msg = "すべての待機予約の解析が終了しました。"
        self.banner_var.set(msg)
        self.left_monitor.show_idle(msg)
        self._refresh_ui()
        if self._close_after_stop:
            self._shutdown_now()

    # ---- Event Loop Polling ----------------------------------------------

    def _poll_events(self) -> None:
        self._poll_token = None
        for _ in range(300):
            try:
                item = self.event_queue.get_nowait()
            except queue.Empty:
                break
            kind = item[0]
            if kind == "__PREVIEW__":
                _, job_id, pil_img, info_text = item
                if pil_img is not None:
                    self._thumbnails[job_id] = pil_img
                if info_text:
                    self._thumb_info[job_id] = info_text
                if job_id == self.current_job_id:
                    self.left_monitor.update_running_preview(pil_img, info_text)
                self._refresh_ui()
            elif kind == "__JOB_FINISHED__":
                self._on_job_finished(item[1], item[2])
                if self._close_after_stop and not self.queue_active:
                    return
            elif kind == "__JOB_LOG__" and item[1] == self.current_job_id:
                line: str = item[2]
                if line.startswith("PROGRESS:"):
                    try:
                        pct_str, phase = line.strip().split(":", 2)[1:]
                        pct = max(0, min(100, int(pct_str)))
                        self.left_monitor.update_progress(pct, phase)
                        job = self.reservations.find(item[1])
                        if job is not None:
                            p_name = "YOLO" if phase.strip().upper() == "YOLO" else "RTMPose"
                            self.banner_var.set(f"解析実行中: {job.video.name}  ({p_name} {pct}%)")
                    except (ValueError, IndexError):
                        self.left_monitor.append_log(line)
                else:
                    self._job_tail.append(line)
                    self._job_tail = self._job_tail[-16:]
                    self.left_monitor.append_log(line)

        if self.root.winfo_exists():
            self._poll_token = self.root.after(100, self._poll_events)

    def _refresh_ui(self) -> None:
        # Prune thumbnails of completed/removed jobs
        active_ids = {j.id for j in self.reservations.jobs if j.state != "done"}
        for stale_id in list(self._thumbnails):
            if stale_id not in active_ids:
                self._thumbnails.pop(stale_id, None)
                self._thumb_info.pop(stale_id, None)
                self._preview_started.discard(stale_id)

        self.queue_view.refresh_jobs(self.reservations.jobs, self._thumbnails)

    # ---- Window Shutdown -------------------------------------------------

    def _on_close_window(self) -> None:
        if self.queue_active:
            confirm = messagebox.askyesno(
                "解析を中断して終了",
                "現在実行中の解析を中断してアプリを終了しますか？\n"
                "（解析中の動画は予約リストの先頭に待機中として保存されます）",
                parent=self.root,
            )
            if confirm:
                self._close_after_stop = True
                self.cancel_queue()
            return
        if self._save_reservations_safe():
            self._shutdown_now()

    def _shutdown_now(self) -> None:
        for attr in ("_poll_token", "_next_token"):
            token = getattr(self, attr, None)
            if token is not None:
                try:
                    self.root.after_cancel(token)
                except tk.TclError:
                    pass
                setattr(self, attr, None)
        if self.root.winfo_exists():
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_gui(
    *,
    base_dir: Path,
    settings_file: Path,
    engine_defaults: dict[str, Any],
    choices: dict[str, tuple[str, ...]],
    bool_keys: set[str],
    int_keys: set[str],
    float_keys: set[str],
    resolve_rtmlib_fn: Callable[[str, str, str, str], dict],
    output_names_fn: Callable[[Path], dict[str, str]],
) -> None:
    app = PoseApp(
        base_dir=base_dir,
        settings_file=settings_file,
        engine_defaults=engine_defaults,
        choices=choices,
        bool_keys=bool_keys,
        int_keys=int_keys,
        float_keys=float_keys,
        resolve_rtmlib_fn=resolve_rtmlib_fn,
        output_names_fn=output_names_fn,
    )
    app.run()
