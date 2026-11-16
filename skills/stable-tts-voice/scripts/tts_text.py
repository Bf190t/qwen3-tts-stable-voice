# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""Text preparation for Qwen3-TTS, as used by the Desktop Companion reading voice and tested there.

Copy this file into an app's TTS helper, or import it. Only the standard library is needed.

  prepare_text(text)      what is sent to the model: quotes and title marks dropped, long pauses
                          become a comma, Chinese clock times written out (8:30 -> 8点半)
  split_parts(text)       sentences packed into parts of at most 80 characters; a part with no
                          letters or digits (a lone "”" or "……") is never spoken on its own
  duration_limit(part)    longest believable reading in seconds; past it the model is rambling
  token_limit(part)       the same limit as max_tokens (the 12 Hz codec makes 12.5 tokens/s)
"""
from __future__ import annotations

import math
import re

MAX_PART = 80

# On their own these made Qwen3-TTS produce 1-6 s of noise; inside a sentence they are not read anyway.
_DROP = str.maketrans("", "", "“”‘’「」『』《》〈〉\"")
_PAUSES = re.compile(r"(?:…+|\.{3,}|—{2,}|-{2,}|～+|~+)")
_SENTENCE_END = "。！？!?；;\n"
# "8:30" was read unreliably (dropped at a sentence start, "7:30" heard as "7:00翻").
_CLOCK = re.compile(r"(?<![\d:：])([01]?\d|2[0-3])[:：]([0-5]\d)(?![\d:：])")


def _clock(match: re.Match) -> str:
    hour, minute = int(match.group(1)), int(match.group(2))
    if minute == 0:
        return f"{hour}点"
    if minute == 30:
        return f"{hour}点半"
    return f"{hour}点零{minute}分" if minute < 10 else f"{hour}点{minute}分"


def prepare_text(text: str, language: str = "chinese") -> str:
    """Words are never changed; only marks the model handles badly, and clock times in Chinese."""
    value = (text or "").translate(_DROP)
    if language == "chinese":
        value = _CLOCK.sub(_clock, value)
    value = _PAUSES.sub("，" if language == "chinese" else ",", value)
    value = re.sub(r"[ \t　]+", " ", value).strip()
    value = re.sub(r"[，,、]+(?=[，,。！？!?；;：:.])", "", value)   # comma right before other punctuation
    value = re.sub(r"^[，,、。；;：:！？!?\s]+", "", value)            # nothing to say before the first word
    return value


def speakable(text: str) -> bool:
    return any(ch.isalnum() for ch in text)


def _glue(a: str, b: str) -> str:
    """Joins two pieces; Latin words keep a space between them ("Really? Yes!")."""
    if a and b and a[-1].isascii() and not a[-1].isspace() and b[0].isascii() and b[0].isalnum():
        return a + " " + b
    return a + b


def split_parts(text: str, maximum: int = MAX_PART) -> list[str]:
    sentences, start = [], 0
    for i, ch in enumerate(text):
        if ch in _SENTENCE_END:
            sentences.append(text[start:i + 1]); start = i + 1
    if start < len(text):
        sentences.append(text[start:])
    pieces = []
    for sentence in sentences:
        while len(sentence) > maximum:
            window = sentence[:maximum]
            cut = max(window.rfind("，"), window.rfind(","), window.rfind("、"), window.rfind(" "))
            cut = cut + 1 if cut >= maximum // 3 else maximum
            pieces.append(sentence[:cut]); sentence = sentence[cut:]
        if sentence:
            pieces.append(sentence)
    parts: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if not speakable(piece):
            if parts:
                parts[-1] += piece
            continue
        if parts and len(parts[-1]) + len(piece) < maximum:
            parts[-1] = _glue(parts[-1], piece)
        else:
            parts.append(piece)
    return parts


def spoken_chars(text: str) -> int:
    return sum(ch.isalnum() for ch in text)


def duration_limit(text: str) -> float:
    """Measured readings run 0.20-0.25 s per character; 0.45 s/char + 4 s leaves room for slow voices."""
    return max(4.0, spoken_chars(text) * 0.45 + 4.0)


def token_limit(text: str) -> int:
    return math.ceil(duration_limit(text) * 12.5)


if __name__ == "__main__":
    import sys
    source = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    for i, part in enumerate(split_parts(prepare_text(source)), 1):
        print(f"{i:02d}  {len(part):3d}  {part}")
