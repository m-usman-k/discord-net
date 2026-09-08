import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .core.api import ZenLLM
from .core.config import Config
from .engines.conversation import ConversationEngine
from .engines.generator import MessageGenerator
from .scheduler.scripted import ScriptedScheduler

load_dotenv()

log = logging.getLogger("discord_net")


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


async def amain(config: Config) -> None:
    errors = config.validate()
    if errors:
        log.error("Configuration errors:")
        for e in errors:
            log.error("  - %s", e)
        sys.exit(1)

    # OpenCode Zen LLM backend (API key from .env / env, config.json fallback).
    api_key = env("LLM_API_KEY") or config.llm.api_key
    llm = ZenLLM(
        base_url=config.llm.base_url,
        api_key=api_key,
        model=config.llm.model,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
    )
    generator = MessageGenerator(llm=llm, use_llm=config.llm.enabled, local_fallback=True)

    if generator.use_llm and api_key:
        log.info("Using OpenCode Zen: %s @ %s", config.llm.model, config.llm.base_url)
    else:
        log.warning("No LLM API key set; using local fallback replies (limited)")

    engine = ConversationEngine(config=config, generator=generator)
    await engine.start()

    scheduler = ScriptedScheduler(config=config, agents=engine.agents)
    await scheduler.start()

    log.info("Running with %d account(s). Ctrl+C to stop.", len(engine.agents))

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await scheduler.stop()
        await engine.stop()


def main() -> None:
    setup_logging()
    config_path = Path(env("CONFIG_PATH", "config.json"))
    config = Config.from_file(config_path, create_template=True)
    log.info("Loaded config from %s", config_path.resolve())

    try:
        asyncio.run(amain(config))
    except KeyboardInterrupt:
        log.info("Shutting down...")


if __name__ == "__main__":
    main()