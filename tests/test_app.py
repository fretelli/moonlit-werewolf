"""Offline entry-point lifecycle tests; no robot connection is created."""
import asyncio
import ast
import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "voice_app", Path(__file__).resolve().parents[1] / "app.py"
)
app_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app_module)


class AppTests(unittest.IsolatedAsyncioTestCase):
    def test_script_entry_runs_main(self):
        tree = ast.parse(Path(app_module.__file__).read_text(encoding="utf-8"))
        guards = [
            node for node in tree.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        ]
        self.assertEqual(len(guards), 1)
        call = guards[0].body[0].value
        self.assertEqual(call.func.attr, "run")
        self.assertEqual(call.args[0].func.id, "main")

    async def test_main_runs_only_monitored_voice_game(self):
        app = SimpleNamespace(
            robot=SimpleNamespace(), shutdown_requested=False,
            logger=Mock(spec=logging.Logger),
        )
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=app)
        manager.__aexit__ = AsyncMock(return_value=False)
        voice_game = AsyncMock()
        monitored = AsyncMock()

        with patch.object(app_module.ApplicationContext, "from_environment", return_value=manager), \
             patch.dict("sys.modules", {
                 "werewolf_voice": SimpleNamespace(run_voice_game=voice_game),
                 "werewolf_monitor": SimpleNamespace(run_game_monitored=monitored),
             }):
            await app_module.main()

        monitored.assert_awaited_once_with(app, app_module.sdk_call, voice_game)

    async def test_main_logs_and_reraises_failure(self):
        app = SimpleNamespace(
            robot=SimpleNamespace(), shutdown_requested=False,
            logger=Mock(spec=logging.Logger),
        )
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=app)
        manager.__aexit__ = AsyncMock(return_value=False)
        monitored = AsyncMock(side_effect=RuntimeError("failed"))

        with patch.object(app_module.ApplicationContext, "from_environment", return_value=manager), \
             patch.dict("sys.modules", {
                 "werewolf_voice": SimpleNamespace(run_voice_game=AsyncMock()),
                 "werewolf_monitor": SimpleNamespace(run_game_monitored=monitored),
             }):
            with self.assertRaises(RuntimeError):
                await app_module.main()

        app.logger.exception.assert_called_once()

    async def test_sdk_call_waits_for_worker_after_cancellation(self):
        entered = threading.Event()
        release = threading.Event()
        completed = []

        def blocking():
            entered.set()
            if not release.wait(2):
                raise TimeoutError("test worker timed out")
            completed.append(True)

        task = asyncio.create_task(app_module.sdk_call(blocking))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        self.assertEqual(completed, [True])


if __name__ == "__main__":
    unittest.main()
