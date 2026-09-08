import asyncio
import logging
import random
from typing import List, Optional

from ..core.config import Config
from .agent import Agent
from .browser import BrowserEngine, BrowserAccount
from .generator import MessageGenerator

log = logging.getLogger("discord_net.engines.conversation")

CHATTER_INTERVAL_RANGE = (60, 180)
THREAD_SEED_INTERVAL_RANGE = (300, 600)


class ConversationEngine:
    """Coordinates the fleet of owned accounts.

    - Connects all agents to the gateway.
    - Runs an ambient chatter loop so accounts post about Learnora.
    - Occasionally seeds a conversation thread between two accounts.
    - Optionally uses Playwright browsers instead of REST for messages.
    """

    def __init__(
        self,
        config: Config,
        generator: Optional[MessageGenerator] = None,
        on_agent_ready=None,
    ) -> None:
        self.config = config
        self.generator = generator or MessageGenerator()
        self.agents: List[Agent] = []
        self.on_agent_ready = on_agent_ready
        self.browser_engine: Optional[BrowserEngine] = None
        self._use_browser = config.use_browser

    # ------------------------------------------------------------------ #
    # Setup
    # ------------------------------------------------------------------ #
    async def build_agents(self) -> List[Agent]:
        for i, acc in enumerate(self.config.accounts):
            agent = Agent(
                index=i,
                config=acc,
                chat=self.config.chat,
                rl=self.config.rate_limit,
                typing_cfg=self.config.typing,
                generator=self.generator,
                api_url=self.config.api_url,
                gateway_url=self.config.gateway_url,
                intents=self.config.intents,
                max_message_len=self.config.max_message_len,
                on_ready=self.on_agent_ready,
            )
            self.agents.append(agent)
        return self.agents

    async def _setup_browser(self) -> None:
        """Launch Playwright browsers for each account."""
        self.browser_engine = BrowserEngine()
        for i, acc in enumerate(self.config.accounts):
            await self.browser_engine.add_account(
                name=acc.name or f"Account{i}",
                token=acc.token,
                headless=False,
                email=acc.email,
                password=acc.password,
            )
        await self.browser_engine.start_all()

    async def start(self) -> None:
        if not self.agents:
            await self.build_agents()

        # Start browser engine if configured
        if self._use_browser:
            log.info("Starting Playwright browsers for %d accounts...", len(self.agents))
            await self._setup_browser()

        for i, agent in enumerate(self.agents):
            try:
                await agent.connect()
            except Exception as e:
                log.error("[%s] failed to start: %s", agent.name, e)
            if i < len(self.agents) - 1:
                await asyncio.sleep(random.uniform(20, 40))
        await asyncio.sleep(5)
        self._start_loops()
        asyncio.create_task(self._initial_post())

    async def _initial_post(self) -> None:
        """Post a first message shortly after connecting."""
        log.info("[initial_post] waiting for channels...")
        for attempt in range(30):
            await asyncio.sleep(5)
            active = [a for a in self.agents if a.me is not None and a._recognized_channels]
            if active:
                log.info("[initial_post] found %d active agent(s) after %ds", len(active), (attempt+1)*5)
                break
        if not active:
            for a in self.agents:
                if a.me is not None:
                    await a._analyze_channels()
            active = [a for a in self.agents if a.me is not None and a._recognized_channels]
        if not active:
            log.warning("[initial_post] No active agents with channels for initial post")
            return
        speaker = random.choice(active)
        channels = await self._channels_for(speaker)
        log.info("[initial_post] channels available: %d", len(channels))
        if not channels:
            return
        log.info("[initial_post] posting initial message...")
        browser_account = None
        if self._use_browser and self.browser_engine:
            browser_account = self.browser_engine.accounts.get(speaker.name)
        await speaker.maybe_chatter(channels, browser_account=browser_account)

    def _start_loops(self) -> None:
        asyncio.create_task(self._chatter_loop())
        asyncio.create_task(self._thread_loop())

    # ------------------------------------------------------------------ #
    # Ambient chatter
    # ------------------------------------------------------------------ #
    async def _chatter_loop(self) -> None:
        while True:
            await asyncio.sleep(random.uniform(*CHATTER_INTERVAL_RANGE))
            active = [a for a in self.agents if a.me is not None and a._recognized_channels]
            if not active:
                continue
            speaker = random.choice(active)
            channels = await self._channels_for(speaker)
            if not channels:
                continue
            browser_account = None
            if self._use_browser and self.browser_engine:
                browser_account = self.browser_engine.accounts.get(speaker.name)
            await speaker.maybe_chatter(channels, browser_account=browser_account)

    async def _channels_for(self, agent) -> list:
        if self.config.chat.channel_ids:
            return list(self.config.chat.channel_ids)
        if not agent._recognized_channels:
            await agent._analyze_channels()
        return list(agent._recognized_channels)

    # ------------------------------------------------------------------ #
    # Two-account threads
    # ------------------------------------------------------------------ #
    async def _thread_loop(self) -> None:
        while True:
            await asyncio.sleep(random.uniform(*THREAD_SEED_INTERVAL_RANGE))
            await self._seed_thread()

    async def _seed_thread(self) -> None:
        active = [a for a in self.agents if a.me is not None and a._recognized_channels]
        if len(active) < 2:
            return

        a, b = random.sample(active, 2)
        channels = await self._channels_for(a)
        if not channels:
            return
        channel = random.choice(channels)

        opener = await self._generate_opener(a)
        if not opener:
            return

        log.info("Seeding thread between %s and %s", a.name, b.name)
        await a.send_natural(channel, opener)

    async def _generate_opener(self, agent) -> str:
        try:
            if not self.generator.use_llm or not self.generator.llm:
                return ""
            reply = await self.generator.llm.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a student in a Discord server about "
                            "learnora (AI study platform that turns lectures, "
                            "notes, PDFs and slides into notes, flashcards, "
                            "quizzes and AI tutoring). You occasionally start "
                            "a thread with a question. Keep it to ONE short "
                            "sentence, casual, no em dashes, no lists. End "
                            "with a question mark so people reply."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Write one brand new thread-opener question about "
                            "studying or learnora that you have never asked "
                            "before. One sentence only."
                        ),
                    },
                ]
            )
            return reply or ""
        except Exception as e:
            log.warning("Opener generation failed: %s", e)
            return ""

    # ------------------------------------------------------------------ #
    # Teardown
    # ------------------------------------------------------------------ #
    async def stop(self) -> None:
        for agent in self.agents:
            try:
                await agent.stop()
            except Exception as e:
                log.warning("[%s] stop error: %s", agent.name, e)
        if self.browser_engine:
            await self.browser_engine.stop_all()
