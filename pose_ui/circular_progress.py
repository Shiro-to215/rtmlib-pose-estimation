"""Smooth anti-aliased circular progress ring widget rendered via Pillow."""
from __future__ import annotations

import math
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from . import theme as t


class CircularProgress(tk.Canvas):
    """Single-lap 0..100% circular ring (0-50% YOLO, 50-100% RTMPose) with center status."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        diameter: int = 184,
        thickness: int = 15,
        bg: str = t.BG_PANEL,
    ) -> None:
        super().__init__(
            master,
            width=diameter,
            height=diameter,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self._diameter = diameter
        self._thickness = thickness
        self._bg_hex = bg
        self._percent: int = 0
        self._phase_title: str = "待機中"
        self._phase_sub: str = "予約を開始すると進捗を表示"
        self._tone: str = "idle"  # "idle" | "yolo" | "rtmpose" | "done" | "stopping"
        self._ring_photo: ImageTk.PhotoImage | None = None

        f = t.fonts()
        cx = diameter // 2
        cy = diameter // 2
        self._img_id = self.create_image(cx, cy, anchor="center")
        self._pct_id = self.create_text(
            cx,
            cy - 18,
            text="0%",
            font=(f.family, 24, "bold"),
            fill=t.TEXT_MUTED,
        )
        self._phase_id = self.create_text(
            cx,
            cy + 14,
            text="待機中",
            font=(f.family, 13, "bold"),
            fill=t.TEXT_SECONDARY,
        )
        self._sub_id = self.create_text(
            cx,
            cy + 36,
            text="",
            font=(f.family, 10),
            fill=t.TEXT_MUTED,
        )
        self._redraw()

    def set_idle(self, subtitle: str = "") -> None:
        self._percent = 0
        self._phase_title = "待機中"
        self._phase_sub = subtitle
        self._tone = "idle"
        self._redraw()

    def set_starting(self) -> None:
        self._percent = 0
        self._phase_title = "起動中..."
        self._phase_sub = "モデル初期化"
        self._tone = "yolo"
        self._redraw()

    def set_progress(self, percent: int, phase_code: str) -> None:
        pct = max(0, min(100, int(percent)))
        self._percent = pct
        upper = phase_code.strip().upper()
        if upper == "YOLO":
            self._phase_title = "YOLO"
            self._phase_sub = "人物検出・追跡 (1/2)"
            self._tone = "yolo"
        else:
            self._phase_title = "RTMPose"
            self._phase_sub = "骨格推定 (2/2)"
            self._tone = "rtmpose"
        self._redraw()

    def set_stopping(self) -> None:
        self._phase_title = "中断処理中"
        self._phase_sub = "待機リストへ戻します"
        self._tone = "stopping"
        self._redraw()

    def set_done(self) -> None:
        self._percent = 100
        self._phase_title = "完了"
        self._phase_sub = ""
        self._tone = "done"
        self._redraw()

    def _redraw(self) -> None:
        if not self.winfo_exists():
            return
        scale = 3  # 3x supersampling for crisp anti-aliased ring edges
        size = self._diameter * scale
        stroke = self._thickness * scale
        pad = (8 * scale) + stroke // 2

        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        bbox = (pad, pad, size - pad, size - pad)

        # Track ring
        track_rgb = _hex_to_rgba("#E2EBE8", 255)
        draw.arc(bbox, start=0, end=360, fill=track_rgb, width=stroke)

        # Subtle 50% milestone marker at bottom (90 degrees in PIL coordinates)
        cx = size / 2
        cy = size / 2
        outer_radius = (size - 2 * pad) / 2
        mid_radius = outer_radius - (stroke / 2.0)
        inner_r = outer_radius - stroke - (scale * 1.5)
        outer_r = outer_radius + (scale * 1.5)
        tick_angle = math.radians(90)
        draw.line(
            [
                (cx + inner_r * math.cos(tick_angle), cy + inner_r * math.sin(tick_angle)),
                (cx + outer_r * math.cos(tick_angle), cy + outer_r * math.sin(tick_angle)),
            ],
            fill=_hex_to_rgba("#FFFFFF", 235),
            width=max(2, scale * 2),
        )

        # Active arc
        arc_hex, pct_color, phase_color = {
            "idle": (t.TEAL, t.TEXT_MUTED, t.TEXT_SECONDARY),
            "yolo": (t.TEAL, t.TEXT_PRIMARY, t.TEAL_TEXT),
            "rtmpose": (t.POSE_BLUE, t.TEXT_PRIMARY, t.POSE_BLUE),
            "done": (t.SUCCESS, t.SUCCESS, t.SUCCESS),
            "stopping": (t.DANGER, t.DANGER, t.DANGER),
        }[self._tone]

        if self._percent > 0:
            sweep = (self._percent / 100.0) * 360.0
            start_deg = -90.0
            end_deg = start_deg + sweep
            arc_rgba = _hex_to_rgba(arc_hex, 255)
            draw.arc(bbox, start=start_deg, end=end_deg, fill=arc_rgba, width=stroke)

            # Seamless rounded end caps aligned with PIL's stroke centerline
            if self._percent < 100:
                cap_r = (stroke / 2.0) - (scale * 0.25)
                for deg in (start_deg, end_deg):
                    rad = math.radians(deg)
                    px = cx + mid_radius * math.cos(rad)
                    py = cy + mid_radius * math.sin(rad)
                    draw.ellipse(
                        (px - cap_r, py - cap_r, px + cap_r, py + cap_r),
                        fill=arc_rgba,
                    )

        smooth = img.resize((self._diameter, self._diameter), Image.Resampling.LANCZOS)
        self._ring_photo = ImageTk.PhotoImage(smooth)
        self.itemconfigure(self._img_id, image=self._ring_photo)
        self.itemconfigure(self._pct_id, text=f"{self._percent}%", fill=pct_color)
        self.itemconfigure(self._phase_id, text=self._phase_title, fill=phase_color)
        self.itemconfigure(self._sub_id, text=self._phase_sub)


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)
