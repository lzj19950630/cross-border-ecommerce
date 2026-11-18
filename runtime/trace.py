"""任务全链路追踪与 LangGraph checkpoint 读取。

- build_trace：把 task.slices / messages / audits / envelopes 归一成事件时间轴；
- list_checkpoints：只读打开 .runtime/checkpoints.db，用 SqliteSaver.list()
  列某 thread 的历史快照（含 step/source/state/interrupt 摘要）。

历史快照当前仅支持查看，不提供回滚；续跑走现有审批/resume 链路，避免外部
TaskRecord 与 LangGraph 图状态不一致。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .storage import TaskRecord


MAX_STATE_BYTES = 64 * 1024
DEFAULT_LIMIT = 50


def build_trace(
    task: TaskRecord, audits: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """把一次任务整理成可直接渲染的事件流 + 原始结构。"""
    audits = list(audits or [])
    events: list[dict[str, Any]] = []

    if task.route:
        events.append(
            {
                "type": "route",
                "at": task.created_at,
                "label": "意图路由",
                "intents": task.route.get("intents", []),
                "confidence": task.route.get("confidence"),
                "reason": task.route.get("reason", ""),
            }
        )
    if task.plan:
        plan_slices = task.plan.get("slices") or []
        events.append(
            {
                "type": "plan",
                "at": task.created_at,
                "label": f"执行计划（{len(plan_slices)} 个切片）",
                "slices": [
                    {"no": item.get("no"), "agent": item.get("agent")}
                    for item in plan_slices
                    if isinstance(item, dict)
                ],
            }
        )
    for item in task.slices:
        events.append(
            {
                "type": "slice",
                "at": item.get("started_at") or task.created_at,
                "finished_at": item.get("finished_at"),
                "no": item.get("no"),
                "agent": item.get("agent"),
                "status": item.get("status"),
                "elapsed_ms": item.get("elapsed_ms"),
                "retries": item.get("retries", 0),
                "artifact_keys": item.get("artifact_keys") or [],
                "evidence_items": item.get("evidence_items", 0),
                "envelope_id": item.get("envelope_id"),
                "messages": item.get("messages") or [],
                "error": item.get("error"),
            }
        )
    for audit in audits:
        events.append(
            {
                "type": "audit",
                "at": audit.get("at"),
                "label": "审批决定",
                **{key: value for key, value in audit.items() if key != "at"},
            }
        )
    events.sort(key=lambda event: str(event.get("at") or ""))

    return {
        "thread_id": task.thread_id,
        "request": task.request,
        "status": task.status,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "route": task.route,
        "plan": task.plan,
        "layers": task.layers,
        "slices": task.slices,
        "messages": task.messages,
        "audits": audits,
        "events": events,
        "checkpoint": task.checkpoint,
        "task_checkpoint": task.checkpoint,
    }


def list_checkpoints(
    checkpoint_db: str | Path,
    thread_id: str,
    *,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """读取某 thread 的 LangGraph 历史快照（新→旧）。"""
    limit = max(1, min(int(limit), 200))
    raw = str(checkpoint_db)
    path = Path(raw)
    result: dict[str, Any] = {
        "thread_id": thread_id,
        "checkpointer": "unavailable",
        "available": False,
        "snapshots": [],
        "reason": "",
        "resume_supported": False,
    }
    if "://" in raw and not raw.startswith("sqlite"):
        result["reason"] = (
            "当前仅支持查看 SQLite checkpoint；Postgres checkpointer 请用数据库工具查看"
        )
        return result
    if not path.exists():
        result["reason"] = "checkpoint 数据库不存在（simple 引擎或未启用 sqlite checkpointer）"
        return result
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except Exception as exc:  # pragma: no cover - 取决于环境
        result["reason"] = f"未安装 langgraph-checkpoint-sqlite：{exc}"
        return result
    try:
        with SqliteSaver.from_conn_string(str(path)) as saver:
            config = {"configurable": {"thread_id": thread_id}}
            snapshots = [_snapshot(item) for item in saver.list(config, limit=limit)]
    except Exception as exc:
        result["reason"] = f"读取 checkpoint 失败：{exc}"
        return result
    result.update(
        {"checkpointer": "sqlite", "available": True, "snapshots": snapshots}
    )
    if not snapshots:
        result["reason"] = "该 thread 没有历史快照（simple 引擎或任务未走 supervisor）"
    return result


def _snapshot(item: Any) -> dict[str, Any]:
    config = getattr(item, "config", None) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    checkpoint = getattr(item, "checkpoint", None) or {}
    metadata = getattr(item, "metadata", None) or {}

    state = {
        str(key): _json_safe(value)
        for key, value in (checkpoint.get("channel_values") or {}).items()
        if not str(key).startswith("branch:")
    }
    try:
        if len(json.dumps(state, ensure_ascii=False)) > MAX_STATE_BYTES:
            state = {"_truncated": True, "keys": sorted(state)}
    except (TypeError, ValueError):
        state = {"_repr": repr(state)}

    pending: list[dict[str, Any]] = []
    interrupt_payload = None
    for write in getattr(item, "pending_writes", None) or []:
        if not isinstance(write, (list, tuple)) or len(write) < 3:
            continue
        channel = str(write[1])
        value = write[2]
        if channel == "__interrupt__":
            payload = value
            if isinstance(value, (list, tuple)) and value:
                payload = getattr(value[0], "value", value[0])
            interrupt_payload = payload
            pending.append(
                {"channel": channel, "summary": _summarize_interrupt(payload)}
            )
        else:
            pending.append({"channel": channel})

    return {
        "checkpoint_id": configurable.get("checkpoint_id"),
        "parent_checkpoint_id": _parent_id(getattr(item, "parent_config", None)),
        "step": metadata.get("step"),
        "source": metadata.get("source"),
        "ts": checkpoint.get("ts"),
        "state": state,
        "writes": _json_safe(metadata.get("writes") or {}),
        "pending": pending,
        "has_interrupt": interrupt_payload is not None,
    }


def _parent_id(parent_config: Any) -> str | None:
    if not isinstance(parent_config, dict):
        return None
    configurable = parent_config.get("configurable") or {}
    return configurable.get("checkpoint_id")


def _summarize_interrupt(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            "thread_id": payload.get("thread_id"),
            "task_status": payload.get("task_status"),
            "pending_envelopes": list(payload.get("pending_envelopes") or []),
        }
    return _json_safe(payload)


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return repr(value)
