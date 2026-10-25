"""Solo policies and scripted integration: no real robot or speech recognition."""
import random
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werewolf_bots import Bot
from werewolf_device import GameStopped
from werewolf_engine import Role
from werewolf_input import Command
from werewolf_solo import SoloHost
from werewolf_speech import TEXTS, load_clips
from test_werewolf_host import FakeDevice


class BotTests(unittest.TestCase):
    def test_information_boundary(self):
        bot = Bot(3, Role.VILLAGER, {1, 2}, random.Random(7))
        self.assertFalse(bot.teammates)
        self.assertFalse(hasattr(bot, "game"))
        self.assertFalse(hasattr(bot, "roles"))
        with self.assertRaises(ValueError):
            bot.remember(1, True)
        twin = Bot(3, Role.VILLAGER, rng=random.Random(7))
        self.assertEqual([bot.choose(range(1, 7), {1: 4}) for _ in range(20)],
                         [twin.choose(range(1, 7), {1: 4}) for _ in range(20)])

    def test_wolf_never_targets_team(self):
        bot = Bot(2, Role.WOLF, {1}, random.Random(0))
        for _ in range(50):
            self.assertIn(bot.choose(range(1, 7), {3: 1}), {3, 4, 5, 6})
        self.assertIsNone(bot.choose({1, 2}))

    def test_seer_uses_only_own_results(self):
        bot = Bot(3, Role.SEER, rng=random.Random(0))
        bot.remember(2, True)
        bot.remember(4, False)
        self.assertEqual(bot.choose({1, 2, 3, 4}, {1: 4}), 2)
        self.assertIn(bot.inspect_target({1, 2, 3, 4, 5}), {1, 5})
        bot.forget()
        self.assertFalse(bot.inspections)

    def test_all_audio_present(self):
        audio_dir = Path(__file__).resolve().parents[1] / "assets" / "werewolf_speech"
        if not any(audio_dir.glob("*.wav")):
            self.skipTest("源代码仓库不分发主持 WAV；准备本地音频后再执行完整资源校验")
        self.assertEqual(set(load_clips()), set(TEXTS))


class SoloTests(unittest.IsolatedAsyncioTestCase):
    async def test_many_full_games_all_human_roles(self):
        roles, winners = set(), set()
        for seed in range(30):
            device = FakeDevice()
            reports = []
            host = SoloHost(device, lambda **kw: reports.append(kw), rng=random.Random(seed),
                            bot_factory=lambda s, r, t: Bot(s, r, t, random.Random(seed * 10 + s)))
            async def select(allowed, **kwargs):
                allowed = set(allowed)
                if Command.START in allowed:
                    return Command.START
                if Command.CONTINUE in allowed:
                    if host.roles:
                        roles.add(host.roles[1])
                    return Command.CONTINUE
                self.assertIn(1, host.game.alive)
                if host.game.phase == "day_speech":
                    return 0
                return min(allowed - {0})
            host.select = AsyncMock(side_effect=select)
            host.night_seconds = 0
            await host.run()
            self.assertIn(host.game.winner, {"good", "wolves"})
            winners.add(host.game.winner)
            self.assertLessEqual(host.game.round, 6)
            self.assertFalse(host.roles)
            self.assertFalse(host.bots)
            self.assertEqual(reports[-1]["game"]["phase"], "finished")
            for call in device.say.await_args_list:
                self.assertIn(call.args[0], TEXTS)
            for report in reports:
                self.assertNotIn("roles", report["game"])
                self.assertNotIn("inspections", report["game"])
        self.assertEqual(roles, set(Role))
        self.assertEqual(winners, {"good", "wolves"})

    async def test_secret_clear_failure_does_not_proceed(self):
        device = FakeDevice()
        host = SoloHost(device)
        host.select = AsyncMock(return_value=Command.CONTINUE)
        device.clear_secret.side_effect = RuntimeError("clear failed")
        with self.assertRaises(RuntimeError):
            await host.reveal("wolf")
        device.say.assert_not_awaited()

    async def test_abort_forgets_deal(self):
        device = FakeDevice()
        host = SoloHost(device)
        host.select = AsyncMock(side_effect=[Command.START, GameStopped()])
        with self.assertRaises(GameStopped):
            await host.run()
        self.assertFalse(host.roles)
        self.assertFalse(host.bots)

    async def test_start_plays_current_voice_prompt_then_listens(self):
        device = FakeDevice()
        host = SoloHost(device)
        host.select = AsyncMock(side_effect=GameStopped())
        with self.assertRaises(GameStopped):
            await host.run()
        device.say.assert_awaited_once_with("solo_ready")
        host.select.assert_awaited_once_with({Command.START}, prompt="solo_ready")
