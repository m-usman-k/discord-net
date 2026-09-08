import asyncio
import logging
import time
from typing import Deque
from collections import deque

log = logging.getLogger("discord_net.core.ratelimit")


class RateLimiter:
    """Limits messages per account to stay under a per-minute ceiling.

    Also enforces randomized 'break' periods (e.g. 40-45s) where the account
    goes quiet so activity looks organic, plus a minimum gap between sends.
    """

    def __init__(
        self,
        max_per_minute: int = 6,
        min_gap: float = 8.0,
        break_min_seconds: float = 40.0,
        break_max_seconds: float = 45.0,
        break_chance: float = 0.3,
    ) -> None:
        self.max_per_minute = max_per_minute
        self.min_gap = min_gap
        self.break_min_seconds = break_min_seconds
        self.break_max_seconds = break_max_seconds
        self.break_chance = break_chance

        self._timestamps: Deque[float] = deque()
        self._lock = asyncio.Lock()
        self._last_send: float = 0.0
        self._in_break = False
        self._in_break_since: float = 0.0

    async def acquire(self) -> float:
        """Block until a send is permitted, returning seconds waited."""
        async with self._lock:
            waited = 0.0
            while True:
                now = time.monotonic()

                should_break = False
                if random_break_roll(self.break_chance):
                    should_break = True

                if self._in_break:
                    elapsed = now - self._in_break_since
                    if elapsed < self.break_min_seconds:
                        remaining = self.break_min_seconds - elapsed
                        await asyncio.sleep(remaining)
                        waited += remaining
                        continue
                    # break finished
                    self._in_break = False
                    log.info("Break over, resuming activity")

                if should_break and not self._in_break:
                    self._in_break = True
                    self._in_break_since = time.monotonic()
                    log.info("Starting %s-%ss break", self.break_min_seconds, self.break_max_seconds)
                    await asyncio.sleep(self.break_min_seconds)
                    waited += self.break_min_seconds
                    continue

                # minimum gap since last send
                since_last = now - self._last_send
                if since_last < self.min_gap:
                    await asyncio.sleep(self.min_gap - since_last)
                    waited += self.min_gap - since_last
                    continue

                # purge old timestamps, keep last rolling ~60s
                cutoff = now - 60.0
                while self._timestamps and self._timestamps[0] < cutoff:
                    self._timestamps.popleft()

                if len(self._timestamps) >= self.max_per_minute:
                    # wait until the oldest timestamp ages out
                    wait = self._timestamps[0] - cutoff
                    await asyncio.sleep(max(wait, 1.0))
                    waited += max(wait, 1.0)
                    continue

                self._timestamps.append(now)
                self._last_send = now
                return waited

    async def release(self) -> None:
        pass


def random_break_roll(chance: float) -> bool:
    import random

    return random.random() < chance