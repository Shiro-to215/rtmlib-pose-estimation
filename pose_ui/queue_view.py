"""Right-pane default home view: Reservation List (予約リスト) with dashed Add button."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import tkinter as tk
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageTk

from reservation_queue import Reservation
from . import theme as t

THUMB_W = 112
THUMB_H = 63


class DashedAddZone(tk.Canvas):
    """Dashed rounded button matching the sketch's '予約を追加' area, with click & drop."""

    def __init__(
        self,
        master: tk.Misc,
        on_click: Callable[[], None],
        on_drop_files: Callable[[list[Path]], None] | None = None,
    ) -> None:
        super().__init__(
            master,
            height=68,
            bg=t.BG_PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._on_click = on_click
        self._hovered = False
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._handle_click)
        if on_drop_files is not None:
            t.register_drop_target(self, on_drop_files)

    def _on_enter(self, _e: tk.Event) -> None:
        self._hovered = True
        self._draw()

    def _on_leave(self, _e: tk.Event) -> None:
        self._hovered = False
        self._draw()

    def _handle_click(self, event: tk.Event) -> None:
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self._on_click()

    def _draw(self) -> None:
        self.delete("all")
        w = max(220, self.winfo_width())
        h = max(56, self.winfo_height())
        # Keep centered rounded dashed box slightly inset like the sketch
        margin_x = max(16, int(w * 0.08))
        x1, y1 = margin_x, 6
        x2, y2 = w - margin_x, h - 6
        r = 12

        fill = t.TEAL_SOFT if self._hovered else "#F9FBFA"
        outline = t.TEAL if self._hovered else "#8DA49E"
        text_color = t.TEAL_TEXT if self._hovered else t.TEXT_PRIMARY

        _draw_rounded_rect(self, x1, y1, x2, y2, r, fill=fill, outline=outline, width=2, dash=(7, 5))

        f = t.fonts()
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        self.create_text(
            cx,
            cy - 7,
            text="＋  予約を追加",
            font=(f.family, 14, "bold"),
            fill=text_color,
        )
        self.create_text(
            cx,
            cy + 14,
            text="クリックして動画と出力先を指定（または動画ファイルをここへドロップ）",
            font=(f.family, 10),
            fill=t.TEAL_TEXT if self._hovered else t.TEXT_MUTED,
        )


def _draw_rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    r: float,
    **kwargs,
) -> int:
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class QueueListView(ctk.CTkFrame):
    """Main reservation list view shown in the right pane."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_open_add: Callable[[list[Path] | None], None],
        on_open_basic_settings: Callable[[], None],
        on_open_job_settings: Callable[[str], None],
        on_delete_jobs: Callable[[list[str]], None],
        on_move_job: Callable[[str, int], None],
        on_retry_job: Callable[[str], None],
    ) -> None:
        super().__init__(
            master,
            fg_color=t.BG_PANEL,
            corner_radius=t.RADIUS_PANEL,
            border_width=1,
            border_color=t.BORDER,
        )
        self._on_open_add = on_open_add
        self._on_open_basic_settings = on_open_basic_settings
        self._on_open_job_settings = on_open_job_settings
        self._on_delete_jobs = on_delete_jobs
        self._on_move_job = on_move_job
        self._on_retry_job = on_retry_job

        self.selected_ids: list[str] = []
        self._visible_ids: list[str] = []
        self._row_widgets: dict[str, ctk.CTkFrame] = {}
        self._thumb_photos: dict[str, ImageTk.PhotoImage] = {}
        self._placeholder_photo = self._make_placeholder()

        f = t.fonts()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Row 0: Header toolbar ("予約リスト" + [削除] [上へ] [下へ] [基本設定])
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 10))
        toolbar.columnconfigure(0, weight=1)

        title_wrap = ctk.CTkFrame(toolbar, fg_color="transparent")
        title_wrap.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_wrap,
            text="予約リスト",
            font=f.h1,
            text_color=t.TEXT_PRIMARY,
        ).pack(side="left")

        self.summary_badge = ctk.CTkLabel(
            title_wrap,
            text=" 待機 0件 ",
            font=f.small_bold,
            text_color=t.TEAL_TEXT,
            fg_color=t.TEAL_SOFT,
            corner_radius=6,
            height=24,
            padx=8,
        )
        self.summary_badge.pack(side="left", padx=(12, 0))

        actions = ctk.CTkFrame(toolbar, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")

        self.delete_btn = t.make_button(
            actions, "削除", self._handle_delete, kind="danger", width=72, height=34
        )
        self.delete_btn.pack(side="left", padx=(0, 6))

        self.up_btn = t.make_button(
            actions, "上へ", lambda: self._handle_move(-1), kind="outline", width=68, height=34
        )
        self.up_btn.pack(side="left", padx=(0, 6))

        self.down_btn = t.make_button(
            actions, "下へ", lambda: self._handle_move(1), kind="outline", width=68, height=34
        )
        self.down_btn.pack(side="left", padx=(0, 12))

        self.basic_settings_btn = t.make_button(
            actions, "基本設定", self._on_open_basic_settings, kind="tonal", width=96, height=34
        )
        self.basic_settings_btn.pack(side="left")

        # Row 1: Column guide header strip matching sketch ([プレビュー] | [設定] | 出力フォルダー)
        col_bar = ctk.CTkFrame(
            self,
            fg_color=t.BG_HEADER,
            corner_radius=6,
            border_width=1,
            border_color=t.BORDER,
            height=32,
        )
        col_bar.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 6))
        col_bar.grid_propagate(False)
        col_bar.columnconfigure(2, weight=1)

        ctk.CTkLabel(
            col_bar, text="順番 / プレビュー", font=f.small_bold, text_color=t.TEXT_SECONDARY, width=152, anchor="w"
        ).grid(row=0, column=0, padx=(12, 6), pady=4, sticky="w")
        ctk.CTkLabel(
            col_bar, text="設定", font=f.small_bold, text_color=t.TEXT_SECONDARY, width=76, anchor="center"
        ).grid(row=0, column=1, padx=6, pady=4)
        ctk.CTkLabel(
            col_bar, text="動画名 / 出力フォルダー", font=f.small_bold, text_color=t.TEXT_SECONDARY, anchor="w"
        ).grid(row=0, column=2, padx=(10, 12), pady=4, sticky="w")

        # Row 2: Scrollable list area + dashed add button inside
        self.scroll = t.SmoothScrollFrame(self, bg=t.BG_PANEL)
        self.scroll.outer.grid(row=2, column=0, sticky="nsew", padx=(18, 10), pady=(0, 14))
        self.scroll.columnconfigure(0, weight=1)

        self.rows_holder = tk.Frame(self.scroll, bg=t.BG_PANEL)
        self.rows_holder.grid(row=0, column=0, sticky="ew")
        self.rows_holder.columnconfigure(0, weight=1)

        self.empty_hint = ctk.CTkLabel(
            self.scroll,
            text="待機中の予約はありません。下の「＋ 予約を追加」から動画を登録してください。",
            font=f.body,
            text_color=t.TEXT_MUTED,
        )

        self.add_zone = DashedAddZone(
            self.scroll,
            on_click=lambda: self._on_open_add(None),
            on_drop_files=self._handle_dropped_paths,
        )
        self.add_zone.grid(row=2, column=0, sticky="ew", pady=(10, 8), padx=(0, 8))

        t.register_drop_target(self.scroll.canvas, self._handle_dropped_paths)
        self._update_toolbar_states()

    def _make_placeholder(self) -> ImageTk.PhotoImage:
        img = Image.new("RGB", (THUMB_W, THUMB_H), (226, 232, 230))
        return ImageTk.PhotoImage(img)

    def _handle_dropped_paths(self, paths: list[Path]) -> None:
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".webm"}
        videos = [p for p in paths if p.is_file() and p.suffix.lower() in video_exts]
        if videos:
            self._on_open_add(videos)

    # ---- Refresh & Row Rendering -----------------------------------------

    def refresh_jobs(
        self,
        all_jobs: list[Reservation],
        thumbnails: dict[str, Image.Image],
    ) -> None:
        # Visible in right list: pending + failed (running is shown on Left Pane; done is hidden)
        visible_jobs = [job for job in all_jobs if job.state in {"pending", "failed"}]
        self._visible_ids = [job.id for job in visible_jobs]
        self.selected_ids = [jid for jid in self.selected_ids if jid in self._visible_ids]

        counts = Counter(job.state for job in all_jobs)
        parts = [f"待機 {counts['pending']}件"]
        if counts["failed"]:
            parts.append(f"失敗 {counts['failed']}件")
        if counts["done"]:
            parts.append(f"完了済 {counts['done']}件")
        self.summary_badge.configure(text="  " + " ・ ".join(parts) + "  ")

        for child in self.rows_holder.winfo_children():
            child.destroy()
        self._row_widgets.clear()

        if not visible_jobs:
            self.empty_hint.grid(row=1, column=0, pady=(18, 6))
        else:
            self.empty_hint.grid_forget()

        for idx, job in enumerate(visible_jobs, start=1):
            pil_thumb = thumbnails.get(job.id)
            if pil_thumb is not None:
                self._thumb_photos[job.id] = ImageTk.PhotoImage(
                    _fit_thumb(pil_thumb, THUMB_W, THUMB_H)
                )
            photo = self._thumb_photos.get(job.id, self._placeholder_photo)
            row_card = self._build_row(self.rows_holder, idx, job, photo)
            row_card.grid(row=idx - 1, column=0, sticky="ew", pady=(0, 8), padx=(0, 8))
            self._row_widgets[job.id] = row_card

        self._apply_selection_visuals()
        self._update_toolbar_states()
        self.scroll._schedule_sync()

    def _build_row(
        self,
        parent: tk.Misc,
        order_num: int,
        job: Reservation,
        photo: ImageTk.PhotoImage,
    ) -> ctk.CTkFrame:
        f = t.fonts()
        is_failed = job.state == "failed"
        base_bg = t.DANGER_SOFT if is_failed else t.BG_ROW
        base_border = t.DANGER_BORDER if is_failed else t.BORDER

        card = ctk.CTkFrame(
            parent,
            fg_color=base_bg,
            corner_radius=t.RADIUS_ITEM,
            border_width=1,
            border_color=base_border,
        )
        card._job_failed = is_failed  # type: ignore[attr-defined]
        card.columnconfigure(2, weight=1)

        # Column 0: Order number + Thumbnail preview
        left_cell = tk.Frame(card, bg=base_bg)
        left_cell.grid(row=0, column=0, padx=(10, 6), pady=8, sticky="w")
        card._bg_frames = [left_cell]  # type: ignore[attr-defined]

        num_lbl = tk.Label(
            left_cell,
            text=f"{order_num}",
            font=(f.family, 11, "bold"),
            fg=t.DANGER if is_failed else t.TEXT_SECONDARY,
            bg=base_bg,
            width=3,
        )
        num_lbl.pack(side="left", padx=(0, 6))
        card._bg_frames.append(num_lbl)  # type: ignore[attr-defined]

        thumb_border = tk.Frame(left_cell, bg=t.BORDER_STRONG, padx=1, pady=1)
        thumb_border.pack(side="left")
        thumb_lbl = tk.Label(thumb_border, image=photo, bg=t.PREVIEW_BG, bd=0)
        thumb_lbl.pack()

        # Column 1: [設定] button (per-reservation settings editor)
        settings_btn = t.make_button(
            card,
            "設定",
            command=lambda jid=job.id: self._on_open_job_settings(jid),
            kind="outline",
            width=72,
            height=36,
        )
        settings_btn.grid(row=0, column=1, padx=8, pady=8)

        # Column 2: Video name + Output folder + Optional failed retry controls
        info_cell = tk.Frame(card, bg=base_bg)
        info_cell.grid(row=0, column=2, padx=(8, 12), pady=8, sticky="ew")
        info_cell.columnconfigure(0, weight=1)
        card._bg_frames.append(info_cell)  # type: ignore[attr-defined]

        top_line = tk.Frame(info_cell, bg=base_bg)
        top_line.grid(row=0, column=0, sticky="ew")
        top_line.columnconfigure(0, weight=1)
        card._bg_frames.append(top_line)  # type: ignore[attr-defined]

        name_lbl = tk.Label(
            top_line,
            text=job.video.name,
            font=(f.family, 12, "bold"),
            fg=t.TEXT_PRIMARY,
            bg=base_bg,
            anchor="w",
        )
        name_lbl.grid(row=0, column=0, sticky="w")
        card._bg_frames.append(name_lbl)  # type: ignore[attr-defined]

        yolo_short = str(job.settings.get("YOLO_MODEL", "")).removeprefix("yolo11").removesuffix(".pt")
        mode_short = str(job.settings.get("MODEL_MODE", ""))
        dev_short = str(job.settings.get("DEVICE", "auto"))
        spec_text = f"{mode_short} / YOLO-{yolo_short} / {dev_short}"

        spec_lbl = tk.Label(
            top_line,
            text=spec_text,
            font=(f.family, 10),
            fg=t.TEXT_MUTED,
            bg=base_bg,
            anchor="e",
        )
        spec_lbl.grid(row=0, column=1, sticky="e", padx=(8, 0))
        card._bg_frames.append(spec_lbl)  # type: ignore[attr-defined]

        out_lbl = tk.Label(
            info_cell,
            text=f"出力先: {_middle_shorten_path(str(job.output), 54)}",
            font=(f.family, 10),
            fg=t.TEXT_SECONDARY,
            bg=base_bg,
            anchor="w",
            justify="left",
        )
        out_lbl.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        card._bg_frames.append(out_lbl)  # type: ignore[attr-defined]

        if is_failed:
            err_bar = tk.Frame(info_cell, bg=base_bg)
            err_bar.grid(row=2, column=0, sticky="ew", pady=(4, 0))
            err_bar.columnconfigure(0, weight=1)
            card._bg_frames.append(err_bar)  # type: ignore[attr-defined]

            last_err = _single_line_error(job.error)
            err_lbl = tk.Label(
                err_bar,
                text=f"失敗: {last_err}",
                font=(f.family, 10, "bold"),
                fg=t.DANGER,
                bg=base_bg,
                anchor="w",
            )
            err_lbl.grid(row=0, column=0, sticky="w")
            card._bg_frames.append(err_lbl)  # type: ignore[attr-defined]

            retry_btn = t.make_button(
                err_bar,
                "再試行",
                command=lambda jid=job.id: self._on_retry_job(jid),
                kind="danger",
                width=68,
                height=28,
            )
            retry_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))

        # Bind click selection on non-button surfaces
        for clickable in (card, left_cell, num_lbl, thumb_lbl, info_cell, top_line, name_lbl, spec_lbl, out_lbl):
            clickable.bind("<Button-1>", lambda e, jid=job.id: self._on_row_click(e, jid))

        return card

    # ---- Selection & Actions ---------------------------------------------

    def select_only(self, job_ids: list[str]) -> None:
        self.selected_ids = [jid for jid in job_ids if jid in self._visible_ids]
        self._apply_selection_visuals()
        self._update_toolbar_states()

    def _on_row_click(self, event: tk.Event, job_id: str) -> None:
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        if shift and self.selected_ids and self.selected_ids[-1] in self._visible_ids:
            anchor = self._visible_ids.index(self.selected_ids[-1])
            target = self._visible_ids.index(job_id)
            lo, hi = sorted((anchor, target))
            self.selected_ids = self._visible_ids[lo : hi + 1]
        elif ctrl:
            if job_id in self.selected_ids:
                self.selected_ids.remove(job_id)
            else:
                self.selected_ids.append(job_id)
        else:
            self.selected_ids = [job_id]
        self._apply_selection_visuals()
        self._update_toolbar_states()

    def _apply_selection_visuals(self) -> None:
        selected_set = set(self.selected_ids)
        for job_id, card in self._row_widgets.items():
            is_sel = job_id in selected_set
            is_failed = getattr(card, "_job_failed", False)
            if is_sel:
                bg = t.BG_ROW_SELECTED
                border = t.TEAL
                bw = 2
            elif is_failed:
                bg = t.DANGER_SOFT
                border = t.DANGER_BORDER
                bw = 1
            else:
                bg = t.BG_ROW
                border = t.BORDER
                bw = 1
            card.configure(fg_color=bg, border_color=border, border_width=bw)
            for child in getattr(card, "_bg_frames", []):
                try:
                    child.configure(bg=bg)
                except tk.TclError:
                    pass

    def _update_toolbar_states(self) -> None:
        has_sel = len(self.selected_ids) > 0
        single_sel = len(self.selected_ids) == 1
        t.set_btn_state(self.delete_btn, has_sel)
        if single_sel and self.selected_ids[0] in self._visible_ids:
            idx = self._visible_ids.index(self.selected_ids[0])
            t.set_btn_state(self.up_btn, idx > 0)
            t.set_btn_state(self.down_btn, idx < len(self._visible_ids) - 1)
        else:
            t.set_btn_state(self.up_btn, False)
            t.set_btn_state(self.down_btn, False)

    def _handle_delete(self) -> None:
        if self.selected_ids:
            self._on_delete_jobs(list(self.selected_ids))

    def _handle_move(self, delta: int) -> None:
        if len(self.selected_ids) == 1:
            self._on_move_job(self.selected_ids[0], delta)


def _fit_thumb(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    w, h = img.size
    if w <= 0 or h <= 0:
        return Image.new("RGB", (target_w, target_h), (226, 232, 230))
    scale = min(target_w / w, target_h / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), (226, 232, 230))
    canvas.paste(resized, ((target_w - nw) // 2, (target_h - nh) // 2))
    return canvas


def _middle_shorten_path(path_str: str, max_len: int = 54) -> str:
    if len(path_str) <= max_len:
        return path_str
    p = Path(path_str)
    tail = f"{p.parent.name}\\{p.name}" if p.parent.name else p.name
    if len(tail) + 10 >= max_len:
        keep_head = max(12, max_len - len(p.name) - 5)
        return f"{path_str[:keep_head]}...\\{p.name}"
    keep_head = max(10, max_len - len(tail) - 5)
    return f"{path_str[:keep_head]}...\\{tail}"


def _single_line_error(error_text: str) -> str:
    if not error_text:
        return "実行エラーが発生しました（ログを確認してください）"
    lines = [ln.strip() for ln in error_text.strip().splitlines() if ln.strip()]
    summary = lines[-1] if lines else "エラー"
    return summary[:78] + ("…" if len(summary) > 78 else "")
