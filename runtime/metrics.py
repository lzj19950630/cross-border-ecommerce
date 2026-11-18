"""运行时指标（Prometheus 文本 / JSON）。"""
from __future__ import annotations

from collections import Counter
from typing import Any


def collect_metrics(store) -> dict[str, Any]:
    tasks = store.list_tasks()
    counts = Counter(task.status for task in tasks)
    pending = sum(len(task.pending_envelopes) for task in tasks)
    eval_runs = len(store.list_eval_runs(limit=1000))
    return {
        "tasks_total": len(tasks),
        "tasks_by_status": dict(counts),
        "pending_approvals": pending,
        "eval_runs": eval_runs,
    }


def prometheus_text(metrics: dict[str, Any]) -> str:
    lines = [
        "# HELP runtime_tasks_total Total tasks",
        "# TYPE runtime_tasks_total gauge",
        f"runtime_tasks_total {metrics['tasks_total']}",
        "# HELP runtime_pending_approvals Pending approval envelopes",
        "# TYPE runtime_pending_approvals gauge",
        f"runtime_pending_approvals {metrics['pending_approvals']}",
        "# HELP runtime_eval_runs Stored eval runs (max 1000)",
        "# TYPE runtime_eval_runs gauge",
        f"runtime_eval_runs {metrics['eval_runs']}",
        "# HELP runtime_tasks_by_status Tasks by status",
        "# TYPE runtime_tasks_by_status gauge",
    ]
    for status, count in sorted(metrics["tasks_by_status"].items()):
        lines.append(f'runtime_tasks_by_status{{status="{status}"}} {count}')
    return "\n".join(lines) + "\n"
