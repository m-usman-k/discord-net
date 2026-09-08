import random
import re

# Famous, widely-used abbreviations/contractions. Each entry:
# (regex to find, replacement, probability applied when found)
# Kept to stuff people actually type in Discord. Lower probability = rarer.

# Strong first-tier: very common in casual chat, applied fairly often.
ABBREVIATIONS = [
    (re.compile(r"\bto be honest\b", re.I), "tbh", 0.55),
    (re.compile(r"\bplease\b", re.I), "plz", 0.5),
    (re.compile(r"\bthough\b", re.I), "tho", 0.5),
    (re.compile(r"\bhonestly\b", re.I), "ngl", 0.45),
    (re.compile(r"\bi don't know\b", re.I), "idk", 0.6),
    (re.compile(r"\bby the way\b", re.I), "btw", 0.45),
    (re.compile(r"\bbecause\b", re.I), "cuz", 0.45),
    (re.compile(r"\bthanks\b", re.I), "thx", 0.5),
    (re.compile(r"\bthank you\b", re.I), "ty", 0.4),
    (re.compile(r"\bfor real\b", re.I), "fr", 0.4),
    (re.compile(r"\btalk to you later\b", re.I), "ttyl", 0.4),
    (re.compile(r"\bbe right back\b", re.I), "brb", 0.4),
    (re.compile(r"\boh my god\b", re.I), "omg", 0.4),
    (re.compile(r"\bin my opinion\b", re.I), "imo", 0.4),
]

# Second tier: applied a bit less often, still famous.
ABBREVIATIONS_RARE = [
    (re.compile(r"\bsomething\b", re.I), "smth", 0.3),
    (re.compile(r"\byou\b", re.I), "u", 0.2),
    (re.compile(r"\bno problem\b", re.I), "np", 0.3),
    (re.compile(r"\bsee you later\b", re.I), "cya", 0.3),
    (re.compile(r"\bgood morning\b", re.I), "gm", 0.3),
    (re.compile(r"\bwhats up\b", re.I), "sup", 0.35),
    (re.compile(r"\bwhat's up\b", re.I), "sup", 0.35),
    (re.compile(r"\bright now\b", re.I), "rn", 0.3),
    (re.compile(r"\bokay\b", re.I), "ok", 0.3),
]

# Dropped apostrophes: famously human, e.g. dont, cant, im, youre its thats.
# Only applied to the common set so it never looks contrived.
DROPPED_APOSTROPHES = [
    "don't", "can't", "won't", "it's", "that's", "what's", "i'm", "you're",
    "doesn't", "isn't", "let's", "they're", "i've", "you've", "we're",
]

LOWER_START_PROB = 0.12       # first letter sometimes lowercase
DROPPED_APOSTROPHE_PROB = 0.18
LOWERCASE_I_PROB = 0.15       # standalone "I" -> "i", a classic
TRAILING_PERIOD_PROB = 0.12   # drop a single final period


class Naturalizer:
    """Injects subtle human imperfections into generated text.

    Only uses turns-of-phrase that are famously common in casual chat
    (plz, tbh, idk, tho, cuz, thx, dropped apostrophes, lowercase i,
    occasionally-unpunctuated sentences). Each tweak is probabilistic so
    messages feel original, never rewritten.
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def naturalize(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        t = text
        t = self._lower_start(t)
        t = self._drop_apostrophes(t)
        t = self._abbreviate(t)
        t = self._lowercase_i(t)
        t = self._trim_trailing_period(t)
        t = t.strip()
        return t

    def _lower_start(self, t: str) -> str:
        if random.random() < LOWER_START_PROB and t[:1].isupper():
            return t[0].lower() + t[1:]
        return t

    def _drop_apostrophes(self, t: str) -> str:
        if random.random() > DROPPED_APOSTROPHE_PROB:
            return t
        for phrase in DROPPED_APOSTROPHES:
            t = re.sub(rf"\b{re.escape(phrase)}\b", phrase.replace("'", ""), t, flags=re.I)
        return t

    def _abbreviate(self, t: str) -> str:
        for pat, repl, prob in ABBREVIATIONS + ABBREVIATIONS_RARE:
            if random.random() < prob:
                t = pat.sub(repl, t)
        return t

    def _lowercase_i(self, t: str) -> str:
        if random.random() < LOWERCASE_I_PROB:
            t = re.sub(r"\bI\b", "i", t)
        return t

    def _trim_trailing_period(self, t: str) -> str:
        if random.random() < TRAILING_PERIOD_PROB:
            stripped = t.rstrip()
            if stripped.endswith("."):
                return stripped[:-1]
        return t