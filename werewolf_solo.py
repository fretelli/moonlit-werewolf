"""One human at seat 1; five limited-information computer players."""
import inspect
import random

from werewolf_bots import Bot
from werewolf_engine import Role
from werewolf_host import Host
from werewolf_input import Command


async def resolve(value):
    return await value if inspect.isawaitable(value) else value


class SoloHost(Host):
    def __init__(self, device, report=None, *, rng=None, bot_factory=Bot):
        super().__init__(device, report)
        self.rng = rng or random.SystemRandom()
        self.bot_factory = bot_factory
        self.roles = {}
        self.bots = {}
        self.accusations = {}

    def deal(self):
        deck = [Role.WOLF, Role.WOLF, Role.SEER] + [Role.VILLAGER] * 3
        self.rng.shuffle(deck)
        self.roles = dict(enumerate(deck, 1))
        wolves = {s for s, role in self.roles.items() if role == Role.WOLF}
        for seat, role in self.roles.items():
            self.game.register(seat, role)
            if seat != 1:
                self.bots[seat] = self.bot_factory(
                    seat, role, wolves - {seat} if role == Role.WOLF else ())

    def forget(self):
        self.roles.clear()
        for bot in self.bots.values():
            bot.forget()
        self.bots.clear()
        self.accusations.clear()

    async def reveal(self, symbol):
        # No role value is spoken or included in public reporting.
        await self.device.show(symbol)
        try:
            await self.select({Command.CONTINUE}, controls=False)
        finally:
            await self.device.clear_secret()

    async def night(self):
        self.publish()
        await self.device.say("solo_night")
        wolves = sorted(s for s in self.game.alive if self.roles[s] == Role.WOLF)
        if 1 in wolves:
            await self.device.say("solo_wolf_action")
            await self.night_action(self.game.wolf_targets(), self.game.choose_wolf_target)
        else:
            target = await resolve(self.bots[wolves[0]].choose(
                self.game.alive, dict(self.accusations)
            ))
            self.game.choose_wolf_target(target)
        self.game.finish_wolf_window()
        self.publish()
        seer = next((s for s in self.game.alive if self.roles[s] == Role.SEER), None)
        if seer == 1:
            await self.device.say("solo_seer_action")
            await self.night_action(self.game.seer_targets(), self.game.inspect)
        elif seer is not None:
            bot = self.bots[seer]
            target = await resolve(bot.inspect_target(self.game.alive))
            bot.remember(target, self.game.inspect(target))
        # No computer target or result is rendered, even after human elimination.
        await self.device.sleep(1)
        await self.device.clear_secret()
        self.game.finish_seer_window()
        self.publish()
        await self.device.say("dawn")
        await self.device.say(f"seat_{self.game.last_eliminated}")
        if self.game.last_eliminated == 1:
            await self.device.say("solo_spectator")

    async def speeches(self):
        await self.observe_public("day_speech")
        self.accusations.clear()
        while self.game.phase == "day_speech":
            seat = self.game.speaker
            self.publish()
            await self.device.say(f"speaker_{seat}")
            if seat == 1:
                await self.device.say("solo_accuse")
                value = await self.select(self.game.alive | {0},
                                          timeout=60, prompt="solo_accuse")
                target = value if value else None
            else:
                target = await resolve(self.bots[seat].choose(
                    self.game.alive, dict(self.accusations)
                ))
            if target is None:
                await self.device.say("solo_no_opinion")
            else:
                self.accusations[seat] = target
                await self.device.say("solo_suspect")
                await self.device.say(f"seat_{target}")
            self.game.finish_speech(seat)

    async def voting(self):
        while self.game.phase == "day_vote":
            await self.device.say("vote")
            while self.game.phase == "day_vote":
                seat = self.game.voter
                self.publish()
                if seat == 1:
                    await self.device.say("voter_1")
                    value = await self.select(self.game.vote_targets() | {0}, prompt="vote")
                    target = value or None
                else:
                    # Only public candidates/opinions and this bot's private memory.
                    target = await resolve(self.bots[seat].choose(
                        self.game.vote_targets(), dict(self.accusations)
                    ))
                self.game.vote(seat, target)
            self.game.resolve_votes()
            self.publish()
            await self.device.say("tally")
            for seat, votes in self.game.public_state()["tally"].items():
                await self.device.say(f"seat_{seat}")
                await self.device.say(f"votes_{votes}")
            if self.game.phase == "day_vote":
                await self.device.say("runoff")
                await self.device.say("candidates")
                for seat in sorted(self.game.vote_targets()):
                    await self.device.say(f"seat_{seat}")
        if self.game.last_eliminated is None:
            await self.device.say("none")
        else:
            await self.device.say("eliminated")
            await self.device.say(f"seat_{self.game.last_eliminated}")
            if self.game.last_eliminated == 1:
                await self.device.say("solo_spectator")

    async def run(self):
        try:
            await self.device.clear_secret()
            await self.device.say("solo_ready")
            await self.select({Command.START}, prompt="solo_ready")
            await self.observe_public("lobby")
            self.deal()
            self.publish()
            await self.device.say("solo_role")
            await self.reveal({Role.WOLF: "wolf", Role.SEER: "seer",
                               Role.VILLAGER: "villager"}[self.roles[1]])
            if self.roles[1] == Role.WOLF:
                await self.device.say("solo_partner")
                partner = next(s for s, r in self.roles.items() if s != 1 and r == Role.WOLF)
                await self.reveal(partner)
            self.game.start()
            while not self.game.winner:
                await self.device.say("solo_next")
                await self.select({Command.CONTINUE}, prompt="solo_next")
                await self.night()
                if not self.game.winner:
                    await self.speeches()
                    await self.voting()
                if not self.game.winner:
                    self.game.next_night()
            self.publish()
            await self.device.clear_secret()
            await self.device.say("good_win" if self.game.winner == "good" else "wolves_win")
        finally:
            self.forget()
