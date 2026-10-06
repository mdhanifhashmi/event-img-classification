"""Pause and stop signals shared by the sorter's long-running steps."""

from __future__ import annotations

import threading
from collections.abc import Callable


class SortCancelled(Exception):
    """Raised at a safe point when the user asked the sort to stop."""


class RunControl:
    """Cooperative pause and stop.

    The sorter calls checkpoint() between batches and between copied files.
    A model call that is already running is never interrupted, so work stops
    at the next checkpoint instead of leaving half-written data.
    """

    def __init__(self, on_state: Callable[[str], None] | None = None) -> None:
        self._stop = threading.Event()
        self._run = threading.Event()
        self._run.set()
        self._on_state = on_state

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    @property
    def paused(self) -> bool:
        return not self._run.is_set()

    def pause(self) -> None:
        self._run.clear()

    def resume(self) -> None:
        self._run.set()

    def stop(self) -> None:
        self._stop.set()
        self._run.set()

    def checkpoint(self) -> None:
        if self._stop.is_set():
            raise SortCancelled
        if self._run.is_set():
            return
        self._emit("paused")
        while not self._run.wait(0.2):
            pass
        if self._stop.is_set():
            raise SortCancelled
        self._emit("resumed")

    def _emit(self, state: str) -> None:
        if self._on_state is not None:
            self._on_state(state)
