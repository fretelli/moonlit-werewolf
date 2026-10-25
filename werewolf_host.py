"""Shared orchestration primitives for the voice-only solo game."""
import time

from werewolf_device import GameStopped
from werewolf_engine import Game
from werewolf_input import Command


class Host:
    def __init__(self, device, report=None, night_seconds=45, speech_seconds=60):
        self.device = device
        self.game = Game()
        self.report = report or (lambda **fields: None)
        self.night_seconds = night_seconds
        self.speech_seconds = speech_seconds

    async def observe_public(self, phase):
        # Retained as a phase hook; voice-only mode has no public sensor work.
        return None

    def publish(self):
        self.report(game=self.game.public_state())

    async def pause(self):
        await self.device.clear_secret()
        await self.device.say("paused")
        await self.select({Command.CONTINUE, Command.END}, controls=False)
        await self.device.say("resume")

    async def select(self, allowed, *, controls=True, timeout=None, prompt=None):
        raise NotImplementedError

    async def night_action(self, allowed, action, *, dummy=False):
        started = time.monotonic()
        if dummy:
            await self.device.sleep(self.night_seconds)
        else:
            value = await self.select(allowed, controls=False,
                                      timeout=max(0, self.night_seconds - 5))
            if value is None:
                raise GameStopped("夜间输入未完成，本局安全中止")
            result = action(value)
            if isinstance(result, bool):
                await self.device.show("wolf" if result else "good")
                await self.device.sleep(3)
            remaining = self.night_seconds - (time.monotonic() - started)
            if remaining > 0:
                await self.device.sleep(remaining)
        await self.device.clear_secret()
