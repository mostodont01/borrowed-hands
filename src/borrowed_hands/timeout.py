"""Inactivity rule, independent of Qt so it can be tested with a fake clock.

After `idle_limit` seconds without progress the user is asked whether to continue.
If they don't answer within `prompt_limit` seconds, the session ends.
"""

from enum import Enum


class Phase(Enum):
    ACTIVE = "active"
    PROMPT = "prompt"
    ENDED = "ended"


class InactivityTimer:
    def __init__(self, now: float, idle_limit: float = 120.0, prompt_limit: float = 60.0):
        self.idle_limit = idle_limit
        self.prompt_limit = prompt_limit
        self.phase = Phase.ACTIVE
        self._since = now

    def activity(self, now: float) -> None:
        """Progress happened (input, page load, Claude acted). Ignored while prompting."""
        if self.phase is Phase.ACTIVE:
            self._since = now

    def answer(self, keep_going: bool, now: float) -> None:
        if self.phase is not Phase.PROMPT:
            return
        if keep_going:
            self.phase = Phase.ACTIVE
            self._since = now
        else:
            self.phase = Phase.ENDED

    def end(self) -> None:
        self.phase = Phase.ENDED

    def tick(self, now: float) -> Phase:
        if self.phase is Phase.ACTIVE and now - self._since >= self.idle_limit:
            self.phase = Phase.PROMPT
            self._since = now
        elif self.phase is Phase.PROMPT and now - self._since >= self.prompt_limit:
            self.phase = Phase.ENDED
        return self.phase

    def seconds_left(self, now: float) -> int:
        """Seconds until the current phase runs out."""
        if self.phase is Phase.ENDED:
            return 0
        limit = self.idle_limit if self.phase is Phase.ACTIVE else self.prompt_limit
        return max(0, int(round(limit - (now - self._since))))
