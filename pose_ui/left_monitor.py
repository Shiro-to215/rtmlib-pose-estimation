"""Always-visible left monitoring pane: video preview, video name, circular progress, and execution log."""
from __future__ import annotations

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk

from . import theme as t
from .circular_progress import CircularProgress

PREVIEW_W = 324
PREVIEW_H = 182


class LeftMonitorPane(ctk.CTkFrame):
    """Left column showing currently analyzing video, circular progress bar, and execution logs."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(
            master,
            fg_color=t.BG_PANEL,
            corner_radius=t.RADIUS_PANEL,
            border_width=1,
            border_color=t.BORDER,
        )
        f = t.fonts()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)  # Execution log expands vertically

        # Row 0: Header ("解析中" + state badge)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        header.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="解析中",
            font=f.h1,
            text_color=t.TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.state_badge = ctk.CTkLabel(
            header,
            text=" 待機中 ",
            font=f.small_bold,
            text_color=t.TEXT_SECONDARY,
            fg_color=t.BG_SUBTLE,
            corner_radius=6,
            height=24,
            padx=8,
        )
        self.state_badge.grid(row=0, column=1, sticky="e")

        # Row 1: Video Preview Box (16:9)
        preview_wrap = tk.Frame(
            self,
            bg=t.BORDER,
            padx=1,
            pady=1,
        )
        preview_wrap.grid(row=1, column=0, padx=16, pady=(0, 8))

        self.preview_canvas = tk.Canvas(
            preview_wrap,
            width=PREVIEW_W,
            height=PREVIEW_H,
            bg=t.PREVIEW_BG,
            highlightthickness=0,
            bd=0,
        )
        self.preview_canvas.pack()
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_img_id = self.preview_canvas.create_image(
            PREVIEW_W // 2, PREVIEW_H // 2, anchor="center"
        )
        self._preview_text_id = self.preview_canvas.create_text(
            PREVIEW_W // 2,
            PREVIEW_H // 2,
            text="動画プレビュー\n（現在解析中の動画はありません）",
            font=(f.family, 11),
            fill=t.TEXT_MUTED,
            justify="center",
        )

        # Row 2: Video Name & Output Info
        info_box = ctk.CTkFrame(self, fg_color="transparent")
        info_box.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 4))
        info_box.columnconfigure(0, weight=1)

        self.video_name_label = ctk.CTkLabel(
            info_box,
            text="待機中",
            font=f.h2,
            text_color=t.TEXT_SECONDARY,
            anchor="center",
        )
        self.video_name_label.grid(row=0, column=0, sticky="ew")

        self.video_meta_label = ctk.CTkLabel(
            info_box,
            text="右側の予約リストから解析を開始できます",
            font=f.small,
            text_color=t.TEXT_MUTED,
            anchor="center",
            wraplength=316,
        )
        self.video_meta_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        # Row 3: Circular Progress Ring
        ring_holder = ctk.CTkFrame(self, fg_color="transparent")
        ring_holder.grid(row=3, column=0, pady=(4, 8))
        self.ring = CircularProgress(ring_holder, diameter=178, thickness=14, bg=t.BG_PANEL)
        self.ring.pack()

        # Row 4: Execution Log (expands to bottom)
        log_section = ctk.CTkFrame(
            self,
            fg_color=t.LOG_BG,
            corner_radius=t.RADIUS_ITEM,
            border_width=1,
            border_color=t.LOG_BORDER,
        )
        log_section.grid(row=4, column=0, sticky="nsew", padx=14, pady=(2, 14))
        log_section.columnconfigure(0, weight=1)
        log_section.rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_section, fg_color="transparent")
        log_header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(6, 2))
        log_header.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_header,
            text="実行ログ",
            font=f.small_bold,
            text_color=t.TEXT_SECONDARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        clear_btn = ctk.CTkButton(
            log_header,
            text="クリア",
            width=52,
            height=22,
            corner_radius=5,
            fg_color="transparent",
            hover_color=t.BG_SUBTLE,
            text_color=t.TEXT_MUTED,
            font=f.small,
            command=self.clear_log,
        )
        clear_btn.grid(row=0, column=1, sticky="e")

        self.log_text = tk.Text(
            log_section,
            height=7,
            wrap="word",
            bg=t.LOG_BG,
            fg=t.TEXT_PRIMARY,
            font=f.mono,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=6,
            state="disabled",
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
        self.log_text.tag_configure("error", foreground=t.DANGER)
        self.log_text.tag_configure("heading", foreground=t.TEAL_TEXT)

        log_scroll = ctk.CTkScrollbar(
            log_section,
            orientation="vertical",
            command=self.log_text.yview,
            fg_color=t.LOG_BG,
            button_color=t.BORDER_STRONG,
            button_hover_color=t.TEXT_MUTED,
            width=12,
        )
        log_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 3), pady=(0, 6))
        self.log_text.configure(yscrollcommand=log_scroll.set)

    # ---- State updates ---------------------------------------------------

    def show_idle(self, message: str = "右側の予約リストから解析を開始できます") -> None:
        self.state_badge.configure(
            text=" 待機中 ",
            fg_color=t.BG_SUBTLE,
            text_color=t.TEXT_SECONDARY,
        )
        self._set_preview_image(None)
        self.video_name_label.configure(text="待機中", text_color=t.TEXT_SECONDARY)
        self.video_meta_label.configure(text=message)
        self.ring.set_idle()

    def show_running_job(
        self,
        video_name: str,
        output_folder: str,
        pil_image: Image.Image | None = None,
        info_text: str = "",
    ) -> None:
        self.state_badge.configure(
            text=" 解析実行中 ",
            fg_color=t.TEAL_SOFT,
            text_color=t.TEAL_TEXT,
        )
        self._set_preview_image(pil_image)
        self.video_name_label.configure(text=_ellipsize(video_name, 28), text_color=t.TEXT_PRIMARY)
        short_out = _ellipsize(output_folder, 38)
        meta = f"出力: {short_out}"
        if info_text:
            meta = f"{info_text}  |  {meta}"
        self.video_meta_label.configure(text=meta)
        self.ring.set_starting()

    def update_running_preview(self, pil_image: Image.Image | None, info_text: str = "") -> None:
        if pil_image is not None:
            self._set_preview_image(pil_image)
        if info_text:
            current = self.video_meta_label.cget("text")
            if info_text not in current:
                self.video_meta_label.configure(text=f"{info_text}  |  {current}")

    def update_progress(self, percent: int, phase_code: str) -> None:
        upper = phase_code.strip().upper()
        if upper == "YOLO":
            self.state_badge.configure(
                text=" YOLO 処理中 ",
                fg_color=t.TEAL_SOFT,
                text_color=t.TEAL_TEXT,
            )
        else:
            self.state_badge.configure(
                text=" RTMPose 処理中 ",
                fg_color=t.POSE_SOFT,
                text_color=t.POSE_BLUE,
            )
        self.ring.set_progress(percent, phase_code)

    def show_stopping(self) -> None:
        self.state_badge.configure(
            text=" 中断処理中 ",
            fg_color=t.DANGER_SOFT,
            text_color=t.DANGER,
        )
        self.ring.set_stopping()

    def _set_preview_image(self, pil_image: Image.Image | None) -> None:
        if pil_image is None:
            self._preview_photo = None
            self.preview_canvas.itemconfigure(self._preview_img_id, image="")
            self.preview_canvas.itemconfigure(self._preview_text_id, state="normal")
            return
        fitted = _fit_cover_letterbox(pil_image, PREVIEW_W, PREVIEW_H)
        self._preview_photo = ImageTk.PhotoImage(fitted)
        self.preview_canvas.itemconfigure(self._preview_img_id, image=self._preview_photo)
        self.preview_canvas.itemconfigure(self._preview_text_id, state="hidden")

    # ---- Log helpers -----------------------------------------------------

    def append_log(self, text: str, *, tag: str | None = None) -> None:
        if not text:
            return
        inferred_tag = tag
        if inferred_tag is None:
            lower = text.lower()
            if "error" in lower or "エラー" in text or "失敗" in text or "traceback" in lower:
                inferred_tag = "error"
            elif text.lstrip().startswith("---"):
                inferred_tag = "heading"
        self.log_text.configure(state="normal")
        if inferred_tag:
            self.log_text.insert("end", text, inferred_tag)
        else:
            self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")


def _fit_cover_letterbox(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    w, h = img.size
    if w <= 0 or h <= 0:
        return Image.new("RGB", (target_w, target_h), (226, 232, 230))
    scale = min(target_w / w, target_h / h)
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), (226, 232, 230))
    canvas.paste(resized, ((target_w - nw) // 2, (target_h - nh) // 2))
    return canvas


def _ellipsize(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    keep = max(4, (limit - 3) // 2)
    return f"{text[:keep]}...{text[-keep:]}"
