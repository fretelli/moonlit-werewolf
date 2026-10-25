"""Voice-only SDK adapter for audio playback and private screen feedback."""
import asyncio
import time

from werewolf_display import payload


class GameStopped(Exception):
    pass


class Device:
    def __init__(self, app, call, clips):
        self.app = app
        self.call = call
        self.clips = clips
        self.display_attempted = False
        self.audio_attempted = False
        self.lock = asyncio.Lock()

    def check_stop(self):
        if self.app.shutdown_requested:
            raise GameStopped("应用已收到停止请求")

    async def sleep(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.check_stop()
            await asyncio.sleep(min(0.1, max(0, deadline - time.monotonic())))
        self.check_stop()

    async def show(self, symbol):
        async with self.lock:
            self.check_stop()
            if self.audio_attempted:
                raise RuntimeError("音频未释放，拒绝切换媒体")
            command = (self.app.robot.expression_runtime.update if self.display_attempted
                       else self.app.robot.expression_runtime.start)
            self.display_attempted = True
            await self.call(command, **payload(symbol))

    async def clear_secret(self):
        await self.show("blank")

    async def say(self, key):
        async with self.lock:
            self.check_stop()
            clip = self.clips[key]
            self.audio_attempted = True
            try:
                playback = await self.call(self.app.robot.audio.play_pcm, clip.data)
                deadline = time.monotonic() + len(clip.data) / 48000 + 20
                while not playback.state.terminal:
                    self.check_stop()
                    if time.monotonic() >= deadline:
                        raise TimeoutError("主持音频播放超时")
                    await asyncio.sleep(0.1)
                await self.call(playback.wait, 0.0)
            finally:
                await self.call(self.app.robot.audio.stop)
                self.audio_attempted = False
            self.check_stop()

    async def close(self):
        try:
            if self.audio_attempted:
                await self.call(self.app.robot.audio.stop)
                self.audio_attempted = False
        finally:
            if self.display_attempted:
                await self.call(self.app.robot.expression_runtime.stop)
                self.display_attempted = False
