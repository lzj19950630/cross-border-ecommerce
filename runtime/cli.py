"""Runtime platform core CLI（不依赖 LangGraph / FastAPI）。

用法：
    python -m runtime route "帮我看下巴西站滑板车类目"
    python -m runtime plan "先分析市场，然后定价，再做主图和广告"
    python -m runtime tools
    python -m runtime actions
    python -m runtime check-envelope envelope.json
    python -m runtime check-evidence --text output.md --evidence evidence.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .actions import DEFAULT_ACTION_REGISTRY, ApprovalEnvelope
from .agent_registry import DEFAULT_REGISTRY
from .contracts import Intent
from .doctor import run_doctor
from .engine import RuntimeEngine
from .evidence import EvidenceBlock, check_citations
from .export import export_task
from .factory import DEFAULT_DB, make_store
from .intent_router import IntentRouter
from .agent_runners import DEFAULT_RUNNER_REGISTRY
from .planner import ManagerPlanner, PlanningError
from .storage import SQLiteStore
from .tools import DEFAULT_TOOL_REGISTRY

def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _route(text: str) -> dict[str, Any]:
    router = IntentRouter()
    decision = router.route(text)
    return decision.to_dict()


def _plan(text: str) -> dict[str, Any]:
    router = IntentRouter()
    decision = router.route(text)
    if decision.intents == (Intent.CLARIFY,):
        return {"status": "clarify", "route": decision.to_dict()}
    planner = ManagerPlanner()
    try:
        plan = planner.plan(text, decision)
    except PlanningError as exc:
        return {"status": "planning_error", "route": decision.to_dict(), "error": str(exc)}
    slices = []
    for item in plan.slices:
        spec = DEFAULT_REGISTRY.get(item.agent)
        slices.append({
            **item.to_dict(),
            "agent_name": spec.name,
            "tools": list(spec.tools),
            "approval_policy": spec.approval_policy,
        })
    return {
        "status": "ok",
        "route": decision.to_dict(),
        "plan": {"slices": slices},
        "execution_layers": plan.execution_order(),
    }


def _load_structured(path: Path) -> dict[str, Any]:
    """读 JSON 或 YAML（YAML 需要可选的 PyYAML）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"无法读取文件：{exc}") from exc
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败：{exc}") from exc
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError("读取 YAML 需要 PyYAML；或先把文件另存为 .json") from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:  # type: ignore[attr-defined]
            raise ValueError(f"YAML 解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("文件顶层必须是对象")
    return data


def _check_envelope(path: Path) -> dict[str, Any]:
    try:
        data = _load_structured(path)
    except ValueError as exc:
        return {"ok": False, "errors": [f"无法读取审批信封：{exc}"]}
    envelope = ApprovalEnvelope.from_dict(data)
    errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
    return {"ok": not errors, "errors": errors, "envelope": envelope.to_dict()}


def _check_evidence(text: str, evidence_path: Path) -> dict[str, Any]:
    try:
        data = _load_structured(evidence_path)
    except ValueError as exc:
        return {"ok": False, "errors": [f"无法读取证据块：{exc}"]}
    block = EvidenceBlock.from_dict(data)
    result = check_citations(text, block)
    return result.to_dict()


def _load_inputs(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    path = Path(raw)
    text = path.read_text(encoding="utf-8") if path.is_file() else raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--inputs 不是有效 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("--inputs 顶层必须是对象")
    return data


def _exit_code(status: str) -> int:
    return {
        "completed": 0,
        "interrupted": 2,
        "clarify": 2,
        "blocked": 3,
        "failed": 1,
        "planning_error": 1,
        "rejected": 1,
    }.get(status, 1)


def _engine(
    db: str | None,
    executor: str = "auto",
    apply_webhook: str | None = None,
    runners=None,
    apply_adapter: str | None = None,
) -> RuntimeEngine:
    from .apply import make_apply_fn
    from .executors import make_executor
    return RuntimeEngine(
        store=make_store(db),
        executor=make_executor(executor),
        apply_fn=make_apply_fn(apply_webhook, adapter_path=apply_adapter),
        runners=runners or DEFAULT_RUNNER_REGISTRY,
    )


def _creative_runners(creative: bool):
    if not creative:
        return None
    from .creative import build_creative_registry
    from .llm import load_llm_from_env
    llm = load_llm_from_env()
    if llm is None:
        raise ValueError(
            "启用 --creative 需要 LLM 配置（RUNTIME_LLM_BASE_URL/MODEL/API_KEY，"
            "或 OPENAI_BASE_URL/OPENAI_MODEL/OPENAI_API_KEY）"
        )
    return build_creative_registry(llm)


def _close_engine(engine: RuntimeEngine) -> None:
    close = getattr(engine.store, "close", None)
    if callable(close):
        close()


def _close_supervisor(supervisor) -> None:
    close = getattr(supervisor, "close", None)
    if callable(close):
        close()
    _close_engine(supervisor.engine)


def _run(
    text: str,
    inputs_raw: str | None,
    thread_id: str | None,
    decision: str,
    comment: str | None,
    db: str | None,
    executor: str = "auto",
    engine_type: str = "simple",
    apply_webhook: str | None = None,
    checkpointer: str = "auto",
    checkpoint_db: str = ".runtime/checkpoints.db",
    creative: bool = False,
    apply_adapter: str | None = None,
) -> tuple[int, dict[str, Any]]:
    try:
        runners = _creative_runners(creative)
    except ValueError as exc:
        return 2, {"status": "config_error", "error": str(exc)}
    if engine_type == "supervisor":
        from .supervisor import LangGraphSupervisor
        from .executors import make_executor
        from .apply import make_apply_fn
        supervisor = LangGraphSupervisor(
            store=make_store(db),
            executor=make_executor(executor),
            apply_fn=make_apply_fn(apply_webhook, adapter_path=apply_adapter),
            checkpointer=checkpointer,
            checkpoint_db=checkpoint_db,
            **({"runners": runners} if runners else {}),
        )
        engine = None
        close_target = supervisor.engine
    else:
        supervisor = None
        engine = _engine(
            db, executor, apply_webhook, runners=runners, apply_adapter=apply_adapter
        )
        close_target = engine
    try:
        try:
            inputs = _load_inputs(inputs_raw)
        except ValueError as exc:
            return 2, {"status": "input_error", "error": str(exc)}
        if supervisor is not None:
            task = supervisor.run(text, inputs=inputs, thread_id=thread_id)
            if decision != "none" and task.status == "interrupted":
                task = supervisor.resume(task.thread_id, decision=decision, comment=comment)
        else:
            assert engine is not None
            task = engine.run(text, inputs=inputs, thread_id=thread_id)
            if decision != "none" and task.status == "interrupted":
                task = engine.resume(task.thread_id, decision=decision, comment=comment)
        return _exit_code(task.status), task.to_dict()
    finally:
        if supervisor is not None:
            _close_supervisor(supervisor)
        else:
            _close_engine(close_target)


def _resume(
    thread_id: str,
    decision: str,
    comment: str | None,
    db: str | None,
    engine_type: str = "simple",
    apply_webhook: str | None = None,
    checkpointer: str = "auto",
    checkpoint_db: str = ".runtime/checkpoints.db",
    creative: bool = False,
    apply_adapter: str | None = None,
) -> tuple[int, dict[str, Any]]:
    try:
        runners = _creative_runners(creative)
    except ValueError as exc:
        return 2, {"status": "config_error", "error": str(exc)}
    if engine_type == "supervisor":
        from .apply import make_apply_fn
        from .supervisor import LangGraphSupervisor
        supervisor = LangGraphSupervisor(
            store=make_store(db),
            apply_fn=make_apply_fn(apply_webhook, adapter_path=apply_adapter),
            checkpointer=checkpointer,
            checkpoint_db=checkpoint_db,
            **({"runners": runners} if runners else {}),
        )
        try:
            try:
                task = supervisor.resume(thread_id, decision=decision, comment=comment)
            except (KeyError, ValueError) as exc:
                return 1, {"status": "resume_error", "error": str(exc)}
            return _exit_code(task.status), task.to_dict()
        finally:
            _close_supervisor(supervisor)

    engine = _engine(
        db, apply_webhook=apply_webhook, runners=runners, apply_adapter=apply_adapter
    )
    try:
        try:
            task = engine.resume(thread_id, decision=decision, comment=comment)
        except (KeyError, ValueError) as exc:
            return 1, {"status": "resume_error", "error": str(exc)}
        return _exit_code(task.status), task.to_dict()
    finally:
        _close_engine(engine)


def _task(thread_id: str, db: str | None) -> tuple[int, dict[str, Any]]:
    engine = _engine(db)
    try:
        try:
            task = engine.get_task(thread_id)
        except KeyError as exc:
            return 1, {"status": "not_found", "error": str(exc)}
        return 0, task.to_dict()
    finally:
        _close_engine(engine)


def _tasks(db: str | None) -> tuple[int, dict[str, Any]]:
    engine = _engine(db)
    try:
        tasks = engine.list_tasks()
        return 0, {
            "tasks": [
                {
                    "thread_id": task.thread_id,
                    "status": task.status,
                    "request": task.request,
                    "updated_at": task.updated_at,
                }
                for task in tasks
            ]
        }
    finally:
        _close_engine(engine)


def _eval(cases_path: str, use_judge: bool = False) -> tuple[int, dict[str, Any]]:
    from .evals import load_cases, run_cases
    judge = None
    if use_judge:
        from .llm import load_llm_from_env
        judge = load_llm_from_env()
        if judge is None:
            return 2, {"ok": False, "error": "启用 --judge 需要 LLM 配置"}
    try:
        cases = load_cases(cases_path)
        report = run_cases(cases, judge=judge)
    except Exception as exc:  # noqa: BLE001
        return 1, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return (0 if report["ok"] else 1), report


def _audits(thread_id: str | None, db: str | None) -> tuple[int, dict[str, Any]]:
    engine = _engine(db)
    try:
        events = engine.store.list_audits(thread_id)
        return 0, {"thread_id": thread_id, "audits": events}
    finally:
        _close_engine(engine)


def _serve(
    host: str, port: int, db: str | None, executor: str, engine_type: str,
    apply_webhook: str | None = None,
    checkpointer: str = "auto",
    checkpoint_db: str = ".runtime/checkpoints.db",
    creative: bool = False,
    apply_adapter: str | None = None,
) -> int:
    try:
        import uvicorn
    except ImportError:
        print("[ERROR] 需要 uvicorn：pip install uvicorn", file=sys.stderr)
        return 1
    from .api import create_app
    from .executors import make_executor
    cors_raw = os.environ.get("RUNTIME_CORS_ORIGINS", "")
    cors_origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()] or None
    api_keys = None
    api_keys_raw = os.environ.get("RUNTIME_API_KEYS")
    if api_keys_raw:
        try:
            parsed = json.loads(api_keys_raw)
        except json.JSONDecodeError:
            print("[ERROR] RUNTIME_API_KEYS 必须是 JSON 对象", file=sys.stderr)
            return 1
        if not isinstance(parsed, dict):
            print("[ERROR] RUNTIME_API_KEYS 顶层必须是对象", file=sys.stderr)
            return 1
        api_keys = parsed
    users = None
    users_raw = os.environ.get("RUNTIME_USERS")
    if users_raw:
        try:
            parsed_users = json.loads(users_raw)
        except json.JSONDecodeError:
            print("[ERROR] RUNTIME_USERS 必须是 JSON 对象", file=sys.stderr)
            return 1
        if not isinstance(parsed_users, dict):
            print("[ERROR] RUNTIME_USERS 顶层必须是对象", file=sys.stderr)
            return 1
        users = parsed_users
    action_roles = None
    roles_raw = os.environ.get("RUNTIME_ACTION_ROLES")
    if roles_raw:
        try:
            parsed_roles = json.loads(roles_raw)
        except json.JSONDecodeError:
            print("[ERROR] RUNTIME_ACTION_ROLES 必须是 JSON 对象", file=sys.stderr)
            return 1
        if not isinstance(parsed_roles, dict):
            print("[ERROR] RUNTIME_ACTION_ROLES 顶层必须是对象", file=sys.stderr)
            return 1
        action_roles = parsed_roles
    rate_limit = None
    rate_raw = os.environ.get("RUNTIME_RATE_LIMIT")
    if rate_raw:
        try:
            rate_limit = int(rate_raw)
        except ValueError:
            print("[ERROR] RUNTIME_RATE_LIMIT 必须是整数（每分钟请求数）", file=sys.stderr)
            return 1
        if rate_limit < 1:
            print("[ERROR] RUNTIME_RATE_LIMIT 必须 >= 1", file=sys.stderr)
            return 1
    app = create_app(
        store=make_store(db), executor=executor,
        engine_type=engine_type, apply_webhook=apply_webhook,
        checkpointer=checkpointer, checkpoint_db=checkpoint_db,
        creative=creative, apply_adapter=apply_adapter,
        api_key=os.environ.get("RUNTIME_API_KEY"),
        api_keys=api_keys,
        jwt_secret=os.environ.get("RUNTIME_JWT_SECRET"),
        users=users,
        action_roles=action_roles,
        proxy_auth_secret=os.environ.get("RUNTIME_PROXY_AUTH_SECRET"),
        rate_limit=rate_limit,
        secret_key=os.environ.get("RUNTIME_SECRET_KEY"),
        cors_origins=cors_origins,
    )
    print(f"Runtime API: http://{host}:{port}  (engine={app.state.engine_type}, executor={app.state.executor_name})")
    uvicorn.run(app, host=host, port=port)
    return 0


def _export(thread_id: str, out: str, db: str | None) -> tuple[int, dict[str, Any]]:
    engine = _engine(db)
    try:
        try:
            task = engine.get_task(thread_id)
        except KeyError as exc:
            return 1, {"status": "not_found", "error": str(exc)}
        return 0, export_task(task, out, audits=engine.store.list_audits(thread_id))
    finally:
        _close_engine(engine)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m runtime",
        description="AI 跨境电商 Agent Runtime 平台核心（意图路由/切片/审批/证据）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    route = sub.add_parser("route", help="只做意图识别与路由")
    route.add_argument("text")

    plan = sub.add_parser("plan", help="意图识别 + Manager 切片计划")
    plan.add_argument("text")

    run = sub.add_parser("run", help="执行一次任务（7 个 Agent 可跑）")
    run.add_argument("text")
    run.add_argument("--inputs", help="输入覆盖 JSON（或 JSON 文件路径）")
    run.add_argument("--thread-id", help="指定 thread id（默认自动生成）")
    run.add_argument(
        "--decision", choices=("none", "approve", "reject"), default="none",
        help="若任务停在审批，立即批准/拒绝（单进程 dry-run）",
    )
    run.add_argument("--comment", help="审批备注")
    run.add_argument("--db", help=f"SQLite 状态文件（默认 {DEFAULT_DB}）")
    run.add_argument(
        "--executor", choices=("auto", "sequential", "langgraph"), default="auto",
        help="层执行器：默认 auto（优先 LangGraph，失败回退 sequential）",
    )
    run.add_argument(
        "--engine", choices=("simple", "supervisor"), default="simple",
        help="编排引擎：simple（默认）/ supervisor（LangGraph interrupt）",
    )
    run.add_argument("--apply-webhook", help="审批通过后 POST 到该 webhook（默认 dry-run）")
    run.add_argument("--apply-adapter", help="平台动作映射 YAML/JSON（优先于 webhook）")
    run.add_argument("--checkpointer", choices=("auto", "memory", "sqlite"), default="auto")
    run.add_argument("--checkpoint-db", default=".runtime/checkpoints.db")
    run.add_argument("--creative", action="store_true", help="启用 LLM 创意层（需 LLM 配置）")

    resume = sub.add_parser("resume", help="批准/拒绝某个任务的待审批信封")
    resume.add_argument("thread_id")
    resume.add_argument("--decision", choices=("approve", "reject"), default="approve")
    resume.add_argument("--comment")
    resume.add_argument("--db", help=f"SQLite 状态文件（默认 {DEFAULT_DB}）")
    resume.add_argument("--engine", choices=("simple", "supervisor"), default="simple")
    resume.add_argument("--apply-webhook", help="审批通过后 POST 到该 webhook（默认 dry-run）")
    resume.add_argument("--apply-adapter", help="平台动作映射 YAML/JSON（优先于 webhook）")
    resume.add_argument("--checkpointer", choices=("auto", "memory", "sqlite"), default="auto")
    resume.add_argument("--checkpoint-db", default=".runtime/checkpoints.db")
    resume.add_argument("--creative", action="store_true", help="启用 LLM 创意层（需 LLM 配置）")

    task = sub.add_parser("task", help="查看单个任务")
    task.add_argument("thread_id")
    task.add_argument("--db", help=f"SQLite 状态文件（默认 {DEFAULT_DB}）")

    tasks = sub.add_parser("tasks", help="列出全部任务")
    tasks.add_argument("--db", help=f"SQLite 状态文件（默认 {DEFAULT_DB}）")

    sub.add_parser("doctor", help="环境/脚本/样本/SQLite 自检")

    eval_parser = sub.add_parser("eval", help="跑确定性金标评测")
    eval_parser.add_argument("cases", help="评测 YAML/JSON，如 Templates/eval_case.yaml")
    eval_parser.add_argument("--judge", action="store_true", help="启用 LLM judge（需 LLM 配置）")

    audits = sub.add_parser("audits", help="查看审批审计")
    audits.add_argument("thread_id", nargs="?")
    audits.add_argument("--db", help=f"SQLite 状态文件（默认 {DEFAULT_DB}）")

    serve = sub.add_parser("serve", help="启动 FastAPI 服务")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--db", help=f"SQLite 状态文件（默认 {DEFAULT_DB}）")
    serve.add_argument("--executor", choices=("auto", "sequential", "langgraph"), default="auto")
    serve.add_argument("--engine", choices=("simple", "supervisor"), default="simple")
    serve.add_argument("--apply-webhook", help="审批通过后 POST 到该 webhook（默认 dry-run）")
    serve.add_argument("--apply-adapter", help="平台动作映射 YAML/JSON（优先于 webhook）")
    serve.add_argument("--checkpointer", choices=("auto", "memory", "sqlite"), default="auto")
    serve.add_argument("--checkpoint-db", default=".runtime/checkpoints.db")
    serve.add_argument("--creative", action="store_true", help="启用 LLM 创意层（需 LLM 配置）")

    export = sub.add_parser("export", help="导出任务产物/证据/信封 + Markdown 摘要")
    export.add_argument("thread_id")
    export.add_argument("--out", required=True, help="导出目录")
    export.add_argument("--db", help=f"SQLite 状态文件（默认 {DEFAULT_DB}）")

    sub.add_parser("tools", help="列出注册的工具")
    sub.add_parser("actions", help="列出动作风险注册表")

    envelope = sub.add_parser("check-envelope", help="校验审批信封 JSON")
    envelope.add_argument("path", type=Path)

    evidence = sub.add_parser("check-evidence", help="校验正文引用 [n] 与证据块")
    evidence.add_argument("--text", required=True, help="正文文本文件，或直接文本")
    evidence.add_argument("--evidence", required=True, type=Path, help="证据块 JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "route":
        _print_json(_route(args.text))
        return 0

    if args.command == "plan":
        result = _plan(args.text)
        _print_json(result)
        return 0 if result["status"] == "ok" else 2

    if args.command == "run":
        code, result = _run(
            args.text, args.inputs, args.thread_id, args.decision, args.comment,
            args.db, args.executor, args.engine, args.apply_webhook,
            args.checkpointer, args.checkpoint_db, args.creative, args.apply_adapter,
        )
        _print_json(result)
        return code

    if args.command == "resume":
        code, result = _resume(
            args.thread_id, args.decision, args.comment,
            args.db, args.engine, args.apply_webhook,
            args.checkpointer, args.checkpoint_db, args.creative, args.apply_adapter,
        )
        _print_json(result)
        return code

    if args.command == "serve":
        return _serve(
            args.host, args.port, args.db, args.executor, args.engine,
            args.apply_webhook, args.checkpointer, args.checkpoint_db, args.creative,
            args.apply_adapter,
        )

    if args.command == "task":
        code, result = _task(args.thread_id, args.db)
        _print_json(result)
        return code

    if args.command == "tasks":
        code, result = _tasks(args.db)
        _print_json(result)
        return code

    if args.command == "eval":
        code, result = _eval(args.cases, args.judge)
        _print_json(result)
        return code

    if args.command == "doctor":
        result = run_doctor()
        _print_json(result)
        return 0 if result["ok"] else 1

    if args.command == "audits":
        code, result = _audits(args.thread_id, args.db)
        _print_json(result)
        return code

    if args.command == "export":
        code, result = _export(args.thread_id, args.out, args.db)
        _print_json(result)
        return code

    if args.command == "tools":
        _print_json({
            "tools": [
                {
                    **tool.to_dict(),
                    "path": (Path(__file__).resolve().parent.parent / tool.script).as_posix(),
                }
                for tool in DEFAULT_TOOL_REGISTRY.all()
            ]
        })
        return 0

    if args.command == "actions":
        _print_json({"actions": DEFAULT_ACTION_REGISTRY.metadata()})
        return 0

    if args.command == "check-envelope":
        result = _check_envelope(args.path)
        _print_json(result)
        return 0 if result["ok"] else 1

    if args.command == "check-evidence":
        text_path = Path(args.text)
        text = text_path.read_text(encoding="utf-8") if text_path.is_file() else args.text
        result = _check_evidence(text, args.evidence)
        _print_json(result)
        return 0 if result["ok"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
