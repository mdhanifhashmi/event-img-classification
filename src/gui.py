"""Rounded window for choosing folders and sorting event photos."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.icons import GROUP_ICONS, ctk_icon, write_app_icon

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "categories.yaml"
APP_ICON = ROOT / "assets" / "app.ico"

BLUE = "#106EBE"
BLUE_DEEP = "#0B4F8C"
BLUE_HOVER = "#0C8FD4"
MINT = "#0FFCBE"
MINT_SOFT = "#E8FFF8"
WHITE = "#FFFFFF"
BG = "#F3FBFF"
SURFACE = "#FFFFFF"
INK = "#0B3A66"
MUTED = "#5A7A96"
LINE = "#D4E8F5"
FIELD = "#F0FAFF"
ACCENT = BLUE
ACCENT_HOVER = "#0C5A9C"
RAIL = "#106EBE"
RAIL_MUTED = "#D5ECFA"
DANGER = "#D64545"
OK = "#0AAF8A"
BUSY = MINT
CREAM = WHITE
DISABLED = "#B7D4EA"
DISABLED_TEXT = "#7FA3BF"


def _enable_sharp_text() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        return


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mix(start: str, end: str, amount: float) -> str:
    left = _hex_to_rgb(start)
    right = _hex_to_rgb(end)
    return _rgb_to_hex(tuple(int(a + (b - a) * amount) for a, b in zip(left, right)))


class SorterApp:
    def __init__(self) -> None:
        _enable_sharp_text()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk()
        self.root.title("Event photos")
        self.root.minsize(860, 560)
        self.root.configure(fg_color=BG)
        self._set_window_icon()
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._running = False
        self._proc: subprocess.Popen | None = None
        self._errlog = None
        self._paused = False
        self._stopping = False
        self._outcome = False
        self._stop_deadline = 0.0
        self._pulse_job: str | None = None
        self._pulse_on = False
        self._anim_jobs: dict[int, str] = {}
        self._icons = {
            "camera": ctk_icon("camera", WHITE, 22),
            "folder": ctk_icon("folder", BLUE, 16),
            "folder-out": ctk_icon("folder-out", BLUE, 16),
            "sort": ctk_icon("sort", WHITE, 16),
            "sort-off": ctk_icon("sort", DISABLED_TEXT, 16),
            "open": ctk_icon("open", BLUE, 16),
            "save": ctk_icon("save", WHITE, 16),
            "save-off": ctk_icon("save", DISABLED_TEXT, 16),
            "back": ctk_icon("back", BLUE, 14),
            "photos": ctk_icon("photos", MINT, 20),
            "plus": ctk_icon("plus", WHITE, 14),
            "plus-dark": ctk_icon("plus", BLUE_DEEP, 14),
            "pause": ctk_icon("pause", BLUE, 16),
            "pause-off": ctk_icon("pause", DISABLED_TEXT, 16),
            "play": ctk_icon("play", BLUE, 16),
            "stop": ctk_icon("stop", DANGER, 16),
            "stop-off": ctk_icon("stop", DISABLED_TEXT, 16),
        }
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.keep_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Choose a mixed folder and a place to save the groups.")
        self.input_var.trace_add("write", lambda *_: self._refresh_buttons())
        self.output_var.trace_add("write", lambda *_: self._refresh_buttons())

        self.settings = self._load_group_settings()
        self._selected = ""
        self._group_buttons: dict[str, ctk.CTkButton] = {}
        self._group_icon_images: dict[str, ctk.CTkImage] = {}
        self._build()
        self._place_on_screen()
        self._refresh_buttons()
        self._set_status_tone("idle")

    def _set_window_icon(self) -> None:
        try:
            if not APP_ICON.exists():
                write_app_icon(APP_ICON)
        except Exception:
            return

        def apply() -> None:
            try:
                self.root.iconbitmap(str(APP_ICON))
            except Exception:
                return

        # CustomTkinter installs its own icon shortly after start, so set ours afterward.
        apply()
        self.root.after(300, apply)

    def _build(self) -> None:
        outer = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        outer.pack(fill="both", expand=True)

        accent = ctk.CTkFrame(outer, fg_color=MINT, corner_radius=0, width=5)
        accent.pack(side="left", fill="y")

        rail = ctk.CTkFrame(outer, fg_color=RAIL, corner_radius=0, width=248)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self._build_rail(rail)

        main = ctk.CTkFrame(outer, fg_color=BG, corner_radius=0)
        main.pack(side="left", fill="both", expand=True, padx=28, pady=24)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        self._main = main

        self.sort_view = ctk.CTkFrame(main, fg_color=BG, corner_radius=0)
        self.sort_view.grid(row=0, column=0, sticky="nsew")
        self.sort_view.grid_columnconfigure(0, weight=1)
        self.sort_view.grid_rowconfigure(7, weight=1)
        self._build_group_view(main)
        self._build_new_view(main)
        self._build_sort_view()

    def _build_sort_view(self) -> None:
        heading = ctk.CTkFrame(self.sort_view, fg_color=BG, corner_radius=0)
        heading.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(heading, image=self._icons["photos"], text="", width=28).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            heading,
            text="Sort a folder",
            text_color=INK,
            font=("Segoe UI", 26),
            anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            self.sort_view,
            text="Copies go into named groups. Choose a group on the left to see how it is defined.",
            text_color=MUTED,
            font=("Segoe UI", 13),
            anchor="w",
            justify="left",
            wraplength=540,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 16))

        self.input_entry, self.input_button = self._field_row(
            self.sort_view, 2, "Mixed photos", "Folder with every shot from the event", self.input_var, self._pick_input, "folder"
        )
        self.output_entry, self.output_button = self._field_row(
            self.sort_view, 3, "Save groups to", "A different folder for Stage, Guests, and the rest", self.output_var, self._pick_output, "folder-out"
        )

        self.keep_check = ctk.CTkCheckBox(
            self.sort_view,
            text="Keep photos already sorted in the output folder",
            variable=self.keep_var,
            fg_color=BLUE,
            hover_color=MINT,
            border_color=LINE,
            checkmark_color=WHITE,
            text_color=INK,
            font=("Segoe UI", 13),
            corner_radius=6,
        )
        self.keep_check.grid(row=4, column=0, sticky="w", pady=(4, 0))
        ctk.CTkLabel(
            self.sort_view,
            text="Adds this input to the groups. Leave this off to replace those groups.",
            text_color=MUTED,
            font=("Segoe UI", 12),
            anchor="w",
        ).grid(row=5, column=0, sticky="w", pady=(2, 12))

        actions = ctk.CTkFrame(self.sort_view, fg_color=BG, corner_radius=0)
        actions.grid(row=6, column=0, sticky="w", pady=(0, 16))
        self.sort_button = self._button(actions, "Sort photos", self._start, primary=True, icon="sort")
        self.sort_button.pack(side="left")
        self.pause_button = self._button(actions, "Pause", self._toggle_pause, primary=False, icon="pause")
        self.pause_button.pack(side="left", padx=(10, 0))
        self.stop_button = self._button(actions, "Stop", self._stop, primary=False, icon="stop", danger=True)
        self.stop_button.pack(side="left", padx=(10, 0))
        self.open_button = self._button(actions, "Open folder", self._open_output, primary=False, icon="open")
        self.open_button.pack(side="left", padx=(10, 0))

        panel = ctk.CTkFrame(self.sort_view, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=LINE)
        panel.grid(row=7, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)
        status_row = ctk.CTkFrame(panel, fg_color=SURFACE, corner_radius=0)
        status_row.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        self.status_dot = ctk.CTkFrame(status_row, width=10, height=10, corner_radius=5, fg_color=MUTED)
        self.status_dot.pack(side="left", padx=(2, 8))
        self.status_dot.pack_propagate(False)
        ctk.CTkLabel(
            status_row,
            textvariable=self.status_var,
            text_color=INK,
            font=("Segoe UI", 13),
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(side="left", fill="x", expand=True)

        self.log = ctk.CTkTextbox(
            panel,
            fg_color=FIELD,
            text_color=INK,
            font=("Segoe UI", 13),
            corner_radius=12,
            border_width=0,
            wrap="word",
            activate_scrollbars=True,
            scrollbar_button_color="#C5E4F4",
            scrollbar_button_hover_color=BLUE,
        )
        self.log.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.log.configure(state="disabled")

    def _build_rail(self, rail: ctk.CTkFrame) -> None:
        brand = ctk.CTkFrame(rail, fg_color=RAIL, corner_radius=0)
        brand.pack(fill="x", padx=18, pady=(22, 0))
        ctk.CTkLabel(brand, image=self._icons["camera"], text="").pack(side="left", padx=(0, 8), pady=(4, 0))
        titles = ctk.CTkFrame(brand, fg_color=RAIL, corner_radius=0)
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(titles, text="EVENT", text_color=MINT, font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w")
        title = ctk.CTkLabel(titles, text="Photos", text_color=WHITE, font=("Segoe UI", 26), anchor="w", cursor="hand2")
        title.pack(anchor="w")
        title.bind("<Button-1>", lambda _event: self._show_sort())
        title.bind("<Enter>", lambda _event: title.configure(text_color=MINT))
        title.bind("<Leave>", lambda _event: title.configure(text_color=WHITE))
        ctk.CTkLabel(
            rail,
            text="Group mixed event photos on this computer.",
            text_color=RAIL_MUTED,
            font=("Segoe UI", 13),
            anchor="w",
            justify="left",
            wraplength=190,
        ).pack(anchor="w", padx=22, pady=(8, 0))
        ctk.CTkFrame(rail, fg_color="#4B9AD8", height=1, corner_radius=0).pack(fill="x", padx=22, pady=16)
        ctk.CTkLabel(rail, text="GROUPS", text_color="#BFE3F7", font=("Segoe UI", 11, "bold"), anchor="w").pack(
            anchor="w", padx=22, pady=(0, 8)
        )
        self.new_group_button = ctk.CTkButton(
            rail,
            text="  New group",
            image=self._icons["plus"],
            compound="left",
            anchor="w",
            height=36,
            corner_radius=10,
            fg_color="#0D5CA0",
            hover_color="#0A4E88",
            text_color=WHITE,
            font=("Segoe UI", 14),
            hover=False,
            command=self._show_new_group,
        )
        self.new_group_button.pack(fill="x", padx=12, pady=(0, 8))
        self._wire_hover(self.new_group_button, rest="#0D5CA0", hover=MINT, mint_border=False, text_rest=WHITE, text_hover=BLUE_DEEP)
        self.new_group_button.bind("<Enter>", lambda _event: self.new_group_button.configure(image=self._icons["plus-dark"]), add="+")
        self.new_group_button.bind("<Leave>", lambda _event: self.new_group_button.configure(image=self._icons["plus"]), add="+")
        groups = ctk.CTkScrollableFrame(
            rail,
            fg_color=RAIL,
            corner_radius=0,
            scrollbar_button_color="#4B9AD8",
            scrollbar_button_hover_color=MINT,
        )
        groups.pack(fill="both", expand=True, padx=6, pady=(0, 12))
        self._groups_frame = groups
        for name in self._group_names():
            self._insert_group_button(name)

    def _build_group_view(self, parent: ctk.CTkFrame) -> None:
        view = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(3, weight=1)
        self.group_view = view

        self.back_button = ctk.CTkButton(
            view,
            text=" Back to sort",
            image=self._icons["back"],
            compound="left",
            command=self._show_sort,
            fg_color="transparent",
            hover_color=MINT_SOFT,
            text_color=BLUE,
            font=("Segoe UI", 13),
            anchor="w",
            height=32,
            corner_radius=8,
            hover=False,
        )
        self.back_button.grid(row=0, column=0, sticky="w")
        self._wire_hover(self.back_button, rest="transparent", hover=MINT_SOFT, mint_border=False, text_rest=BLUE, text_hover=BLUE_DEEP)

        self.group_title = ctk.CTkLabel(view, text="", text_color=INK, font=("Segoe UI", 26), anchor="w")
        self.group_title.grid(row=1, column=0, sticky="ew", pady=(10, 4))
        self.group_hint = ctk.CTkLabel(
            view,
            text="",
            text_color=MUTED,
            font=("Segoe UI", 13),
            anchor="w",
            justify="left",
            wraplength=540,
        )
        self.group_hint.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        self.prompt_box = ctk.CTkTextbox(
            view,
            fg_color=SURFACE,
            text_color=INK,
            font=("Segoe UI", 15),
            corner_radius=16,
            border_width=1,
            border_color=LINE,
            wrap="word",
        )
        self.prompt_box.grid(row=3, column=0, sticky="nsew")
        self.prompt_box.bind("<FocusIn>", lambda _event: self.prompt_box.configure(border_color=BLUE))
        self.prompt_box.bind("<FocusOut>", lambda _event: self.prompt_box.configure(border_color=LINE))

        foot = ctk.CTkFrame(view, fg_color=BG, corner_radius=0)
        foot.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        self.save_group = self._button(foot, "Save description", self._save_group, primary=True, icon="save")
        self.save_group.pack(side="left")
        self.group_status = ctk.CTkLabel(foot, text="", text_color=MUTED, font=("Segoe UI", 13), anchor="w")
        self.group_status.pack(side="left", padx=(12, 0))

    def _build_new_view(self, parent: ctk.CTkFrame) -> None:
        view = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(6, weight=1)
        self.new_view = view

        back = ctk.CTkButton(
            view,
            text=" Back to sort",
            image=self._icons["back"],
            compound="left",
            command=self._show_sort,
            fg_color="transparent",
            hover_color=MINT_SOFT,
            text_color=BLUE,
            font=("Segoe UI", 13),
            anchor="w",
            height=32,
            corner_radius=8,
            hover=False,
        )
        back.grid(row=0, column=0, sticky="w")
        self._wire_hover(back, rest="transparent", hover=MINT_SOFT, mint_border=False, text_rest=BLUE, text_hover=BLUE_DEEP)

        ctk.CTkLabel(view, text="New group", text_color=INK, font=("Segoe UI", 26), anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(10, 4)
        )
        ctk.CTkLabel(
            view,
            text="Name the folder, then describe the photos that belong in it. Sort again to start using it.",
            text_color=MUTED,
            font=("Segoe UI", 13),
            anchor="w",
            justify="left",
            wraplength=540,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(view, text="Group name", text_color=INK, font=("Segoe UI", 14, "bold"), anchor="w").grid(
            row=3, column=0, sticky="w"
        )
        self.new_name_var = tk.StringVar()
        self.new_name_entry = ctk.CTkEntry(
            view,
            textvariable=self.new_name_var,
            height=42,
            corner_radius=12,
            fg_color=FIELD,
            border_color=LINE,
            border_width=1,
            text_color=INK,
            placeholder_text="Cake table",
            font=("Segoe UI", 13),
        )
        self.new_name_entry.grid(row=4, column=0, sticky="ew", pady=(6, 12))
        self.new_name_entry.bind("<FocusIn>", lambda _event: self.new_name_entry.configure(border_color=BLUE, border_width=2))
        self.new_name_entry.bind("<FocusOut>", lambda _event: self.new_name_entry.configure(border_color=LINE, border_width=1))

        ctk.CTkLabel(view, text="Description", text_color=INK, font=("Segoe UI", 14, "bold"), anchor="w").grid(
            row=5, column=0, sticky="nw"
        )
        self.new_prompt = ctk.CTkTextbox(
            view,
            fg_color=SURFACE,
            text_color=INK,
            font=("Segoe UI", 15),
            corner_radius=16,
            border_width=1,
            border_color=LINE,
            wrap="word",
            height=140,
        )
        self.new_prompt.grid(row=6, column=0, sticky="nsew", pady=(6, 0))
        self.new_prompt.bind("<FocusIn>", lambda _event: self.new_prompt.configure(border_color=BLUE))
        self.new_prompt.bind("<FocusOut>", lambda _event: self.new_prompt.configure(border_color=LINE))

        foot = ctk.CTkFrame(view, fg_color=BG, corner_radius=0)
        foot.grid(row=7, column=0, sticky="ew", pady=(14, 0))
        self.create_group = self._button(foot, "Create group", self._create_group, primary=True, icon="plus")
        self.create_group.pack(side="left")
        ctk.CTkLabel(
            foot,
            text="Example: a photo of a wedding cake table",
            text_color=MUTED,
            font=("Segoe UI", 12),
            anchor="w",
        ).pack(side="left", padx=(12, 0))

    def _insert_group_button(self, name: str) -> None:
        glyph = GROUP_ICONS.get(name, "photos")
        image = ctk_icon(glyph, WHITE, 15)
        self._group_icon_images[name] = image
        button = ctk.CTkButton(
            self._groups_frame,
            text=f"  {name}",
            image=image,
            compound="left",
            anchor="w",
            height=36,
            corner_radius=10,
            fg_color=RAIL,
            hover_color="#0D5CA0",
            text_color=WHITE,
            font=("Segoe UI", 14),
            hover=False,
            command=lambda group=name: self._show_group(group),
        )
        review = self._group_buttons.get(self.settings.review_label)
        if review is not None and name != self.settings.review_label:
            button.pack(fill="x", pady=2, before=review)
        else:
            button.pack(fill="x", pady=2)
        self._wire_hover(button, rest=RAIL, hover="#0D5CA0", mint_border=False)
        self._group_buttons[name] = button

    def _reveal_group(self, name: str) -> None:
        canvas = getattr(self._groups_frame, "_parent_canvas", None)
        if canvas is None:
            return
        self._groups_frame.update_idletasks()
        canvas.yview_moveto(1.0)

    def _field_row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        title: str,
        hint: str,
        variable: tk.StringVar,
        command,
        icon_name: str,
    ) -> tuple[ctk.CTkEntry, ctk.CTkButton]:
        block = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        block.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(block, text=title, text_color=INK, font=("Segoe UI", 14, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(block, text=hint, text_color=MUTED, font=("Segoe UI", 12), anchor="w").grid(
            row=1, column=0, sticky="w", pady=(1, 6)
        )
        row_frame = ctk.CTkFrame(block, fg_color=BG, corner_radius=0)
        row_frame.grid(row=2, column=0, sticky="ew")
        row_frame.grid_columnconfigure(0, weight=1)
        entry = ctk.CTkEntry(
            row_frame,
            textvariable=variable,
            height=42,
            corner_radius=12,
            fg_color=FIELD,
            border_color=LINE,
            border_width=1,
            text_color=INK,
            font=("Segoe UI", 13),
        )
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        entry.bind("<FocusIn>", lambda _event, box=entry: box.configure(border_color=BLUE, border_width=2))
        entry.bind("<FocusOut>", lambda _event, box=entry: box.configure(border_color=LINE, border_width=1))
        entry.bind("<Enter>", lambda _event, box=entry: box.configure(border_color=MINT) if box.cget("state") != "disabled" else None)
        entry.bind("<Leave>", lambda _event, box=entry: box.configure(border_color=BLUE if box.focus_get() == box else LINE))
        browse = ctk.CTkButton(
            row_frame,
            text=" Browse",
            image=self._icons[icon_name],
            compound="left",
            command=command,
            width=110,
            height=42,
            corner_radius=12,
            fg_color=SURFACE,
            hover_color=MINT_SOFT,
            border_width=1,
            border_color=LINE,
            text_color=BLUE,
            font=("Segoe UI", 13),
            hover=False,
        )
        browse.grid(row=0, column=1)
        self._wire_hover(browse, rest=SURFACE, hover=MINT_SOFT, mint_border=True, text_rest=BLUE, text_hover=BLUE_DEEP)
        return entry, browse

    def _button(
        self, parent, text: str, command, *, primary: bool, icon: str, danger: bool = False
    ) -> ctk.CTkButton:
        if primary:
            button = ctk.CTkButton(
                parent,
                text=f"  {text}",
                image=self._icons[icon],
                compound="left",
                command=command,
                height=42,
                corner_radius=12,
                fg_color=BLUE,
                hover_color=BLUE_HOVER,
                text_color=WHITE,
                text_color_disabled=DISABLED_TEXT,
                font=("Segoe UI", 14, "bold"),
                hover=False,
            )
            self._wire_hover(button, rest=BLUE, hover=BLUE_HOVER, mint_border=False, text_rest=WHITE, text_hover=WHITE)
            return button
        button = ctk.CTkButton(
            parent,
            text=f"  {text}",
            image=self._icons[icon],
            compound="left",
            command=command,
            height=42,
            corner_radius=12,
            fg_color=SURFACE,
            hover_color=MINT_SOFT,
            border_width=1,
            border_color=LINE,
            text_color=DANGER if danger else BLUE,
            text_color_disabled=DISABLED_TEXT,
            font=("Segoe UI", 14),
            hover=False,
        )
        if danger:
            self._wire_hover(button, rest=SURFACE, hover="#FDEEEE", mint_border=False, text_rest=DANGER, text_hover=DANGER)
        else:
            self._wire_hover(button, rest=SURFACE, hover=MINT_SOFT, mint_border=True, text_rest=BLUE, text_hover=BLUE_DEEP)
        return button

    def _wire_hover(
        self,
        widget: ctk.CTkButton,
        *,
        rest: str,
        hover: str,
        mint_border: bool,
        text_rest: str | None = None,
        text_hover: str | None = None,
    ) -> None:
        widget._rest_color = rest  # noqa: SLF001 - small hover state for animation
        widget._hover_color_to = hover

        def enter(_event=None) -> None:
            if str(widget.cget("state")) == "disabled":
                return
            if self._is_selected_group(widget):
                return
            self._animate_widget(widget, rest, hover, border=MINT if mint_border else None, text=text_hover)

        def leave(_event=None) -> None:
            if self._is_selected_group(widget):
                return
            idle_border = LINE if mint_border and rest == SURFACE else None
            self._animate_widget(widget, hover, rest, border=idle_border, text=text_rest)

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _is_selected_group(self, widget: ctk.CTkButton) -> bool:
        if not self._selected:
            return False
        return self._group_buttons.get(self._selected) is widget

    def _animate_widget(
        self,
        widget: ctk.CTkButton,
        start: str,
        end: str,
        *,
        border: str | None = None,
        text: str | None = None,
        steps: int = 7,
    ) -> None:
        key = id(widget)
        previous = self._anim_jobs.pop(key, None)
        if previous is not None:
            self.root.after_cancel(previous)

        if start in {"transparent", "None"} or end in {"transparent", "None"}:
            widget.configure(fg_color=end)
            if border:
                widget.configure(border_color=border)
            if text:
                widget.configure(text_color=text)
            return

        def tick(step: int) -> None:
            amount = step / steps
            widget.configure(fg_color=_mix(start, end, amount))
            if step >= steps:
                self._anim_jobs.pop(key, None)
                if border:
                    widget.configure(border_color=border)
                if text:
                    widget.configure(text_color=text)
                return
            self._anim_jobs[key] = self.root.after(16, lambda: tick(step + 1))

        if border:
            widget.configure(border_color=border)
        if text:
            widget.configure(text_color=text)
        tick(1)

    def _flash_view(self) -> None:
        frames = (MINT_SOFT, "#F0FCFF", BG)

        def tick(index: int = 0) -> None:
            if index >= len(frames):
                self._main.configure(fg_color=BG)
                self.sort_view.configure(fg_color=BG)
                self.group_view.configure(fg_color=BG)
                self.new_view.configure(fg_color=BG)
                return
            color = frames[index]
            self._main.configure(fg_color=color)
            self.sort_view.configure(fg_color=color)
            self.group_view.configure(fg_color=color)
            self.new_view.configure(fg_color=color)
            self.root.after(45, lambda: tick(index + 1))

        tick()

    def _place_on_screen(self) -> None:
        self.root.update_idletasks()
        left, top, work_w, work_h = self._work_area()
        scale = self._window_scale()
        width = min(980, max(720, int((work_w - 48) / scale)))
        height = min(640, max(520, int((work_h - 96) / scale)))
        self.root.geometry(f"{width}x{height}")
        self.root.update_idletasks()
        outer_w, outer_h = self._outer_size()
        extra_h = max(0, outer_h - int(height * scale))
        if extra_h:
            height = max(520, int((work_h - extra_h - 12) / scale))
            self.root.geometry(f"{width}x{height}")
            self.root.update_idletasks()
            outer_w, outer_h = self._outer_size()
        x = left + max(0, (work_w - outer_w) // 2)
        y = top + max(0, (work_h - outer_h) // 2)
        self.root.geometry(f"+{int(x / scale)}+{int(y / scale)}")

    def _outer_size(self) -> tuple[int, int]:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            hwnd = ctypes.windll.user32.GetAncestor(self.root.winfo_id(), 2)
            rect = wintypes.RECT()
            if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return rect.right - rect.left, rect.bottom - rect.top
        return self.root.winfo_width(), self.root.winfo_height()

    def _window_scale(self) -> float:
        try:
            scale = float(ctk.ScalingTracker.get_window_scaling(self.root))
        except Exception:
            return 1.0
        return scale if scale > 0 else 1.0

    def _work_area(self) -> tuple[int, int, int, int]:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _pick_input(self) -> None:
        chosen = filedialog.askdirectory(title="Select the mixed photo folder")
        if chosen:
            self.input_var.set(chosen)

    def _pick_output(self) -> None:
        chosen = filedialog.askdirectory(title="Select where grouped copies should go")
        if chosen:
            self.output_var.set(chosen)

    def _refresh_buttons(self) -> None:
        if self._running:
            return
        ready = bool(self.input_var.get().strip() and self.output_var.get().strip())
        self._enable(self.pause_button, False)
        self._enable(self.stop_button, False)
        self._enable(self.sort_button, ready)
        output = self.output_var.get().strip()
        self._enable(self.open_button, bool(output) and Path(output).is_dir())

    def _set_busy(self, busy: bool) -> None:
        self._running = busy
        entry_state = "readonly" if busy else "normal"
        self.input_entry.configure(state=entry_state)
        self.output_entry.configure(state=entry_state)
        self._enable(self.input_button, not busy)
        self._enable(self.output_button, not busy)
        self.keep_check.configure(state="normal" if not busy else "disabled")
        if busy:
            self._paused = False
            self._stopping = False
            self._set_pause_label("pause")
            self._enable(self.sort_button, False)
            self._enable(self.open_button, False)
            self._enable(self.pause_button, True)
            self._enable(self.stop_button, True)
            self._set_status_tone("busy")
        else:
            self._paused = False
            self._stopping = False
            self._set_pause_label("pause")
            self._enable(self.pause_button, False)
            self._enable(self.stop_button, False)
            self._refresh_buttons()

    def _set_pause_label(self, mode: str) -> None:
        if mode == "resume":
            self.pause_button.configure(text="  Resume", image=self._icons["play"])
        elif mode == "pausing":
            self.pause_button.configure(text="  Pausing...", image=self._icons["pause"])
        else:
            self.pause_button.configure(text="  Pause", image=self._icons["pause"])

    def _enable(self, button: ctk.CTkButton, enabled: bool) -> None:
        button.configure(state="normal" if enabled else "disabled")
        if button is getattr(self, "pause_button", None) and not enabled:
            button.configure(image=self._icons["pause-off"])
            return
        if button is getattr(self, "stop_button", None):
            button.configure(image=self._icons["stop" if enabled else "stop-off"])
            return
        if button is getattr(self, "sort_button", None):
            if enabled:
                button.configure(fg_color=BLUE, text_color=WHITE, image=self._icons["sort"])
            else:
                button.configure(fg_color=DISABLED, text_color=DISABLED_TEXT, image=self._icons["sort-off"], border_color=DISABLED)
            return
        if button is getattr(self, "save_group", None):
            if enabled:
                button.configure(fg_color=BLUE, text_color=WHITE, image=self._icons["save"])
            else:
                button.configure(fg_color=DISABLED, text_color=DISABLED_TEXT, image=self._icons["save-off"], border_color=DISABLED)

    def _set_status_tone(self, tone: str) -> None:
        self._stop_pulse()
        color = {"idle": "#8FB8D4", "busy": MINT, "paused": BLUE_HOVER, "done": OK, "error": DANGER}.get(tone, MUTED)
        self.status_dot.configure(fg_color=color)
        if tone == "busy":
            self._pulse_on = True
            self._pulse()

    def _pulse(self) -> None:
        if not self._running or self._paused:
            return
        self._pulse_on = not self._pulse_on
        self.status_dot.configure(fg_color=MINT if self._pulse_on else BLUE)
        grow = 12 if self._pulse_on else 10
        self.status_dot.configure(width=grow, height=grow, corner_radius=grow // 2)
        self._pulse_job = self.root.after(380, self._pulse)

    def _stop_pulse(self) -> None:
        if self._pulse_job is not None:
            self.root.after_cancel(self._pulse_job)
            self._pulse_job = None
        self.status_dot.configure(width=10, height=10, corner_radius=5)

    def _paint_groups(self) -> None:
        for name, button in self._group_buttons.items():
            if name == self._selected:
                button.configure(fg_color=MINT, text_color=BLUE_DEEP, hover_color=MINT)
                glyph = GROUP_ICONS.get(name, "photos")
                image = ctk_icon(glyph, BLUE_DEEP, 15)
                self._group_icon_images[name] = image
                button.configure(image=image)
            else:
                button.configure(fg_color=RAIL, text_color=WHITE, hover_color="#0D5CA0")
                glyph = GROUP_ICONS.get(name, "photos")
                image = ctk_icon(glyph, WHITE, 15)
                self._group_icon_images[name] = image
                button.configure(image=image)

    def _show_sort(self) -> None:
        self._selected = ""
        self._paint_groups()
        self.group_view.grid_remove()
        self.new_view.grid_remove()
        self.sort_view.grid(row=0, column=0, sticky="nsew")
        self._flash_view()

    def _show_new_group(self) -> None:
        self._selected = ""
        self._paint_groups()
        self.sort_view.grid_remove()
        self.group_view.grid_remove()
        self.new_name_var.set("")
        self.new_prompt.delete("1.0", "end")
        self.new_view.grid(row=0, column=0, sticky="nsew")
        self._flash_view()
        self.new_name_entry.focus()

    def _create_group(self) -> None:
        try:
            from src.labels import add_category

            name = add_category(DEFAULT_CONFIG, self.new_name_var.get(), self.new_prompt.get("1.0", "end"))
            self.settings = self._load_group_settings()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Event photos", str(exc))
            return
        self._insert_group_button(name)
        self._reveal_group(name)
        self._show_group(name)
        self.group_status.configure(text="Created. Sort again to use this group.")

    def _show_group(self, name: str) -> None:
        self._selected = name
        self._paint_groups()
        self.sort_view.grid_remove()
        self.new_view.grid_remove()
        self.group_view.grid(row=0, column=0, sticky="nsew")
        self.group_title.configure(text=name)
        self.group_status.configure(text="")
        self._flash_view()
        review = name == self.settings.review_label
        category = next((item for item in self.settings.categories if item.name == name), None)
        self.prompt_box.configure(state="normal")
        self.prompt_box.delete("1.0", "end")
        if review or category is None:
            self.group_hint.configure(
                text="Photos land here when none of the groups above score high enough. This folder has no description of its own."
            )
            self.prompt_box.insert("1.0", "Assigned automatically during sorting.")
            self.prompt_box.configure(state="disabled")
            self._enable(self.save_group, False)
            return
        self.group_hint.configure(
            text="Each photo is compared with this sentence. Save it, then sort again to use the new wording."
        )
        self.prompt_box.insert("1.0", category.prompt)
        self._enable(self.save_group, True)

    def _save_group(self) -> None:
        name = self._selected
        prompt = self.prompt_box.get("1.0", "end").strip()
        try:
            from src.labels import save_category_prompt

            save_category_prompt(DEFAULT_CONFIG, name, prompt)
            self.settings = self._load_group_settings()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Event photos", str(exc))
            return
        self.group_status.configure(text="Saved. Sort again to apply it.")

    def _load_group_settings(self):
        from src.labels import load_settings

        return load_settings(DEFAULT_CONFIG)

    def _group_names(self) -> list[str]:
        try:
            return [*self.settings.names, self.settings.review_label]
        except Exception:
            return ["Stage", "Decoration", "Guests", "Food", "Venue"]

    def _start(self) -> None:
        input_dir = Path(self.input_var.get().strip())
        output_dir = Path(self.output_var.get().strip())
        if not input_dir.is_dir():
            messagebox.showerror("Event photos", "Choose an input folder that exists.")
            return
        if input_dir.resolve() == output_dir.resolve():
            messagebox.showerror("Event photos", "The output folder must be different from the input folder.")
            return

        self._clear_log()
        self._outcome = False
        self._queue = queue.Queue()
        try:
            self._launch(input_dir, output_dir)
        except OSError as exc:
            messagebox.showerror("Event photos", f"Could not start the sort: {exc}")
            return
        self._set_busy(True)
        self.status_var.set("Starting...")
        self._append("Starting sort")
        self.root.after(100, self._poll)

    def _worker_python(self) -> str:
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            console = python.with_name("python.exe")
            if console.exists():
                return str(console)
        return str(python)

    def _launch(self, input_dir: Path, output_dir: Path) -> None:
        """Run the sort in its own process so this window never waits on it."""
        command = [
            self._worker_python(),
            "-m",
            "src.runner",
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
            "--batch-size",
            "4",
        ]
        if self.keep_var.get():
            command.append("--keep-existing")
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._errlog = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        self._proc = subprocess.Popen(  # noqa: S603 - fixed arguments, no shell
            command,
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._errlog,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=environment,
            creationflags=flags,
        )
        threading.Thread(target=self._read_output, args=(self._proc, self._queue), daemon=True).start()

    @staticmethod
    def _read_output(proc: subprocess.Popen, events: queue.Queue) -> None:
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                events.put((str(event.get("kind", "status")), str(event.get("message", ""))))
        except (OSError, ValueError):
            pass
        finally:
            events.put(("exit", str(proc.wait())))

    def _send(self, command: str) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            return
        try:
            proc.stdin.write(command + "\n")
            proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def _kill_process(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            # The virtual environment launcher starts a second Python, so end the whole tree.
            subprocess.run(  # noqa: S603, S607
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            proc.kill()

    def _toggle_pause(self) -> None:
        if not self._running or self._stopping:
            return
        self._enable(self.pause_button, False)
        if self._paused:
            self._send("resume")
            self.status_var.set("Resuming...")
        else:
            self._send("pause")
            self._set_pause_label("pausing")
            self.status_var.set("Pausing at the next safe point. A photo batch in progress finishes first.")

    def _stop(self) -> None:
        if not self._running or self._stopping:
            return
        self._stopping = True
        self._enable(self.pause_button, False)
        self._enable(self.stop_button, False)
        self.status_var.set("Stopping. The photo batch in progress finishes first.")
        self._append("Stop requested")
        self._send("stop")
        self._stop_deadline = time.monotonic() + 10
        self.root.after(300, self._watch_stop)

    def _watch_stop(self) -> None:
        if not self._running or not self._stopping or self._outcome:
            return
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        if time.monotonic() >= self._stop_deadline:
            self._kill_process()
            self._append("The sort did not answer, so it was ended.")
            self._finish(
                "idle",
                "Stopped. Photos already copied are listed in manifest.csv. Sort again to continue.",
            )
            return
        self.root.after(300, self._watch_stop)

    def _finish(self, tone: str, text: str) -> None:
        self._outcome = True
        self.status_var.set(text)
        self._set_status_tone(tone)
        self._set_busy(False)

    def _error_tail(self) -> str:
        if self._errlog is None:
            return ""
        try:
            self._errlog.flush()
            self._errlog.seek(0)
            lines = [line.strip() for line in self._errlog.read().splitlines() if line.strip()]
        except (OSError, ValueError):
            return ""
        return lines[-1] if lines else ""

    def _poll(self) -> None:
        events = self._queue
        while True:
            try:
                kind, message = events.get_nowait()
            except queue.Empty:
                break
            if self._outcome:
                continue
            if kind == "status":
                self.status_var.set(message)
                self._append(message)
            elif kind == "state":
                if message == "paused":
                    self._paused = True
                    self._set_pause_label("resume")
                    self._enable(self.pause_button, not self._stopping)
                    self._set_status_tone("paused")
                    self.status_var.set("Paused. Press Resume to continue, or Stop to cancel.")
                    self._append("Paused")
                elif message == "resumed":
                    self._paused = False
                    self._set_pause_label("pause")
                    self._enable(self.pause_button, not self._stopping)
                    self._set_status_tone("busy")
                    self.status_var.set("Working...")
                    self._append("Resumed")
            elif kind == "error":
                self._append(message)
                self._finish("error", message)
                messagebox.showerror("Event photos", message)
                return
            elif kind == "done":
                self._append("Finished")
                self._finish("done", "Finished. Original photos were left in place.")
                return
            elif kind == "stopped":
                self._append("Stopped")
                self._finish("idle", "Stopped. Sort again to continue. Photos already analysed are reused.")
                return
            elif kind == "exit":
                detail = self._error_tail()
                text = "The sort closed unexpectedly."
                if detail:
                    text = f"{text} {detail}"
                self._append(text)
                self._finish("error", text)
                messagebox.showerror("Event photos", text)
                return
        if self._running and not self._outcome:
            self.root.after(100, self._poll)

    def _on_close(self) -> None:
        if self._running:
            if not messagebox.askyesno(
                "Event photos",
                "A sort is still running. Stop it and close the window?",
            ):
                return
            self._send("stop")
            self._kill_process()
        self.root.destroy()

    def _append(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _open_output(self) -> None:
        folder = self.output_var.get().strip()
        if folder and Path(folder).is_dir():
            os.startfile(folder)  # noqa: S606 - the user asked to open this local folder


def main() -> None:
    SorterApp().root.mainloop()


if __name__ == "__main__":
    main()
