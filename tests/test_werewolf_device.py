"""Mock SDK lifecycle tests; these never connect to a physical robot."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werewolf_device import Device, GameStopped


async def direct(function, *args, **kwargs):
    return function(*args, **kwargs)


def fixture():
    job = SimpleNamespace(state=SimpleNamespace(terminal=True), wait=Mock())
    robot = SimpleNamespace(
        audio=SimpleNamespace(play_pcm=Mock(return_value=job), stop=Mock()),
        expression_runtime=SimpleNamespace(start=Mock(), update=Mock(), stop=Mock()),
    )
    app = SimpleNamespace(robot=robot, shutdown_requested=False)
    device = Device(app, direct, {"test": SimpleNamespace(data=b"00")})
    return app, device, job


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    async def test_audio_terminal_validated_and_stopped(self):
        app, device, job = fixture()
        await device.say("test")
        job.wait.assert_called_once_with(0.0)
        app.robot.audio.stop.assert_called_once()
        self.assertFalse(device.audio_attempted)

    async def test_audio_failed_start_still_stops(self):
        app, device, _ = fixture()
        app.robot.audio.play_pcm.side_effect = RuntimeError("lost ack")
        with self.assertRaises(RuntimeError):
            await device.say("test")
        app.robot.audio.stop.assert_called_once()

    async def test_failed_stop_cleanup_retries(self):
        app, device, _ = fixture()
        await device.show(1)
        app.robot.audio.stop.side_effect = [RuntimeError("stop failed"), None]
        with self.assertRaises(RuntimeError):
            await device.say("test")
        with self.assertRaises(RuntimeError):
            await device.show(2)
        await device.close()
        self.assertEqual(app.robot.audio.stop.call_count, 2)
        app.robot.expression_runtime.stop.assert_called_once()

    async def test_failed_display_start_cleanup_and_clear_failure_propagates(self):
        app, device, _ = fixture()
        app.robot.expression_runtime.start.side_effect = RuntimeError("lost ack")
        with self.assertRaises(RuntimeError):
            await device.show(1)
        await device.close()
        app.robot.expression_runtime.stop.assert_called_once()
        app.robot.expression_runtime.start.side_effect = None
        await device.show(1)
        app.robot.expression_runtime.update.side_effect = RuntimeError("clear failed")
        with self.assertRaises(RuntimeError):
            await device.clear_secret()
        app.robot.audio.play_pcm.assert_not_called()

    async def test_shutdown_rejects_new_commands_but_permits_cleanup(self):
        app, device, _ = fixture()
        await device.show(1)
        app.shutdown_requested = True
        with self.assertRaises(GameStopped):
            await device.show(2)
        with self.assertRaises(GameStopped):
            await device.say("test")
        await device.close()
        app.robot.expression_runtime.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
