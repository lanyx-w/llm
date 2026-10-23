"""Cooperative cancellation shared by any front-end."""

from __future__ import annotations

import threading


class CancellationToken:
    """A thread-safe flag checked by the agent between streaming chunks."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()
