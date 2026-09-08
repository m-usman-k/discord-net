import asyncio
import json
import logging
import random
from typing import Any, Awaitable, Callable, Dict, Optional

import aiohttp

from .heartbeat import Heartbeat

log = logging.getLogger("discord_net.gateway")

OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11


class Gateway:
    """Manages a single WebSocket connection to Discord's gateway for one user."""

    def __init__(
        self,
        token: str,
        url: str,
        intents: int,
        session: Optional[aiohttp.ClientSession] = None,
        on_event: Optional[Callable[[int, Dict[str, Any]], Awaitable[None]]] = None,
        on_ready: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        self.token = token
        self.url = url
        self.intents = intents
        self._session = session
        self._on_event = on_event
        self._on_ready = on_ready

        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._hb: Optional[Heartbeat] = None
        self._seq: Optional[int] = None
        self._session_id: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._closed = False

    async def connect(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(self.url, heartbeat=60, compress=False)
        log.info("Connected to gateway")

    async def identify(self) -> None:
        assert self._ws is not None
        payload = {
            "op": OP_IDENTIFY,
            "d": {
                "token": self.token,
                "intents": self.intents,
                "capabilities": 253,
                "properties": {
                    "os": "windows",
                    "browser": "chrome",
                    "device": "chrome",
                },
                "presence": {
                    "status": "online",
                    "activities": [],
                    "afk": False,
                    "since": 0,
                },
            },
        }
        await self._ws.send_str(json.dumps(payload))
        log.debug("Identify sent")

    async def resume(self) -> None:
        assert self._ws is not None
        if not self._session_id:
            return
        payload = {
            "op": 6,
            "d": {
                "token": self.token,
                "session_id": self._session_id,
                "seq": self._seq,
            },
        }
        await self._ws.send_str(json.dumps(payload))
        log.info("Resume attempt sent (session_id=%s)", self._session_id)

    async def recv_loop(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            if raw.type == aiohttp.WSMsgType.TEXT:
                await self._handle_message(json.loads(raw.data))
            elif raw.type == aiohttp.WSMsgType.CLOSED:
                log.warning("Gateway closed")
                break
            elif raw.type == aiohttp.WSMsgType.ERROR:
                log.error("Gateway error: %s", raw.data)
                break

    async def _handle_message(self, msg: Dict[str, Any]) -> None:
        op = msg.get("op")
        data = msg.get("d")

        if op == OP_HELLO:
            interval = data.get("heartbeat_interval", 41250)
            if self._hb:
                self._hb.stop()
            self._hb = Heartbeat(self._ws, interval, self._sequence)
            self._hb.start()
            if self._session_id:
                await self.resume()
            else:
                await self.identify()

        elif op == OP_HEARTBEAT:
            self._hb= self._hb
            if self._hb:
                self._hb.acked = False
                await self._ws.send_str(json.dumps({"op": 1, "d": self._seq}))

        elif op == OP_HEARTBEAT_ACK:
            if self._hb:
                self._hb.acked = True

        elif op == OP_DISPATCH:
            t = msg.get("t")
            self._seq = msg.get("s", self._seq)
            if self._session_id is None and t == "READY":
                self._session_id = data.get("session_id")
                log.info(
                    "READY: %s (session_id=%s)",
                    data.get("user", {}).get("username"),
                    self._session_id,
                )
                if self._on_ready:
                    try:
                        await self._on_ready(data)
                    except Exception:
                        log.exception("on_ready handler failed")
            if self._on_event:
                try:
                    await self._on_event(
                        EVENT_CODES.get(t, -1), data
                    )
                except Exception:
                    log.exception("on_event handler failed for %s", t)

    def _sequence(self) -> Optional[int]:
        return self._seq

    async def send_presence(self, status: str, activity: Optional[str] = None) -> None:
        if not self._ws:
            return
        activities = []
        if activity:
            activities = [{"type": 0, "name": activity}]
        payload = {
            "op": 3,
            "d": {"since": 0, "activities": activities, "status": status, "afk": False},
        }
        await self._ws.send_str(json.dumps(payload))

    def run(self) -> None:
        self._task = asyncio.create_task(self._recv_guard())
        self._task.add_done_callback(self._on_task_done)

    async def _recv_guard(self) -> None:
        while not self._closed:
            try:
                await self.connect()
                await self.recv_loop()
            except (aiohttp.ClientError, ConnectionError, asyncio.TimeoutError) as e:
                log.warning("Gateway connection error: %s; retrying", e)
            except Exception:
                log.exception("Gateway loop crashed")
            if self._closed:
                break
            await asyncio.sleep(3 + random.random() * 4)

    def _on_task_done(self, _task: asyncio.Task) -> None:
        if not self._closed:
            log.info("Gateway loop stopped unexpectedly; restart scheduled")

    async def close(self) -> None:
        self._closed = True
        if self._hb:
            self._hb.stop()
        if self._ws:
            await self._ws.close()


EVENT_CODES = {
    "READY": 0,
    "MESSAGE_CREATE": 1,
    "MESSAGE_REACTION_ADD": 2,
    "TYPING_START": 3,
    "GUILD_CREATE": 4,
    "PRESENCE_UPDATE": 5,
    "CHANNEL_CREATE": 6,
    "GUILD_UPDATE": 7,
    "GUILD_DELETE": 8,
}
