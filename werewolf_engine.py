"""Six-player deterministic rules. No IO, logging or implicit timeout actions.

Private state is deliberately excluded from repr and public_state. This is an
application boundary, not protection against someone inspecting process memory.
"""
from collections import Counter
from enum import Enum


class Role(str, Enum):
    WOLF = "wolf"
    SEER = "seer"
    VILLAGER = "villager"


class RuleError(ValueError):
    """Generic errors must never include secret values."""


class Game:
    ROLE_COUNTS = Counter({Role.WOLF: 2, Role.SEER: 1, Role.VILLAGER: 3})

    def __init__(self):
        self.phase = "registration"
        self.round = 0
        self.alive = set()
        self.winner = None
        self.last_eliminated = None
        self.speaker = None
        self.voter = None
        self.runoff = False
        self._roles = {}
        self._night_target = None
        self._wolf_submitted = False
        self._seer_submitted = False
        self._votes = {}
        self._candidates = set()
        self._speakers = []
        self._published_tally = {}

    def _require(self, phase):
        if self.phase != phase:
            raise RuleError("当前阶段不接受此操作")

    @staticmethod
    def _seat(seat):
        if type(seat) is not int or seat not in range(1, 7):
            raise RuleError("座位编号无效")

    @property
    def registration_seat(self):
        return len(self._roles) + 1 if len(self._roles) < 6 else None

    def register(self, seat, role):
        self._require("registration")
        self._seat(seat)
        if seat != self.registration_seat:
            raise RuleError("请按座位顺序登记，不可重复登记")
        try:
            role = Role(role)
        except (ValueError, TypeError):
            raise RuleError("身份无效") from None
        if Counter(self._roles.values())[role] >= self.ROLE_COUNTS[role]:
            raise RuleError("身份配置不符，请重新开局")
        self._roles[seat] = role

    def start(self):
        self._require("registration")
        if Counter(self._roles.values()) != self.ROLE_COUNTS:
            raise RuleError("登记尚未完成")
        self.alive = set(range(1, 7))
        self._begin_night()

    def _begin_night(self):
        self.round += 1
        self.phase = "night_wolf"
        self._night_target = None
        self._wolf_submitted = False
        self._seer_submitted = False
        self.speaker = self.voter = None
        self.runoff = False
        self._votes.clear()
        self._candidates.clear()
        self._published_tally.clear()

    def wolf_targets(self):
        """PRIVATE: only the night input controller may use this result."""
        self._require("night_wolf")
        return {s for s in self.alive if self._roles[s] != Role.WOLF}

    def choose_wolf_target(self, target):
        self._require("night_wolf")
        self._seat(target)
        if self._wolf_submitted or target not in self.wolf_targets():
            raise RuleError("此选择不可提交")
        self._night_target = target
        self._wolf_submitted = True
        # Do not advance immediately: controller must finish fixed night window.

    def finish_wolf_window(self):
        self._require("night_wolf")
        if not self._wolf_submitted:
            raise RuleError("行动未完成，不得自动选择或进入下一阶段")
        self.phase = "night_seer"

    def seer_alive(self):
        """PRIVATE: a dead seer still receives an equal-length dummy window."""
        return any(self._roles[s] == Role.SEER for s in self.alive)

    def seer_targets(self):
        self._require("night_seer")
        if not self.seer_alive():
            return set()
        return {s for s in self.alive if self._roles[s] != Role.SEER}

    def inspect(self, target):
        self._require("night_seer")
        self._seat(target)
        if self._seer_submitted or target not in self.seer_targets():
            raise RuleError("此选择不可提交")
        self._seer_submitted = True
        return self._roles[target] == Role.WOLF

    def finish_seer_window(self):
        self._require("night_seer")
        if self.seer_alive() and not self._seer_submitted:
            raise RuleError("行动未完成，不得自动跳过")
        # Night casualties resolve after seer action, including a targeted seer.
        self.alive.remove(self._night_target)
        self.last_eliminated = self._night_target
        self._night_target = None
        if not self._check_winner():
            self.phase = "day_speech"
            self._speakers = sorted(self.alive)
            self.speaker = self._speakers[0]

    def finish_speech(self, seat):
        self._require("day_speech")
        self._seat(seat)
        if seat != self.speaker:
            raise RuleError("不是当前发言座位")
        self._speakers.pop(0)
        self.speaker = self._speakers[0] if self._speakers else None
        if self.speaker is None:
            self.phase = "day_vote"
            self._candidates = set(self.alive)
            self._votes.clear()
            self.voter = min(self.alive)

    def vote_targets(self):
        self._require("day_vote")
        # Self-votes are allowed. Abstention is represented by None.
        return set(self._candidates)

    def vote(self, seat, target):
        self._require("day_vote")
        self._seat(seat)
        if seat != self.voter or seat in self._votes:
            raise RuleError("不是当前投票座位")
        if target is not None:
            self._seat(target)
            if target not in self._candidates:
                raise RuleError("投票目标无效")
        self._votes[seat] = target
        remaining = sorted(self.alive - self._votes.keys())
        self.voter = remaining[0] if remaining else None
        if self.voter is None:
            self.phase = "vote_result"

    def resolve_votes(self):
        self._require("vote_result")
        counts = Counter(t for t in self._votes.values() if t is not None)
        self._published_tally = {s: counts[s] for s in sorted(self._candidates)}
        leaders = {s for s, n in counts.items() if n == max(counts.values())} if counts else set()
        self._votes.clear()
        if len(leaders) > 1 and not self.runoff:
            self.runoff = True
            self._candidates = leaders
            self.phase = "day_vote"
            self.voter = min(self.alive)
            return None
        self.last_eliminated = next(iter(leaders)) if len(leaders) == 1 else None
        if self.last_eliminated is not None:
            self.alive.remove(self.last_eliminated)
        if not self._check_winner():
            self.phase = "day_result"
        return self.last_eliminated

    def next_night(self):
        self._require("day_result")
        self._begin_night()

    def _check_winner(self):
        wolves = sum(self._roles[s] == Role.WOLF for s in self.alive)
        good = len(self.alive) - wolves
        if wolves == 0:
            self.winner = "good"
        elif wolves >= good:
            self.winner = "wolves"
        if self.winner:
            self.phase = "finished"
            self.speaker = self.voter = None
            return True
        return False

    def abort(self):
        """Forget secrets on controlled termination; no resumable save file."""
        self.phase = "aborted"
        self._roles.clear()
        self._votes.clear()
        self._night_target = None
        self._candidates.clear()
        self.speaker = self.voter = None

    def public_state(self):
        """Allowlisted output. Never serialize this object's __dict__."""
        return {
            "phase": self.phase,
            "round": self.round,
            "alive": sorted(self.alive),
            "registered": len(self._roles) if self.phase == "registration" else None,
            "speaker": self.speaker,
            "voter": self.voter,
            "runoff": self.runoff,
            "candidates": sorted(self._candidates) if self.phase in ("day_vote", "vote_result") else [],
            "tally": dict(self._published_tally),
            "last_eliminated": self.last_eliminated,
            "winner": self.winner,
        }
