"""Right-pane inline view for adding new video reservation(s) and configuring I/O paths."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from . import theme as t

VIDEO_FILETYPES = [
    ("動画ファイル", "*.mp4 *.MP4 *.mov *.MOV *.avi *.AVI *.mkv *.MKV *.m4v *.wmv"),
    ("すべてのファイル", "*.*"),
]
IMAGE_FILETYPES = [
    ("画像ファイル", "*.jpg *.JPG *.jpeg *.JPEG *.png *.PNG"),
    ("すべてのファイル", "*.*"),
]


class AddReservationView(ctk.CTkFrame):
    """Inline screen for selecting input video(s) and output destination before adding to queue."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        output_names_fn: Callable[[Path], dict[str, str]],
        on_cancel: Callable[[], None],
        on_submit: Callable[[list[Path], Path, Path | None, str | None], bool],
        on_open_basic_settings: Callable[[], None],
    ) -> None:
        super().__init__(
            master,
            fg_color=t.BG_PANEL,
            corner_radius=t.RADIUS_PANEL,
            border_width=1,
            border_color=t.BORDER,
        )
        self._output_names_fn = output_names_fn
        self._on_cancel = on_cancel
        self._on_submit = on_submit
        self._on_open_basic_settings = on_open_basic_settings

        self._videos: list[Path] = []
        self._default_root: Path = Path.home()
        self._custom_dest_touched = False

        self.parent_root_var = tk.StringVar()
        self.single_dest_var = tk.StringVar()
        self.thumbnail_var = tk.StringVar()
        self.preview_files_var = tk.StringVar()

        f = t.fonts()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Row 0: Header bar with Back button
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 10))
        header.columnconfigure(1, weight=1)

        back_btn = t.make_button(
            header, "← 予約リストへ戻る", self._on_cancel, kind="outline", width=150, height=34
        )
        back_btn.grid(row=0, column=0, sticky="w", padx=(0, 12))

        ctk.CTkLabel(
            header,
            text="予約を追加",
            font=f.h1,
            text_color=t.TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=1, sticky="w")

        # Row 1: Scrollable form body
        self.scroll = t.SmoothScrollFrame(self, bg=t.BG_PANEL)
        self.scroll.outer.grid(row=1, column=0, sticky="nsew", padx=(18, 10), pady=(0, 8))
        self.scroll.columnconfigure(0, weight=1)

        # Section 1: Input Videos
        in_card = self._make_section(
            self.scroll,
            title="1. 入力ファイルの選択",
            subtitle="解析したい動画ファイルを選択してください（複数まとめて選択・ドロップも可能）。",
        )
        in_card.grid(row=0, column=0, sticky="ew", pady=(2, 12), padx=(0, 8))

        btn_row = ctk.CTkFrame(in_card, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 8))

        t.make_button(
            btn_row, "動画ファイルを選択…", self._browse_videos, kind="tonal", width=168, height=36
        ).pack(side="left")

        self.clear_videos_btn = t.make_button(
            btn_row, "選択をクリア", self._clear_videos, kind="ghost", width=108, height=36
        )
        self.clear_videos_btn.pack(side="left", padx=(8, 0))

        self.video_list_frame = ctk.CTkFrame(
            in_card,
            fg_color=t.BG_HEADER,
            corner_radius=6,
            border_width=1,
            border_color=t.BORDER,
        )
        self.video_list_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.video_list_frame.columnconfigure(0, weight=1)

        # Section 2: Output Configuration
        self.out_card = self._make_section(
            self.scroll,
            title="2. 出力先フォルダーの設定",
            subtitle="解析結果（骨格動画・YOLO動画・CSV・メタデータ）の保存先を指定します。",
        )
        self.out_card.grid(row=1, column=0, sticky="ew", pady=(0, 12), padx=(0, 8))

        self.out_body = ctk.CTkFrame(self.out_card, fg_color="transparent")
        self.out_body.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        self.out_body.columnconfigure(0, weight=1)

        # Single-video output widgets
        self.single_frame = ctk.CTkFrame(self.out_body, fg_color="transparent")
        self.single_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.single_frame,
            text="出力先フォルダー（フォルダー名から出力ファイル名を自動生成します）",
            font=f.body_bold,
            text_color=t.TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        single_entry = ctk.CTkEntry(
            self.single_frame,
            textvariable=self.single_dest_var,
            height=36,
            corner_radius=6,
            border_color=t.BORDER_STRONG,
            fg_color=t.BG_PANEL,
            text_color=t.TEXT_PRIMARY,
            font=f.body,
        )
        single_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        single_entry.bind("<KeyRelease>", lambda _e: self._mark_custom_dest_touched())

        t.make_button(
            self.single_frame, "参照…", self._browse_single_dest, kind="outline", width=80, height=36
        ).grid(row=1, column=1, padx=(8, 0), pady=(4, 0))

        ctk.CTkLabel(
            self.single_frame,
            textvariable=self.preview_files_var,
            font=f.small,
            text_color=t.TEAL_TEXT,
            anchor="w",
            wraplength=620,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 10))

        # Optional thumbnail for timestamp (1 video mode)
        ctk.CTkLabel(
            self.single_frame,
            text="撮影日時取得用サムネイル画像（任意・SONY機のTHMBNL等がある場合のみ）",
            font=f.small_bold,
            text_color=t.TEXT_SECONDARY,
            anchor="w",
        ).grid(row=3, column=0, columnspan=2, sticky="w")

        thumb_row = ctk.CTkFrame(self.single_frame, fg_color="transparent")
        thumb_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        thumb_row.columnconfigure(0, weight=1)

        ctk.CTkEntry(
            thumb_row,
            textvariable=self.thumbnail_var,
            height=34,
            corner_radius=6,
            border_color=t.BORDER_STRONG,
            fg_color=t.BG_PANEL,
            text_color=t.TEXT_PRIMARY,
            placeholder_text="未指定（動画ファイル自体のメタデータを使用）",
            font=f.small,
        ).grid(row=0, column=0, sticky="ew")

        t.make_button(
            thumb_row, "参照…", self._browse_thumbnail, kind="outline", width=76, height=34
        ).grid(row=0, column=1, padx=(8, 0))

        t.make_button(
            thumb_row, "空欄にする", lambda: self.thumbnail_var.set(""), kind="ghost", width=84, height=34
        ).grid(row=0, column=2, padx=(4, 0))

        # Multi-video output widgets
        self.multi_frame = ctk.CTkFrame(self.out_body, fg_color="transparent")
        self.multi_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.multi_frame,
            text="出力親フォルダー（この中に動画ごとのサブフォルダーを自動作成します）",
            font=f.body_bold,
            text_color=t.TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ctk.CTkEntry(
            self.multi_frame,
            textvariable=self.parent_root_var,
            height=36,
            corner_radius=6,
            border_color=t.BORDER_STRONG,
            fg_color=t.BG_PANEL,
            text_color=t.TEXT_PRIMARY,
            font=f.body,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        t.make_button(
            self.multi_frame, "参照…", self._browse_parent_root, kind="outline", width=80, height=36
        ).grid(row=1, column=1, padx=(8, 0), pady=(4, 0))

        self.multi_preview_label = ctk.CTkLabel(
            self.multi_frame,
            text="",
            font=f.small,
            text_color=t.TEXT_SECONDARY,
            anchor="w",
            justify="left",
            wraplength=620,
        )
        self.multi_preview_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # Section 3: Settings snapshot info
        self.preset_card = ctk.CTkFrame(
            self.scroll,
            fg_color=t.BG_SUBTLE,
            corner_radius=8,
            border_width=1,
            border_color=t.BORDER,
        )
        self.preset_card.grid(row=2, column=0, sticky="ew", pady=(0, 8), padx=(0, 8))
        self.preset_card.columnconfigure(0, weight=1)

        self.preset_info_label = ctk.CTkLabel(
            self.preset_card,
            text="",
            font=f.small,
            text_color=t.TEXT_SECONDARY,
            anchor="w",
            justify="left",
        )
        self.preset_info_label.grid(row=0, column=0, sticky="ew", padx=14, pady=10)

        t.make_button(
            self.preset_card,
            "基本設定を確認",
            self._on_open_basic_settings,
            kind="outline",
            width=118,
            height=30,
        ).grid(row=0, column=1, padx=(0, 12), pady=10)

        # Row 2: Bottom submit bar
        footer = ctk.CTkFrame(
            self,
            fg_color=t.BG_HEADER,
            corner_radius=0,
            border_width=1,
            border_color=t.BORDER,
            height=60,
        )
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.columnconfigure(0, weight=1)

        t.make_button(
            footer, "キャンセル", self._on_cancel, kind="outline", width=110, height=38
        ).grid(row=0, column=1, padx=(0, 10), pady=11)

        self.submit_btn = t.make_button(
            footer,
            "＋ 予約リストに追加する",
            self._handle_submit,
            kind="primary",
            width=200,
            height=38,
            large=True,
        )
        self.submit_btn.grid(row=0, column=2, padx=(0, 18), pady=11)

        self.single_dest_var.trace_add("write", lambda *_: self._refresh_output_previews())
        self.parent_root_var.trace_add("write", lambda *_: self._refresh_output_previews())

        t.register_drop_target(self, self._on_drop_files)
        t.register_drop_target(self.scroll.canvas, self._on_drop_files)

    def _make_section(self, master: tk.Misc, title: str, subtitle: str) -> ctk.CTkFrame:
        f = t.fonts()
        card = ctk.CTkFrame(
            master,
            fg_color=t.BG_PANEL,
            corner_radius=8,
            border_width=1,
            border_color=t.BORDER,
        )
        card.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card, text=title, font=f.h2, text_color=t.TEXT_PRIMARY, anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(
            card, text=subtitle, font=f.small, text_color=t.TEXT_MUTED, anchor="w"
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 6))
        return card

    # ---- Public lifecycle ------------------------------------------------

    def prepare(
        self,
        default_output_root: str | Path,
        default_settings: dict,
        initial_videos: list[Path] | None = None,
    ) -> None:
        self._default_root = Path(default_output_root).expanduser()
        self.parent_root_var.set(str(self._default_root))
        self.thumbnail_var.set("")
        self._custom_dest_touched = False
        self._videos = []
        if initial_videos:
            self._add_video_paths(initial_videos)
        else:
            self._sync_ui()

        yolo = str(default_settings.get("YOLO_MODEL", "")).removeprefix("yolo11").removesuffix(".pt")
        mode = default_settings.get("MODEL_MODE", "performance")
        device = default_settings.get("DEVICE", "auto")
        self.preset_info_label.configure(
            text=(
                f"適用される初期設定:  姿勢推定={mode}  /  YOLO={yolo}  /  デバイス={device}\n"
                "※ リストへ追加したあとでも、各行の「設定」ボタンから動画ごとに変更できます。"
            )
        )
        self.scroll.scroll_to_top()

    # ---- Handlers --------------------------------------------------------

    def _mark_custom_dest_touched(self) -> None:
        self._custom_dest_touched = True

    def _on_drop_files(self, paths: list[Path]) -> None:
        exts = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".webm"}
        videos = [p for p in paths if p.is_file() and p.suffix.lower() in exts]
        if videos:
            self._add_video_paths(videos)

    def _browse_videos(self) -> None:
        init_dir = str(self._videos[-1].parent) if self._videos else str(Path.home())
        chosen = filedialog.askopenfilenames(
            parent=self.winfo_toplevel(),
            title="予約する動画を選択",
            initialdir=init_dir,
            filetypes=VIDEO_FILETYPES,
        )
        if chosen:
            self._add_video_paths([Path(p) for p in chosen])

    def _add_video_paths(self, new_paths: list[Path]) -> None:
        existing = {str(p.resolve()).casefold() for p in self._videos}
        for p in new_paths:
            resolved = p.expanduser().resolve()
            if resolved.is_file() and str(resolved).casefold() not in existing:
                self._videos.append(resolved)
                existing.add(str(resolved).casefold())
        if len(self._videos) == 1 and not self._custom_dest_touched:
            root = Path(self.parent_root_var.get().strip() or str(self._default_root))
            self.single_dest_var.set(str(root / self._videos[0].stem))
        self._sync_ui()

    def _remove_video_at(self, index: int) -> None:
        if 0 <= index < len(self._videos):
            self._videos.pop(index)
            if len(self._videos) == 1 and not self._custom_dest_touched:
                root = Path(self.parent_root_var.get().strip() or str(self._default_root))
                self.single_dest_var.set(str(root / self._videos[0].stem))
            self._sync_ui()

    def _clear_videos(self) -> None:
        self._videos.clear()
        self._custom_dest_touched = False
        self._sync_ui()

    def _browse_single_dest(self) -> None:
        current = self.single_dest_var.get().strip()
        init_dir = str(Path(current).parent) if current else str(self._default_root)
        chosen = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title="出力先フォルダーを選択",
            initialdir=init_dir,
        )
        if chosen:
            self._custom_dest_touched = True
            self.single_dest_var.set(chosen)

    def _browse_parent_root(self) -> None:
        current = self.parent_root_var.get().strip() or str(self._default_root)
        chosen = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title="出力親フォルダーを選択",
            initialdir=current,
        )
        if chosen:
            self.parent_root_var.set(chosen)
            if len(self._videos) == 1 and not self._custom_dest_touched:
                self.single_dest_var.set(str(Path(chosen) / self._videos[0].stem))

    def _browse_thumbnail(self) -> None:
        init_dir = str(self._videos[0].parent) if self._videos else str(Path.home())
        chosen = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="撮影日時取得用のサムネイル画像を選択",
            initialdir=init_dir,
            filetypes=IMAGE_FILETYPES,
        )
        if chosen:
            self.thumbnail_var.set(chosen)

    def _sync_ui(self) -> None:
        f = t.fonts()
        for child in self.video_list_frame.winfo_children():
            child.destroy()

        if not self._videos:
            ctk.CTkLabel(
                self.video_list_frame,
                text="動画がまだ選択されていません。「動画ファイルを選択…」またはドラッグ＆ドロップで追加してください。",
                font=f.small,
                text_color=t.TEXT_MUTED,
                pady=14,
            ).grid(row=0, column=0, padx=12)
        else:
            for i, video in enumerate(self._videos):
                item = ctk.CTkFrame(self.video_list_frame, fg_color="transparent")
                item.grid(row=i, column=0, sticky="ew", padx=10, pady=(6 if i == 0 else 2, 6 if i == len(self._videos) - 1 else 2))
                item.columnconfigure(1, weight=1)

                ctk.CTkLabel(
                    item,
                    text=f"{i + 1}.",
                    font=f.small_bold,
                    text_color=t.TEAL_TEXT,
                    width=24,
                    anchor="w",
                ).grid(row=0, column=0, sticky="w")

                ctk.CTkLabel(
                    item,
                    text=f"{video.name}   ({video.parent})",
                    font=f.small,
                    text_color=t.TEXT_PRIMARY,
                    anchor="w",
                ).grid(row=0, column=1, sticky="ew")

                ctk.CTkButton(
                    item,
                    text="除外",
                    width=48,
                    height=24,
                    corner_radius=5,
                    fg_color="transparent",
                    hover_color=t.DANGER_SOFT,
                    text_color=t.DANGER,
                    font=f.small,
                    command=lambda idx=i: self._remove_video_at(idx),
                ).grid(row=0, column=2, padx=(6, 0))

        # Switch output form between single-video direct folder vs multi-video parent folder
        self.single_frame.grid_forget()
        self.multi_frame.grid_forget()
        if len(self._videos) <= 1:
            self.single_frame.grid(row=0, column=0, sticky="ew")
        else:
            self.multi_frame.grid(row=0, column=0, sticky="ew")

        t.set_btn_state(self.submit_btn, len(self._videos) > 0)
        t.set_btn_state(self.clear_videos_btn, len(self._videos) > 0)
        self._refresh_output_previews()
        self.scroll._schedule_sync()

    def _refresh_output_previews(self) -> None:
        if len(self._videos) <= 1:
            raw = self.single_dest_var.get().strip()
            if raw:
                try:
                    names = self._output_names_fn(Path(raw))
                    self.preview_files_var.set(
                        "自動生成される出力ファイル:  " + "  /  ".join(names.values())
                    )
                except ValueError:
                    self.preview_files_var.set("出力先フォルダーを指定してください。")
            else:
                self.preview_files_var.set("動画を1本選ぶと、既定の出力先フォルダー名が自動入力されます。")
        else:
            root = Path(self.parent_root_var.get().strip() or str(self._default_root))
            lines = [f"・ {v.name}  →  {root / v.stem}" for v in self._videos[:5]]
            if len(self._videos) > 5:
                lines.append(f"… ほか {len(self._videos) - 5} 件（重複時は自動で連番が付きます）")
            self.multi_preview_label.configure(text="\n".join(lines))

    def _handle_submit(self) -> None:
        if not self._videos:
            messagebox.showinfo("動画を選択してください", "予約に追加する動画を選択してください。", parent=self.winfo_toplevel())
            return

        if len(self._videos) == 1:
            dest_raw = self.single_dest_var.get().strip()
            if not dest_raw:
                messagebox.showerror("出力先エラー", "出力先フォルダーを指定してください。", parent=self.winfo_toplevel())
                return
            custom_dest = Path(dest_raw).expanduser()
            parent_root = custom_dest.parent if str(custom_dest.parent) else self._default_root
            thumb = self.thumbnail_var.get().strip() or None
            if thumb and not Path(thumb).expanduser().is_file():
                messagebox.showerror(
                    "サムネイルが見つかりません",
                    f"指定された撮影日時用サムネイル画像が存在しません。\n不要な場合は空欄にしてください。\n{thumb}",
                    parent=self.winfo_toplevel(),
                )
                return
            self._on_submit(self._videos, parent_root, custom_dest, thumb)
        else:
            root_raw = self.parent_root_var.get().strip()
            if not root_raw:
                messagebox.showerror("出力先エラー", "出力親フォルダーを指定してください。", parent=self.winfo_toplevel())
                return
            parent_root = Path(root_raw).expanduser()
            self._on_submit(self._videos, parent_root, None, None)
