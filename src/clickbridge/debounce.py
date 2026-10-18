"""One key per press: fire on the rising edge only, ignore contact chatter."""
from __future__ import annotations

CHATTER_S = 0.08


class Debouncer:
    def __init__(self, chatter_s: float = CHATTER_S):
        self.chatter_s = chatter_s
        self.held: set[str] = set()
        self.last_fire: dict[str, float] = {}

    def update(self, pressed: set[str], now: float) -> list[str]:
        """Return the buttons that must fire for this frame."""
        new = pressed - self.held
        self.held = set(pressed)
        fire = []
        for name in sorted(new):
            if now - self.last_fire.get(name, float("-inf")) < self.chatter_s:
                continue
            self.last_fire[name] = now
            fire.append(name)
        return fire

    def reset(self) -> None:
        self.held = set()
