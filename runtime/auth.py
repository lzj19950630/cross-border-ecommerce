"""认证与授权：API Key / JWT + 多用户角色 + 动作级审批策略。

环境变量：
    RUNTIME_API_KEY   单密钥 → admin
    RUNTIME_API_KEYS  JSON {"key":"name:role"} 或 {"key":{"name","role"}}
    RUNTIME_JWT_SECRET JWT HS256 密钥
    RUNTIME_USERS     JSON {"alice":{"password_sha256":"...","role":"admin"}}
    RUNTIME_ACTION_ROLES JSON {"product.update_price":["admin"]}
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

ROLES = {"admin", "operator", "viewer"}


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    tenant: str = ""


def hash_password(password: str) -> str:
    """旧版 sha256（保留兼容；生产建议 bcrypt）。"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password_bcrypt(password: str) -> str:
    try:
        import bcrypt
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("bcrypt 未安装：pip install bcrypt") from exc
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode_jwt(secret: str, payload: dict[str, Any], ttl: int = 3600) -> str:
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl
    claims = _b64encode(json.dumps(body, ensure_ascii=False).encode())
    signing_input = f"{header}.{claims}".encode()
    signature = _b64encode(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return f"{header}.{claims}.{signature}"


def decode_jwt(secret: str, token: str) -> dict[str, Any] | None:
    try:
        header, claims, signature = token.split(".", 2)
        signing_input = f"{header}.{claims}".encode()
        expected = _b64encode(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature):
            return None
        payload = json.loads(_b64decode(claims))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


class AuthConfig:
    def __init__(
        self,
        api_key: str | None = None,
        api_keys: dict[str, object] | None = None,
        jwt_secret: str | None = None,
        users: dict[str, object] | None = None,
        account_store: Any | None = None,
    ) -> None:
        self._keys: dict[str, Principal] = {}
        self.jwt_secret = jwt_secret
        self.account_store = account_store
        self.users: dict[str, dict[str, str]] = {}
        if api_key:
            self._keys[api_key] = Principal(name="api", role="admin")
        for token, spec in (api_keys or {}).items():
            if not token:
                continue
            tenant = ""
            if isinstance(spec, str):
                parts = spec.split(":")
                if len(parts) == 3:
                    tenant, name, role = parts
                else:
                    name, _, role = spec.partition(":")
            elif isinstance(spec, dict):
                tenant = str(spec.get("tenant") or "")
                name = str(spec.get("name") or "")
                role = str(spec.get("role") or "")
            else:
                raise ValueError(f"API key {token[:4]}… 的配置格式非法")
            tenant, name, role = tenant.strip(), name.strip(), role.strip()
            if not name or role not in ROLES:
                raise ValueError(f"API key 用户/角色非法：{name!r}/{role!r}")
            self._keys[token] = Principal(name=name, role=role, tenant=tenant)
        for name, spec in (users or {}).items():
            if not isinstance(spec, dict):
                raise ValueError(f"用户 {name} 配置必须是对象")
            role = str(spec.get("role") or "")
            bcrypt_hash = str(spec.get("password_bcrypt") or "")
            sha_hash = str(spec.get("password_sha256") or "")
            if role not in ROLES or not (bcrypt_hash or sha_hash):
                raise ValueError(
                    f"用户 {name} 缺少角色或密码哈希（password_bcrypt / password_sha256）"
                )
            self.users[str(name)] = {
                "role": role,
                "password_bcrypt": bcrypt_hash,
                "password_sha256": sha_hash,
                "tenant": str(spec.get("tenant") or "").strip(),
            }

    @property
    def enabled(self) -> bool:
        return bool(self._keys or (self.jwt_secret and self.users))

    def authenticate(
        self,
        token: str | None,
        is_revoked: Callable[[str], bool] | None = None,
    ) -> Principal | None:
        if not token:
            return None
        principal = self._keys.get(token)
        if principal:
            return principal
        if self.jwt_secret:
            payload = decode_jwt(self.jwt_secret, token)
            if payload is None:
                return None
            jti = str(payload.get("jti") or "")
            if is_revoked is not None and jti and is_revoked(jti):
                return None
            name = str(payload.get("sub") or "")
            role = str(payload.get("role") or "")
            tenant = str(payload.get("tenant") or "")
            if name and role in ROLES:
                return Principal(name=name, role=role, tenant=tenant)
        return None

    def issue(self, principal: Principal) -> str | None:
        if not self.jwt_secret:
            return None
        return encode_jwt(
            self.jwt_secret,
            {
                "sub": principal.name,
                "role": principal.role,
                "tenant": principal.tenant,
                "jti": uuid.uuid4().hex,
            },
        )

    def payload(self, token: str) -> dict[str, Any] | None:
        if not self.jwt_secret:
            return None
        return decode_jwt(self.jwt_secret, token)

    def refresh(
        self, token: str, is_revoked: Callable[[str], bool] | None = None
    ) -> tuple[str, Principal] | None:
        principal = self.authenticate(token, is_revoked=is_revoked)
        if principal is None:
            return None
        issued = self.issue(principal)
        if issued is None:
            return None
        return issued, principal

    def login(self, username: str, password: str) -> tuple[str, Principal] | None:
        if not self.jwt_secret:
            return None
        user = self.users.get(username)
        if user is None and self.account_store is not None:
            record = self.account_store.get_user(username)
            if record is not None and record.get("active", True):
                user = {
                    "role": record.get("role", ""),
                    "tenant": record.get("tenant_id", ""),
                    "password_bcrypt": record.get("password_bcrypt", ""),
                    "password_sha256": "",
                }
        if user is None:
            return None
        if user.get("password_bcrypt"):
            try:
                import bcrypt
            except ImportError:  # pragma: no cover
                return None
            try:
                valid = bcrypt.checkpw(
                    password.encode("utf-8"),
                    user["password_bcrypt"].encode("ascii"),
                )
            except ValueError:
                return None
        else:
            valid = hmac.compare_digest(user["password_sha256"], hash_password(password))
        if not valid:
            return None
        principal = Principal(
            name=username, role=user["role"], tenant=user.get("tenant", "")
        )
        token = self.issue(principal)
        if token is None:
            return None
        return token, principal


class ActionPolicy:
    """动作级审批策略：action → 允许的角色；未配置的动作默认 admin/operator。"""

    def __init__(self, mapping: dict[str, object] | None = None) -> None:
        self._mapping: dict[str, set[str]] = {}
        for action, roles in (mapping or {}).items():
            if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
                raise ValueError(f"动作 {action} 的角色配置必须是字符串数组")
            invalid = set(roles) - ROLES
            if invalid:
                raise ValueError(f"动作 {action} 含非法角色：{sorted(invalid)}")
            self._mapping[str(action)] = set(roles)

    def allowed(self, principal: Principal | None, action: str) -> bool:
        if principal is None:
            return True
        roles = self._mapping.get(action)
        if roles is None:
            for key, value in self._mapping.items():
                if key.endswith("*") and action.startswith(key[:-1]):
                    roles = value
                    break
        if roles is None:
            return principal.role in {"admin", "operator"}
        return principal.role in roles


def load_auth_config() -> AuthConfig:
    raw_keys = os.environ.get("RUNTIME_API_KEYS")
    api_keys = None
    if raw_keys:
        try:
            parsed = json.loads(raw_keys)
        except json.JSONDecodeError as exc:
            raise ValueError(f"RUNTIME_API_KEYS 不是有效 JSON：{exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("RUNTIME_API_KEYS 顶层必须是对象")
        api_keys = parsed

    raw_users = os.environ.get("RUNTIME_USERS")
    users = None
    if raw_users:
        try:
            parsed_users = json.loads(raw_users)
        except json.JSONDecodeError as exc:
            raise ValueError(f"RUNTIME_USERS 不是有效 JSON：{exc}") from exc
        if not isinstance(parsed_users, dict):
            raise ValueError("RUNTIME_USERS 顶层必须是对象")
        users = parsed_users

    return AuthConfig(
        api_key=os.environ.get("RUNTIME_API_KEY"),
        api_keys=api_keys,
        jwt_secret=os.environ.get("RUNTIME_JWT_SECRET"),
        users=users,
    )


def load_action_policy() -> ActionPolicy:
    raw = os.environ.get("RUNTIME_ACTION_ROLES")
    if not raw:
        return ActionPolicy()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"RUNTIME_ACTION_ROLES 不是有效 JSON：{exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("RUNTIME_ACTION_ROLES 顶层必须是对象")
    return ActionPolicy(parsed)
