"""Public-only game monitor. No generic log forwarding or camera endpoint."""
import asyncio
from pathlib import Path
import time

from monitor import MonitorServer, MonitorState, ObservedApp

WEB = Path(__file__).with_name("werewolf_web")
MONITOR_PORT = 8766  # Keep separate from the SDK Runtime's device port 8765.
PUBLIC_FIELDS = frozenset({"phase", "round", "alive", "registered", "speaker", "voter",
                           "runoff", "candidates", "tally", "last_eliminated", "winner"})


def publish(state, *, game=None):
    if game is None:
        return
    if set(game) != PUBLIC_FIELDS:
        raise ValueError("公开状态字段不符合约定")
    state.update(game=game)


async def run_game_monitored(app, call, run_game):
    state = MonitorState()
    server = MonitorServer(state, port=MONITOR_PORT, web=WEB)
    server.start()
    state.update(active=True, phase="running")
    try:
        await run_game(ObservedApp(app, state), call,
                       report=lambda **fields: publish(state, **fields))
        state.update(active=False, phase="stopped")
    except asyncio.CancelledError:
        state.update(active=False, phase="stopped")
        raise
    except Exception:
        # Do not expose arbitrary SDK exceptions or payloads to the HTTP client.
        state.update(active=False, phase="error")
        state.log("应用异常退出；保持遮挡，现场检查设备后重新开局。", "ERROR")
        raise
    finally:
        await asyncio.to_thread(server.close)


if __name__ == "__main__":
    state = MonitorState()
    state.update(phase="preview", active=False)
    server = MonitorServer(state, port=MONITOR_PORT, web=WEB)
    server.start()
    print(f"Public monitor preview: http://127.0.0.1:{server.port} (no robot connected)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.close()
