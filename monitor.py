"""Loopback-only HTTP monitor primitives for the voice werewolf game."""
from __future__ import annotations

from collections import deque
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time


class MonitorState:
    """Thread-safe public state shared by the game and HTTP server."""

    def __init__(self):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.token = secrets.token_urlsafe(32)
        self.data = {
            "phase": "idle",
            "active": False,
            "updated_at": time.time(),
        }
        self.logs = deque(maxlen=20)

    def update(self, **fields):
        with self.lock:
            self.data.update(fields, updated_at=time.time())

    def log(self, message, level="INFO"):
        with self.lock:
            self.logs.append({"time": time.time(), "level": level, "message": message})

    def snapshot(self):
        with self.lock:
            return {
                **copy.deepcopy(self.data),
                "logs": list(self.logs),
                "server_time": time.time(),
                "stop_requested": self.stop.is_set(),
            }

    def request_stop(self):
        with self.lock:
            if not self.data["active"]:
                return False
            self.stop.set()
            self.data.update(phase="stopping", updated_at=time.time())
            return True


class MonitorServer:
    """Serve the public monitor and cooperative stop endpoint on loopback."""

    def __init__(self, state, *, port, web):
        self.state = state
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body, content_type="application/json; charset=utf-8"):
                if not isinstance(body, bytes):
                    body = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; frame-ancestors 'none'",
                )
                self.end_headers()
                self.wfile.write(body)

            def valid_host(self):
                return self.headers.get("Host") in owner.hosts

            def do_GET(self):
                if not self.valid_host():
                    self.reply(403, {"error": "仅允许本机访问"})
                    return
                if self.path == "/api/state":
                    self.reply(200, state.snapshot())
                    return
                if self.path == "/api/session":
                    self.reply(200, {"token": state.token})
                    return
                files = {
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/style.css": ("style.css", "text/css; charset=utf-8"),
                }
                if self.path not in files:
                    self.reply(404, {"error": "Not found"})
                    return
                filename, content_type = files[self.path]
                self.reply(200, (web / filename).read_bytes(), content_type)

            def do_POST(self):
                valid_request = (
                    self.valid_host()
                    and self.headers.get("Origin") in owner.origins
                    and secrets.compare_digest(
                        self.headers.get("X-Monitor-Token", ""), state.token
                    )
                )
                if not valid_request:
                    self.reply(403, {"error": "请求来源或会话校验失败"})
                    return
                if self.path != "/api/stop":
                    self.reply(404, {"error": "Not found"})
                elif state.request_stop():
                    self.reply(202, {"message": "停止请求已接受，等待应用安全清理。"})
                else:
                    self.reply(409, {"error": "当前没有可停止的游戏"})

        self.http = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.http.daemon_threads = True
        self.port = self.http.server_address[1]
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.origins = {f"http://{host}" for host in self.hosts}
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)


class ObservedApp:
    """Expose monitor stop requests through the normal app shutdown flag."""

    def __init__(self, app, state):
        self._app = app
        self._state = state

    @property
    def shutdown_requested(self):
        return self._state.stop.is_set() or self._app.shutdown_requested

    def __getattr__(self, name):
        return getattr(self._app, name)
