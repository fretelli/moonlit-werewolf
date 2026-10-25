"""Offline voice tests; never acquire a real hardware or audio device."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werewolf_voice import (LocalRecognizer, parse_command, require_voice_capabilities,
                            VoiceDevice, VoiceSoloHost)
from werewolf_input import Command
from werewolf_device import GameStopped


class CapabilityTests(unittest.TestCase):
    def robot(self, capabilities):
        available = tuple(capabilities)
        return SimpleNamespace(capabilities=available,
                               supports=lambda name: name in available)

    def test_complete_voice_capabilities_are_accepted(self):
        require_voice_capabilities(self.robot({
            "audio.stream", "microphone", "expression.runtime.v3"
        }))

    def test_missing_capability_reports_current_device_snapshot(self):
        robot = self.robot({"microphone", "expression.runtime.v3"})
        with self.assertRaisesRegex(RuntimeError, "audio.stream") as caught:
            require_voice_capabilities(robot)
        message = str(caught.exception)
        self.assertIn("Desktop Link", message)
        self.assertIn("设备当前上报能力", message)
        self.assertIn("microphone", message)


class ParserTests(unittest.TestCase):
    def test_exact_commands(self):
        for text, expected in [("开始游戏", Command.START), (" 确 认。", Command.CONFIRM),
                               ("投给三号", 3), ("查验两号", 2), ("弃票", 0)]:
            self.assertEqual(parse_command(text), expected)

    def test_ambiguous_or_negated(self):
        for text in ["不投三号", "三号或者四号", "我不是说确认", "七号", "三号确认",
                     "他怀疑三号", "不要结束游戏", "", "一二", "开始然后结束游戏"]:
            self.assertIsNone(parse_command(text))


class RecognizerTests(unittest.IsolatedAsyncioTestCase):
    def recognizer(self, text, confidence=0.99):
        payload = json.dumps({
            "text": text,
            "result": [{"word": text, "conf": confidence}],
        }, ensure_ascii=False)
        return SimpleNamespace(Result=Mock(return_value=payload),
                               FinalResult=Mock(return_value=payload))

    async def test_exact_command_avoids_network_interpretation(self):
        interpreter = SimpleNamespace(interpret=AsyncMock())
        local = object.__new__(LocalRecognizer)
        local.interpreter = interpreter
        self.assertEqual(await local.result(self.recognizer("确认")), Command.CONFIRM)
        interpreter.interpret.assert_not_awaited()

    async def test_free_form_transcript_uses_llm_interpreter(self):
        interpreter = SimpleNamespace(interpret=AsyncMock(return_value=3))
        local = object.__new__(LocalRecognizer)
        local.interpreter = interpreter
        transcript = "我觉得坐在三号的玩家最可疑"
        self.assertEqual(await local.result(self.recognizer(transcript)), 3)
        interpreter.interpret.assert_awaited_once_with(transcript)

    async def test_exact_command_survives_marginal_word_confidence(self):
        interpreter = SimpleNamespace(interpret=AsyncMock())
        local = object.__new__(LocalRecognizer)
        local.interpreter = interpreter
        self.assertEqual(await local.result(self.recognizer("开始游戏", 0.4)), Command.START)
        interpreter.interpret.assert_not_awaited()

    async def test_low_confidence_free_form_never_calls_llm(self):
        interpreter = SimpleNamespace(interpret=AsyncMock())
        local = object.__new__(LocalRecognizer)
        local.interpreter = interpreter
        transcript = "我觉得三号比较可疑"
        self.assertIsNone(await local.result(self.recognizer(transcript, 0.4)))
        interpreter.interpret.assert_not_awaited()

    async def test_final_result_is_used_for_unendpointed_short_command(self):
        interpreter = SimpleNamespace(interpret=AsyncMock())
        local = object.__new__(LocalRecognizer)
        local.interpreter = interpreter
        recognizer = self.recognizer("开始游戏")
        recognizer.Result.return_value = json.dumps({"text": "", "result": []})
        self.assertEqual(await local.result(recognizer, final=True), Command.START)
        recognizer.FinalResult.assert_called_once_with()
        recognizer.Result.assert_not_called()


class HostTests(unittest.IsolatedAsyncioTestCase):
    def device(self, commands):
        return SimpleNamespace(listen=AsyncMock(side_effect=commands),
                               show=AsyncMock(), say=AsyncMock(), clear_secret=AsyncMock())

    async def test_confirm_and_cancel(self):
        device = self.device([2, Command.CANCEL, 3, Command.CONFIRM])
        self.assertEqual(await VoiceSoloHost(device).select({2, 3}), 3)
        device.show.assert_not_called()

    async def test_target_preview_never_renders_number(self):
        device = self.device([2, Command.CONFIRM])
        self.assertEqual(await VoiceSoloHost(device).select({2, 3}), 2)
        device.show.assert_not_called()

    async def test_illegal_target_clears_pending_choice(self):
        device = self.device([2, 6, Command.CONFIRM, 3, Command.CONFIRM])
        self.assertEqual(await VoiceSoloHost(device).select({2, 3}), 3)
        self.assertEqual(device.listen.await_count, 5)

    async def test_identity_ack_does_not_preview(self):
        device = self.device([Command.CONTINUE])
        self.assertEqual(await VoiceSoloHost(device).select({Command.CONTINUE}), Command.CONTINUE)
        device.show.assert_not_called()

    async def test_continue_with_end_available_needs_no_confirmation(self):
        device = self.device([Command.CONTINUE])
        self.assertEqual(
            await VoiceSoloHost(device).select({Command.CONTINUE, Command.END}, controls=False),
            Command.CONTINUE,
        )
        self.assertEqual(device.listen.await_count, 1)

    async def test_end_requires_confirmation(self):
        device = self.device([Command.END, Command.CANCEL, Command.END, Command.CONFIRM])
        with self.assertRaises(GameStopped):
            await VoiceSoloHost(device).select({2})
        self.assertEqual(device.listen.await_count, 4)

    async def test_timeout_does_not_guess(self):
        device = self.device([])
        self.assertIsNone(await VoiceSoloHost(device).select({2}, timeout=0))
        device.listen.assert_not_called()


async def direct_call(fn, *args, **kwargs):
    return fn(*args, **kwargs)


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        session = SimpleNamespace(
            format=SimpleNamespace(sample_rate_hz=16000, channels=1,
                                   sample_width_bytes=2, encoding="pcm_s16le"),
            dropped_frames=0, decode_failures=0,
            read=Mock(return_value=SimpleNamespace(data=b"\0\0" * 320)), close=Mock())
        robot = SimpleNamespace(microphone=SimpleNamespace(open_pcm=Mock(return_value=session)))
        decoder = SimpleNamespace(AcceptWaveform=Mock(return_value=True))
        recognizer = SimpleNamespace(new_utterance=Mock(return_value=decoder),
                                     result=AsyncMock(return_value=2))
        device = VoiceDevice(SimpleNamespace(robot=robot, shutdown_requested=False),
                             direct_call, {}, recognizer)
        return device, session, recognizer

    async def test_read_and_release(self):
        device, session, _ = self.make()
        self.assertEqual(await device.listen(), 2)
        session.close.assert_called_once()
        self.assertIsNone(device.microphone)
        self.assertFalse(hasattr(device, "detector"))

    async def test_close_failure_retains_handle_for_retry(self):
        device, session, _ = self.make()
        session.close.side_effect = [RuntimeError("stop failure"), None]
        with self.assertRaises(RuntimeError):
            await device.listen()
        self.assertIs(device.microphone, session)
        await device.close()
        self.assertIsNone(device.microphone)
        self.assertEqual(session.close.call_count, 2)

    async def test_bad_audio_not_accepted(self):
        device, session, recognizer = self.make()
        session.decode_failures = 1
        with self.assertRaises(RuntimeError):
            await device.listen()
        recognizer.result.assert_not_called()
        session.close.assert_called_once()

    async def test_read_failure_releases(self):
        device, session, _ = self.make()
        session.read.side_effect = RuntimeError("transport failed")
        with self.assertRaises(RuntimeError):
            await device.listen()
        session.close.assert_called_once()

    async def test_voice_device_exposes_no_camera_api(self):
        device, _, _ = self.make()
        self.assertFalse(hasattr(device, "read_card"))
        self.assertFalse(hasattr(device.app.robot, "camera"))


if __name__ == "__main__":
    unittest.main()
