"""运行时告警：失败/阻塞任务 + 长时间未处理审批。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def collect_alerts(store, stale_minutes: int = 30) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    alerts: list[dict[str, Any]] = []
    for task in store.list_tasks():
        if task.status in {"failed", "blocked"}:
            alerts.append({
                "level": "error",
                "kind": "task_" + task.status,
                "thread_id": task.thread_id,
                "status": task.status,
                "message": task.error or task.request,
            })
        elif task.status == "interrupted":
            try:
                updated = datetime.fromisoformat(task.updated_at)
            except ValueError:
                updated = now
            if now - updated > timedelta(minutes=stale_minutes):
                alerts.append({
                    "level": "warning",
                    "kind": "approval_stale",
                    "thread_id": task.thread_id,
                    "status": task.status,
                    "message": f"审批已等待超过 {stale_minutes} 分钟",
                })
    return alerts
