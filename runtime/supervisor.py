"""LangGraph supervisor：完整 plan → layer → interrupt → resume 流程。

与 RuntimeEngine 的分工：
- RuntimeEngine：自研逐层循环（稳定、无依赖），也是 supervisor 的复用内核；
- LangGraphSupervisor：用 LangGraph StateGraph + MemorySaver + interrupt 表达同样的语义，
  对外提供 run/resume，适合作为底座接入点。

注意：当前使用 MemorySaver（进程内）；跨重启的 durable interrupt 需要
Postgres/SQLite checkpointer（P4 后续）。
"""
from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
from typing import Any, TypedDict

from .agent_registry import DEFAULT_REGISTRY, AgentRegistry
from .agent_runners import AgentContext, AgentResult, DEFAULT_RUNNER_REGISTRY, RunnerRegistry
from .contracts import SlicePlan
from .engine import ApplyFunction, RuntimeEngine
from .executors import LayerExecutor, SequentialLayerExecutor
from .intent_router import IntentRouter
from .planner import ManagerPlanner, PlanningError
from .storage import InMemoryStore, TaskRecord, TaskStore


class SupervisorState(TypedDict, total=False):
    thread_id: str
    request: str
    inputs: dict[str, Any]
    current_layer: int
    status: str


def _require_langgraph():
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Command, interrupt
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("LangGraph supervisor 需要 langgraph：pip install langgraph") from exc
    return MemorySaver, END, START, StateGraph, Command, interrupt


class LangGraphSupervisor:
    """用 LangGraph 表达 RuntimeEngine 的编排语义。"""

    def __init__(
        self,
        store: TaskStore | None = None,
        executor: LayerExecutor | None = None,
        registry: AgentRegistry = DEFAULT_REGISTRY,
        router: IntentRouter | None = None,
        planner: ManagerPlanner | None = None,
        runners: RunnerRegistry = DEFAULT_RUNNER_REGISTRY,
        apply_fn: ApplyFunction | None = None,
        checkpointer: str = "auto",
        checkpoint_db: str = ".runtime/checkpoints.db",
    ) -> None:
        MemorySaver, self._END, self._START, StateGraph, self._Command, self._interrupt = _require_langgraph()
        # Supervisor 本身已是 LangGraph 图；层执行保持顺序，避免嵌套图把 AgentResult
        # 写进父图 checkpoint（SqliteSaver 无法序列化）。
        if executor is None or getattr(executor, "name", "") == "langgraph":
            executor = SequentialLayerExecutor()
        self._MemorySaver = MemorySaver
        self._checkpoint_stack: ExitStack | None = None
        self._checkpointer, self.checkpointer_name = self._make_checkpointer(
            checkpointer, checkpoint_db
        )
        self.engine = RuntimeEngine(
            registry=registry,
            router=router,
            planner=planner,
            runners=runners,
            store=store or InMemoryStore(),
            executor=executor,
            apply_fn=apply_fn,
        )
        self.store = self.engine.store
        self._StateGraph = StateGraph
        self._graph = self._build()

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
        task.inputs = dict(inputs or {})
        self.store.save_task(task)
        final = self._graph.invoke(
            {"thread_id": task.thread_id, "request": request, "inputs": dict(inputs or {})},
            self._config(task.thread_id),
        )
        task = self.store.get_task(task.thread_id)
        task.checkpoint = {
            "current_layer": int((final or {}).get("current_layer", 0) or 0),
            "status": (final or {}).get("status", task.status),
        }
        self.store.save_task(task)
        return task

    def resume(
        self,
        thread_id: str,
        decision: str = "approve",
        comment: str | None = None,
        decided_by: str = "supervisor",
    ) -> TaskRecord:
        task = self.store.get_task(thread_id)
        if not task.pending_envelopes:
            raise ValueError(f"任务没有待审批信封：{thread_id}")

        # 同进程：MemorySaver 有状态 → 用 LangGraph Command 续跑
        try:
            snapshot = self._graph.get_state(self._config(thread_id))
            has_state = bool(snapshot.values)
        except Exception:
            has_state = False

        if has_state:
            final = self._graph.invoke(
                self._Command(resume={
                    "decision": decision,
                    "comment": comment,
                    "decided_by": decided_by,
                }),
                self._config(thread_id),
            )
            task = self.store.get_task(thread_id)
            task.checkpoint = {
                "current_layer": int((final or {}).get("current_layer", 0) or 0),
                "status": (final or {}).get("status", task.status),
            }
            self.store.save_task(task)
            return task

        # 跨进程：MemorySaver 无状态 → 用任务表里的进度 + simple 引擎续跑
        task = self.engine.decide_pending(
            task, decision=decision, comment=comment, decided_by=decided_by
        )
        if task.status == "rejected":
            return task
        task.messages.append("MemorySaver 无状态，使用任务 checkpoint 继续执行")
        self.store.save_task(task)
        return self.engine.continue_plan(task)

    def cancel(self, thread_id: str) -> TaskRecord:
        return self.engine.cancel(thread_id)

    def get_task(self, thread_id: str) -> TaskRecord:
        return self.store.get_task(thread_id)

    def list_tasks(self) -> list[TaskRecord]:
        return self.store.list_tasks()

    def _make_checkpointer(self, kind: str, db: str):
        if kind == "memory":
            return self._MemorySaver(), "memory"
        if kind in {"auto", "sqlite"}:
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore

                Path(db).parent.mkdir(parents=True, exist_ok=True)
                stack = ExitStack()
                saver = stack.enter_context(SqliteSaver.from_conn_string(db))
                self._checkpoint_stack = stack
                return saver, "sqlite"
            except Exception:
                if kind == "sqlite":
                    raise
        if kind == "postgres":
            try:
                from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("postgres checkpointer 需要 langgraph-checkpoint-postgres") from exc
            dsn = db or os.environ.get("RUNTIME_CHECKPOINT_DSN")
            if not dsn:
                raise RuntimeError("postgres checkpointer 需要 DSN（--checkpoint-db 或 RUNTIME_CHECKPOINT_DSN）")
            stack = ExitStack()
            saver = stack.enter_context(PostgresSaver.from_conn_string(dsn))
            saver.setup()
            self._checkpoint_stack = stack
            return saver, "postgres"
        return self._MemorySaver(), "memory"

    def close(self) -> None:
        if self._checkpoint_stack is not None:
            self._checkpoint_stack.close()
            self._checkpoint_stack = None

    def _config(self, thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}

    def _build(self):
        graph = self._StateGraph(SupervisorState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("execute_layer", self._execute_layer_node)
        graph.add_node("approval", self._approval_node)
        graph.add_edge(self._START, "plan")
        graph.add_conditional_edges("plan", self._after_plan, {
            "execute_layer": "execute_layer",
            self._END: self._END,
        })
        graph.add_conditional_edges("execute_layer", self._after_layer, {
            "approval": "approval",
            "execute_layer": "execute_layer",
            self._END: self._END,
        })
        graph.add_conditional_edges("approval", self._after_approval, {
            "execute_layer": "execute_layer",
            self._END: self._END,
        })
        return graph.compile(checkpointer=self._checkpointer)

    def _plan_node(self, state: SupervisorState) -> dict[str, Any]:
        task = self.store.get_task(state["thread_id"])
        route = self.engine.router.route(state["request"])
        task.route = route.to_dict()
        if route.intents == (route.intents[0],) and route.intents[0].value == "clarify":
            task.set_status("clarify")
            task.messages.append(route.reason)
            self.store.save_task(task)
            return {"status": "clarify"}
        try:
            plan = self.engine.planner.plan(state["request"], route)
        except PlanningError as exc:
            task.set_status("planning_error")
            task.error = str(exc)
            task.messages.append(f"规划失败：{exc}")
            self.store.save_task(task)
            return {"status": "planning_error"}

        task.plan = plan.to_dict()
        task.layers = plan.execution_order()
        task.inputs = dict(state.get("inputs") or {})
        task.set_status("running")
        task.messages.append(f"执行器：{self.engine.executor.name}（LangGraph supervisor）")
        self.store.save_task(task)
        return {"current_layer": 0, "status": "running"}

    def _execute_layer_node(self, state: SupervisorState) -> dict[str, Any]:
        task = self.store.get_task(state["thread_id"])
        current = int(state.get("current_layer", 0))
        if current >= len(task.layers):
            task.set_status("completed")
            self.store.save_task(task)
            return {"status": "completed", "current_layer": current}

        plan = SlicePlan.from_dict(task.plan)
        by_no = {item.no: item for item in plan.slices}
        executed = {item["no"] for item in task.slices}
        pending = [by_no[no] for no in task.layers[current] if no not in executed]
        upstream = dict(task.artifacts)

        def run_slice(slice_) -> AgentResult:
            return self.engine.execute_slice(AgentContext(
                thread_id=task.thread_id,
                request=task.request,
                slice=slice_,
                tenant_id=task.tenant_id,
                inputs=dict(task.inputs),
                upstream_artifacts=dict(upstream),
            ))

        results = self.engine.executor.run(pending, run_slice)
        failure: AgentResult | None = None
        for slice_ in pending:
            result = results.get(slice_.no)
            if result is None:
                result = AgentResult(agent=slice_.agent, status="failed", error="执行器未返回该切片结果")
            self.engine.record_result(task, slice_.no, slice_.agent, result, upstream)
            if result.status != "ok":
                failure = result

        next_layer = current + 1
        if failure is not None:
            task.set_status("blocked" if failure.status == "blocked" else "failed")
            task.error = failure.error
            self.store.save_task(task)
            return {"status": task.status, "current_layer": next_layer}

        if task.pending_envelopes:
            task.set_status("interrupted")
            task.messages.append(f"等待审批：{task.pending_envelopes}")
            self.store.save_task(task)
            return {"status": "interrupted", "current_layer": next_layer}

        task.set_status("running")
        self.store.save_task(task)
        return {"status": "running", "current_layer": next_layer}

    def _approval_node(self, state: SupervisorState) -> dict[str, Any]:
        task = self.store.get_task(state["thread_id"])
        if not task.pending_envelopes:
            return {"status": "running"}
        payload = {
            "thread_id": task.thread_id,
            "pending_envelopes": list(task.pending_envelopes),
            "envelopes": [
                task.envelopes[env_id]
                for env_id in task.pending_envelopes
                if env_id in task.envelopes
            ],
            "task_status": task.status,
        }
        decision = self._interrupt(payload)
        if not isinstance(decision, dict):
            decision = {"decision": "approve"}
        try:
            task = self.engine.decide_pending(
                task,
                decision=str(decision.get("decision", "approve")),
                comment=decision.get("comment"),
                decided_by=str(decision.get("decided_by", "supervisor")),
            )
        except ValueError as exc:
            task.set_status("failed")
            task.error = str(exc)
            self.store.save_task(task)
            return {"status": "failed"}
        return {"status": task.status}

    def _after_plan(self, state: SupervisorState) -> str:
        return self._END if state.get("status") in {"clarify", "planning_error"} else "execute_layer"

    def _after_layer(self, state: SupervisorState) -> str:
        status = state.get("status")
        if status in {"blocked", "failed", "completed"}:
            return self._END
        if status == "interrupted":
            return "approval"
        return "execute_layer"

    def _after_approval(self, state: SupervisorState) -> str:
        status = state.get("status")
        return self._END if status in {"rejected", "failed"} else "execute_layer"
