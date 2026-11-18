"""确定性评测跑批（零 LLM）。

读取金标场景 YAML/JSON，跑固定输入，执行 mechanical checks：
    number_traceable / required_sections / action_envelope_valid /
    no_forbidden_action / attribution_sum
不依赖 judge；改 Prompt/工具后可快速回归。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .actions import ApprovalEnvelope, DEFAULT_ACTION_REGISTRY
from .contracts import EvalCase
from .engine import RuntimeEngine
from .llm import LLMClient, LLMError
from .executors import SequentialLayerExecutor
from .storage import InMemoryStore, TaskRecord
from .contracts import RiskLevel

CheckFn = Callable[[TaskRecord, EvalCase], tuple[bool, str]]


def _evidence_present(task: TaskRecord, _case: EvalCase) -> tuple[bool, str]:
    missing = [
        agent for agent in task.artifacts
        if not (task.evidence.get(agent) or {}).get("items")
    ]
    return (not missing, "每个产物都有证据" if not missing else f"缺证据：{missing}")


def _required_sections(task: TaskRecord, _case: EvalCase) -> tuple[bool, str]:
    ok = bool(task.artifacts) and bool(task.slices)
    return (ok, "产物/切片非空" if ok else "没有产物或切片")


def _action_envelope_valid(task: TaskRecord, _case: EvalCase) -> tuple[bool, str]:
    errors: list[str] = []
    for envelope_id, raw in task.envelopes.items():
        envelope = ApprovalEnvelope.from_dict(raw)
        errors.extend(envelope.validate(DEFAULT_ACTION_REGISTRY))
    return (not errors, "审批信封合法" if not errors else "；".join(errors))


def _no_forbidden_action(task: TaskRecord, _case: EvalCase) -> tuple[bool, str]:
    forbidden: list[str] = []
    for raw in task.envelopes.values():
        for action in raw.get("actions") or []:
            action_id = str(action.get("action", ""))
            if DEFAULT_ACTION_REGISTRY.classify(action_id) == RiskLevel.FORBIDDEN:
                forbidden.append(action_id)
    return (not forbidden, "无禁止动作" if not forbidden else f"禁止动作：{forbidden}")


def _skus_nonempty(task: TaskRecord, _case: EvalCase) -> tuple[bool, str]:
    skus = (task.artifacts.get("product_strategy") or {}).get("skus") or []
    return (bool(skus), f"{len(skus)} 个 SKU")


def _title_present(task: TaskRecord, _case: EvalCase) -> tuple[bool, str]:
    artifact = task.artifacts.get("listing_creative") or {}
    title = artifact.get("title_final") or artifact.get("title") or ""
    return (bool(str(title).strip()), f"标题：{str(title)[:60]}")


def _image_plan_present(task: TaskRecord, _case: EvalCase) -> tuple[bool, str]:
    plan = (task.artifacts.get("product_image") or {}).get("image_plan") or []
    return (len(plan) >= 9, f"{len(plan)} 个图位")


def _video_timing_ok(task: TaskRecord, _case: EvalCase) -> tuple[bool, str]:
    artifact = task.artifacts.get("product_video") or {}
    return (bool(artifact.get("within_tolerance")), f"within_tolerance={artifact.get('within_tolerance')}")


def _attribution_sum(task: TaskRecord, _case: EvalCase) -> tuple[bool, str]:
    review = task.artifacts.get("review_analysis") or {}
    reviews = review.get("reviews") or {}
    mismatch = reviews.get("attribution_mismatch")
    if mismatch is None:
        return (False, "没有 review_analysis 归因数据")
    return (mismatch == 0, f"归因差异 {mismatch}")


CHECKS: dict[str, CheckFn] = {
    "number_traceable": _evidence_present,
    "evidence_present": _evidence_present,
    "required_sections": _required_sections,
    "action_envelope_valid": _action_envelope_valid,
    "no_forbidden_action": _no_forbidden_action,
    "attribution_sum": _attribution_sum,
    "skus_nonempty": _skus_nonempty,
    "title_present": _title_present,
    "image_plan_present": _image_plan_present,
    "video_timing_ok": _video_timing_ok,
}


def load_cases(path: str | Path) -> list[EvalCase]:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if file.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("读取 YAML 需要 PyYAML；或改用 .json") from exc
        data = yaml.safe_load(text)
    raw_cases = data.get("scenarios") if isinstance(data, dict) else None
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{file} 缺少 scenarios")
    cases = [EvalCase.from_dict(item) for item in raw_cases]
    for case in cases:
        case.validate()
    return cases


JUDGE_SYSTEM = """你是跨境电商运营质量评审。按 rubric 逐条判 0/1，并给一句理由。
只输出 JSON：{"scores":[{"rubric":"原文","pass":true,"reason":"..."}]}
必须覆盖每一条 rubric，不得增加/删减；不要评价 rubric 之外的内容。"""


def _judge_case(case: EvalCase, task: TaskRecord, judge: LLMClient) -> list[dict[str, Any]]:
    payload = {
        "surface": case.surface,
        "input": case.input,
        "rubric": list(case.rubric),
        "task": {
            "status": task.status,
            "artifacts": task.artifacts,
            "evidence": task.evidence,
            "envelopes": task.envelopes,
        },
    }
    data = judge.complete_json(
        JUDGE_SYSTEM,
        json.dumps(payload, ensure_ascii=False)[:12000],
    )
    scores = data.get("scores")
    if not isinstance(scores, list):
        raise LLMError("judge 输出缺少 scores 数组")
    if len(scores) != len(case.rubric):
        raise LLMError(f"judge 判据数量不符：{len(scores)} != {len(case.rubric)}")
    normalized: list[dict[str, Any]] = []
    for index, (item, rubric) in enumerate(zip(scores, case.rubric), start=1):
        if not isinstance(item, dict):
            raise LLMError(f"judge 第 {index} 条不是对象")
        passed = item.get("pass")
        if not isinstance(passed, bool):
            raise LLMError(f"judge 第 {index} 条 pass 不是布尔值")
        normalized.append({
            "rubric": rubric,
            "pass": passed,
            "reason": str(item.get("reason", "")),
        })
    return normalized


def run_cases(
    cases: list[EvalCase],
    engine: RuntimeEngine | None = None,
    judge: LLMClient | None = None,
) -> dict[str, Any]:
    engine = engine or RuntimeEngine(
        store=InMemoryStore(),
        executor=SequentialLayerExecutor(),
    )
    results: list[dict[str, Any]] = []
    for case in cases:
        task = engine.run(case.input)
        checks: list[dict[str, Any]] = []
        for name in case.deterministic_checks:
            fn = CHECKS.get(name)
            if fn is None:
                checks.append({"name": name, "ok": False, "detail": "未知检查项"})
                continue
            ok, detail = fn(task, case)
            checks.append({"name": name, "ok": ok, "detail": detail})
        judge_scores: list[dict[str, Any]] = []
        judge_error: str | None = None
        if judge is not None and case.rubric:
            try:
                judge_scores = _judge_case(case, task, judge)
            except LLMError as exc:
                judge_error = str(exc)

        passed = all(item["ok"] for item in checks) and judge_error is None
        if judge_scores:
            passed = passed and all(item["pass"] for item in judge_scores)
        results.append({
            "id": case.id,
            "surface": case.surface,
            "thread_id": task.thread_id,
            "status": task.status,
            "passed": passed,
            "checks": checks,
            "judge": judge_scores,
            "judge_error": judge_error,
            "artifacts": list(task.artifacts),
        })
    failed = sum(1 for item in results if not item["passed"])
    return {
        "version": 1,
        "ok": failed == 0,
        "passed": len(results) - failed,
        "failed": failed,
        "cases": results,
    }
