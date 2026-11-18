"""租户级模型配置：API Key 加密保存、按租户解析 LLM。"""
from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .llm import LLMClient, LLMError, OpenAICompatibleClient


class ProviderError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def derive_key(secret: str) -> bytes:
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover
        raise ProviderError("需要 cryptography：pip install cryptography") from exc
    try:
        Fernet(secret.encode("ascii"))
        return secret.encode("ascii")
    except Exception:
        return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


@dataclass
class ProviderService:
    store: Any
    secret_key: str | None = None

    def __post_init__(self) -> None:
        self.secret_key = self.secret_key or os.environ.get("RUNTIME_SECRET_KEY")
        self._cipher = None
        if self.secret_key:
            from cryptography.fernet import Fernet
            self._cipher = Fernet(derive_key(self.secret_key))

    def _require_cipher(self):
        if self._cipher is None:
            raise ProviderError("RUNTIME_SECRET_KEY 未配置，不能保存/读取模型密钥")
        return self._cipher

    @staticmethod
    def masked(config: dict[str, Any]) -> dict[str, Any]:
        return {
            "tenant_id": config.get("tenant_id", ""),
            "name": config.get("name", "default"),
            "base_url": config.get("base_url", ""),
            "model": config.get("model", ""),
            "api_key_set": bool(config.get("api_key_enc")),
            "api_key_last4": config.get("api_key_last4", ""),
            "updated_at": config.get("updated_at", ""),
            "updated_by": config.get("updated_by", ""),
        }

    def save(
        self,
        *,
        tenant_id: str,
        name: str,
        base_url: str,
        model: str,
        api_key: str,
        updated_by: str,
    ) -> dict[str, Any]:
        if not tenant_id:
            raise ProviderError("缺少 tenant_id")
        if not base_url.startswith(("http://", "https://")):
            raise ProviderError("base_url 必须是 http(s)")
        if not model.strip():
            raise ProviderError("model 不能为空")
        if not api_key.strip():
            raise ProviderError("api_key 不能为空")
        cipher = self._require_cipher()
        config = {
            "tenant_id": tenant_id,
            "name": name or "default",
            "base_url": base_url.rstrip("/"),
            "model": model.strip(),
            "api_key_enc": cipher.encrypt(api_key.encode("utf-8")).decode("ascii"),
            "api_key_last4": api_key[-4:],
            "updated_at": _now(),
            "updated_by": updated_by,
        }
        self.store.save_provider_config(config)
        return self.masked(config)

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        return [self.masked(item) for item in self.store.list_provider_configs(tenant_id)]

    def delete(self, tenant_id: str, name: str = "default") -> None:
        self.store.delete_provider_config(tenant_id, name)

    def llm_for(self, tenant_id: str, name: str = "default") -> LLMClient | None:
        config = self.store.get_provider_config(tenant_id, name)
        if config is None:
            return None
        cipher = self._require_cipher()
        try:
            api_key = cipher.decrypt(config["api_key_enc"].encode("ascii")).decode("utf-8")
        except Exception as exc:
            raise ProviderError(f"租户模型密钥解密失败：{type(exc).__name__}") from exc
        return OpenAICompatibleClient(
            config["base_url"], config["model"], api_key
        )

    def test(self, tenant_id: str, name: str = "default") -> dict[str, Any]:
        llm = self.llm_for(tenant_id, name)
        if llm is None:
            raise ProviderError(f"租户 {tenant_id} 未配置模型 {name}")
        try:
            data = llm.complete_json(
                "只输出 JSON：{\"ok\": true}",
                "这是连接测试，请输出 {\"ok\": true}",
            )
        except LLMError as exc:
            raise ProviderError(str(exc)) from exc
        return {"ok": True, "model": self.masked(self.store.get_provider_config(tenant_id, name) or {})["model"], "response": data}


class TenantLLMResolver:
    """按 AgentContext.tenant_id 选择租户模型；没有配置则回退全局 LLM。"""

    def __init__(self, providers: ProviderService, fallback: LLMClient | None = None) -> None:
        self.providers = providers
        self.fallback = fallback

    def __call__(self, context) -> LLMClient:
        if context.tenant_id:
            try:
                llm = self.providers.llm_for(context.tenant_id)
            except ProviderError as exc:
                raise LLMError(str(exc)) from exc
            if llm is not None:
                return llm
        if self.fallback is None:
            raise LLMError(f"租户 {context.tenant_id or '(无)'} 未配置模型，且无全局 LLM")
        return self.fallback
