"""OpenAI-compatible text intelligence for commands and bot decisions.

The configured service is text-only from this application's perspective:
microphone transcription remains local Vosk and audible hosting remains the
validated fixed WAV set. All model outputs are treated as untrusted.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from urllib import error, request

from werewolf_engine import Role
from werewolf_input import Command


COMMAND_NAMES = {
    "start": Command.START,
    "confirm": Command.CONFIRM,
    "cancel": Command.CANCEL,
    "continue": Command.CONTINUE,
    "end": Command.END,
    "pause": Command.PAUSE,
    "repeat": Command.REPEAT,
    "abstain": 0,
}


class LLMError(RuntimeError):
    """Safe model-service error without response payload leakage."""


def load_local_env(path=None):
    """Load a small, dependency-free .env file without overriding real env."""
    path = Path(path) if path else Path(__file__).resolve().with_name(".env")
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


class OpenAICompatibleClient:
    """Provider-neutral client for an OpenAI-compatible chat endpoint."""

    def __init__(self, *, base_url=None, api_key=None, model=None, timeout=20,
                 env_path=None):
        load_local_env(env_path)
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_MODEL")
        self.timeout = timeout
        missing = [name for name, value in (
            ("OPENAI_BASE_URL", self.base_url),
            ("OPENAI_API_KEY", self.api_key),
            ("OPENAI_MODEL", self.model),
        ) if not value]
        if missing:
            raise RuntimeError(
                "OpenAI 兼容接口配置不完整，请在 .env 或环境变量中配置："
                + ", ".join(missing)
            )

    def _complete_sync(self, system, user):
        payload = json.dumps({
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }, ensure_ascii=False).encode("utf-8")
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions" if endpoint.endswith("/v1") else "/v1/chat/completions"
        req = request.Request(endpoint, data=payload, method="POST", headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, str):
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if not match:
                    raise ValueError("missing JSON object")
                return json.loads(match.group(0))
            if isinstance(content, dict):
                return content
            raise ValueError("invalid content")
        except (error.URLError, TimeoutError, KeyError, IndexError, TypeError,
                ValueError, json.JSONDecodeError) as exc:
            raise LLMError("大模型接口调用失败或返回格式无效") from exc

    async def complete_json(self, system, user):
        return await asyncio.to_thread(self._complete_sync, system, user)


class CommandInterpreter:
    """Map free-form Chinese transcripts to the small trusted command set."""

    def __init__(self, client):
        self.client = client

    async def interpret(self, transcript):
        result = await self.client.complete_json(
            "你是狼人杀机器人输入解析器。只分析用户明确表达的当前操作，不猜测。"
            "输出JSON且仅含kind和value。kind只能是command、seat、invalid。"
            "command的value只能是start,confirm,cancel,continue,end,pause,repeat,abstain。"
            "seat的value只能是0到6的整数。否定、含糊、多目标或闲聊必须invalid。",
            json.dumps({"utterance": transcript}, ensure_ascii=False),
        )
        kind = result.get("kind")
        value = result.get("value")
        if kind == "command" and value in COMMAND_NAMES:
            return COMMAND_NAMES[value]
        if kind == "seat" and type(value) is int and value in range(7):
            return value
        return None


class ModelBot:
    """Limited-information model player; never receives the full role map."""

    def __init__(self, seat, role, teammates=(), *, client):
        self.seat = seat
        self.role = Role(role)
        self.teammates = frozenset(teammates) if self.role == Role.WOLF else frozenset()
        self.inspections = {}
        self.client = client

    def remember(self, target, is_wolf):
        if self.role != Role.SEER:
            raise ValueError("Only the seer receives private inspection results")
        self.inspections[target] = bool(is_wolf)

    async def _pick(self, action, candidates, accusations=None):
        candidates = sorted(set(candidates) - {self.seat})
        if self.role == Role.WOLF:
            candidates = [seat for seat in candidates if seat not in self.teammates]
        if not candidates:
            return None
        private = {}
        if self.role == Role.WOLF:
            private["wolf_teammates"] = sorted(self.teammates)
        if self.role == Role.SEER:
            private["inspection_results"] = {
                str(seat): "wolf" if value else "good"
                for seat, value in self.inspections.items()
            }
        result = await self.client.complete_json(
            "你是六人狼人杀中的一名电脑玩家。只能依据提供的信息决策，不得声称知道未提供的身份。"
            "输出JSON且仅含choice和reason。choice必须是候选座位整数；reason不超过40字。",
            json.dumps({
                "action": action,
                "your_seat": self.seat,
                "your_role": self.role.value,
                "candidates": candidates,
                "public_accusations": accusations or {},
                "private_information": private,
            }, ensure_ascii=False),
        )
        choice = result.get("choice")
        if type(choice) is not int or choice not in candidates:
            raise LLMError("大模型返回了规则不允许的座位")
        return choice

    async def choose(self, candidates, accusations=None):
        return await self._pick("choose_target_or_vote", candidates, accusations)

    async def inspect_target(self, alive):
        if self.role != Role.SEER:
            raise ValueError("Only the seer may inspect")
        candidates = set(alive) - self.inspections.keys()
        if not candidates:
            candidates = set(alive)
        return await self._pick("inspect", candidates)

    def forget(self):
        self.inspections.clear()
        self.teammates = frozenset()
