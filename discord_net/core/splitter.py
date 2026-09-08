"""Split long messages into multiple smaller, natural-sounding ones."""

import re

MAX_CHUNK = 180


def split_message(text: str, max_len: int = MAX_CHUNK) -> list:
    """Split text into 1..N chunks at sentence/word boundaries.

    Returns a list of trimmed chunks; if text is short, returns [text].
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    # Split into sentences first (., !, ? followed by space/end)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks: list = []
    current = ""

    for sent in sentences:
        if len(current) + len(sent) + 1 <= max_len:
            current = (current + " " + sent).strip() if current else sent
        else:
            # sentence itself too long: hard-split by words
            while len(sent) > max_len:
                cut = sent[:max_len]
                # try to cut at a space
                sp = cut.rfind(" ")
                if sp > max_len * 0.6:
                    cut = cut[:sp]
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(cut.strip())
                sent = sent[len(cut):].strip()
            if current:
                chunks.append(current)
                current = sent
            else:
                current = sent

    if current:
        chunks.append(current)

    # fix trailing fragments at start when a chunk starts lowercase w/ comma etc.
    cleaned = []
    for c in chunks:
        c = c.strip()
        if not c:
            continue
        cleaned.append(c)
    return cleaned