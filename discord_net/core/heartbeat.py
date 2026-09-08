import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

import aiohttp

log = logging.getLogger("discord_net.heartbeat")

HEARTBEAT_INTERVAL_MULTIPLIER = 0.75


class Heartbeat:
    def __init__(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        interval_ms: int,
        seq: "callable" = lambda: None,
    ) -> None:
        self.ws = ws
        self.interval = interval_ms / 1000.0
        self._seq = seq
        self._task: Optional[asyncio.Task] = None
        self.acked = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.interval)
                seq = self._seq()
                await self.ws.send_str(json.dumps({"op": 1, "d": seq}))
                log.debug("Heartbeat sent (seq=%s)", seq)
                self.acked = False
        except asyncio.CancelledError:
            pass
