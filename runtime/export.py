"""任务导出：把一次运行落成可交付的目录（JSON + Markdown 摘要）。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .storage import TaskRecord


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "item"


def export_task(
    task: TaskRecord,
    out_dir: str | Path,
    audits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    for sub in ("artifacts", "evidence", "envelopes"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    files: list[str] = []
    task_path = out / "task.json"
    task_path.write_text(json.dumps(task.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files.append(str(task_path))

    for agent, artifact in task.artifacts.items():
        path = out / "artifacts" / f"{_safe(agent)}.json"
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files.append(str(path))

    for agent, evidence in task.evidence.items():
        path = out / "evidence" / f"{_safe(agent)}.json"
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files.append(str(path))

    for envelope_id, envelope in task.envelopes.items():
        path = out / "envelopes" / f"{_safe(envelope_id)}.json"
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files.append(str(path))

    if audits is not None:
        path = out / "audits.json"
        path.write_text(
            json.dumps(audits, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        files.append(str(path))

    summary_path = out / "summary.md"
    summary_path.write_text(_summary(task, audits=audits), encoding="utf-8")
    files.append(str(summary_path))
    return {"out_dir": str(out), "files": files}


def _summary(task: TaskRecord, audits: list[dict[str, Any]] | None = None) -> str:
    lines = [
        f"# Task {task.thread_id}",
        "",
        f"- 状态：`{task.status}`",
        f"- 请求：{task.request}",
        f"- 创建：{task.created_at}",
        f"- 更新：{task.updated_at}",
        "",
        "## 切片",
        "",
        "| # | Agent | 状态 | 证据条数 | 审批信封 |",
        "|---|---|---|---|---|",
    ]
    for item in task.slices:
        lines.append(
            f"| {item.get('no')} | {item.get('agent')} | {item.get('status')} | "
            f"{item.get('evidence_items', 0)} | {item.get('envelope_id') or '-'} |"
        )
    if task.envelopes:
        lines.extend(["", "## 审批信封", "", "| 信封 | 决策 |", "|---|---|"])
        for envelope_id, envelope in task.envelopes.items():
            lines.append(f"| {envelope_id} | {envelope.get('decision')} |")
    lines.extend(["", "## 证据清单", ""])
    for agent, block in task.evidence.items():
        items = block.get("items") or []
        lines.append(f"### {agent}")
        for item in items:
            lines.append(f"- `{item.get('claim_id')}` {item.get('claim')}（{item.get('source')} · {item.get('locator')}）")
        lines.append("")
    if audits is not None:
        lines.extend(["", "## 审计", "", f"共 {len(audits)} 条审批决定", ""])
    if task.error:
        lines.extend(["## 错误", "", task.error, ""])
    return "\n".join(lines).rstrip() + "\n"
