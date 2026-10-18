"""
Message moderation.

`moderate()` is the single entry point the WebSocket consumer calls. It masks
blocked words instead of dropping the message, so conversations keep flowing.
To plug in an AI moderation model later (OpenAI moderation, Perspective API,
a local classifier), call it inside `moderate()` and set `flagged` from its score.
"""
import re
import time
from collections import deque
from dataclasses import dataclass

from django.conf import settings

# Keep this list short and obvious for the demo; load from a file or DB in production.
BLOCKED_WORDS = {"idiot", "stupid", "dumb", "loser", "shut up"}

_pattern = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(BLOCKED_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


@dataclass
class ModerationResult:
    ok: bool
    text: str = ""
    flagged: bool = False
    error: str = ""


def moderate(raw):
    if not isinstance(raw, str):
        return ModerationResult(ok=False, error="Message must be text.")
    text = raw.strip()
    if not text:
        return ModerationResult(ok=False, error="Message is empty.")
    limit = settings.CHAT_MAX_MESSAGE_LENGTH
    if len(text) > limit:
        return ModerationResult(ok=False, error=f"Message is longer than {limit} characters.")

    masked, count = _pattern.subn(lambda m: "*" * len(m.group(0)), text)
    return ModerationResult(ok=True, text=masked, flagged=count > 0)


class RateLimiter:
    """Sliding-window limiter, one per WebSocket connection."""

    def __init__(self, max_events=None, window=None, clock=time.monotonic):
        self.max_events = max_events or settings.CHAT_RATE_LIMIT_MESSAGES
        self.window = window or settings.CHAT_RATE_LIMIT_WINDOW
        self.clock = clock
        self.events = deque()

    def allow(self):
        now = self.clock()
        while self.events and now - self.events[0] > self.window:
            self.events.popleft()
        if len(self.events) >= self.max_events:
            return False
        self.events.append(now)
        return True
