"""Shared structured settings view for both Basic Settings (基本設定) and Per-Job Settings (予約の個別設定)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Callable, Literal

import customtkinter as ctk

from reservation_queue import Reservation
from . import theme as t

PRIMARY_KEYS = (
    "DEVICE",
    "MODEL_MODE",
    "YOLO_MODEL",
    "CSV_MAX_PERSONS",
    "YOLO_TRACK_ID",
)

DETECTION_DETAIL_KEYS = (
    "RTMLIB_POSE_MODEL",
    "RTMLIB_POSE_INPUT_SIZE",
    "RTMLIB_PERSON_DETECTOR",
    "BACKEND",
    "KEYPOINT_THRESHOLD",
    "YOLO_IMAGE_SIZE",
    "YOLO_CONFIDENCE",
    "YOLO_IOU",
    "YOLO_BATCH_SIZE",
    "RTMPOSE_BATCH_SIZE",
    "YOLO_TRACKER",
    "YOLO_CLASSES",
    "CROP_PADDING_RATIO",
)

FRIENDLY_LABELS: dict[str, str] = {
    "DEVICE": "実行デバイス（YOLO・姿勢推定）",
    "MODEL_MODE": "姿勢推定モード（プリセット）",
    "YOLO_MODEL": "YOLO11 モデルサイズ",
    "CSV_MAX_PERSONS": "CSV出力の最大人数列数",
    "YOLO_TRACK_ID": "対象のYOLO追跡ID（空欄＝自動選択）",
    "RTMLIB_POSE_MODEL": "RTMPose モデル（mode＝プリセット連動）",
    "RTMLIB_POSE_INPUT_SIZE": "RTMPose 入力解像度（mode＝自動）",
    "RTMLIB_PERSON_DETECTOR": "RTMLib 人物検出器 YOLOX（mode＝連動）",
    "BACKEND": "推論バックエンド",
    "KEYPOINT_THRESHOLD": "関節スコアしきい値 (KEYPOINT_THRESHOLD)",
    "YOLO_IMAGE_SIZE": "YOLO 入力解像度 (YOLO_IMAGE_SIZE)",
    "YOLO_CONFIDENCE": "YOLO 検出信頼度 (YOLO_CONFIDENCE)",
    "YOLO_IOU": "YOLO NMS IoU (YOLO_IOU)",
    "YOLO_BATCH_SIZE": "YOLO バッチサイズ (1〜64)",
    "RTMPOSE_BATCH_SIZE": "RTMPose バッチサイズ (1〜64)",
    "YOLO_TRACKER": "YOLO トラッカー設定ファイル",
    "YOLO_CLASSES": "検出対象クラスID（カンマ区切り、0=人物）",
    "CROP_PADDING_RATIO": "人物クロップ余白率 (CROP_PADDING_RATIO)",
    "TARGET_SELECTION_MIN_FRAMES": "自動対象選択の最低フレーム数",
    "TARGET_SELECTION_COVERAGE_WEIGHT": "自動対象選択の出現率重み",
    "TARGET_BOX_FILL_MAX_FRAMES": "対象欠損時の線形補間上限フレーム数",
    "TARGET_REACQUIRE_MAX_DISTANCE": "対象再捕捉の最大距離 (px)",
    "TARGET_REACQUIRE_MIN_IOU": "対象再捕捉の最小IoU",
}


class CollapsibleSection(ctk.CTkFrame):
    """Expandable/collapsible parameter card to keep advanced tracking settings tidy."""

    def __init__(self, master: tk.Misc, title: str, subtitle: str, *, initially_open: bool = False) -> None:
        super().__init__(
            master,
            fg_color=t.BG_PANEL,
            corner_radius=8,
            border_width=1,
            border_color=t.BORDER,
        )
        self._open = initially_open
        self.columnconfigure(0, weight=1)
        f = t.fonts()

        self.header = ctk.CTkFrame(self, fg_color=t.BG_HEADER, corner_radius=7, cursor="hand2")
        self.header.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        self.header.columnconfigure(1, weight=1)

        self.arrow_lbl = ctk.CTkLabel(
            self.header,
            text="▾" if self._open else "▸",
            font=f.h2,
            text_color=t.TEAL_TEXT,
            width=24,
        )
        self.arrow_lbl.grid(row=0, column=0, rowspan=2, padx=(12, 4), pady=10)

        t_lbl = ctk.CTkLabel(
            self.header, text=title, font=f.h3, text_color=t.TEXT_PRIMARY, anchor="w"
        )
        t_lbl.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(8, 0))

        s_lbl = ctk.CTkLabel(
            self.header, text=subtitle, font=f.small, text_color=t.TEXT_MUTED, anchor="w"
        )
        s_lbl.grid(row=1, column=1, sticky="w", padx=(0, 12), pady=(0, 8))

        for w in (self.header, self.arrow_lbl, t_lbl, s_lbl):
            w.bind("<Button-1>", lambda _e: self.toggle())

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.columnconfigure(1, weight=1)
        if self._open:
            self.body.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 14))

    def toggle(self) -> None:
        self._open = not self._open
        self.arrow_lbl.configure(text="▾" if self._open else "▸")
        if self._open:
            self.body.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 14))
        else:
            self.body.grid_forget()


class SettingsView(ctk.CTkFrame):
    """Unified settings view supporting 'default' (基本設定) and 'job' (予約の個別設定)."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        engine_defaults: dict[str, Any],
        choices: dict[str, tuple[str, ...]],
        bool_keys: set[str],
        int_keys: set[str],
        float_keys: set[str],
        resolve_rtmlib_fn: Callable[[str, str, str, str], dict],
        output_names_fn: Callable[[Path], dict[str, str]],
        on_back: Callable[[], None],
        on_save_default: Callable[[dict[str, Any], str], None],
        on_save_job: Callable[[str, dict[str, Any], Path, bool], None],
        get_current_defaults: Callable[[], dict[str, Any]],
    ) -> None:
        super().__init__(
            master,
            fg_color=t.BG_PANEL,
            corner_radius=t.RADIUS_PANEL,
            border_width=1,
            border_color=t.BORDER,
        )
        self._engine_defaults = engine_defaults
        self._choices = choices
        self._bool_keys = bool_keys
        self._int_keys = int_keys
        self._float_keys = float_keys
        self._resolve_rtmlib_fn = resolve_rtmlib_fn
        self._output_names_fn = output_names_fn
        self._on_back = on_back
        self._on_save_default = on_save_default
        self._on_save_job = on_save_job
        self._get_current_defaults = get_current_defaults

        self._mode: Literal["default", "job"] = "default"
        self._editing_job: Reservation | None = None

        # Parameter keys excluding path/output-name keys
        excluded = {
            "INPUT_ROOT",
            "INPUT_VIDEO_NAME",
            "THUMBNAIL_ROOT",
            "THUMBNAIL_IMAGE_NAME",
            "OUTPUT_ROOT",
            "OUTPUT_FOLDER_NAME",
            "OUTPUT_VIDEO_NAME",
            "OUTPUT_YOLO_VIDEO_NAME",
            "OUTPUT_CSV_NAME",
            "OUTPUT_METADATA_NAME",
        }
        all_param_keys = [k for k in engine_defaults if k not in excluded]
        known = set(PRIMARY_KEYS) | set(DETECTION_DETAIL_KEYS)
        self._tracking_keys = [k for k in all_param_keys if k not in known]

        self.param_vars: dict[str, tk.Variable] = {}
        self.default_root_var = tk.StringVar()
        self.job_output_var = tk.StringVar()
        self.job_thumb_var = tk.StringVar()
        self.job_output_preview_var = tk.StringVar()
        self.reset_failed_var = tk.BooleanVar(value=True)

        f = t.fonts()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Row 0: Top Header Bar
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 10))
        header.columnconfigure(1, weight=1)

        t.make_button(
            header, "← 戻る", self._on_back, kind="outline", width=92, height=34
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self.title_label = ctk.CTkLabel(
            header, text="基本設定", font=f.h1, text_color=t.TEXT_PRIMARY, anchor="w"
        )
        self.title_label.grid(row=0, column=1, sticky="w")

        self.reset_or_copy_btn = t.make_button(
            header, "初期値に戻す", self._handle_secondary_action, kind="outline", width=136, height=34
        )
        self.reset_or_copy_btn.grid(row=0, column=2, padx=(8, 8))

        self.save_top_btn = t.make_button(
            header, "保存する", self._handle_save, kind="primary", width=132, height=34
        )
        self.save_top_btn.grid(row=0, column=3)

        # Row 1: Scrollable Settings Form
        self.scroll = t.SmoothScrollFrame(self, bg=t.BG_PANEL)
        self.scroll.outer.grid(row=1, column=0, sticky="nsew", padx=(18, 10), pady=(0, 12))
        self.scroll.columnconfigure(0, weight=1)

        # Mode-specific top card (Default Output Root vs Job I/O Paths)
        self.default_io_card = self._build_default_io_card(self.scroll)
        self.job_io_card = self._build_job_io_card(self.scroll)

        # Primary Parameters Card (always expanded)
        primary_card = ctk.CTkFrame(
            self.scroll,
            fg_color=t.BG_PANEL,
            corner_radius=8,
            border_width=1,
            border_color=t.BORDER,
        )
        primary_card.grid(row=1, column=0, sticky="ew", pady=(0, 12), padx=(0, 8))
        primary_card.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            primary_card, text="主要解析設定", font=f.h2, text_color=t.TEXT_PRIMARY, anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(
            primary_card,
            text="使用頻度が高いモデル・実行デバイス・対象人物の設定です。",
            font=f.small,
            text_color=t.TEXT_MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        primary_grid = ctk.CTkFrame(primary_card, fg_color="transparent")
        primary_grid.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        primary_grid.columnconfigure(1, weight=1)
        self._populate_fields(primary_grid, PRIMARY_KEYS)

        # Collapsible 1: Model & Detection Details
        det_section = CollapsibleSection(
            self.scroll,
            title="モデル・検出の詳細設定",
            subtitle="RTMPose個別モデル・解像度・YOLO信頼度・クロップ余白などを調整します",
            initially_open=False,
        )
        det_section.grid(row=2, column=0, sticky="ew", pady=(0, 12), padx=(0, 8))
        self._populate_fields(det_section.body, DETECTION_DETAIL_KEYS)

        # Collapsible 2: Advanced Tracking Weights
        trk_section = CollapsibleSection(
            self.scroll,
            title="追跡・ID安定化の高度なパラメータ",
            subtitle="ByteTrack後のID維持・欠損補間・骨格マッチング重みなどの詳細設定です",
            initially_open=False,
        )
        trk_section.grid(row=3, column=0, sticky="ew", pady=(0, 12), padx=(0, 8))
        self._populate_fields(trk_section.body, self._tracking_keys)

        self.job_output_var.trace_add("write", lambda *_: self._update_job_output_preview())

    def _build_default_io_card(self, parent: tk.Misc) -> ctk.CTkFrame:
        f = t.fonts()
        card = ctk.CTkFrame(
            parent, fg_color=t.TEAL_SOFT, corner_radius=8, border_width=1, border_color="#B7DFD8"
        )
        card.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="新規予約時の既定出力親フォルダー",
            font=f.h3,
            text_color=t.TEAL_TEXT,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(
            card,
            text="「予約を追加」を開いたときに最初から入力される出力先の親フォルダーです（登録済みの予約には影響しません）。",
            font=f.small,
            text_color=t.TEXT_SECONDARY,
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))

        ctk.CTkEntry(
            card,
            textvariable=self.default_root_var,
            height=36,
            corner_radius=6,
            border_color=t.BORDER_STRONG,
            fg_color=t.BG_PANEL,
            text_color=t.TEXT_PRIMARY,
            font=f.body,
        ).grid(row=2, column=0, sticky="ew", padx=(16, 8), pady=(0, 14))

        t.make_button(
            card, "参照…", self._browse_default_root, kind="outline", width=80, height=36
        ).grid(row=2, column=1, padx=(0, 16), pady=(0, 14))
        return card

    def _build_job_io_card(self, parent: tk.Misc) -> ctk.CTkFrame:
        f = t.fonts()
        card = ctk.CTkFrame(
            parent, fg_color=t.BG_HEADER, corner_radius=8, border_width=1, border_color=t.BORDER_STRONG
        )
        card.columnconfigure(0, weight=1)

        self.job_video_info = ctk.CTkLabel(
            card,
            text="",
            font=f.body_bold,
            text_color=t.TEXT_PRIMARY,
            anchor="w",
            justify="left",
        )
        self.job_video_info.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(12, 8))

        ctk.CTkLabel(
            card,
            text="この予約の出力先フォルダー",
            font=f.small_bold,
            text_color=t.TEXT_SECONDARY,
            anchor="w",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=16)

        ctk.CTkEntry(
            card,
            textvariable=self.job_output_var,
            height=36,
            corner_radius=6,
            border_color=t.BORDER_STRONG,
            fg_color=t.BG_PANEL,
            text_color=t.TEXT_PRIMARY,
            font=f.body,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=(16, 8), pady=(4, 2))

        t.make_button(
            card, "参照…", self._browse_job_output, kind="outline", width=80, height=36
        ).grid(row=2, column=2, padx=(0, 16), pady=(4, 2))

        ctk.CTkLabel(
            card,
            textvariable=self.job_output_preview_var,
            font=f.small,
            text_color=t.TEAL_TEXT,
            anchor="w",
            wraplength=600,
        ).grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(2, 8))

        ctk.CTkLabel(
            card,
            text="撮影日時取得用サムネイル画像（任意）",
            font=f.small_bold,
            text_color=t.TEXT_SECONDARY,
            anchor="w",
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=16)

        ctk.CTkEntry(
            card,
            textvariable=self.job_thumb_var,
            height=34,
            corner_radius=6,
            border_color=t.BORDER_STRONG,
            fg_color=t.BG_PANEL,
            text_color=t.TEXT_PRIMARY,
            placeholder_text="未指定",
            font=f.small,
        ).grid(row=5, column=0, sticky="ew", padx=(16, 8), pady=(4, 12))

        t.make_button(
            card, "参照…", self._browse_job_thumb, kind="outline", width=76, height=34
        ).grid(row=5, column=1, padx=(0, 6), pady=(4, 12))

        t.make_button(
            card, "クリア", lambda: self.job_thumb_var.set(""), kind="ghost", width=64, height=34
        ).grid(row=5, column=2, padx=(0, 16), pady=(4, 12))

        self.reset_failed_chk = ctk.CTkCheckBox(
            card,
            text="保存時に「失敗」状態を解除して「待機中」に戻す",
            variable=self.reset_failed_var,
            font=f.small_bold,
            text_color=t.TEXT_PRIMARY,
            fg_color=t.TEAL,
            hover_color=t.TEAL_HOVER,
        )
        return card

    def _populate_fields(self, container: tk.Misc, keys: tuple[str, ...] | list[str]) -> None:
        f = t.fonts()
        for row_idx, key in enumerate(keys):
            lbl_text = FRIENDLY_LABELS.get(key, key)
            ctk.CTkLabel(
                container,
                text=lbl_text,
                font=f.body,
                text_color=t.TEXT_PRIMARY,
                anchor="w",
            ).grid(row=row_idx, column=0, sticky="w", padx=(0, 16), pady=5)

            if key in self._bool_keys:
                var: tk.Variable = tk.BooleanVar(value=bool(self._engine_defaults[key]))
                chk = ctk.CTkCheckBox(
                    container,
                    text="",
                    variable=var,
                    fg_color=t.TEAL,
                    hover_color=t.TEAL_HOVER,
                    width=28,
                )
                chk.grid(row=row_idx, column=1, sticky="w", pady=5)
            elif key in self._choices:
                var = tk.StringVar(value=self._format_value(key, self._engine_defaults[key]))
                menu = ctk.CTkOptionMenu(
                    container,
                    variable=var,
                    values=list(self._choices[key]),
                    width=180,
                    height=34,
                    corner_radius=6,
                    fg_color=t.BG_HEADER,
                    button_color=t.TEAL_SOFT,
                    button_hover_color=t.TEAL_SOFT_HOVER,
                    text_color=t.TEXT_PRIMARY,
                    dropdown_fg_color=t.BG_PANEL,
                    dropdown_text_color=t.TEXT_PRIMARY,
                    font=f.body,
                )
                menu.grid(row=row_idx, column=1, sticky="w", pady=5)
            else:
                var = tk.StringVar(value=self._format_value(key, self._engine_defaults[key]))
                ent = ctk.CTkEntry(
                    container,
                    textvariable=var,
                    height=34,
                    corner_radius=6,
                    border_color=t.BORDER_STRONG,
                    fg_color=t.BG_PANEL,
                    text_color=t.TEXT_PRIMARY,
                    font=f.body,
                )
                ent.grid(row=row_idx, column=1, sticky="ew", pady=5)

            self.param_vars[key] = var

    # ---- Mode Openers ----------------------------------------------------

    def open_for_default(self, current_settings: dict[str, Any], default_output_root: str) -> None:
        self._mode = "default"
        self._editing_job = None
        self.title_label.configure(text="基本設定（初期値）")
        self.reset_or_copy_btn.configure(text="初期値に戻す")
        self.save_top_btn.configure(text="基本設定を保存")

        self.job_io_card.grid_forget()
        self.default_io_card.grid(row=0, column=0, sticky="ew", pady=(2, 12), padx=(0, 8))

        self.default_root_var.set(default_output_root)
        self._load_values_into_vars(current_settings)
        self.scroll.scroll_to_top()

    def open_for_job(self, job: Reservation) -> None:
        self._mode = "job"
        self._editing_job = job
        short_name = job.video.name if len(job.video.name) <= 20 else f"{job.video.name[:17]}..."
        self.title_label.configure(text=f"個別設定 — {short_name}")
        self.reset_or_copy_btn.configure(text="基本設定を反映")
        self.save_top_btn.configure(text="この予約に保存")

        self.default_io_card.grid_forget()
        self.job_io_card.grid(row=0, column=0, sticky="ew", pady=(2, 12), padx=(0, 8))

        self.job_video_info.configure(text=f"対象動画: {job.video}")
        self.job_output_var.set(str(job.output))

        t_root = job.settings.get("THUMBNAIL_ROOT", "")
        t_name = job.settings.get("THUMBNAIL_IMAGE_NAME", "")
        self.job_thumb_var.set(str(Path(t_root) / t_name) if (t_root and t_name) else "")

        if job.state == "failed":
            self.reset_failed_var.set(True)
            self.reset_failed_chk.grid(row=6, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 12))
        else:
            self.reset_failed_chk.grid_forget()

        self._load_values_into_vars(job.settings)
        self._update_job_output_preview()
        self.scroll.scroll_to_top()

    # ---- Value Marshalling & Validation ----------------------------------

    def _format_value(self, key: str, value: Any) -> str:
        if key == "YOLO_MODEL":
            return str(value).removeprefix("yolo11").removesuffix(".pt")
        if key == "YOLO_TRACK_ID" and value is None:
            return ""
        if isinstance(value, list):
            return ", ".join(map(str, value))
        return str(value)

    def _load_values_into_vars(self, settings: dict[str, Any]) -> None:
        for key, var in self.param_vars.items():
            raw = settings.get(key, self._engine_defaults[key])
            if key in self._bool_keys:
                var.set(bool(raw))
            else:
                var.set(self._format_value(key, raw))

    def _collect_validated_params(self) -> dict[str, Any]:
        collected: dict[str, Any] = {}
        for key, var in self.param_vars.items():
            if key in self._bool_keys:
                collected[key] = bool(var.get())
                continue
            raw = str(var.get()).strip()
            label = FRIENDLY_LABELS.get(key, key)
            if key == "YOLO_MODEL":
                if raw not in self._choices[key]:
                    raise ValueError("YOLOモデルサイズは n / s / m / l / x から選択してください。")
                collected[key] = f"yolo11{raw}.pt"
            elif key in self._choices:
                if raw not in self._choices[key]:
                    raise ValueError(f"「{label}」の選択肢を確認してください。")
                collected[key] = raw
            elif key == "YOLO_TRACK_ID":
                collected[key] = None if not raw else int(raw)
            elif key == "YOLO_CLASSES":
                classes = [int(part.strip()) for part in raw.split(",") if part.strip()]
                if not classes:
                    raise ValueError("検出対象クラスIDを1つ以上入力してください（例: 0）。")
                collected[key] = classes
            elif key in self._int_keys:
                collected[key] = int(raw)
            elif key in self._float_keys:
                collected[key] = float(raw)
            else:
                collected[key] = raw

        # Validate RTMPose model + resolution compatibility
        self._resolve_rtmlib_fn(
            collected["MODEL_MODE"],
            collected["RTMLIB_POSE_MODEL"],
            collected["RTMLIB_POSE_INPUT_SIZE"],
            collected["RTMLIB_PERSON_DETECTOR"],
        )
        return collected

    # ---- Actions ---------------------------------------------------------

    def _handle_secondary_action(self) -> None:
        if self._mode == "default":
            self._load_values_into_vars(self._engine_defaults)
        else:
            self._load_values_into_vars(self._get_current_defaults())

    def _handle_save(self) -> None:
        try:
            params = self._collect_validated_params()
        except ValueError as exc:
            messagebox.showerror("設定値エラー", f"入力内容を確認してください。\n\n{exc}", parent=self.winfo_toplevel())
            return

        if self._mode == "default":
            root_path = self.default_root_var.get().strip()
            if not root_path:
                messagebox.showerror("設定値エラー", "既定の出力親フォルダーを指定してください。", parent=self.winfo_toplevel())
                return
            self._on_save_default(params, root_path)
        else:
            if self._editing_job is None:
                return
            dest_raw = self.job_output_var.get().strip()
            if not dest_raw:
                messagebox.showerror("出力先エラー", "この予約の出力先フォルダーを指定してください。", parent=self.winfo_toplevel())
                return
            thumb_raw = self.job_thumb_var.get().strip()
            if thumb_raw and not Path(thumb_raw).expanduser().is_file():
                messagebox.showerror(
                    "サムネイルが見つかりません",
                    f"指定されたサムネイル画像が見つかりません。\n{thumb_raw}",
                    parent=self.winfo_toplevel(),
                )
                return
            merged = deepcopy(self._editing_job.settings)
            merged.update(params)
            if thumb_raw:
                tp = Path(thumb_raw).expanduser().resolve()
                merged["THUMBNAIL_ROOT"] = str(tp.parent)
                merged["THUMBNAIL_IMAGE_NAME"] = tp.name
            else:
                merged["THUMBNAIL_ROOT"] = ""
                merged["THUMBNAIL_IMAGE_NAME"] = ""
            self._on_save_job(
                self._editing_job.id,
                merged,
                Path(dest_raw).expanduser(),
                bool(self.reset_failed_var.get()),
            )

    def _browse_default_root(self) -> None:
        cur = self.default_root_var.get().strip() or str(Path.home())
        chosen = filedialog.askdirectory(
            parent=self.winfo_toplevel(), title="既定の出力親フォルダーを選択", initialdir=cur
        )
        if chosen:
            self.default_root_var.set(chosen)

    def _browse_job_output(self) -> None:
        cur = self.job_output_var.get().strip()
        init_dir = str(Path(cur).parent) if cur else str(Path.home())
        chosen = filedialog.askdirectory(
            parent=self.winfo_toplevel(), title="この予約の出力先フォルダーを選択", initialdir=init_dir
        )
        if chosen:
            self.job_output_var.set(chosen)

    def _browse_job_thumb(self) -> None:
        init_dir = str(self._editing_job.video.parent) if self._editing_job else str(Path.home())
        chosen = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="撮影日時取得用のサムネイル画像を選択",
            initialdir=init_dir,
            filetypes=[("画像ファイル", "*.jpg *.JPG *.jpeg *.JPEG *.png *.PNG"), ("すべて", "*.*")],
        )
        if chosen:
            self.job_thumb_var.set(chosen)

    def _update_job_output_preview(self) -> None:
        raw = self.job_output_var.get().strip()
        if not raw:
            self.job_output_preview_var.set("出力先フォルダーを指定してください。")
            return
        try:
            names = self._output_names_fn(Path(raw))
            self.job_output_preview_var.set("生成ファイル:  " + "  /  ".join(names.values()))
        except ValueError:
            self.job_output_preview_var.set("出力先フォルダーを指定してください。")
