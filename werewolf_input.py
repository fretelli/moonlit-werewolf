"""Voice-game commands and two-step confirmation state."""
from enum import IntEnum


class Command(IntEnum):
    ABSTAIN = 0
    CONFIRM = 20
    CANCEL = 21
    START = 22
    PAUSE = 23
    CONTINUE = 24
    END = 25
    REPEAT = 26


class Selection:
    """Two-phase input; confirmation without a candidate has no effect."""

    def __init__(self, allowed):
        self.allowed = frozenset(allowed)
        self.pending = None
        self.committed = False

    def feed(self, command):
        if self.committed:
            return "ignored", None
        if command == Command.CANCEL:
            self.pending = None
            return "cancelled", None
        if command == Command.CONFIRM:
            if self.pending is None:
                return "ignored", None
            self.committed = True
            return "confirmed", self.pending
        if command in self.allowed:
            self.pending = command
            return "preview", command
        return "invalid", None
