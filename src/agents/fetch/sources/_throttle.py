"""Process-wide minimum gap between outbound requests."""

import threading
import time
from collections.abc import Callable

_MAX_INTERVAL = 60.0


class Throttle:
    """Sleep so that at least ``min_interval()`` seconds pass between calls.

    The first ``wait`` never sleeps. The interval callable is read on every
    call, so a settings change takes effect at once.
    """

    def __init__(
        self,
        min_interval: Callable[[], float],
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last: float | None = None

    def wait(self) -> None:
        with self._lock:
            if self._last is not None:
                remaining = (
                    self._last + min(_MAX_INTERVAL, max(0.0, self._min_interval())) - self._clock()
                )
                if remaining > 0:
                    self._sleep(remaining)
            self._last = self._clock()
