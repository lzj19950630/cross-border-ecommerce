"""Phase 2 编排引擎（内存版）。

流程：
    IntentRouter → ManagerPlanner → 逐层执行切片 → Runner（工具+证据）
    → 审批信封 → interrupted → resume（approve/reject）→ completed/rejected

它不是 LangGraph 的替代品；先把"路由 → 切片 → 执行 → 审批"的语义跑通，
Phase 3 再把这套引擎替换成 LangGraph supervisor。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from .actions import ApprovalEnvelope, DEFAULT_ACTION_REGISTRY
from .agent_registry import DEFAULT_REGISTRY, AgentRegistry
from .agent_runners import (
    AgentContext,
    AgentResult,
    DEFAULT_RUNNER_REGISTRY,
    RunnerRegistry,
)
from .contracts import Intent, SlicePlan
from .executors import LayerExecutor, SequentialLayerExecutor, make_default_executor
from .intent_router import IntentRouter
from .planner import ManagerPlanner, PlanningError
from .storage import InMemoryStore, TaskRecord, TaskStore

ApplyFunction = Callable[[ApprovalEnvelope], dict[str, Any]]


class RuntimeEngine:
    """Phase 2 内存编排引擎。"""

    def __init__(
        self,
        registry: AgentRegistry = DEFAULT_REGISTRY,
        router: IntentRouter | None = None,
        planner: ManagerPlanner | None = None,
        runners: RunnerRegistry = DEFAULT_RUNNER_REGISTRY,
        store: TaskStore | None = None,
        apply_fn: ApplyFunction | None = None,
        executor: LayerExecutor | None = None,
    ) -> None:
        self.registry = registry
        self.router = router or IntentRouter(registry=registry)
        self.planner = planner or ManagerPlanner(registry=registry)
        self.runners = runners
        self.store = store or InMemoryStore()
        self.apply_fn = apply_fn or self._default_apply
        self.executor = executor or make_default_executor()

    def run(
        self,
        request: str,
        inputs: dict[str, Any] | None = None,
        thread_id: str | None = None,
        owner: str = "",
        idempotency_key: str = "",
        tenant_id: str = "",
    ) -> TaskRecord:
        task = self.store.create_task(request, thread_id=thread_id, owner=owner)
        task.idempotency_key = idempotency_key
        task.tenant_id = tenant_id
        route = self.router.route(request)
        task.route = route.to_dict()
        task.messages.append(route.reason)

        if Intent.CLARIFY in route.intents:
            task.set_status("clarify")
            self.store.save_task(task)
            return task

        try:
            plan = self.planner.plan(request, route)
        except PlanningError as exc:
            task.set_status("planning_error")
            task.error = str(exc)
            task.messages.append(f"规划失败：{exc}")
            self.store.save_task(task)
            return task

        task.plan = plan.to_dict()
        task.layers = plan.execution_order()
        task.inputs = dict(inputs or {})
        self.store.save_task(task)
        return self._execute_plan(task)

    def _execute_plan(self, task: TaskRecord) -> TaskRecord:
        """执行尚未完成的切片；resume 审批通过后也走这里继续。"""
        plan = SlicePlan.from_dict(task.plan)
        by_no = {item.no: item for item in plan.slices}
        executed = {item["no"] for item in task.slices}
        upstream: dict[str, Any] = dict(task.artifacts)

        task.messages.append(f"执行器：{self.executor.name}")

        for layer in task.layers:
            pending = [by_no[no] for no in layer if no not in executed]
            if not pending:
                continue

            def run_slice(slice_: Any) -> AgentResult:
                return self._execute(AgentContext(
                    thread_id=task.thread_id,
                    request=task.request,
                    slice=slice_,
                    inputs=dict(task.inputs),
                    upstream_artifacts=dict(upstream),
                ))

            try:
                results = self.executor.run(pending, run_slice)
            except Exception as exc:
                if self.executor.name != "sequential":
                    task.messages.append(
                        f"{self.executor.name} 执行失败，回退 sequential：{type(exc).__name__}: {exc}"
                    )
                    results = SequentialLayerExecutor().run(pending, run_slice)
                else:
                    raise

            failed = False
            failure: AgentResult | None = None
            for slice_ in pending:
                result = results.get(slice_.no)
                if result is None:
                    result = AgentResult(
                        agent=slice_.agent,
                        status="failed",
                        error="执行器未返回该切片结果",
                    )
                self._record_result(task, slice_.no, slice_.agent, result, upstream)
                executed.add(slice_.no)
                if result.status != "ok":
                    failed = True
                    failure = result

            if failed and failure is not None:
                task.set_status("blocked" if failure.status == "blocked" else "failed")
                task.error = failure.error
                self.store.save_task(task)
                return task

            if task.pending_envelopes:
                task.set_status("interrupted")
                if not any("等待审批" in message for message in task.messages[-2:]):
                    task.messages.append(f"等待审批：{task.pending_envelopes}")
                self.store.save_task(task)
                return task

        task.set_status("completed")
        self.store.save_task(task)
        return task

    @staticmethod
    def _stamp(result: AgentResult, start: float, started_at: str) -> AgentResult:
        result.started_at = started_at
        result.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result.elapsed_ms = int((time.monotonic() - start) * 1000)
        return result

    def _execute(self, context: AgentContext) -> AgentResult:
        start = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        runner = self.runners.get(context.slice.agent)
        try:
            result = runner.run(context)
        except Exception as exc:  # Runner 崩溃 → 如实失败，不静默
            return self._stamp(AgentResult(
                agent=context.slice.agent,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            ), start, started_at)

        if result.agent != context.slice.agent:
            return self._stamp(AgentResult(
                agent=context.slice.agent,
                status="failed",
                error=f"Runner 返回的 Agent 不一致：{result.agent} != {context.slice.agent}",
            ), start, started_at)

        if result.status == "ok":
            if not result.evidence.items:
                return self._stamp(AgentResult(
                    agent=context.slice.agent,
                    status="failed",
                    artifact=result.artifact,
                    evidence=result.evidence,
                    error="缺少证据块：没有证据的产出不许交付",
                ), start, started_at)
            evidence_errors = result.evidence.validate()
            if evidence_errors:
                return self._stamp(AgentResult(
                    agent=context.slice.agent,
                    status="failed",
                    artifact=result.artifact,
                    evidence=result.evidence,
                    error="证据校验失败：" + "；".join(evidence_errors),
                ), start, started_at)
            if result.envelope is not None:
                envelope_errors = result.envelope.validate(DEFAULT_ACTION_REGISTRY)
                if envelope_errors:
                    return self._stamp(AgentResult(
                        agent=context.slice.agent,
                        status="failed",
                        artifact=result.artifact,
                        evidence=result.evidence,
                        envelope=result.envelope,
                        error="审批信封校验失败：" + "；".join(envelope_errors),
                    ), start, started_at)
        return self._stamp(result, start, started_at)

    def execute_slice(self, context: AgentContext) -> AgentResult:
        """公开的切片执行入口（Supervisor 复用同一套不变量校验）。"""
        return self._execute(context)

    def record_result(
        self,
        task: TaskRecord,
        slice_no: int,
        agent: str,
        result: AgentResult,
        upstream: dict[str, Any],
    ) -> None:
        """公开的结果落库入口（Supervisor 复用）。"""
        self._record_result(task, slice_no, agent, result, upstream)

    def _record_result(
        self,
        task: TaskRecord,
        slice_no: int,
        agent: str,
        result: AgentResult,
        upstream: dict[str, Any],
    ) -> None:
        if result.artifact:
            task.artifacts[agent] = result.artifact
            upstream[agent] = result.artifact
        if result.evidence.items:
            task.evidence[agent] = result.evidence.to_dict()
        if result.envelope is not None:
            task.envelopes[result.envelope.envelope_id] = result.envelope.to_dict()
            if result.envelope.envelope_id not in task.pending_envelopes:
                task.pending_envelopes.append(result.envelope.envelope_id)
            # 持久化信封行（SQLite）；任务聚合状态由下面的 save_task 统一落盘
            self.store.save_envelope(task.thread_id, result.envelope)

        task.slices.append({
            "no": slice_no,
            "agent": agent,
            "status": result.status,
            "artifact_keys": list(result.artifact.keys()),
            "evidence_items": len(result.evidence.items),
            "envelope_id": result.envelope.envelope_id if result.envelope else None,
            "messages": result.messages,
            "error": result.error,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "elapsed_ms": result.elapsed_ms,
            "retries": result.retries,
        })
        task.messages.extend(result.messages)
        self.store.save_task(task)

    def decide_pending(
        self,
        task: TaskRecord,
        decision: str = "approve",
        comment: str | None = None,
        decided_by: str = "human",
        current_snapshots: dict[str, dict[str, Any]] | None = None,
    ) -> TaskRecord:
        """只处理待审批信封，不继续执行切片（Supervisor 用）。"""
        if decision not in {"approve", "reject"}:
            raise ValueError("decision 只能是 approve 或 reject")
        if not task.pending_envelopes:
            raise ValueError(f"任务没有待审批信封：{task.thread_id}")

        for envelope_id in list(task.pending_envelopes):
            envelope = self.store.get_envelope(envelope_id)
            envelope.decision = "approved" if decision == "approve" else "rejected"
            envelope.decided_by = decided_by
            envelope.comment = comment
            errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
            if errors:
                raise ValueError("审批信封校验失败：" + "；".join(errors))

            if decision == "approve":
                if current_snapshots is not None:
                    drift = envelope.check_drift(current_snapshots)
                    if drift:
                        raise ValueError("快照漂移，整批回滚：" + "；".join(drift))
                apply_result = self.apply_fn(envelope)
                self.store.append_audit(task.thread_id, {
                    "envelope_id": envelope_id,
                    "decision": "approve",
                    "decided_by": decided_by,
                    "comment": comment,
                    "apply": apply_result,
                })
            else:
                self.store.append_audit(task.thread_id, {
                    "envelope_id": envelope_id,
                    "decision": "reject",
                    "decided_by": decided_by,
                    "comment": comment,
                })

            task.envelopes[envelope_id] = envelope.to_dict()
            task.pending_envelopes.remove(envelope_id)

        if decision == "reject":
            task.set_status("rejected")
            task.messages.append(f"审批被拒绝：{comment or ''}".strip())
            self.store.save_task(task)
            return task

        task.set_status("running")
        task.messages.append("审批通过；继续执行剩余切片（apply 为 dry-run）")
        self.store.save_task(task)
        return task

    def resume(
        self,
        thread_id: str,
        decision: str = "approve",
        comment: str | None = None,
        decided_by: str = "human",
        current_snapshots: dict[str, dict[str, Any]] | None = None,
    ) -> TaskRecord:
        task = self.store.get_task(thread_id)
        task = self.decide_pending(task, decision, comment, decided_by, current_snapshots)
        if decision == "reject":
            return task
        return self._execute_plan(task)

    def cancel(self, thread_id: str) -> TaskRecord:
        task = self.store.get_task(thread_id)
        if task.status in {"completed", "rejected", "cancelled", "failed", "blocked"}:
            raise ValueError(f"任务当前状态不可取消：{task.status}")
        task.set_status("cancelled")
        task.pending_envelopes = []
        task.messages.append("任务已取消")
        self.store.save_task(task)
        return task

    def continue_plan(self, task: TaskRecord) -> TaskRecord:
        """从任务当前进度继续执行剩余切片（Supervisor 跨进程续跑用）。"""
        return self._execute_plan(task)

    def get_task(self, thread_id: str) -> TaskRecord:
        return self.store.get_task(thread_id)

    def list_tasks(self) -> list[TaskRecord]:
        return self.store.list_tasks()

    @staticmethod
    def _default_apply(envelope: ApprovalEnvelope) -> dict[str, Any]:
        """Phase 2 默认不触碰平台后台；只记录"本应执行"的动作。"""
        return {
            "applied": True,
            "mode": "dry_run",
            "actions": [action.action for action in envelope.actions],
            "note": "Phase 2 dry-run：真实执行由底座的事务 apply 接管",
        }
