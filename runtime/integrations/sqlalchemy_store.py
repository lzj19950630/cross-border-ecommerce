"""SQLAlchemy 存储：SQLite 可直接跑，Postgres 换 URL + psycopg 驱动即可。

这是 P3d 的 Postgres-ready 适配层：
    sqlite:///./runtime.db
    postgresql+psycopg://user:pass@host:5432/db
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from ..actions import ApprovalEnvelope
from ..storage import TaskRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLAlchemyStore:
    """TaskStore 的 SQLAlchemy 实现（SQLite/Postgres 通用）。"""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        self.engine: Engine = create_engine(url, future=True, echo=echo)
        self.metadata = MetaData()
        self.tasks = Table(
            "runtime_tasks",
            self.metadata,
            Column("thread_id", String(128), primary_key=True),
            Column("payload", Text, nullable=False),
        )
        self.envelopes = Table(
            "runtime_envelopes",
            self.metadata,
            Column("envelope_id", String(128), primary_key=True),
            Column("thread_id", String(128), nullable=False, index=True),
            Column("payload", Text, nullable=False),
        )
        self.audits = Table(
            "runtime_audits",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("thread_id", String(128), nullable=False, index=True),
            Column("payload", Text, nullable=False),
        )
        self.eval_runs = Table(
            "runtime_eval_runs",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("created_at", String(64), nullable=False),
            Column("payload", Text, nullable=False),
        )
        self.revoked_tokens = Table(
            "runtime_revoked_tokens",
            self.metadata,
            Column("jti", String(128), primary_key=True),
            Column("expires_at", Float, nullable=False),
        )
        self.provider_configs = Table(
            "runtime_provider_configs",
            self.metadata,
            Column("tenant_id", String(128), primary_key=True),
            Column("name", String(64), primary_key=True),
            Column("payload", Text, nullable=False),
        )
        self.tenants = Table(
            "runtime_tenants",
            self.metadata,
            Column("id", String(128), primary_key=True),
            Column("payload", Text, nullable=False),
        )
        self.users = Table(
            "runtime_users",
            self.metadata,
            Column("username", String(128), primary_key=True),
            Column("tenant_id", String(128), nullable=False, index=True),
            Column("payload", Text, nullable=False),
        )
        self.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    # ── tasks ──────────────────────────────────────────────
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
        payload = json.dumps(task.to_dict(), ensure_ascii=False)
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(self.tasks.c.thread_id).where(self.tasks.c.thread_id == task.thread_id)
            ).first()
            if exists:
                conn.execute(
                    update(self.tasks)
                    .where(self.tasks.c.thread_id == task.thread_id)
                    .values(payload=payload)
                )
            else:
                conn.execute(insert(self.tasks).values(thread_id=task.thread_id, payload=payload))

    def get_task(self, thread_id: str) -> TaskRecord:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.tasks.c.payload).where(self.tasks.c.thread_id == thread_id)
            ).first()
        if row is None:
            raise KeyError(f"任务不存在：{thread_id}")
        return TaskRecord.from_dict(json.loads(row[0]))

    def list_tasks(self) -> list[TaskRecord]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(self.tasks.c.payload)).fetchall()
        return [TaskRecord.from_dict(json.loads(row[0])) for row in rows]

    def save_artifact(self, thread_id: str, agent: str, artifact: dict[str, Any]) -> None:
        task = self.get_task(thread_id)
        task.artifacts[agent] = artifact
        self.save_task(task)

    def save_evidence(self, thread_id: str, agent: str, evidence: dict[str, Any]) -> None:
        task = self.get_task(thread_id)
        task.evidence[agent] = evidence
        self.save_task(task)

    # ── envelopes ──────────────────────────────────────────
    def save_envelope(self, thread_id: str, envelope: ApprovalEnvelope) -> None:
        payload = json.dumps(envelope.to_dict(), ensure_ascii=False)
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(self.envelopes.c.envelope_id).where(
                    self.envelopes.c.envelope_id == envelope.envelope_id
                )
            ).first()
            if exists:
                conn.execute(
                    update(self.envelopes)
                    .where(self.envelopes.c.envelope_id == envelope.envelope_id)
                    .values(payload=payload)
                )
            else:
                conn.execute(insert(self.envelopes).values(
                    envelope_id=envelope.envelope_id,
                    thread_id=thread_id,
                    payload=payload,
                ))

    def get_envelope(self, envelope_id: str) -> ApprovalEnvelope:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.envelopes.c.payload).where(
                    self.envelopes.c.envelope_id == envelope_id
                )
            ).first()
        if row is None:
            raise KeyError(f"审批信封不存在：{envelope_id}")
        return ApprovalEnvelope.from_dict(json.loads(row[0]))

    # ── audits ─────────────────────────────────────────────
    def append_audit(self, thread_id: str, entry: dict[str, Any]) -> None:
        payload = {"thread_id": thread_id, "at": _now(), **entry}
        with self.engine.begin() as conn:
            conn.execute(insert(self.audits).values(
                thread_id=thread_id,
                payload=json.dumps(payload, ensure_ascii=False),
            ))

    def list_audits(self, thread_id: str | None = None) -> list[dict[str, Any]]:
        stmt = select(self.audits.c.payload).order_by(self.audits.c.id)
        if thread_id is not None:
            stmt = stmt.where(self.audits.c.thread_id == thread_id)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_eval_run(self, report: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(self.eval_runs).values(
                created_at=_now(),
                payload=json.dumps(report, ensure_ascii=False),
            ))

    def list_eval_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        stmt = select(self.eval_runs.c.payload).order_by(self.eval_runs.c.id.desc()).limit(limit)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_tenant(self, tenant: dict[str, Any]) -> None:
        payload = json.dumps(tenant, ensure_ascii=False)
        with self.engine.begin() as conn:
            exists = conn.execute(select(self.tenants.c.id).where(self.tenants.c.id == tenant["id"])).first()
            if exists:
                conn.execute(update(self.tenants).where(self.tenants.c.id == tenant["id"]).values(payload=payload))
            else:
                conn.execute(insert(self.tenants).values(id=str(tenant["id"]), payload=payload))

    def list_tenants(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(self.tenants.c.payload).order_by(self.tenants.c.id)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(self.tenants.c.payload).where(self.tenants.c.id == tenant_id)).first()
        return json.loads(row[0]) if row else None

    def delete_tenant(self, tenant_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(self.tenants).where(self.tenants.c.id == tenant_id))

    def save_user(self, user: dict[str, Any]) -> None:
        payload = json.dumps(user, ensure_ascii=False)
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(self.users.c.username).where(self.users.c.username == user["username"])
            ).first()
            if exists:
                conn.execute(update(self.users).where(self.users.c.username == user["username"]).values(
                    tenant_id=str(user.get("tenant_id") or ""), payload=payload
                ))
            else:
                conn.execute(insert(self.users).values(
                    username=str(user["username"]),
                    tenant_id=str(user.get("tenant_id") or ""),
                    payload=payload,
                ))

    def list_users(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        stmt = select(self.users.c.payload).order_by(self.users.c.username)
        if tenant_id is not None:
            stmt = stmt.where(self.users.c.tenant_id == tenant_id)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_user(self, username: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(self.users.c.payload).where(self.users.c.username == username)).first()
        return json.loads(row[0]) if row else None

    def delete_user(self, username: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(self.users).where(self.users.c.username == username))

    def save_provider_config(self, config: dict[str, Any]) -> None:
        tenant = str(config["tenant_id"])
        name = str(config.get("name") or "default")
        payload = json.dumps(config, ensure_ascii=False)
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(self.provider_configs.c.tenant_id).where(
                    self.provider_configs.c.tenant_id == tenant,
                    self.provider_configs.c.name == name,
                )
            ).first()
            if exists:
                conn.execute(
                    update(self.provider_configs)
                    .where(
                        self.provider_configs.c.tenant_id == tenant,
                        self.provider_configs.c.name == name,
                    )
                    .values(payload=payload)
                )
            else:
                conn.execute(insert(self.provider_configs).values(
                    tenant_id=tenant, name=name, payload=payload
                ))

    def get_provider_config(self, tenant_id: str, name: str = "default") -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.provider_configs.c.payload).where(
                    self.provider_configs.c.tenant_id == tenant_id,
                    self.provider_configs.c.name == name,
                )
            ).first()
        return json.loads(row[0]) if row else None

    def list_provider_configs(self, tenant_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(self.provider_configs.c.payload)
                .where(self.provider_configs.c.tenant_id == tenant_id)
                .order_by(self.provider_configs.c.name)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def delete_provider_config(self, tenant_id: str, name: str = "default") -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(self.provider_configs).where(
                self.provider_configs.c.tenant_id == tenant_id,
                self.provider_configs.c.name == name,
            ))

    def revoke_token(self, jti: str, expires_at: float) -> None:
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(self.revoked_tokens.c.jti).where(self.revoked_tokens.c.jti == jti)
            ).first()
            if exists:
                conn.execute(
                    update(self.revoked_tokens)
                    .where(self.revoked_tokens.c.jti == jti)
                    .values(expires_at=expires_at)
                )
            else:
                conn.execute(insert(self.revoked_tokens).values(jti=jti, expires_at=expires_at))

    def is_token_revoked(self, jti: str) -> bool:
        import time

        with self.engine.begin() as conn:
            conn.execute(
                delete(self.revoked_tokens).where(self.revoked_tokens.c.expires_at < time.time())
            )
            row = conn.execute(
                select(self.revoked_tokens.c.jti).where(self.revoked_tokens.c.jti == jti)
            ).first()
        return row is not None

    def reset(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(self.tasks))
            conn.execute(delete(self.envelopes))
            conn.execute(delete(self.audits))
            conn.execute(delete(self.eval_runs))
            conn.execute(delete(self.revoked_tokens))
            conn.execute(delete(self.provider_configs))
            conn.execute(delete(self.tenants))
            conn.execute(delete(self.users))
