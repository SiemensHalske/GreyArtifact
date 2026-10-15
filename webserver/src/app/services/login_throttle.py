from __future__ import annotations

import math
import time
from collections import deque
from threading import Lock


class LoginThrottle:
    """Counts failed logins per username and per client address in one process.

    The state is lost on restart and is not shared between processes; that is
    sufficient for the single-process deployment and keeps the login path free
    of an additional dependency.
    """

    def __init__(
        self,
        *,
        window_seconds: int,
        max_failures_per_username: int,
        max_failures_per_address: int,
        clock=time.monotonic,
    ) -> None:
        self._window = window_seconds
        self._limits = {
            "username": max_failures_per_username,
            "address": max_failures_per_address,
        }
        self._clock = clock
        self._failures: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def _keys(self, username: str, address: str | None) -> list[tuple[str, str]]:
        keys = [("username", username.casefold())]
        if address:
            keys.append(("address", address))
        return keys

    def _recent(self, key: tuple[str, str], now: float) -> deque[float]:
        failures = self._failures.get(key)
        if failures is None:
            return deque()
        while failures and failures[0] <= now - self._window:
            failures.popleft()
        if not failures:
            del self._failures[key]
        return failures

    def retry_after(self, username: str, address: str | None) -> int | None:
        """Return the seconds until the next attempt is allowed, or None."""
        now = self._clock()
        with self._lock:
            waits = []
            for key in self._keys(username, address):
                failures = self._recent(key, now)
                if len(failures) >= self._limits[key[0]]:
                    waits.append(failures[0] + self._window - now)
        return max(1, math.ceil(max(waits))) if waits else None

    def record_failure(self, username: str, address: str | None) -> None:
        now = self._clock()
        with self._lock:
            for key in self._keys(username, address):
                self._recent(key, now)
                self._failures.setdefault(key, deque()).append(now)

    def record_success(self, username: str) -> None:
        with self._lock:
            self._failures.pop(("username", username.casefold()), None)
