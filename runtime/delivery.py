"""交付审核门 + 归档 ZIP。

流程：机器审核 → 人工交付决定 → ZIP 归档。
- 机器审核复用证据/信封/合规模块；
- 归档只允许 delivery_status == passed；
- ZIP 内含 task/artifacts/evidence/envelopes/audits/summary/manifest。
"""
from __future__ import annotations

import json
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actions import ApprovalEnvelope, DEFAULT_ACTION_REGISTRY
from .evidence import EvidenceBlock
from .export import export_task
from .storage import TaskRecord

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FORBIDDEN = (
    "100% original", "100% garantido", "sem risco", "cura", "milagre",
    "melhor do mundo", "o melhor produto", "primeiro lugar",
    "best in the world", "cheapest", "guaranteed", "cure",
)
ASSET_KEYS = {"image_path", "script_file", "reference_image", "file", "path"}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iter_strings(value: Any, skip_keys: set[str] | None = None):
    skip = skip_keys or set()
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in skip:
                continue
            yield from _iter_strings(item, skip)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item, skip)


def _forbidden_words(task: TaskRecord) -> list[str]:
    raw = task.inputs.get("forbidden_words") if isinstance(task.inputs, dict) else None
    words = list(DEFAULT_FORBIDDEN)
    if isinstance(raw, list):
        words.extend(str(item) for item in raw)
    return list(dict.fromkeys(words))


def artifact_compliance(
    artifacts: dict[str, Any],
    forbidden_words: list[str] | None = None,
) -> dict[str, Any]:
    words = list(dict.fromkeys(list(DEFAULT_FORBIDDEN) + list(forbidden_words or [])))
    violations: list[str] = []
    for agent, artifact in (artifacts or {}).items():
        texts = list(_iter_strings(artifact, skip_keys={"compliance_report", "llm_title_lint", "llm_spec_consistency", "llm_timing"}))
        for word in words:
            for text in texts:
                if word.casefold() in text.casefold():
                    violations.append(f"{agent}: 发现禁用/绝对化表述「{word}」")
                    break
    violations = list(dict.fromkeys(violations))
    score = max(0.0, 100.0 - 10 * len(violations))
    return {
        "reviewer": "deterministic",
        "passed": not violations,
        "score": score,
        "violations": violations,
        "suggestions": ["移除或改写违规表述后再提交"] if violations else [],
    }


def compliance_report(task: TaskRecord) -> dict[str, Any]:
    """确定性合规扫描：禁用词/绝对化用语。"""
    return artifact_compliance(task.artifacts or {}, _forbidden_words(task))


def machine_review(task: TaskRecord) -> dict[str, Any]:
    """机器交付审核：状态/产物/证据/信封/合规。"""
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failures.append(detail)

    add("task_status", task.status == "completed", f"status={task.status}")
    add("artifacts", bool(task.artifacts), f"{len(task.artifacts)} 个产物")

    for agent, artifact in (task.artifacts or {}).items():
        block = task.evidence.get(agent) or {}
        items = block.get("items") or []
        add(f"evidence:{agent}", bool(items), f"{len(items)} 条证据")

    for agent, raw in (task.evidence or {}).items():
        errors = EvidenceBlock.from_dict(raw).validate()
        add(f"evidence_valid:{agent}", not errors, "；".join(errors) or "OK")

    for envelope_id, raw in (task.envelopes or {}).items():
        errors = ApprovalEnvelope.from_dict(raw).validate(DEFAULT_ACTION_REGISTRY)
        add(f"envelope:{envelope_id}", not errors, "；".join(errors) or "OK")

    compliance = compliance_report(task)
    add("compliance", compliance["passed"], "；".join(compliance["violations"]) or "无违规")
    if task.error:
        add("task_error", False, task.error)

    passed = not failures
    return {
        "reviewer": "machine",
        "passed": passed,
        "score": compliance["score"],
        "violations": compliance["violations"] + [f for f in failures if f not in compliance["violations"]],
        "suggestions": compliance["suggestions"],
        "checks": checks,
        "reviewed_at": _now(),
    }


def _asset_paths(task: TaskRecord) -> list[Path]:
    found: list[Path] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ASSET_KEYS and isinstance(item, str) and item:
                    path = Path(item)
                    if not path.is_absolute():
                        path = PROJECT_ROOT / path
                    try:
                        resolved = path.resolve()
                        if resolved.is_file() and resolved.is_relative_to(PROJECT_ROOT):
                            found.append(resolved)
                    except (OSError, ValueError):
                        pass
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(task.artifacts)
    return list(dict.fromkeys(found))


def archive_bytes(task: TaskRecord, audits: list[dict[str, Any]] | None = None) -> bytes:
    if task.delivery_status != "passed":
        raise ValueError(f"交付状态为 {task.delivery_status}，不能归档")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        export_task(task, root, audits=audits)
        assets: list[str] = []
        for path in _asset_paths(task):
            safe = _SAFE.sub("-", path.name).strip("-") or "asset"
            target = root / "assets" / safe
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            assets.append(f"assets/{safe}")
        manifest = {
            "task_id": task.thread_id,
            "status": task.status,
            "delivery_status": task.delivery_status,
            "delivery_review": task.delivery_review,
            "assets": assets,
            "generated_at": _now(),
            "version": "agent-runtime",
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        buffer = __import__("io").BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(root).as_posix())
        return buffer.getvalue()
