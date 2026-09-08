import asyncio
import logging
import random

log = logging.getLogger("discord_net.core.typing")

WORDS_PER_MIN = (40, 65)  # casual human typing speed


def estimate_seconds(text: str) -> float:
    """Estimate how long a human would take typing this text."""
    words = max(1, len((text or "").split()))
    wpm = random.uniform(*WORDS_PER_MIN)
    return (words / wpm) * 60.0


async def simulate_typing(text: str, min_seconds: float = 1.5, max_seconds: float = 15.0) -> None:
    """Sleep for a realistic 'typing + thinking' duration."""
    est = estimate_seconds(text)
    jitter = random.uniform(1.0, 4.0)
    total = est + jitter
    total = max(min_seconds, min(total, max_seconds))
    log.info("Typing for %.1fs...", total)
    await asyncio.sleep(total)