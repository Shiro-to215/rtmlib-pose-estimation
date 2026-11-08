"""Clean-light teal & slate design system for the RTMPose GUI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Callable, Literal

import customtkinter as ctk

# ---- Palette (Clean Light + Calm Teal / Slate) ---------------------------
BG_WINDOW = "#F2F5F4"          # Subtle sage-tinted light neutral window backdrop
BG_PANEL = "#FFFFFF"           # Primary panel & card surface
BG_SUBTLE = "#EBF0EE"          # Muted inset background
BG_HEADER = "#F8FAFA"          # Light toolbar surface

BG_ROW = "#FFFFFF"
BG_ROW_HOVER = "#F4F9F8"
BG_ROW_SELECTED = "#E2F2EE"

BORDER = "#D4DFDC"
BORDER_STRONG = "#B2C4BE"
BORDER_FOCUS = "#0F766E"

TEXT_PRIMARY = "#1E293B"       # Slate 800
TEXT_SECONDARY = "#475569"     # Slate 600
TEXT_MUTED = "#64748B"         # Slate 500
TEXT_ON_ACCENT = "#FFFFFF"

# Accents
TEAL = "#0F766E"               # Primary brand / YOLO active
TEAL_HOVER = "#115E59"
TEAL_SOFT = "#E4F3F0"
TEAL_SOFT_HOVER = "#D0EBE6"
TEAL_TEXT = "#0B534D"

POSE_BLUE = "#0369A1"          # RTMPose phase ring color (deep ocean cyan)
POSE_SOFT = "#E0F2FE"

SUCCESS = "#15803D"
SUCCESS_SOFT = "#DCFCE7"

DANGER = "#C8332B"
DANGER_HOVER = "#A62620"
DANGER_SOFT = "#FEF2F2"
DANGER_BORDER = "#F5C2C0"

DISABLED_BG = "#E2E8F0"
DISABLED_TEXT = "#94A3B8"

LOG_BG = "#F8FAFC"
LOG_BORDER = "#CBD5E1"
PREVIEW_BG = "#E2E8E6"

RADIUS_PANEL = 10
RADIUS_ITEM = 8
RADIUS_BTN = 7

_UI_FONT_CANDIDATES = (
    "Yu Gothic UI",
    "Meiryo UI",
    "BIZ UDPGothic",
    "Hiragino Sans",
    "Noto Sans CJK JP",
    "Segoe UI",
)
_MONO_FONT_CANDIDATES = (
    "BIZ UDGothic",
    "Cascadia Mono",
    "Consolas",
    "Yu Gothic UI",
    "Menlo",
)


@dataclass
class FontSet:
    family: str
    mono_family: str
    h1: ctk.CTkFont
    h2: ctk.CTkFont
    h3: ctk.CTkFont
    body: ctk.CTkFont
    body_bold: ctk.CTkFont
    small: ctk.CTkFont
    small_bold: ctk.CTkFont
    btn: ctk.CTkFont
    btn_lg: ctk.CTkFont
    mono: tuple[str, int]


_FONTS: FontSet | None = None


def _select_font_family(root: tk.Misc, candidates: tuple[str, ...]) -> str:
    available = set(tkfont.families(root))
    for name in candidates:
        if name in available:
            return name
    return tkfont.nametofont("TkDefaultFont", root).actual("family")


def init_theme(root: tk.Misc) -> FontSet:
    global _FONTS
    ctk.set_appearance_mode("light")
    try:
        from customtkinter.windows.widgets.core_rendering import DrawEngine

        if DrawEngine.preferred_drawing_method == "circle_shapes":
            DrawEngine.preferred_drawing_method = "polygon_shapes"
    except Exception:
        pass
    family = _select_font_family(root, _UI_FONT_CANDIDATES)
    mono = _select_font_family(root, _MONO_FONT_CANDIDATES)
    _FONTS = FontSet(
        family=family,
        mono_family=mono,
        h1=ctk.CTkFont(family=family, size=18, weight="bold"),
        h2=ctk.CTkFont(family=family, size=15, weight="bold"),
        h3=ctk.CTkFont(family=family, size=13, weight="bold"),
        body=ctk.CTkFont(family=family, size=13),
        body_bold=ctk.CTkFont(family=family, size=13, weight="bold"),
        small=ctk.CTkFont(family=family, size=12),
        small_bold=ctk.CTkFont(family=family, size=12, weight="bold"),
        btn=ctk.CTkFont(family=family, size=13, weight="bold"),
        btn_lg=ctk.CTkFont(family=family, size=14, weight="bold"),
        mono=(mono, 10),
    )
    return _FONTS


def fonts() -> FontSet:
    if _FONTS is None:
        raise RuntimeError("init_theme() must be called after creating root window.")
    return _FONTS


ButtonKind = Literal["primary", "outline", "tonal", "danger", "danger_fill", "ghost"]


def make_button(
    master: tk.Misc,
    text: str,
    command: Callable[[], Any] | None = None,
    *,
    kind: ButtonKind = "outline",
    width: int = 96,
    height: int = 36,
    large: bool = False,
) -> ctk.CTkButton:
    f = fonts()
    palette = {
        "primary": dict(
            fg_color=TEAL,
            hover_color=TEAL_HOVER,
            text_color=TEXT_ON_ACCENT,
            border_width=0,
            text_color_disabled=DISABLED_TEXT,
        ),
        "outline": dict(
            fg_color=BG_PANEL,
            hover_color=BG_SUBTLE,
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color=BORDER_STRONG,
            text_color_disabled=DISABLED_TEXT,
        ),
        "tonal": dict(
            fg_color=TEAL_SOFT,
            hover_color=TEAL_SOFT_HOVER,
            text_color=TEAL_TEXT,
            border_width=1,
            border_color="#B5DDD6",
            text_color_disabled=DISABLED_TEXT,
        ),
        "danger": dict(
            fg_color=BG_PANEL,
            hover_color=DANGER_SOFT,
            text_color=DANGER,
            border_width=1,
            border_color=DANGER_BORDER,
            text_color_disabled=DISABLED_TEXT,
        ),
        "danger_fill": dict(
            fg_color=DANGER,
            hover_color=DANGER_HOVER,
            text_color=TEXT_ON_ACCENT,
            border_width=0,
            text_color_disabled=DISABLED_TEXT,
        ),
        "ghost": dict(
            fg_color="transparent",
            hover_color=BG_SUBTLE,
            text_color=TEXT_SECONDARY,
            border_width=0,
            text_color_disabled=DISABLED_TEXT,
        ),
    }[kind]
    btn = ctk.CTkButton(
        master,
        text=text,
        command=command,
        width=width,
        height=height,
        corner_radius=RADIUS_BTN,
        font=f.btn_lg if large else f.btn,
        **palette,
    )
    btn._btn_kind = kind  # type: ignore[attr-defined]
    return btn


def set_btn_state(btn: ctk.CTkButton, enabled: bool) -> None:
    kind = getattr(btn, "_btn_kind", "outline")
    btn.configure(state="normal" if enabled else "disabled")
    if kind == "primary":
        btn.configure(fg_color=TEAL if enabled else DISABLED_BG)
    elif kind == "danger_fill":
        btn.configure(fg_color=DANGER if enabled else DISABLED_BG)


def parse_dnd_files(root: tk.Misc, raw_data: str) -> list[Path]:
    """Parse TkinterDnD file drop payload into Path objects."""
    if not raw_data:
        return []
    try:
        items = root.tk.splitlist(raw_data)
    except tk.TclError:
        items = raw_data.split()
    paths: list[Path] = []
    for item in items:
        cleaned = str(item).strip().strip("{}")
        if cleaned:
            paths.append(Path(cleaned))
    return paths


def register_drop_target(
    widget: tk.Misc,
    on_drop_paths: Callable[[list[Path]], None],
) -> bool:
    """Register file drag-and-drop on a widget if TkinterDnD is active."""
    try:
        from tkinterdnd2 import DND_FILES
    except ImportError:
        return False

    target = getattr(widget, "_canvas", widget)
    for candidate in (widget, target):
        try:
            candidate.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            candidate.dnd_bind(  # type: ignore[attr-defined]
                "<<Drop>>",
                lambda event: on_drop_paths(parse_dnd_files(widget.winfo_toplevel(), getattr(event, "data", ""))),
            )
            return True
        except Exception:
            continue
    return False


class SmoothScrollFrame(tk.Frame):
    """Smooth, flicker-free scrollable frame for lists and forms."""

    def __init__(self, master: tk.Misc, *, bg: str = BG_PANEL) -> None:
        self._container = tk.Frame(master, bg=bg, highlightthickness=0, bd=0)
        self._container.rowconfigure(0, weight=1)
        self._container.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self._container,
            bg=bg,
            highlightthickness=0,
            bd=0,
            yscrollincrement=20,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.scrollbar = ctk.CTkScrollbar(
            self._container,
            orientation="vertical",
            command=self.canvas.yview,
            fg_color=bg,
            button_color=BORDER_STRONG,
            button_hover_color=TEXT_MUTED,
            width=12,
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        self.canvas.configure(yscrollcommand=self._on_yscroll)

        super().__init__(self.canvas, bg=bg, highlightthickness=0, bd=0)
        self._win_id = self.canvas.create_window((0, 0), window=self, anchor="nw")
        self._sync_job: str | None = None

        self.bind("<Configure>", self._schedule_sync, add="+")
        self.canvas.bind("<Configure>", self._on_canvas_resize, add="+")
        self.canvas.bind("<Enter>", self._bind_wheel, add="+")
        self.canvas.bind("<Leave>", self._unbind_wheel, add="+")

    @property
    def outer(self) -> tk.Frame:
        return self._container

    def _on_yscroll(self, first: str | float, last: str | float) -> None:
        self.scrollbar.set(first, last)
        f_val, l_val = float(first), float(last)
        if f_val <= 0.001 and l_val >= 0.999:
            self.scrollbar.grid_remove()
        else:
            self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(2, 0))

    def _on_canvas_resize(self, event: tk.Event) -> None:
        if event.width > 1:
            self.canvas.itemconfigure(self._win_id, width=event.width)
        self._schedule_sync()

    def _schedule_sync(self, _event: tk.Event | None = None) -> None:
        if self._sync_job is None and self.winfo_exists():
            self._sync_job = self.after_idle(self._update_scrollregion)

    def _update_scrollregion(self) -> None:
        self._sync_job = None
        if not self.winfo_exists() or not self.canvas.winfo_exists():
            return
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        rw = max(cw, self.winfo_reqwidth())
        rh = max(ch, self.winfo_reqheight())
        self.canvas.configure(scrollregion=(0, 0, rw, rh))

    def _bind_wheel(self, _event: tk.Event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_linux_scroll_up)
        self.canvas.bind_all("<Button-5>", self._on_linux_scroll_down)

    def _unbind_wheel(self, _event: tk.Event) -> None:
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _can_scroll(self) -> bool:
        return self.winfo_reqheight() > self.canvas.winfo_height() + 2

    def _on_mousewheel(self, event: tk.Event) -> None:
        if not self.winfo_exists() or not self._can_scroll():
            return
        # Avoid scrolling if mouse is over a Text widget with its own scroll
        target = event.widget
        if isinstance(target, tk.Text):
            return
        delta = -1 if event.delta > 0 else 1
        steps = max(1, abs(int(event.delta / 120))) if abs(event.delta) >= 120 else 1
        self.canvas.yview_scroll(delta * steps * 2, "units")

    def _on_linux_scroll_up(self, _event: tk.Event) -> None:
        if self._can_scroll():
            self.canvas.yview_scroll(-2, "units")

    def _on_linux_scroll_down(self, _event: tk.Event) -> None:
        if self._can_scroll():
            self.canvas.yview_scroll(2, "units")

    def scroll_to_top(self) -> None:
        if self.canvas.winfo_exists():
            self.canvas.yview_moveto(0.0)
