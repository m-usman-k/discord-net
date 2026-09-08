import logging
import random
import re

from ..core.api import ZenLLM
from ..core.humanize import Naturalizer
from ..core.learnora_context import CONTEXT_SYSTEM_PROMPT

log = logging.getLogger("discord_net.engines.generator")


class MessageGenerator:
    """Generates natural Discord-style replies about the Learnora community.

    Primary path uses the OpenCode Zen LLM. If it is unavailable or fails, a
    lightweight local template fallback keeps the bot functional offline.
    """

    def __init__(
        self,
        llm: ZenLLM | None = None,
        use_llm: bool = True,
        local_fallback: bool = True,
    ) -> None:
        self.llm = llm
        self.use_llm = use_llm
        self.local_fallback = local_fallback
        self.naturalizer = Naturalizer(enabled=True)

    # ------------------------------------------------------------------ #
    # LLM-backed replies
    # ------------------------------------------------------------------ #
    async def reply(
        self,
        conversation: list,
        personality: str,
        extra_instruction: str = "",
    ) -> str | None:
        """Generate a reply from the LLM given recent conversation context."""
        if not (self.use_llm and self.llm and self.llm.api_key):
            return None

        sys = CONTEXT_SYSTEM_PROMPT
        if personality:
            sys += f"\nYour persona: {personality}.\n"
        if extra_instruction:
            sys += f"\nSpecial this turn: {extra_instruction}\n"

        messages = [{"role": "system", "content": sys}] + conversation[-12:]
        return await self.llm.complete(messages)

    # ------------------------------------------------------------------ #
    # Local fallback (no LLM needed)
    # ------------------------------------------------------------------ #
    def _local_reply(self, message: str, personality: str = "") -> str:
        text = (message or "").strip().lower()
        if not text:
            return random.choice(
                ["honestly learnora is such a time saver", "anyone else use the flashcards a lot?",
                 "I dropped a 200 page PDF in earlier, instant notes", "spaced repetition is underrated"]
            )
        if re.search(r"\b(hi|hey|hello|yo|sup)\b", text):
            return random.choice(["hey! what's up", "yo", "hi!"])
        if "learnora" in text:
            return random.choice(
                ["I love the note system, so clean", "the AI tutor is the best part tbh",
                 "yeah I've been using it for all my classes this semester"]
            )
        if any(w in text for w in ["flashcard", "memorize", "remember"]):
            return "try the flashcards, spaced repetition actually works"
        if any(w in text for w in ["quiz", "test", "exam", "sat"]):
            return "the quiz generator is pretty solid for that"
        return random.choice(
            ["that makes sense", "same honestly", "good point",
             "yeah I think so too", "that tracks"]
        )

    # ------------------------------------------------------------------ #
    # Post-processing to de-AI response text
    # ------------------------------------------------------------------ #
    @staticmethod
    def humanize(text: str) -> str:
        """Strip AI-ish punctuation and formatting artifacts."""
        text = (text or "").strip()
        text = re.sub(r"[\u2014\u2013]", "-", text)          # em/en dash
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = re.sub(r"[ \t]+", " ", text)                   # collapse spaces
        text = re.sub(r"\n{2,}", "\n", text)                  # collapse newlines
        text = re.sub(r"^[\s>*#\-]+", "", text)               # strip list/md prefixes
        text = text.strip()
        if not text:
            return text
        if not text[0].isupper() and text[0].isalpha():
            text = text[0].upper() + text[1:]
        return text

    def pick_reaction(self) -> str:
        return random.choice(["👍", "🔥", "😂", "🙌", "👀", "💯", "🎉"])

    # ------------------------------------------------------------------ #
    # Final pipeline: clean AI artifacts, then inject human imperfections
    # ------------------------------------------------------------------ #
    def finalize(self, text: str) -> str:
        """Apply the full post-LLM pipeline: humanize() then naturalize()."""
        if not text:
            return ""
        cleaned = self.humanize(text)
        return self.naturalizer.naturalize(cleaned)