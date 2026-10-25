"""Local limited-information policies. Never pass a Game or full role map here."""
import random

from werewolf_engine import Role


class Bot:
    def __init__(self, seat, role, teammates=(), rng=None):
        self.seat = seat
        self.role = Role(role)
        self.teammates = frozenset(teammates) if self.role == Role.WOLF else frozenset()
        self.inspections = {}
        # Independent entropy: policy draws must not expose the deck shuffle RNG.
        self.rng = rng or random.Random()

    def remember(self, target, is_wolf):
        if self.role != Role.SEER:
            raise ValueError("Only the seer receives private inspection results")
        self.inspections[target] = bool(is_wolf)

    def choose(self, candidates, accusations=None):
        pool = set(candidates) - {self.seat}
        if self.role == Role.WOLF:
            pool -= self.teammates
        if not pool:
            return None
        known_wolves = {s for s in pool if self.inspections.get(s) is True}
        if known_wolves:
            pool = known_wolves
        else:
            unknown = {s for s in pool if self.inspections.get(s) is not False}
            if unknown:
                pool = unknown
        # Accusations are unverified public opinions, not knowledge of roles.
        accusations = accusations or {}
        scores = {s: sum(target == s for speaker, target in accusations.items()
                         if speaker != self.seat) for s in pool}
        best = max(scores.values())
        return self.rng.choice(sorted(s for s in pool if scores[s] == best))

    def inspect_target(self, alive):
        if self.role != Role.SEER:
            raise ValueError("Only the seer may inspect")
        pool = set(alive) - {self.seat}
        fresh = pool - self.inspections.keys()
        return self.rng.choice(sorted(fresh or pool))

    def forget(self):
        self.inspections.clear()
        self.teammates = frozenset()
