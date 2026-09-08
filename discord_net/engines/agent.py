import asyncio
import logging
import random
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from ..core.api import DiscordAPI, DiscordAPIError, ZenLLM
from ..core.config import AccountConfig, ChatConfig, RateLimitConfig, TypingConfig
from ..core.gateway import EVENT_CODES, Gateway
from ..core.learnora_context import (
    CONTEXT_SYSTEM_PROMPT,
    LEARNORA_OVERVIEW,
    LEARNORA_STUDENT_FEATURES,
    LEARNORA_WEBSITE_FACTS,
)
from ..core.ratelimit import RateLimiter
from ..core.splitter import split_message
from ..core.typing import simulate_typing
from ..engines.generator import MessageGenerator

log = logging.getLogger("discord_net.agent")

BOT_FLAG = 1 << 6
SYSTEM_FLAG = 1 << 8


class Agent:
    """One owned user account acting in the Discord server.

    Maintains its own gateway + REST client, keeps a rolling conversation
    memory, replies through the LLM (Learnora-aware), and paces itself with
    typing simulation and rate limiting so traffic looks human.
    """

    def __init__(
        self,
        index: int,
        config: AccountConfig,
        chat: ChatConfig,
        rl: RateLimitConfig,
        typing_cfg: TypingConfig,
        generator: MessageGenerator,
        api_url: str,
        gateway_url: str,
        intents: int,
        max_message_len: int = 180,
        on_ready=None,
        shared_session=None,
    ) -> None:
        self.index = index
        self.config = config
        self.chat = chat
        self.rl_cfg = rl
        self.typing_cfg = typing_cfg
        self.generator = generator
        self.max_message_len = max_message_len

        self.name = config.name or f"Account{index}"
        self.api = DiscordAPI(config.token, api_url, session=shared_session)
        self.gateway = Gateway(
            config.token,
            gateway_url,
            intents,
            session=shared_session,
            on_event=self._on_gateway_event,
            on_ready=self._on_ready,
        )
        self.on_ready_cb = on_ready

        self.me: Optional[Dict[str, Any]] = None
        self._recognized_channels: set = set()
        self._ratelimiter = RateLimiter(
            max_per_minute=rl.max_per_minute,
            min_gap=rl.min_gap_between_messages,
            break_min_seconds=rl.break_min,
            break_max_seconds=rl.break_max,
            break_chance=rl.break_chance,
        )

        # Per-account rolling memory of what this account has seen/said.
        self.memory: Deque[Dict[str, str]] = deque(maxlen=30)
        self.known_topics: set = set()
        self._seen_questions: set = set()
        self._random_ping_time = 0.0
        self._pending_process: set = set()  # message ids currently handled

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        try:
            self.me = await self.api.get_me()
            log.info("[%s] connected as %s", self.name, self.me.get("username"))
        except DiscordAPIError as e:
            log.error("[%s] auth failed: %s", self.name, e)
            raise
        self.gateway.run()

        # Start membership/channel upkeep in the background.
        asyncio.create_task(self._membership_loop())

    async def stop(self) -> None:
        await self.gateway.close()
        await self.api.close()

    # ------------------------------------------------------------------ #
    # Server membership + channel analysis
    # ------------------------------------------------------------------ #
    async def _membership_loop(self) -> None:
        """Join the target server if needed, analyze channels, repeat on a
        slow cadence. Join attempts are staggered with human-like delays."""
        if not self.chat.server_id:
            return
        # Let the account settle in before doing anything.
        await asyncio.sleep(random.uniform(15, 45))

        join_done = False
        while True:
            try:
                joined = await self._ensure_in_server()
                if joined and not join_done:
                    await self._analyze_channels()
                    join_done = True
            except DiscordAPIError as e:
                log.warning("[%s] membership check failed: %s", self.name, e)
            except Exception:
                log.exception("[%s] membership check crashed", self.name)
            await asyncio.sleep(self.chat.recheck_interval + random.uniform(0, 120))

    async def _ensure_in_server(self) -> bool:
        """Return True if the account is a member of the target server."""
        if not self.chat.server_id:
            return False
        guilds = await self.api.get_guilds()
        member = any(str(g.get("id")) == str(self.chat.server_id) for g in guilds)
        if member:
            return True

        if not self.chat.invite_code:
            log.warning(
                "[%s] not in server %s and no invite_code set in config.json",
                self.name, self.chat.server_id,
            )
            return False

        # Not a member: wait a bit (organic), then join via invite.
        await asyncio.sleep(random.uniform(20, 45))
        ok = await self.api.join_server(self.chat.invite_code)
        if ok:
            await asyncio.sleep(random.uniform(15, 40))
            return True
        return False

    async def _analyze_channels(self) -> None:
        """Fetch all text channels in the server and update the watch set."""
        try:
            channels = await self.api.get_channels(self.chat.server_id)
        except DiscordAPIError as e:
            log.warning("[%s] could not fetch channels: %s", self.name, e)
            return

        text_channels = [int(c["id"]) for c in channels if c.get("type") == 0]
        if self.chat.channel_ids:
            # explicit config wins
            keep = set(text_channels) & set(self.chat.channel_ids)
            self._recognized_channels = keep
            log.info(
                "[%s] watching %d configured channel(s) present in server",
                self.name, len(keep),
            )
        else:
            self._recognized_channels = set(text_channels)
            log.info(
                "[%s] analyzed %d text channel(s): %s",
                self.name, len(text_channels), sorted(self._recognized_channels)[:10],
            )

    # ------------------------------------------------------------------ #
    # Public send helpers (common to engines + scheduler)
    # ------------------------------------------------------------------ #
    async def send_natural(
        self,
        channel_id: int,
        text: str,
        with_typing: bool = True,
    ) -> bool:
        """Send text naturally: typing delay, split long messages, rate limit."""
        text = self.generator.finalize(text)
        if not text:
            return False
        chunks = split_message(text, max_len=self.max_message_len)
        if not chunks:
            return False

        for idx, chunk in enumerate(chunks):
            await self._ratelimiter.acquire()

            if with_typing and self.typing_cfg.enabled:
                await simulate_typing(
                    chunk,
                    min_seconds=self.typing_cfg.min_seconds,
                    max_seconds=self.typing_cfg.max_seconds,
                )

            try:
                await self.api.send_message(channel_id, chunk)
                log.info("[%s] -> #%s: %s", self.name, channel_id, chunk[:50])
            except DiscordAPIError as e:
                log.warning("[%s] send failed: %s", self.name, e)
                return False

            if idx < len(chunks) - 1:
                await asyncio.sleep(random.uniform(1.5, 4.0))

        self._remember("assistant", text, channel_id)
        return True

    async def react(self, channel_id: int, message_id: int, emoji: str = "") -> bool:
        emoji = emoji or self.generator.pick_reaction()
        return await self.api.react(channel_id, message_id, emoji)

    async def set_presence(self, status: str = "online", activity: Optional[str] = None) -> None:
        await self.gateway.send_presence(status, activity)

    # ------------------------------------------------------------------ #
    # Memory
    # ------------------------------------------------------------------ #
    def _remember(self, role: str, content: str, channel_id: int = 0) -> None:
        self.memory.append(
            {"role": role, "content": content[:500], "channel_id": str(channel_id)}
        )

    def conversation_for_llm(self, channel_id: int = 0) -> List[Dict[str, str]]:
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self.memory
            if not channel_id or m.get("channel_id") == str(channel_id)
        ]

    # ------------------------------------------------------------------ #
    # Gateway events
    # ------------------------------------------------------------------ #
    async def _on_ready(self, data: Dict[str, Any]) -> None:
        user = data.get("user", {})
        self.me = user or self.me
        if self.on_ready_cb:
            try:
                await self.on_ready_cb(self, data)
            except Exception:
                log.exception("[%s] on_ready callback failed", self.name)

    async def _on_gateway_event(self, event_code: int, data: Dict[str, Any]) -> None:
        if event_code == EVENT_CODES["MESSAGE_CREATE"]:
            asyncio.create_task(self._on_message(data))
        elif event_code == EVENT_CODES["GUILD_CREATE"]:
            asyncio.create_task(self._collect_channels(data))
        elif event_code == EVENT_CODES["CHANNEL_CREATE"]:
            asyncio.create_task(self._on_channel_create(data))
        elif event_code == EVENT_CODES["GUILD_UPDATE"]:
            asyncio.create_task(self._collect_channels(data))
        elif event_code == EVENT_CODES["GUILD_DELETE"]:
            gid = data.get("id")
            if gid and str(gid) == str(self.chat.server_id):
                log.info("[%s] no longer in server %s; will re-check", self.name, gid)
                self._recognized_channels = set()

    async def _on_channel_create(self, channel: Dict[str, Any]) -> None:
        gid = channel.get("guild_id")
        if gid and str(gid) == str(self.chat.server_id) and channel.get("type") == 0:
            self._recognized_channels.add(int(channel["id"]))
            log.info("[%s] tracking new text channel #%s", self.name, channel["id"])

    async def _collect_channels(self, guild: Dict[str, Any]) -> None:
        gid = guild.get("id")
        if gid and str(gid) != str(self.chat.server_id):
            return
        for ch in guild.get("channels", []) or []:
            if ch.get("type") == 0:
                self._recognized_channels.add(int(ch["id"]))
        if self._recognized_channels:
            log.info(
                "[%s] watching %d channel(s): %s",
                self.name, len(self._recognized_channels),
                sorted(self._recognized_channels)[:10],
            )

    async def _on_message(self, msg: Dict[str, Any]) -> None:
        channel_id = msg.get("channel_id")
        author = msg.get("author", {})
        author_id = author.get("id")
        msg_id = str(msg.get("id", ""))

        if channel_id not in self._recognized_channels:
            return
        if not author_id:
            return
        if self.me is not None and author_id == str(self.me.get("id")):
            return
        if msg_id in self._pending_process:
            return

        is_bot = bool(author.get("bot")) or bool(author.get("flags", 0) & BOT_FLAG)
        if is_system_flag(author):
            return
        if is_bot and not self.chat.chat_with_bots:
            return

        self._pending_process.add(msg_id)
        try:
            await self._decide_response(msg)
        finally:
            self._pending_process.discard(msg_id)

    async def _decide_response(self, msg: Dict[str, Any]) -> None:
        channel_id = int(msg["channel_id"])
        content = (msg.get("content") or "").strip()
        author = msg.get("author", {})
        author_name = author.get("username", "someone")

        if not content:
            return

        # log to memory
        self._remember("user", f"{author_name}: {content}", channel_id)
        self._remember("user_name", author_name, channel_id)

        mentioned = False
        if self.me:
            mentioned = f"<@{self.me['id']}>" in content or author_id_mention(msg, self.me)

        is_question = content.rstrip().endswith("?")

        # Answer direct questions with high probability; otherwise reply
        # based on response_chance.
        should_reply = mentioned or is_question
        if not should_reply:
            should_reply = random.random() < self.config.response_chance

        if not should_reply:
            # occasional emoji reaction instead of reply
            if random.random() < 0.12:
                await self.react(channel_id, int(msg["id"]))
            return

        delay = random.uniform(
            self.config.min_reply_delay, self.config.max_reply_delay
        )
        await asyncio.sleep(delay)

        try:
            reply = await self._build_reply(content, author_name, channel_id, is_question)
        except Exception as e:
            log.warning("[%s] reply build failed: %s", self.name, e)
            reply = self.generator._local_reply(content, self.config.personality)

        if reply:
            await self.send_natural(channel_id, reply)

    async def _build_reply(
        self, content: str, author_name: str, channel_id: int, is_question: bool
    ) -> str:
        purpose = "answer their question accurately" if is_question else "keep the conversation going naturally"

        context = "\n".join([
            LEARNORA_OVERVIEW.strip(),
            LEARNORA_WEBSITE_FACTS.strip(),
            LEARNORA_STUDENT_FEATURES.strip(),
        ])

        history = self.conversation_for_llm(channel_id)

        instruction = (
            f"Here is {author_name}'s latest message: \"{content[:400]}\". "
            f"{purpose}. Reply as yourself, at most 2 short sentences, Discord style."
        )

        messages = [
            {"role": "system", "content": CONTEXT_SYSTEM_PROMPT + context},
            *history[-8:],
            {"role": "user", "content": instruction},
        ]

        reply = await self.generator.llm.complete(messages)
        if not reply:
            reply = self.generator._local_reply(content, self.config.personality)
        return reply

    # ------------------------------------------------------------------ #
    # Ambient chatter (spontaneous posts about Learnora)
    # ------------------------------------------------------------------ #
    async def maybe_chatter(self, channels: List[int], browser_account=None) -> None:
        """Randomly post an LLM-generated thought if it's natural to do so."""
        if not channels:
            log.debug("[%s] maybe_chatter: no channels", self.name)
            return
        if self.me is None:
            log.debug("[%s] maybe_chatter: not connected", self.name)
            return
        now = time.monotonic()
        cooldown = random.uniform(60, 180)
        elapsed = now - self._random_ping_time
        log.debug("[%s] maybe_chatter: elapsed=%.1f cooldown=%.1f", self.name, elapsed, cooldown)
        if elapsed < cooldown:
            return
        self._random_ping_time = now

        channel = random.choice(channels)
        text = await self._generate_chatter()
        if not text:
            log.debug("[%s] maybe_chatter: no text generated", self.name)
            return

        await self._ratelimiter.acquire()
        if self.typing_cfg.enabled and not browser_account:
            await simulate_typing(text, min_seconds=2.0, max_seconds=12.0)
        try:
            finalized = self.generator.finalize(text)
            if browser_account:
                url = f"https://discord.com/channels/{self.chat.server_id}/{channel}"
                await browser_account.send_message(url, finalized)
            else:
                await self.api.send_message(channel, finalized)
            log.info("[%s] chattered: %s", self.name, text[:60])
            self._remember("assistant", text, channel)
        except DiscordAPIError as e:
            log.warning("[%s] chatter failed: %s", self.name, e)

    async def _generate_chatter(self) -> str:
        """Fresh, unique spontaneous post generated by the LLM."""
        context = "\n".join(
            [
                LEARNORA_OVERVIEW.strip(),
                LEARNORA_STUDENT_FEATURES.strip(),
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    CONTEXT_SYSTEM_PROMPT
                    + "You occasionally post a casual, original thought about "
                    "studying or learnora, like someone texting the group. "
                    + context
                ),
            },
            {
                "role": "user",
                "content": (
                    "Post one new, original casual thought as yourself. One "
                    "sentence, Discord style, never repeats something already "
                    "posted before."
                ),
            },
        ]
        reply = await self.generator.llm.complete(messages)
        if reply:
            return reply
        return self.generator._local_reply("", self.config.personality)


def is_system_flag(author: Dict[str, Any]) -> bool:
    return bool(author.get("flags", 0) & SYSTEM_FLAG)


def author_id_mention(msg: Dict[str, Any], me: Dict[str, Any]) -> bool:
    """True if the message content references our user id."""
    try:
        mentions = msg.get("mentions") or []
        return any(str(m.get("id")) == str(me.get("id")) for m in mentions)
    except Exception:
        return False