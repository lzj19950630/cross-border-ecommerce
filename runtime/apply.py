"""审批通过后的 apply 执行器。

- DryRunExecutor：默认，只记录不执行；
- WebhookExecutor：把已批准的审批信封 POST 到外部执行器（底座/中间层/平台网关）。

安全：不执行任意 shell；token 只从参数或环境变量读取，不打印。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from .actions import ApprovalEnvelope


class ApplyError(RuntimeError):
    """apply 失败（网络/HTTP/响应非法）。"""


class DryRunExecutor:
    mode = "dry_run"

    def execute(self, envelope: ApprovalEnvelope) -> dict[str, Any]:
        return {
            "applied": True,
            "mode": self.mode,
            "actions": [action.action for action in envelope.actions],
            "note": "dry-run：未改平台后台",
        }

    def as_apply_fn(self) -> Callable[[ApprovalEnvelope], dict[str, Any]]:
        return self.execute


class WebhookExecutor:
    """把审批信封 POST 到外部执行器；2xx 视为成功。"""

    def __init__(
        self,
        url: str,
        token: str | None = None,
        timeout: int = 30,
    ) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError("webhook URL 必须是 http(s)")
        self.url = url
        self.token = token or os.environ.get("RUNTIME_APPLY_TOKEN")
        self.timeout = timeout

    def execute(self, envelope: ApprovalEnvelope) -> dict[str, Any]:
        payload = json.dumps(envelope.to_dict(), ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            self.url, data=payload, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ApplyError(f"webhook HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ApplyError(f"webhook 连接失败：{exc.reason}") from exc
        except TimeoutError as exc:
            raise ApplyError(f"webhook 超时（{self.timeout}s）") from exc

        if not (200 <= status < 300):
            raise ApplyError(f"webhook 返回非 2xx：{status}")
        try:
            parsed = json.loads(body) if body.strip() else None
        except json.JSONDecodeError:
            parsed = body[:2000]
        return {
            "applied": True,
            "mode": "webhook",
            "status": status,
            "actions": [action.action for action in envelope.actions],
            "response": parsed,
        }

    def as_apply_fn(self) -> Callable[[ApprovalEnvelope], dict[str, Any]]:
        return self.execute


def make_apply_fn(
    webhook_url: str | None = None,
    token: str | None = None,
    adapter_path: str | None = None,
) -> Callable[[ApprovalEnvelope], dict[str, Any]]:
    if adapter_path:
        from .platforms import MappingAdapter
        return MappingAdapter.from_file(adapter_path).as_apply_fn()
    if webhook_url:
        return WebhookExecutor(webhook_url, token=token).as_apply_fn()
    return DryRunExecutor().as_apply_fn()
