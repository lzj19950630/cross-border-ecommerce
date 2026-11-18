"""运行时存储抽象。

- Phase 2：InMemoryStore（单进程）
- Phase 3b：SQLiteStore（stdlib sqlite3，可跨进程）
- 未来：Postgres 实现同一套 TaskStore 协议。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .actions import ApprovalEnvelope


VALID_TASK_STATUSES = {
    "created",
    "running",
    "clarify",
    "planning_error",
    "interrupted",
    "completed",
    "blocked",
    "failed",
    "rejected",
    "cancelled",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class TaskRecord:
    """一次任务（thread）的完整状态。"""

    thread_id: str
    request: str
    owner: str = ""
    tenant_id: str = ""
    status: str = "created"
    route: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    layers: list[list[int]] = field(default_factory=list)
    slices: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    envelopes: dict[str, Any] = field(default_factory=dict)
    pending_envelopes: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    delivery_status: str = "not_reviewed"
    delivery_review: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    error: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def set_status(self, status: str) -> None:
        if status not in VALID_TASK_STATUSES:
            raise ValueError(f"非法任务状态：{status}（可用：{sorted(VALID_TASK_STATUSES)}）")
        self.status = status

    def touch(self) -> None:
        self.updated_at = _now()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskRecord":
        return cls(
            thread_id=str(data["thread_id"]),
            request=str(data.get("request", "")),
            owner=str(data.get("owner", "")),
            tenant_id=str(data.get("tenant_id", "")),
            status=str(data.get("status", "created")),
            route=dict(data.get("route") or {}),
            plan=dict(data.get("plan") or {}),
            inputs=dict(data.get("inputs") or {}),
            layers=[[int(x) for x in layer] for layer in (data.get("layers") or [])],
            slices=list(data.get("slices") or []),
            artifacts=dict(data.get("artifacts") or {}),
            evidence=dict(data.get("evidence") or {}),
            envelopes=dict(data.get("envelopes") or {}),
            pending_envelopes=[str(x) for x in (data.get("pending_envelopes") or [])],
            messages=[str(x) for x in (data.get("messages") or [])],
            checkpoint=dict(data.get("checkpoint") or {}),
            delivery_status=str(data.get("delivery_status", "not_reviewed")),
            delivery_review=dict(data.get("delivery_review") or {}),
            idempotency_key=str(data.get("idempotency_key", "")),
            error=data.get("error"),
            created_at=str(data.get("created_at") or _now()),
            updated_at=str(data.get("updated_at") or _now()),
        )


class TaskStore(Protocol):
    """编排引擎依赖的存储协议。"""

    def create_task(
        self, request: str, thread_id: str | None = None, owner: str = ""
    ) -> TaskRecord: ...
    def save_task(self, task: TaskRecord) -> None: ...
    def get_task(self, thread_id: str) -> TaskRecord: ...
    def list_tasks(self) -> list[TaskRecord]: ...
    def save_artifact(self, thread_id: str, agent: str, artifact: dict[str, Any]) -> None: ...
    def save_evidence(self, thread_id: str, agent: str, evidence: dict[str, Any]) -> None: ...
    def save_envelope(self, thread_id: str, envelope: ApprovalEnvelope) -> None: ...
    def get_envelope(self, envelope_id: str) -> ApprovalEnvelope: ...
    def append_audit(self, thread_id: str, entry: dict[str, Any]) -> None: ...
    def list_audits(self, thread_id: str | None = None) -> list[dict[str, Any]]: ...
    def save_eval_run(self, report: dict[str, Any]) -> None: ...
    def list_eval_runs(self, limit: int = 20) -> list[dict[str, Any]]: ...
    def revoke_token(self, jti: str, expires_at: float) -> None: ...
    def is_token_revoked(self, jti: str) -> bool: ...
    def save_tenant(self, tenant: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO tenants(id, payload) VALUES (?, ?)",
            (str(tenant["id"]), json.dumps(tenant, ensure_ascii=False)),
        )
        self._conn.commit()

    def list_tenants(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT payload FROM tenants ORDER BY id").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT payload FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def delete_tenant(self, tenant_id: str) -> None:
        self._conn.execute("DELETE FROM tenants WHERE id=?", (tenant_id,))
        self._conn.commit()

    def save_user(self, user: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO users(username, tenant_id, payload) VALUES (?, ?, ?)",
            (
                str(user["username"]),
                str(user.get("tenant_id") or ""),
                json.dumps(user, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def list_users(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        if tenant_id is None:
            rows = self._conn.execute("SELECT payload FROM users ORDER BY username").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM users WHERE tenant_id=? ORDER BY username", (tenant_id,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_user(self, username: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT payload FROM users WHERE username=?", (username,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def delete_user(self, username: str) -> None:
        self._conn.execute("DELETE FROM users WHERE username=?", (username,))
        self._conn.commit()

    def save_provider_config(self, config: dict[str, Any]) -> None: ...
    def get_provider_config(self, tenant_id: str, name: str = "default") -> dict[str, Any] | None: ...
    def list_provider_configs(self, tenant_id: str) -> list[dict[str, Any]]: ...
    def delete_provider_config(self, tenant_id: str, name: str = "default") -> None: ...
    def save_tenant(self, tenant: dict[str, Any]) -> None: ...
    def list_tenants(self) -> list[dict[str, Any]]: ...
    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None: ...
    def delete_tenant(self, tenant_id: str) -> None: ...
    def save_user(self, user: dict[str, Any]) -> None: ...
    def list_users(self, tenant_id: str | None = None) -> list[dict[str, Any]]: ...
    def get_user(self, username: str) -> dict[str, Any] | None: ...
    def delete_user(self, username: str) -> None: ...


class InMemoryStore:
    """Phase 2 的内存存储。"""

    def __init__(self) -> None:
        self.tasks: dict[str, TaskRecord] = {}
        self.envelopes: dict[str, ApprovalEnvelope] = {}
        self.audits: list[dict[str, Any]] = []
        self.eval_runs: list[dict[str, Any]] = []
        self.revoked_tokens: dict[str, float] = {}
        self.provider_configs: dict[tuple[str, str], dict[str, Any]] = {}
        self.tenants: dict[str, dict[str, Any]] = {}
        self.users: dict[str, dict[str, Any]] = {}

    def create_task(
        self, request: str, thread_id: str | None = None, owner: str = ""
    ) -> TaskRecord:
        task = TaskRecord(
            thread_id=thread_id or uuid.uuid4().hex, request=request, owner=owner
        )
        self.tasks[task.thread_id] = task
        return task

    def save_task(self, task: TaskRecord) -> None:
        task.touch()
        self.tasks[task.thread_id] = task

    def get_task(self, thread_id: str) -> TaskRecord:
        try:
            return self.tasks[thread_id]
        except KeyError:
            raise KeyError(f"任务不存在：{thread_id}") from None

    def list_tasks(self) -> list[TaskRecord]:
        return list(self.tasks.values())

    def save_artifact(self, thread_id: str, agent: str, artifact: dict[str, Any]) -> None:
        task = self.get_task(thread_id)
        task.artifacts[agent] = artifact
        self.save_task(task)

    def save_evidence(self, thread_id: str, agent: str, evidence: dict[str, Any]) -> None:
        task = self.get_task(thread_id)
        task.evidence[agent] = evidence
        self.save_task(task)

    def save_envelope(self, thread_id: str, envelope: ApprovalEnvelope) -> None:
        # 只存信封本体；任务聚合状态由编排引擎统一 save_task
        self.envelopes[envelope.envelope_id] = envelope

    def get_envelope(self, envelope_id: str) -> ApprovalEnvelope:
        try:
            return self.envelopes[envelope_id]
        except KeyError:
            raise KeyError(f"审批信封不存在：{envelope_id}") from None

    def append_audit(self, thread_id: str, entry: dict[str, Any]) -> None:
        self.audits.append({"thread_id": thread_id, "at": _now(), **entry})

    def list_audits(self, thread_id: str | None = None) -> list[dict[str, Any]]:
        if thread_id is None:
            return list(self.audits)
        return [item for item in self.audits if item.get("thread_id") == thread_id]

    def save_eval_run(self, report: dict[str, Any]) -> None:
        self.eval_runs.append(dict(report))
        self.eval_runs = self.eval_runs[-100:]

    def list_eval_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(reversed(self.eval_runs[-limit:]))

    def save_tenant(self, tenant: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO tenants(id, payload) VALUES (?, ?)",
            (str(tenant["id"]), json.dumps(tenant, ensure_ascii=False)),
        )
        self._conn.commit()

    def list_tenants(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT payload FROM tenants ORDER BY id").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT payload FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def delete_tenant(self, tenant_id: str) -> None:
        self._conn.execute("DELETE FROM tenants WHERE id=?", (tenant_id,))
        self._conn.commit()

    def save_user(self, user: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO users(username, tenant_id, payload) VALUES (?, ?, ?)",
            (
                str(user["username"]),
                str(user.get("tenant_id") or ""),
                json.dumps(user, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def list_users(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        if tenant_id is None:
            rows = self._conn.execute("SELECT payload FROM users ORDER BY username").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM users WHERE tenant_id=? ORDER BY username", (tenant_id,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_user(self, username: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT payload FROM users WHERE username=?", (username,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def delete_user(self, username: str) -> None:
        self._conn.execute("DELETE FROM users WHERE username=?", (username,))
        self._conn.commit()

    def save_provider_config(self, config: dict[str, Any]) -> None:
        key = (str(config["tenant_id"]), str(config.get("name") or "default"))
        self.provider_configs[key] = dict(config)

    def get_provider_config(self, tenant_id: str, name: str = "default") -> dict[str, Any] | None:
        return self.provider_configs.get((tenant_id, name))

    def list_provider_configs(self, tenant_id: str) -> list[dict[str, Any]]:
        return [
            value for (tenant, _), value in self.provider_configs.items()
            if tenant == tenant_id
        ]

    def delete_provider_config(self, tenant_id: str, name: str = "default") -> None:
        self.provider_configs.pop((tenant_id, name), None)

    def save_tenant(self, tenant: dict[str, Any]) -> None:
        self.tenants[str(tenant["id"])] = dict(tenant)

    def list_tenants(self) -> list[dict[str, Any]]:
        return list(self.tenants.values())

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        return self.tenants.get(tenant_id)

    def delete_tenant(self, tenant_id: str) -> None:
        self.tenants.pop(tenant_id, None)

    def save_user(self, user: dict[str, Any]) -> None:
        self.users[str(user["username"])] = dict(user)

    def list_users(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        return [
            user for user in self.users.values()
            if tenant_id is None or user.get("tenant_id") == tenant_id
        ]

    def get_user(self, username: str) -> dict[str, Any] | None:
        return self.users.get(username)

    def delete_user(self, username: str) -> None:
        self.users.pop(username, None)

    def revoke_token(self, jti: str, expires_at: float) -> None:
        self.revoked_tokens[jti] = expires_at

    def is_token_revoked(self, jti: str) -> bool:
        now = __import__("time").time()
        expired = [key for key, exp in self.revoked_tokens.items() if exp < now]
        for key in expired:
            self.revoked_tokens.pop(key, None)
        return jti in self.revoked_tokens

    def reset(self) -> None:
        self.tasks.clear()
        self.envelopes.clear()
        self.audits.clear()
        self.eval_runs.clear()
        self.revoked_tokens.clear()
        self.provider_configs.clear()
        self.tenants.clear()
        self.users.clear()


class _LockedConnection:
    """把单个 sqlite3 连接的操作串行化，供 FastAPI 线程池共享。

    sqlite3 默认 check_same_thread=True，连接不能在创建线程之外使用；
    API 的同步端点跑在 anyio 线程池里，因此必须关闭该检查并自己加锁。
    """

    def __init__(self, conn: sqlite3.Connection, lock: Any) -> None:
        self._conn = conn
        self._lock = lock

    def execute(self, *args: Any, **kwargs: Any):
        with self._lock:
            return self._conn.execute(*args, **kwargs)

    def executescript(self, *args: Any, **kwargs: Any):
        with self._lock:
            return self._conn.executescript(*args, **kwargs)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class SQLiteStore:
    """Phase 3b：stdlib sqlite3 持久化，CLI 可跨进程 run → resume。"""

    def __init__(self, path: str | Path = ".runtime/runtime.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        conn = sqlite3.connect(
            str(self.path), check_same_thread=False, timeout=30
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        self._conn = _LockedConnection(conn, self._lock)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                thread_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS envelopes (
                envelope_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS eval_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                jti TEXT PRIMARY KEY,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_configs (
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (tenant_id, name)
            );
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_envelopes_thread ON envelopes(thread_id);
            CREATE INDEX IF NOT EXISTS idx_audits_thread ON audits(thread_id);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def create_task(
        self, request: str, thread_id: str | None = None, owner: str = ""
    ) -> TaskRecord:
        task = TaskRecord(
            thread_id=thread_id or uuid.uuid4().hex, request=request, owner=owner
        )
        self.save_task(task)
        return task

    def save_task(self, task: TaskRecord) -> None:
        task.touch()
        self._conn.execute(
            """
            INSERT INTO tasks(thread_id, payload) VALUES (?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET payload=excluded.payload
            """,
            (task.thread_id, json.dumps(task.to_dict(), ensure_ascii=False)),
        )
        self._conn.commit()

    def get_task(self, thread_id: str) -> TaskRecord:
        row = self._conn.execute(
            "SELECT payload FROM tasks WHERE thread_id=?", (thread_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"任务不存在：{thread_id}")
        return TaskRecord.from_dict(json.loads(row["payload"]))

    def list_tasks(self) -> list[TaskRecord]:
        rows = self._conn.execute(
            "SELECT payload FROM tasks ORDER BY rowid DESC"
        ).fetchall()
        return [TaskRecord.from_dict(json.loads(row["payload"])) for row in rows]

    def save_artifact(self, thread_id: str, agent: str, artifact: dict[str, Any]) -> None:
        task = self.get_task(thread_id)
        task.artifacts[agent] = artifact
        self.save_task(task)

    def save_evidence(self, thread_id: str, agent: str, evidence: dict[str, Any]) -> None:
        task = self.get_task(thread_id)
        task.evidence[agent] = evidence
        self.save_task(task)

    def save_envelope(self, thread_id: str, envelope: ApprovalEnvelope) -> None:
        # 只存信封行；任务聚合状态由编排引擎统一 save_task
        self._conn.execute(
            """
            INSERT INTO envelopes(envelope_id, thread_id, payload) VALUES (?, ?, ?)
            ON CONFLICT(envelope_id) DO UPDATE SET payload=excluded.payload
            """,
            (
                envelope.envelope_id,
                thread_id,
                json.dumps(envelope.to_dict(), ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def get_envelope(self, envelope_id: str) -> ApprovalEnvelope:
        row = self._conn.execute(
            "SELECT payload FROM envelopes WHERE envelope_id=?", (envelope_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"审批信封不存在：{envelope_id}")
        return ApprovalEnvelope.from_dict(json.loads(row["payload"]))

    def append_audit(self, thread_id: str, entry: dict[str, Any]) -> None:
        payload = {"thread_id": thread_id, "at": _now(), **entry}
        self._conn.execute(
            "INSERT INTO audits(thread_id, payload) VALUES (?, ?)",
            (thread_id, json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    def list_audits(self, thread_id: str | None = None) -> list[dict[str, Any]]:
        if thread_id is None:
            rows = self._conn.execute("SELECT payload FROM audits ORDER BY id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM audits WHERE thread_id=? ORDER BY id", (thread_id,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_eval_run(self, report: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO eval_runs(created_at, payload) VALUES (?, ?)",
            (_now(), json.dumps(report, ensure_ascii=False)),
        )
        self._conn.commit()

    def list_eval_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT payload FROM eval_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_tenant(self, tenant: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO tenants(id, payload) VALUES (?, ?)",
            (str(tenant["id"]), json.dumps(tenant, ensure_ascii=False)),
        )
        self._conn.commit()

    def list_tenants(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT payload FROM tenants ORDER BY id").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT payload FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def delete_tenant(self, tenant_id: str) -> None:
        self._conn.execute("DELETE FROM tenants WHERE id=?", (tenant_id,))
        self._conn.commit()

    def save_user(self, user: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO users(username, tenant_id, payload) VALUES (?, ?, ?)",
            (
                str(user["username"]),
                str(user.get("tenant_id") or ""),
                json.dumps(user, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def list_users(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        if tenant_id is None:
            rows = self._conn.execute("SELECT payload FROM users ORDER BY username").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM users WHERE tenant_id=? ORDER BY username", (tenant_id,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_user(self, username: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT payload FROM users WHERE username=?", (username,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def delete_user(self, username: str) -> None:
        self._conn.execute("DELETE FROM users WHERE username=?", (username,))
        self._conn.commit()

    def save_provider_config(self, config: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO provider_configs(tenant_id, name, payload) VALUES (?, ?, ?)",
            (
                str(config["tenant_id"]),
                str(config.get("name") or "default"),
                json.dumps(config, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def get_provider_config(self, tenant_id: str, name: str = "default") -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload FROM provider_configs WHERE tenant_id=? AND name=?",
            (tenant_id, name),
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_provider_configs(self, tenant_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT payload FROM provider_configs WHERE tenant_id=? ORDER BY name",
            (tenant_id,),
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete_provider_config(self, tenant_id: str, name: str = "default") -> None:
        self._conn.execute(
            "DELETE FROM provider_configs WHERE tenant_id=? AND name=?",
            (tenant_id, name),
        )
        self._conn.commit()

    def revoke_token(self, jti: str, expires_at: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO revoked_tokens(jti, expires_at) VALUES (?, ?)",
            (jti, expires_at),
        )
        self._conn.commit()

    def is_token_revoked(self, jti: str) -> bool:
        now = __import__("time").time()
        self._conn.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (now,))
        self._conn.commit()
        row = self._conn.execute(
            "SELECT 1 FROM revoked_tokens WHERE jti=?", (jti,)
        ).fetchone()
        return row is not None

    def reset(self) -> None:
        self._conn.executescript(
            "DELETE FROM tasks; DELETE FROM envelopes; DELETE FROM audits; "
            "DELETE FROM eval_runs; DELETE FROM revoked_tokens; DELETE FROM provider_configs; "
            "DELETE FROM tenants; DELETE FROM users;"
        )
        self._conn.commit()
