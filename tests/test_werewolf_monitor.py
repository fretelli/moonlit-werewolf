"""Public-only HTTP and lifecycle regression tests; no hardware."""
import http.client
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import werewolf_monitor as monitor
from werewolf_engine import Game


class PublicTests(unittest.TestCase):
    def test_allowlist_rejects_secret_fields(self):
        state = monitor.MonitorState()
        game = Game().public_state()
        monitor.publish(state, game=game)
        for field in ("roles", "target", "image", "inspection"):
            with self.assertRaises(ValueError):
                monitor.publish(state, game={**game, field: "secret"})
        self.assertEqual(state.snapshot()["game"], game)

    def test_public_web_and_no_private_endpoints(self):
        state = monitor.MonitorState()
        monitor.publish(state, game=Game().public_state())
        server = monitor.MonitorServer(state, port=0, web=monitor.WEB)
        server.start()
        try:
            for path, expected in (("/", 200), ("/app.js", 200),
                                   ("/style.css", 200), ("/api/state", 200),
                                   ("/api/camera", 404), ("/api/roles", 404)):
                conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
                try:
                    conn.request("GET", path)
                    response = conn.getresponse()
                    body = response.read()
                    self.assertEqual(response.status, expected)
                    if path == "/":
                        self.assertIn("语音狼人杀", body.decode("utf-8"))
                    if path == "/api/state":
                        self.assertEqual(json.loads(body)["game"], Game().public_state())
                finally:
                    conn.close()
        finally:
            server.close()


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cooperative_stop_without_log_forwarding(self):
        state = monitor.MonitorState()
        server = monitor.MonitorServer(state, port=0, web=monitor.WEB)
        logger = logging.getLogger("werewolf-public-test")
        app = SimpleNamespace(shutdown_requested=False, logger=logger)
        handlers = list(logger.handlers)

        async def game(observed, call, report):
            report(game=Game().public_state())
            self.assertEqual(logger.handlers, handlers)
            self.assertTrue(state.request_stop())
            self.assertTrue(observed.shutdown_requested)
            self.assertFalse(app.shutdown_requested)

        with patch.object(monitor, "MonitorState", return_value=state), \
             patch.object(monitor, "MonitorServer", return_value=server):
            await monitor.run_game_monitored(app, None, game)
        self.assertFalse(server.thread.is_alive())
        self.assertFalse(state.snapshot()["active"])

    async def test_exception_payload_is_not_public(self):
        state = monitor.MonitorState()
        server = monitor.MonitorServer(state, port=0, web=monitor.WEB)
        app = SimpleNamespace(shutdown_requested=False)

        async def game(*args, **kwargs):
            raise RuntimeError("PRIVATE_ROLE_PAYLOAD")

        with patch.object(monitor, "MonitorState", return_value=state), \
             patch.object(monitor, "MonitorServer", return_value=server):
            with self.assertRaises(RuntimeError):
                await monitor.run_game_monitored(app, None, game)
        self.assertNotIn("PRIVATE_ROLE_PAYLOAD", json.dumps(state.snapshot()))
        self.assertEqual(state.snapshot()["phase"], "error")
        self.assertFalse(server.thread.is_alive())
