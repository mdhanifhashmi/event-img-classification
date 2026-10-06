"""Run one sort in its own process so the window never waits on it.

The window starts this module, sends "pause", "resume", or "stop" lines on
stdin, and reads one JSON object per line from stdout.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from argparse import Namespace

from src.control import RunControl

STOPPED = 130
_lock = threading.Lock()
_events = sys.stdout


def emit(kind: str, message: str = "") -> None:
    line = json.dumps({"kind": kind, "message": message})
    with _lock:
        _events.write(line + "\n")
        _events.flush()


def _lower_priority() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00004000)  # below normal
    except Exception:
        return


def _listen(control: RunControl) -> None:
    for line in sys.stdin:
        command = line.strip().lower()
        if command == "pause":
            control.pause()
        elif command == "resume":
            control.resume()
        elif command == "stop":
            control.stop()
    # The window closed the pipe, so nobody is watching this sort any more.
    control.stop()


def main(argv: list[str] | None = None) -> int:
    global _events
    _events = sys.stdout
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

    _lower_priority()
    try:
        from src.cli import build_parser, run
    except (ModuleNotFoundError, SystemExit):
        emit("error", "A required library is missing. Run Setup.bat, then try again.")
        return 1

    args = build_parser().parse_args(argv)
    control = RunControl(on_state=lambda state: emit("state", state))
    threading.Thread(target=_listen, args=(control,), daemon=True).start()

    try:
        import torch

        # Leave one core free so the window and Windows itself stay smooth.
        torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
    except Exception:
        pass

    run_args = Namespace(**vars(args))
    run_args.on_status = lambda message: emit("status", message)
    run_args.control = control
    try:
        code = run(run_args)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        emit("error", str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001 - report anything to the window
        emit("error", f"{type(exc).__name__}: {exc}")
        return 1
    if code == STOPPED:
        emit("stopped")
    else:
        emit("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
