"""Tests for shared voice-only host orchestration."""
import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werewolf_device import GameStopped
from werewolf_host import Host
from werewolf_input import Command


class FakeDevice:
    def __init__(self):
        self.say = AsyncMock()
        self.show = AsyncMock()
        self.clear_secret = AsyncMock()
        self.sleep = AsyncMock()


class HostTests(unittest.IsolatedAsyncioTestCase):
    async def test_night_timeout_never_selects_target(self):
        device = FakeDevice()
        host = Host(device, night_seconds=1)
        host.select = AsyncMock(return_value=None)
        action = AsyncMock()
        with self.assertRaises(GameStopped):
            await host.night_action({1, 2}, action)
        action.assert_not_called()

    async def test_dummy_window_uses_no_input_or_result(self):
        device = FakeDevice()
        host = Host(device, night_seconds=45)
        host.select = AsyncMock()
        await host.night_action(set(), None, dummy=True)
        host.select.assert_not_called()
        device.sleep.assert_awaited_once_with(45)
        device.show.assert_not_called()
        device.clear_secret.assert_awaited_once()

    async def test_pause_waits_for_voice_continue(self):
        device = FakeDevice()
        host = Host(device)
        host.select = AsyncMock(return_value=Command.CONTINUE)
        await host.pause()
        device.say.assert_any_await("paused")
        host.select.assert_awaited_once_with(
            {Command.CONTINUE, Command.END}, controls=False
        )
        device.say.assert_any_await("resume")

    async def test_public_observation_has_no_camera_work(self):
        device = FakeDevice()
        host = Host(device)
        self.assertIsNone(await host.observe_public("lobby"))
        device.show.assert_not_called()


if __name__ == "__main__":
    unittest.main()
