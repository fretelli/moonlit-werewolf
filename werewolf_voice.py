"""Bounded microphone input with local Vosk transcription and LLM semantics."""
import inspect
import json
import os
import re
import time
from pathlib import Path

from werewolf_input import Command, Selection
from werewolf_device import Device, GameStopped
from werewolf_llm import CommandInterpreter, ModelBot, OpenAICompatibleClient
from werewolf_solo import SoloHost
from werewolf_speech import ROOT, load_clips


COMMANDS = {
    "开始": Command.START, "开始游戏": Command.START, "开始狼人杀": Command.START,
    "确认": Command.CONFIRM, "确认选择": Command.CONFIRM,
    "取消": Command.CANCEL, "重新选择": Command.CANCEL,
    "继续": Command.CONTINUE, "准备好了": Command.CONTINUE, "记住了": Command.CONTINUE,
    "结束游戏": Command.END, "退出游戏": Command.END,
    "暂停": Command.PAUSE, "暂停游戏": Command.PAUSE,
    "重复提示": Command.REPEAT,
    "弃票": 0, "暂无意见": 0, "不指认": 0,
    "确认继续": Command.CONFIRM,
    "确认开始": Command.CONFIRM,
    "确认结束": Command.CONFIRM,
}
DIGITS = {str(i): i for i in range(7)}
DIGITS.update(dict(zip("零一二三四五六", range(7))))
DIGITS["两"] = 2


def parse_command(text):
    """Only whole utterances act; negations/multiple targets never match."""
    text = re.sub(r"[\s，。！？,.!?]", "", text)
    if text in COMMANDS:
        return COMMANDS[text]
    match = re.fullmatch(r"(?:选择|选|投给|投|查验|怀疑|我怀疑|我投)?([0-6零一二两三四五六])(?:号)?", text)
    return DIGITS[match[1]] if match else None


class LocalRecognizer:
    """Explicit local model path; never downloads or calls a cloud service."""
    def __init__(self, model_path, interpreter):
        model_path = Path(model_path)
        for name in ("am/final.mdl", "conf/model.conf"):
            if not (model_path / name).is_file():
                raise RuntimeError("本地中文语音模型未准备好，拒绝打开麦克风")
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        self.model = Model(str(model_path))
        self.factory = KaldiRecognizer
        self.interpreter = interpreter

    def new_utterance(self):
        recognizer = self.factory(self.model, 16000)
        recognizer.SetWords(True)
        return recognizer

    async def result(self, recognizer, *, final=False):
        get_result = recognizer.FinalResult if final else recognizer.Result
        result = json.loads(get_result())
        transcript = result.get("text", "").strip()
        if not transcript:
            return None
        exact = parse_command(transcript)
        # Exact whole-utterance commands are safer than throwing away a correctly
        # decoded phrase because one Vosk word had a marginal confidence score.
        if exact is not None:
            return exact
        words = result.get("result", [])
        if not words:
            return None
        confidence = sum(word.get("conf", 0) for word in words) / len(words)
        if confidence < 0.75:
            return None
        return await self.interpreter.interpret(transcript)


class VoiceDevice(Device):
    def __init__(self, app, call, clips, recognizer):
        super().__init__(app, call, clips)
        self.recognizer = recognizer
        self.microphone = None

    async def listen(self, seconds=8):
        """One endpointed utterance per fresh lease, no late/final partial action."""
        async with self.lock:
            self.check_stop()
            if self.audio_attempted or self.microphone is not None:
                raise RuntimeError("媒体未释放，拒绝启动聆听")
            decoder = self.recognizer.new_utterance()
            deadline = time.monotonic() + max(0, min(seconds, 8))
            if deadline <= time.monotonic():
                return None
            try:
                # Assignment happens inside the worker, so cancellation cannot
                # lose a successfully opened lease before final cleanup.
                def acquire():
                    self.microphone = self.app.robot.microphone.open_pcm(queue_size=32)
                await self.call(acquire)
                fmt = self.microphone.format
                if (fmt.sample_rate_hz, fmt.channels, fmt.sample_width_bytes,
                        fmt.encoding) != (16000, 1, 2, "pcm_s16le"):
                    raise RuntimeError("麦克风音频格式不兼容")
                while time.monotonic() < deadline:
                    self.check_stop()
                    try:
                        frame = await self.call(self.microphone.read,
                                                timeout=min(0.25, deadline-time.monotonic()))
                    except TimeoutError:
                        continue
                    self.check_stop()
                    if self.microphone.dropped_frames or self.microphone.decode_failures:
                        raise RuntimeError("麦克风丢帧或解码失败，拒绝接受不完整指令")
                    complete = await self.call(decoder.AcceptWaveform, frame.data)
                    if complete:
                        result = self.recognizer.result(decoder)
                        return await result if inspect.isawaitable(result) else result
                # A short utterance may never trigger Vosk's silence endpoint
                # before this bounded lease expires. Finalize buffered audio
                # instead of silently discarding a valid command such as “开始游戏”.
                result = self.recognizer.result(decoder, final=True)
                return await result if inspect.isawaitable(result) else result
            finally:
                await self.close_microphone()

    async def close_microphone(self):
        if self.microphone is not None:
            await self.call(self.microphone.close)
            self.microphone = None

    async def say(self, key):
        if self.microphone is not None:
            raise RuntimeError("麦克风未释放，拒绝播报")
        await super().say(key)

    async def close(self):
        try:
            await self.close_microphone()
        finally:
            await super().close()


class VoiceSoloHost(SoloHost):
    """Voice commands are deliberately confined to single-human gameplay."""
    async def select(self, allowed, *, controls=True, timeout=None, prompt=None):
        allowed = set(allowed)
        selection = Selection(allowed | {Command.END})
        deadline = time.monotonic() + (timeout if timeout is not None else 120)
        while time.monotonic() < deadline:
            command = await self.device.listen(min(8, deadline - time.monotonic()))
            if time.monotonic() >= deadline:
                break
            if command is None:
                continue
            if controls and command == Command.PAUSE:
                before = time.monotonic()
                await self.pause()
                deadline += time.monotonic() - before
                selection = Selection(allowed | {Command.END})
                continue
            if controls and command == Command.REPEAT and prompt:
                await self.device.clear_secret()
                await self.device.say(prompt)
                selection = Selection(allowed | {Command.END})
                continue
            # Starting and continuing are affirmative flow controls rather than
            # target choices. A single explicit utterance completes them even
            # when END is also allowed; ending still requires confirmation.
            if command in {Command.START, Command.CONTINUE} and command in allowed:
                await self.device.clear_secret()
                return command
            event, value = selection.feed(command)
            if event == "preview":
                # Keep the two-step voice confirmation without rendering a
                # number that could be mistaken for the removed card UI.
                continue
            elif event == "confirmed":
                await self.device.clear_secret()
                if value == Command.END:
                    raise GameStopped("玩家结束本局")
                return value
            elif event in {"cancelled", "invalid"}:
                # Rejecting an invalid utterance also invalidates any pending
                # target; a later confirmation must never submit a stale choice.
                selection = Selection(allowed | {Command.END})
                await self.device.clear_secret()
        await self.device.clear_secret()
        if timeout is None:
            raise GameStopped("语音等待超时，本局安全中止")
        return None


def require_voice_capabilities(robot):
    """Fail early with actionable firmware diagnostics for required hardware APIs."""
    required = ("audio.stream", "microphone", "expression.runtime.v3")
    missing = [name for name in required if not robot.supports(name)]
    if not missing:
        return
    advertised = ", ".join(robot.capabilities) or "（设备未上报任何能力）"
    raise RuntimeError(
        "当前机器人固件缺少语音狼人杀所需能力："
        + ", ".join(missing)
        + "。audio.stream 用于播放应用内 PCM 语音，microphone 用于语音输入，"
          "expression.runtime.v3 用于私密身份屏幕；这些能力不能由应用代码绕过。"
          "请确认机器人处于 Desktop Link、升级为与当前 Desktop/SDK 配套的固件后重试。"
          "设备当前上报能力："
        + advertised
    )


async def run_voice_game(app, call, report=None, *, model_path=None, llm_client=None):
    """Run model decisions with local transcription and fixed WAV output."""
    if app.shutdown_requested:
        return
    require_voice_capabilities(app.robot)

    client = llm_client or OpenAICompatibleClient()
    configured = model_path or os.environ.get("VOSK_MODEL_PATH")
    if not configured:
        configured = ROOT / "assets" / "vosk-model-cn"
    recognizer = LocalRecognizer(configured, CommandInterpreter(client))
    clips = load_clips(ROOT)
    device = VoiceDevice(app, call, clips, recognizer)
    host = VoiceSoloHost(
        device,
        report,
        bot_factory=lambda seat, role, teammates: ModelBot(
            seat, role, teammates, client=client
        ),
    )
    try:
        await host.run()
    except GameStopped:
        host.game.abort()
        host.publish()
    finally:
        host.game.abort()
        await device.close()
