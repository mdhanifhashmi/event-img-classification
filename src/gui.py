"""Window for choosing folders and sorting event photos."""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from argparse import Namespace
from pathlib import Path
from tkinter import filedialog, messagebox

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


def _enable_sharp_text() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        return


class ActionButton(tk.Frame):
    """Flat button with hover and disabled colors."""

    def __init__(self, parent: tk.Misc, text: str, command, *, primary: bool, compact: bool = False) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg, cursor="hand2")
        self.command = command
        self.primary = primary
        self.enabled = True
        fill = ACCENT if primary else SURFACE
        color = "#FFFFFF" if primary else INK
        border = ACCENT if primary else LINE
        self.body = tk.Frame(self, bg=border, padx=1, pady=1)
        self.body.pack()
        self.face = tk.Label(
            self.body,
            text=text,
            bg=fill,
            fg=color,
            font=("Segoe UI", 9 if compact else 10, "bold" if primary else "normal"),
            padx=12 if compact else 18,
            pady=3 if compact else 8,
            cursor="hand2",
        )
        self.face.pack()
        for widget in (self, self.body, self.face):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def _click(self, _event=None) -> None:
        if self.enabled:
            self.command()

    def _enter(self, _event=None) -> None:
        if not self.enabled:
            return
        if self.primary:
            self.face.configure(bg="#2E2C28")
        else:
            self.face.configure(bg="#EAE4DA")

    def _leave(self, _event=None) -> None:
        self._paint()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        cursor = "hand2" if enabled else "arrow"
        for widget in (self, self.body, self.face):
            widget.configure(cursor=cursor)
        self._paint()

    def _paint(self) -> None:
        if self.primary and self.enabled:
            fill, color, border = INK, "#F6F3EC", INK
        elif self.primary:
            fill, color, border = "#D9D3C8", "#A39E96", "#D9D3C8"
        elif self.enabled:
            fill, color, border = SURFACE, INK, LINE
        else:
            fill, color, border = FIELD, "#B0A89E", LINE
        self.body.configure(bg=border)
        self.face.configure(bg=fill, fg=color)


class SorterApp:
    def __init__(self) -> None:
        _enable_sharp_text()
        self.root = tk.Tk()
        self.root.title("Event photos")
        self.root.minsize(820, 520)
        self.root.configure(bg=BG)
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self._running = False

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Choose a mixed folder and a place to save the groups.")
        self.input_var.trace_add("write", lambda *_: self._refresh_buttons())
        self.output_var.trace_add("write", lambda *_: self._refresh_buttons())

        self._build()
        self._place_on_screen()
        self._refresh_buttons()
        self._set_status_tone("idle")

    def _build(self) -> None:
        outer = tk.Frame(self.root, bg=RAIL)
        outer.pack(fill="both", expand=True)

        rail = tk.Frame(outer, bg=RAIL, width=232)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self._build_rail(rail)

        main = tk.Frame(outer, bg=BG, padx=28, pady=24)
        main.pack(side="left", fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        tk.Label(main, text="Sort a folder", bg=BG, fg=INK, font=("Segoe UI", 22), anchor="w").grid(
            row=0, column=0, sticky="ew"
        )
        tk.Label(
            main,
            text="Copies go into named groups. The original folder is left untouched.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 18))

        self.input_entry, self.input_button = self._field_row(
            main, 2, "Mixed photos", "Folder with every shot from the event", self.input_var, self._pick_input
        )
        self.output_entry, self.output_button = self._field_row(
            main, 3, "Save groups to", "A different folder for Stage, Guests, and the rest", self.output_var, self._pick_output
        )

        actions = tk.Frame(main, bg=BG)
        actions.grid(row=4, column=0, sticky="nw", pady=(8, 16))
        self.sort_button = ActionButton(actions, "Sort photos", self._start, primary=True)
        self.sort_button.pack(side="left")
        self.open_button = ActionButton(actions, "Open folder", self._open_output, primary=False)
        self.open_button.pack(side="left", padx=(10, 0))

        panel = tk.Frame(main, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        panel.grid(row=5, column=0, sticky="nsew")
        main.rowconfigure(5, weight=1)
        inner = tk.Frame(panel, bg=SURFACE, padx=14, pady=12)
        inner.pack(fill="both", expand=True)
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(1, weight=1)

        heading = tk.Frame(inner, bg=SURFACE)
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.status_dot = tk.Canvas(heading, width=8, height=8, bg=SURFACE, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 8), pady=3)
        self.dot = self.status_dot.create_oval(0, 0, 8, 8, fill=MUTED, outline=MUTED)
        tk.Label(
            heading,
            textvariable=self.status_var,
            bg=SURFACE,
            fg=INK,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=460,
        ).pack(side="left", fill="x", expand=True)

        self.log = tk.Text(
            inner,
            height=6,
            wrap="word",
            font=("Segoe UI", 9),
            bg=FIELD,
            fg=INK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            state="disabled",
        )
        self.log.grid(row=1, column=0, sticky="nsew")

    def _build_rail(self, rail: tk.Frame) -> None:
        tk.Label(rail, text="EVENT", bg=RAIL, fg=ACCENT, font=("Segoe UI", 8, "bold"), anchor="w").pack(
            anchor="w", padx=24, pady=(22, 0)
        )
        tk.Label(rail, text="Photos", bg=RAIL, fg="#F6F3EC", font=("Segoe UI", 22), anchor="w").pack(
            anchor="w", padx=24, pady=(2, 8)
        )
        tk.Label(
            rail,
            text="Group mixed event photos on this computer.",
            bg=RAIL,
            fg=RAIL_MUTED,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=180,
        ).pack(anchor="w", padx=24)

        tk.Frame(rail, bg="#2C2A26", height=1).pack(fill="x", padx=24, pady=16)
        tk.Label(rail, text="GROUPS", bg=RAIL, fg="#8A847A", font=("Segoe UI", 8, "bold"), anchor="w").pack(
            anchor="w", padx=24, pady=(0, 8)
        )
        for name in self._group_names():
            tk.Label(rail, text=name, bg=RAIL, fg="#E7E1D6", font=("Segoe UI", 10), anchor="w").pack(
                anchor="w", padx=24, pady=0
            )

    def _group_names(self) -> list[str]:
        try:
            from src.labels import load_settings

            settings = load_settings(DEFAULT_CONFIG)
        except Exception:
            return ["Stage", "Decoration", "Guests", "Food", "Venue"]
        return [*settings.names, settings.review_label]

    def _field_row(
        self,
        parent: tk.Frame,
        row: int,
        title: str,
        hint: str,
        variable: tk.StringVar,
        command,
    ) -> tuple[tk.Entry, ActionButton]:
        block = tk.Frame(parent, bg=BG)
        block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        block.columnconfigure(0, weight=1)
        tk.Label(block, text=title, bg=BG, fg=INK, font=("Segoe UI", 10, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        tk.Label(block, text=hint, bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w").grid(
            row=1, column=0, sticky="w", pady=(1, 6)
        )

        field = tk.Frame(block, bg=LINE, padx=1, pady=1)
        field.grid(row=2, column=0, sticky="ew")
        inner = tk.Frame(field, bg=FIELD)
        inner.pack(fill="x")
        entry = tk.Entry(
            inner,
            textvariable=variable,
            relief="flat",
            bg=FIELD,
            fg=INK,
            insertbackground=INK,
            font=("Segoe UI", 10),
            highlightthickness=0,
            borderwidth=0,
        )
        entry.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        browse = ActionButton(inner, "Browse", command, primary=False, compact=True)
        browse.pack(side="right", padx=(0, 4), pady=4)

        def focus_in(_event=None, box=field) -> None:
            box.configure(bg=ACCENT)

        def focus_out(_event=None, box=field) -> None:
            box.configure(bg=LINE)

        entry.bind("<FocusIn>", focus_in)
        entry.bind("<FocusOut>", focus_out)
        return entry, browse

    def _place_on_screen(self) -> None:
        self.root.update_idletasks()
        width, height = 900, 640
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

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
        self.sort_button.set_enabled(ready)
        output = self.output_var.get().strip()
        self.open_button.set_enabled(bool(output) and Path(output).is_dir())

    def _set_busy(self, busy: bool) -> None:
        self._running = busy
        entry_state = "readonly" if busy else "normal"
        self.input_entry.configure(state=entry_state)
        self.output_entry.configure(state=entry_state)
        self.input_button.set_enabled(not busy)
        self.output_button.set_enabled(not busy)
        if busy:
            self.sort_button.set_enabled(False)
            self.open_button.set_enabled(False)
            self._set_status_tone("busy")
        else:
            self._refresh_buttons()

    def _set_status_tone(self, tone: str) -> None:
        color = {"idle": "#A39E96", "busy": BUSY, "done": OK, "error": DANGER}.get(tone, MUTED)
        self.status_dot.itemconfigure(self.dot, fill=color, outline=color)

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
        worker = threading.Thread(
            target=self._sort,
            args=(input_dir, output_dir),
            daemon=True,
        )
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
