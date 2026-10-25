"""Offline OpenAI-compatible integration tests; no real network requests."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werewolf_engine import Role
from werewolf_input import Command
from werewolf_llm import (
    CommandInterpreter, LLMError, ModelBot, OpenAICompatibleClient,
)


class ClientConfigTests(unittest.TestCase):
    def test_local_env_configures_any_openai_compatible_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "OPENAI_BASE_URL=https://gateway.example/v1\n"
                "OPENAI_API_KEY='local-secret'\n"
                "OPENAI_MODEL=custom-chat\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                client = OpenAICompatibleClient(env_path=env_path)
            self.assertEqual(client.base_url, "https://gateway.example/v1")
            self.assertEqual(client.api_key, "local-secret")
            self.assertEqual(client.model, "custom-chat")

    def test_real_environment_overrides_local_env(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "OPENAI_BASE_URL=https://file.example\n"
                "OPENAI_API_KEY=file-key\n"
                "OPENAI_MODEL=file-model\n",
                encoding="utf-8",
            )
            configured = {
                "OPENAI_BASE_URL": "https://environment.example",
                "OPENAI_API_KEY": "environment-key",
                "OPENAI_MODEL": "environment-model",
            }
            with patch.dict(os.environ, configured, clear=True):
                client = OpenAICompatibleClient(env_path=env_path)
            self.assertEqual(client.base_url, configured["OPENAI_BASE_URL"])
            self.assertEqual(client.api_key, configured["OPENAI_API_KEY"])
            self.assertEqual(client.model, configured["OPENAI_MODEL"])

    def test_missing_generic_configuration_lists_required_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "OPENAI_BASE_URL"):
                    OpenAICompatibleClient(env_path=Path(directory) / ".env")


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_free_form_command_is_constrained(self):
        client = AsyncMock()
        client.complete_json.return_value = {"kind": "seat", "value": 3}
        interpreter = CommandInterpreter(client)
        self.assertEqual(await interpreter.interpret("我觉得还是投三号吧"), 3)

        client.complete_json.return_value = {"kind": "command", "value": "confirm"}
        self.assertEqual(await interpreter.interpret("就这样，确定"), Command.CONFIRM)

    async def test_invalid_model_output_never_becomes_action(self):
        client = AsyncMock()
        interpreter = CommandInterpreter(client)
        for result in (
            {"kind": "seat", "value": 9},
            {"kind": "seat", "value": "2"},
            {"kind": "command", "value": "kill"},
            {"kind": "invalid", "value": None},
        ):
            client.complete_json.return_value = result
            self.assertIsNone(await interpreter.interpret("任意文本"))


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def test_wolf_context_and_choice_are_limited(self):
        client = AsyncMock()
        client.complete_json.return_value = {"choice": 4, "reason": "测试"}
        bot = ModelBot(2, Role.WOLF, {1}, client=client)
        self.assertEqual(await bot.choose({1, 2, 3, 4}, {3: 4}), 4)
        user = client.complete_json.await_args.args[1]
        self.assertIn('"candidates": [3, 4]', user)
        self.assertIn('"wolf_teammates": [1]', user)
        self.assertNotIn('"roles"', user)

    async def test_illegal_choice_is_rejected(self):
        client = AsyncMock()
        client.complete_json.return_value = {"choice": 1, "reason": "违规选择队友"}
        bot = ModelBot(2, Role.WOLF, {1}, client=client)
        with self.assertRaises(LLMError):
            await bot.choose({1, 2, 3})

    async def test_seer_receives_only_own_inspections(self):
        client = AsyncMock()
        client.complete_json.return_value = {"choice": 5, "reason": "未查验"}
        bot = ModelBot(3, Role.SEER, client=client)
        bot.remember(2, True)
        self.assertEqual(await bot.inspect_target({1, 2, 3, 4, 5}), 5)
        user = client.complete_json.await_args.args[1]
        self.assertIn('"inspection_results": {"2": "wolf"}', user)
        self.assertIn('"candidates": [1, 4, 5]', user)


if __name__ == "__main__":
    unittest.main()
