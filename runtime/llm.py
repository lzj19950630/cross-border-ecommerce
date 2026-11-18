"""可选 LLM 客户端（OpenAI 兼容 Chat Completions）。

默认不启用；CLI/API 需要显式 --creative。测试用 FakeLLM，不访问网络。
环境变量：
    RUNTIME_LLM_BASE_URL / LLM_BASE_URL / OPENAI_BASE_URL
    RUNTIME_LLM_MODEL    / LLM_MODEL / OPENAI_MODEL / DEEPSEEK_MODEL
    RUNTIME_LLM_API_KEY  / LLM_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> dict[str, Any]: ...


class FakeLLM:
    """测试替身：按顺序返回预设 JSON，并记录调用。"""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append((system, user))
        if not self.responses:
            raise LLMError("FakeLLM 没有剩余响应")
        return self.responses.pop(0)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM 返回不是有效 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("LLM 返回顶层必须是对象")
    return data


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout: int = 90,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"LLM 连接失败：{exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError(f"LLM 超时（{self.timeout}s）") from exc
        try:
            body = json.loads(raw)
            content = body["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"LLM 响应结构非法：{raw[:500]}") from exc
        return _extract_json(str(content))


def llm_configured() -> bool:
    return bool(_env("api_key") and _env("model"))


def _env(name: str) -> str | None:
    aliases = {
        "base_url": ("RUNTIME_LLM_BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE"),
        "model": ("RUNTIME_LLM_MODEL", "LLM_MODEL", "OPENAI_MODEL", "DEEPSEEK_MODEL"),
        "api_key": ("RUNTIME_LLM_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"),
    }[name]
    for key in aliases:
        value = os.environ.get(key)
        if value:
            return value
    return None


def load_llm_from_env() -> LLMClient | None:
    base = _env("base_url") or "https://api.openai.com/v1"
    model = _env("model")
    key = _env("api_key")
    if not model or not key:
        return None
    return OpenAICompatibleClient(base, model, key)
