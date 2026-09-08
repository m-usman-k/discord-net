import asyncio
import logging
import random
from typing import List

from ..core.config import Config
from ..engines.agent import Agent

log = logging.getLogger("discord_net.scheduler.scripted")


class ScriptedScheduler:
    """Runs configured scripted actions at fixed offsets/rules.

    Each ScriptedAction is scheduled to fire on a loop, optionally spaced by a
    randomized interval so activity looks organic rather than robotic.
    """

    def __init__(self, config: Config, agents: List[Agent]) -> None:
        self.config = config
        self.agents = agents
        self._tasks: List[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        if not self.config.scripted.enabled:
            log.info("Scripted activity disabled; skipping")
            return
        if not self.config.scripted.actions:
            log.warning("No scripted actions defined")
            return
        self._running = True
        for action in self.config.scripted.actions:
            if 0 <= action.account_index < len(self.agents):
                task = asyncio.create_task(self._run_action(action))
                self._tasks.append(task)
        log.info("Scripted scheduler started with %d action task(s)", len(self._tasks))

    async def _run_action(self, action) -> None:
        # iterate so the action repeats at a natural cadence
        while self._running:
            try:
                await self._execute(action)
            except Exception as e:
                log.warning("Scripted action failed: %s", e)
            await asyncio.sleep(random.uniform(60, 180))

    async def _execute(self, action) -> None:
        agent = self.agents[action.account_index]
        if action.delay_before > 0:
            await asyncio.sleep(action.delay_before)

        if action.kind == "message":
            await agent.send_natural(action.channel_id, action.content)
        elif action.kind == "reaction":
            # reaction scripted action needs a message id; try latest message
            await self._react_to_latest(agent, action)
        elif action.kind == "presence":
            await agent.set_presence(action.content or "online", action.emoji or None)
        else:
            log.warning("Unknown scripted action kind: %s", action.kind)

    async def _react_to_latest(self, agent: Agent, action) -> None:
        try:
            channel = agent.api.api_url and action.channel_id
            import aiohttp

            # simplest reliable reaction: send a message containing the emoji is
            # not identical to reacting, so fetch the last message and react.
            if not channel:
                return
            async with aiohttp.ClientSession() as session:
                url = f"{agent.api.api_url}/channels/{action.channel_id}/messages?limit=1"
                async with session.get(url, headers=agent.api._headers()) as resp:
                    if resp.status >= 400:
                        return
                    data = await resp.json()
            if data:
                await agent.api.react(
                    action.channel_id, int(data[0]["id"]), action.emoji or "👍"
                )
        except Exception as e:
            log.warning("Reaction action failed: %s", e)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
