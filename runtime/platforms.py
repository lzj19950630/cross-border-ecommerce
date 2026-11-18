"""配置驱动的平台动作适配器。

把内部 ApprovalEnvelope 映射成平台 HTTP 请求：
    actions:
      ad.set_bid:
        method: POST
        path: /campaigns/{target}/bid
        body: {bid: "{after.cpc}"}

只做通用 HTTP 映射；具体 Shopee/ML/TikTok API 字段由使用者按官方文档填写。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .actions import ApprovalEnvelope


class PlatformAdapterError(RuntimeError):
    pass


_VAR = re.compile(r"\{([a-zA-Z0-9_.]+)\}")


def _lookup(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise PlatformAdapterError(f"模板变量不存在：{path}")
    return current


def _render(value: Any, context: dict[str, Any], *, url_quote: bool = False) -> Any:
    if isinstance(value, dict):
        return {key: _render(item, context, url_quote=url_quote) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, context) for item in value]
    if not isinstance(value, str):
        return value

    # 整个字符串就是一个变量 → 保留原始类型（数字/布尔）
    whole = re.fullmatch(r"\{([a-zA-Z0-9_.]+)\}", value)
    if whole and not url_quote:
        return _lookup(context, whole.group(1))

    def replace(match: re.Match[str]) -> str:
        raw = _lookup(context, match.group(1))
        text = str(raw)
        return urllib.parse.quote(text, safe="") if url_quote else text

    return _VAR.sub(replace, value)


class MappingAdapter:
    def __init__(self, config: dict[str, Any], env: dict[str, str] | None = None) -> None:
        self.config = config
        self.env = env or os.environ
        self.name = str(config.get("name") or "platform")
        self.base_url = str(config.get("base_url") or "").rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise PlatformAdapterError("base_url 必须是 http(s)")
        self.timeout = int(config.get("timeout") or 30)
        self.headers = dict(config.get("headers") or {"Content-Type": "application/json"})
        self.actions = config.get("actions") or {}
        if not isinstance(self.actions, dict) or not self.actions:
            raise PlatformAdapterError("actions 不能为空")
        retry = config.get("retry") or {}
        self.retry_attempts = max(1, int(retry.get("attempts", 1)))
        self.retry_backoff = float(retry.get("backoff", 0.5))
        self.idempotency_header = config.get("idempotency_header")
        self.signing = config.get("signing") or {}

    @classmethod
    def from_file(cls, path: str | Path, env: dict[str, str] | None = None) -> "MappingAdapter":
        file = Path(path)
        text = file.read_text(encoding="utf-8")
        if file.suffix.lower() == ".json":
            config = json.loads(text)
        else:
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise PlatformAdapterError("读取 YAML 需要 PyYAML；或改用 .json") from exc
            config = yaml.safe_load(text)
        if not isinstance(config, dict):
            raise PlatformAdapterError("适配器配置顶层必须是对象")
        return cls(config, env=env)

    def _auth_headers(self) -> dict[str, str]:
        auth = self.config.get("auth") or {}
        if not auth:
            return {}
        kind = str(auth.get("type") or "none")
        token_env = auth.get("token_env")
        token = self.env.get(str(token_env)) if token_env else None
        if kind == "bearer":
            if not token:
                raise PlatformAdapterError(f"缺少环境变量 {token_env}")
            return {"Authorization": f"Bearer {token}"}
        if kind == "header":
            if not token:
                raise PlatformAdapterError(f"缺少环境变量 {token_env}")
            header_name = str(auth.get("header_name") or "X-API-Key")
            return {header_name: token}
        return {}

    def _sign(self, payload: bytes | None) -> dict[str, str]:
        if not self.signing:
            return {}
        kind = str(self.signing.get("type") or "hmac_sha256")
        if kind != "hmac_sha256":
            raise PlatformAdapterError(f"不支持的签名类型：{kind}")
        secret_env = str(self.signing.get("secret_env") or "RUNTIME_APPLY_SIGNING_SECRET")
        secret = self.env.get(secret_env)
        if not secret:
            raise PlatformAdapterError(f"缺少签名密钥环境变量 {secret_env}")
        header = str(self.signing.get("header") or "X-Signature")
        prefix = str(self.signing.get("prefix") or "sha256=")
        digest = hmac.new(secret.encode("utf-8"), payload or b"", hashlib.sha256).hexdigest()
        return {header: f"{prefix}{digest}"}

    def _request(
        self,
        method: str,
        url: str,
        payload: bytes | None,
        headers: dict[str, str],
        action: str,
    ) -> tuple[str, int]:
        last_error: Exception | None = None
        for attempt in range(self.retry_attempts):
            request = urllib.request.Request(url, data=payload, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8", errors="replace"), response.status
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                last_error = exc
                if exc.code >= 500 and attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_backoff * (2 ** attempt))
                    continue
                raise PlatformAdapterError(f"{action} HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_backoff * (2 ** attempt))
                    continue
                raise PlatformAdapterError(f"{action} 连接失败：{exc.reason}") from exc
            except TimeoutError as exc:
                last_error = exc
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_backoff * (2 ** attempt))
                    continue
                raise PlatformAdapterError(f"{action} 超时（{self.timeout}s）") from exc
        raise PlatformAdapterError(f"{action} 重试耗尽：{last_error}")

    def execute(self, envelope: ApprovalEnvelope) -> dict[str, Any]:
        # 先校验所有 action 都有映射，避免执行到一半才发现漏配
        missing = [action.action for action in envelope.actions if action.action not in self.actions]
        if missing:
            raise PlatformAdapterError(f"适配器缺少动作映射：{missing}")

        results: list[dict[str, Any]] = []
        for index, action in enumerate(envelope.actions, start=1):
            spec = self.actions[action.action]
            context = {
                "envelope_id": envelope.envelope_id,
                "module": envelope.module,
                "action_type": envelope.action_type,
                "action": action.action,
                "target": action.target,
                "reason": action.reason,
                "before": action.before,
                "after": action.after,
            }
            method = str(spec.get("method") or "POST").upper()
            path = str(_render(spec.get("path") or "/", context, url_quote=True))
            url = f"{self.base_url}{path}"
            body = spec.get("body")
            payload = None
            if body is not None:
                payload = json.dumps(_render(body, context), ensure_ascii=False).encode("utf-8")
            headers = {**self.headers, **self._auth_headers()}
            if self.idempotency_header:
                headers[str(self.idempotency_header)] = (
                    f"{envelope.envelope_id}:{index}:{action.action}"
                )
            headers.update(self._sign(payload))
            raw, status = self._request(method, url, payload, headers, action.action)

            if not (200 <= status < 300):
                raise PlatformAdapterError(f"{action.action} 返回非 2xx：{status}")
            try:
                parsed = json.loads(raw) if raw.strip() else None
            except json.JSONDecodeError:
                parsed = raw[:2000]
            results.append({
                "action": action.action,
                "method": method,
                "url": url,
                "status": status,
                "response": parsed,
            })
        return {
            "applied": True,
            "mode": f"adapter:{self.name}",
            "actions": [action.action for action in envelope.actions],
            "results": results,
        }

    def as_apply_fn(self) -> Callable[[ApprovalEnvelope], dict[str, Any]]:
        return self.execute
