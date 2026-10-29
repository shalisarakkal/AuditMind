"""Bound progress writes, independently of database insertion/checkpoint sizes."""
import time
from collections.abc import Callable


class ProgressReporter:
    """Report changed counts once a second, plus phase boundaries/final writing counts.

    Called at row boundaries: never manufactures progress during a slow SQL call.
    """
    def __init__(self, callback, *, clock: Callable[[], float] = time.monotonic):
        self.callback = callback
        self.clock = clock
        self.last = None
        self.last_at = float('-inf')

    def __call__(self, phase: str, done: int, total: int) -> None:
        value = (phase, done, total)
        if value == self.last:
            return
        now = self.clock()
        boundary = self.last is None or phase != self.last[0] or (phase in {'writing', 'findings'} and total > 0 and done >= total)
        if not boundary and now - self.last_at < 1.0:
            return
        self.callback(phase, done, total)
        self.last = value
        self.last_at = now
