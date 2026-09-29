"""Rounded window for choosing folders and sorting event photos."""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from argparse import Namespace
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "categories.yaml"

BG = "#EFECE6"
SURFACE = "#FBF9F6"
INK = "#1A1916"
MUTED = "#746E66"
LINE = "#E3DDD4"
FIELD = "#F4F1EB"
ACCENT = "#8C5E3C"
ACCENT_HOVER = "#734B30"
RAIL = "#1A1916"
RAIL_MUTED = "#B7B1A6"
DANGER = "#9B3A2F"
OK = "#3F6B4E"
BUSY = "#C4A484"
CREAM = "#F6F3EC"


def _enable_sharp_text() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        return


class SorterApp:
    def __init__(self) -> None:
        _enable_sharp_text()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("dark-blue")
        self.root = ctk.CTk()
        self.root.title("Event photos")
        self.root.minsize(860, 560)
        self.root.configure(fg_color=BG)
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self._running = False

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.keep_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Choose a mixed folder and a place to save the groups.")
        self.input_var.trace_add("write", lambda *_: self._refresh_buttons())
        self.output_var.trace_add("write", lambda *_: self._refresh_buttons())

        self.settings = self._load_group_settings()
        self._selected = ""
        self._group_buttons: dict[str, ctk.CTkButton] = {}
        self._build()
        self._place_on_screen()
        self._refresh_buttons()
        self._set_status_tone("idle")

    def _build(self) -> None:
        outer = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        outer.pack(fill="both", expand=True)

        rail = ctk.CTkFrame(outer, fg_color=RAIL, corner_radius=0, width=248)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self._build_rail(rail)

        main = ctk.CTkFrame(outer, fg_color=BG, corner_radius=0)
        main.pack(side="left", fill="both", expand=True, padx=28, pady=24)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        self.sort_view = ctk.CTkFrame(main, fg_color=BG, corner_radius=0)
        self.sort_view.grid(row=0, column=0, sticky="nsew")
        self.sort_view.grid_columnconfigure(0, weight=1)
        self.sort_view.grid_rowconfigure(7, weight=1)
        self._build_group_view(main)
        self._build_sort_view()

    def _build_sort_view(self) -> None:
        ctk.CTkLabel(
            self.sort_view,
            text="Sort a folder",
            text_color=INK,
            font=("Segoe UI", 26),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
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
            self.sort_view, 2, "Mixed photos", "Folder with every shot from the event", self.input_var, self._pick_input
        )
        self.output_entry, self.output_button = self._field_row(
            self.sort_view, 3, "Save groups to", "A different folder for Stage, Guests, and the rest", self.output_var, self._pick_output
        )

        self.keep_check = ctk.CTkCheckBox(
            self.sort_view,
            text="Keep photos already sorted in the output folder",
            variable=self.keep_var,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            border_color=LINE,
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
        self.sort_button = self._button(actions, "Sort photos", self._start, primary=True)
        self.sort_button.pack(side="left")
        self.open_button = self._button(actions, "Open folder", self._open_output, primary=False)
        self.open_button.pack(side="left", padx=(10, 0))

        panel = ctk.CTkFrame(self.sort_view, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=LINE)
        panel.grid(row=7, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)
        heading = ctk.CTkFrame(panel, fg_color=SURFACE, corner_radius=0)
        heading.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        self.status_dot = ctk.CTkFrame(heading, width=10, height=10, corner_radius=5, fg_color=MUTED)
        self.status_dot.pack(side="left", padx=(2, 8))
        self.status_dot.pack_propagate(False)
        ctk.CTkLabel(
            heading,
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
            scrollbar_button_color="#DDD8CE",
            scrollbar_button_hover_color="#C9C3B8",
        )
        self.log.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.log.configure(state="disabled")

    def _build_rail(self, rail: ctk.CTkFrame) -> None:
        ctk.CTkLabel(rail, text="EVENT", text_color=ACCENT, font=("Segoe UI", 11, "bold"), anchor="w").pack(
            anchor="w", padx=22, pady=(26, 0)
        )
        title = ctk.CTkLabel(rail, text="Photos", text_color=CREAM, font=("Segoe UI", 28), anchor="w", cursor="hand2")
        title.pack(anchor="w", padx=22, pady=(2, 6))
        title.bind("<Button-1>", lambda _event: self._show_sort())
        ctk.CTkLabel(
            rail,
            text="Group mixed event photos on this computer.",
            text_color=RAIL_MUTED,
            font=("Segoe UI", 13),
            anchor="w",
            justify="left",
            wraplength=190,
        ).pack(anchor="w", padx=22)
        ctk.CTkFrame(rail, fg_color="#2C2A26", height=1, corner_radius=0).pack(fill="x", padx=22, pady=16)
        ctk.CTkLabel(rail, text="GROUPS", text_color="#8A847A", font=("Segoe UI", 11, "bold"), anchor="w").pack(
            anchor="w", padx=22, pady=(0, 8)
        )
        groups = ctk.CTkFrame(rail, fg_color=RAIL, corner_radius=0)
        groups.pack(fill="both", expand=True, padx=10, pady=(0, 16))
        for name in self._group_names():
            button = ctk.CTkButton(
                groups,
                text=name,
                anchor="w",
                height=36,
                corner_radius=10,
                fg_color=RAIL,
                hover_color="#24221F",
                text_color="#E7E1D6",
                font=("Segoe UI", 14),
                command=lambda group=name: self._show_group(group),
            )
            button.pack(fill="x", pady=2)
            self._group_buttons[name] = button

    def _build_group_view(self, parent: ctk.CTkFrame) -> None:
        view = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(3, weight=1)
        self.group_view = view

        ctk.CTkButton(
            view,
            text="Back to sort",
            command=self._show_sort,
            fg_color="transparent",
            hover_color="#E7E1D8",
            text_color=ACCENT,
            font=("Segoe UI", 13),
            anchor="w",
            height=32,
            corner_radius=8,
        ).grid(row=0, column=0, sticky="w")

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

        foot = ctk.CTkFrame(view, fg_color=BG, corner_radius=0)
        foot.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        self.save_group = self._button(foot, "Save description", self._save_group, primary=True)
        self.save_group.pack(side="left")
        self.group_status = ctk.CTkLabel(foot, text="", text_color=MUTED, font=("Segoe UI", 13), anchor="w")
        self.group_status.pack(side="left", padx=(12, 0))

    def _field_row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        title: str,
        hint: str,
        variable: tk.StringVar,
        command,
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
        browse = ctk.CTkButton(
            row_frame,
            text="Browse",
            command=command,
            width=96,
            height=42,
            corner_radius=12,
            fg_color=SURFACE,
            hover_color="#EAE4DA",
            border_width=1,
            border_color=LINE,
            text_color=INK,
            font=("Segoe UI", 13),
        )
        browse.grid(row=0, column=1)
        return entry, browse

    def _button(self, parent, text: str, command, *, primary: bool) -> ctk.CTkButton:
        if primary:
            return ctk.CTkButton(
                parent,
                text=text,
                command=command,
                height=42,
                corner_radius=12,
                fg_color=INK,
                hover_color="#2E2C28",
                text_color=CREAM,
                text_color_disabled="#A39E96",
                font=("Segoe UI", 14, "bold"),
            )
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=42,
            corner_radius=12,
            fg_color=SURFACE,
            hover_color="#EAE4DA",
            border_width=1,
            border_color=LINE,
            text_color=INK,
            text_color_disabled="#B0A89E",
            font=("Segoe UI", 14),
        )

    def _place_on_screen(self) -> None:
        self.root.update_idletasks()
        left, top, work_w, work_h = self._work_area()
        scale = self._window_scale()
        width = min(980, max(720, int((work_w - 48) / scale)))
        height = min(640, max(520, int((work_h - 96) / scale)))
        self.root.geometry(f"{width}x{height}")
        self.root.update_idletasks()
        outer_w, outer_h = self._outer_size()
        extra_w = max(0, outer_w - int(width * scale))
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
            self._enable(self.sort_button, False)
            self._enable(self.open_button, False)
            self._set_status_tone("busy")
        else:
            self._refresh_buttons()

    def _enable(self, button: ctk.CTkButton, enabled: bool) -> None:
        button.configure(state="normal" if enabled else "disabled")
        if button is getattr(self, "sort_button", None) or button is getattr(self, "save_group", None):
            if enabled:
                button.configure(fg_color=INK, text_color=CREAM)
            else:
                button.configure(fg_color="#D9D3C8", text_color="#A39E96")

    def _set_status_tone(self, tone: str) -> None:
        color = {"idle": "#A39E96", "busy": BUSY, "done": OK, "error": DANGER}.get(tone, MUTED)
        self.status_dot.configure(fg_color=color)

    def _paint_groups(self) -> None:
        for name, button in self._group_buttons.items():
            if name == self._selected:
                button.configure(fg_color="#2C2925", text_color="#F3E6D4", hover_color="#2C2925")
            else:
                button.configure(fg_color=RAIL, text_color="#E7E1D6", hover_color="#24221F")

    def _show_sort(self) -> None:
        self._selected = ""
        self._paint_groups()
        self.group_view.grid_remove()
        self.sort_view.grid(row=0, column=0, sticky="nsew")

    def _show_group(self, name: str) -> None:
        self._selected = name
        self._paint_groups()
        self.sort_view.grid_remove()
        self.group_view.grid(row=0, column=0, sticky="nsew")
        self.group_title.configure(text=name)
        self.group_status.configure(text="")
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
        self._set_busy(True)
        self.status_var.set("Starting…")
        self._append("Starting sort")
        worker = threading.Thread(target=self._sort, args=(input_dir, output_dir), daemon=True)
        worker.start()
        self.root.after(100, self._poll)

    def _sort(self, input_dir: Path, output_dir: Path) -> None:
        try:
            from src.cli import run
        except ModuleNotFoundError as exc:
            self.messages.put(("error", f"Missing library '{exc.name}'. Follow the setup steps in README.md."))
            return
        args = Namespace(
            input=input_dir,
            output=output_dir,
            config=DEFAULT_CONFIG,
            threshold=None,
            batch_size=4,
            device="auto",
            model=None,
            keep_existing=bool(self.keep_var.get()),
            on_status=lambda message: self.messages.put(("status", message)),
        )
        try:
            run(args)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            self.messages.put(("error", str(exc)))
            return
        except Exception as exc:
            self.messages.put(("error", str(exc)))
            return
        self.messages.put(("done", str(output_dir)))

    def _poll(self) -> None:
        while True:
            try:
                kind, message = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.status_var.set(message)
                self._append(message)
            elif kind == "error":
                self.status_var.set(message)
                self._append(message)
                self._set_status_tone("error")
                self._set_busy(False)
                messagebox.showerror("Event photos", message)
                return
            elif kind == "done":
                self.status_var.set("Finished. Original photos were left in place.")
                self._append("Finished")
                self._set_status_tone("done")
                self._set_busy(False)
                return
        if self._running:
            self.root.after(100, self._poll)

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
