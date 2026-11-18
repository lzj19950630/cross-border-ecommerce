"""运行时自检：Python/脚本/样本/SQLite/可选依赖。"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .agent_registry import DEFAULT_REGISTRY
from .agent_runners import DEFAULT_AD_REPORT, DEFAULT_METRICS, DEFAULT_NARRATION, DEFAULT_REVIEWS, DEFAULT_SKUS, DEFAULT_SPEC, DEFAULT_IMAGE
from .storage import SQLiteStore
from .tools import DEFAULT_TOOL_REGISTRY, PROJECT_ROOT, ToolRegistry


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def run_doctor(
    *,
    project_root: Path = PROJECT_ROOT,
    tools: ToolRegistry = DEFAULT_TOOL_REGISTRY,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append(_check(
        "python",
        sys.version_info >= (3, 10),
        f"Python {version}（需要 >= 3.10）",
    ))

    for tool in tools.all():
        script = (project_root / tool.script).resolve()
        checks.append(_check(f"tool:{tool.name}", script.is_file(), str(script)))

    for agent in DEFAULT_REGISTRY.all():
        missing = [name for name in agent.tools if name not in tools.names()]
        checks.append(_check(
            f"agent:{agent.key}",
            not missing,
            "工具齐备" if not missing else f"缺工具：{missing}",
        ))

    samples = {
        "01 metrics": DEFAULT_METRICS,
        "02 skus": DEFAULT_SKUS,
        "03 spec": DEFAULT_SPEC,
        "04 image": DEFAULT_IMAGE,
        "05 narration": DEFAULT_NARRATION,
        "06 ad report": DEFAULT_AD_REPORT,
        "07 reviews": DEFAULT_REVIEWS,
    }
    for name, relative in samples.items():
        path = (project_root / relative).resolve()
        checks.append(_check(f"sample:{name}", path.is_file(), str(path)))

    try:
        probe = sqlite3.connect(":memory:")
        try:
            probe.execute("SELECT 1").fetchone()
        finally:
            probe.close()
        with tempfile.TemporaryDirectory() as td:
            store = SQLiteStore(Path(td) / "doctor.db")
            store.list_tasks()
            store.close()
        checks.append(_check("sqlite", True, "sqlite3 + schema OK"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("sqlite", False, f"{type(exc).__name__}: {exc}"))

    try:
        import sqlalchemy
        from .integrations.sqlalchemy_store import SQLAlchemyStore

        probe_store = SQLAlchemyStore("sqlite://")
        probe_store.list_tasks()
        probe_store.close()
        checks.append(_check("optional:sqlalchemy", True, f"SQLAlchemy {sqlalchemy.__version__} OK"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("optional:sqlalchemy", True, f"未启用（可选）：{type(exc).__name__}"))

    for module in ("yaml", "PIL"):
        try:
            __import__(module)
            checks.append(_check(f"optional:{module}", True, "已安装（可选）"))
        except ImportError:
            checks.append(_check(f"optional:{module}", True, "未安装（可选；仅部分 YAML/图片校验需要）"))

    try:
        import langgraph  # noqa: F401
        checks.append(_check("optional:langgraph", True, "已安装（supervisor 可用）"))
    except ImportError:
        checks.append(_check("optional:langgraph", True, "未安装（supervisor 不可用；simple 仍可用）"))

    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        checks.append(_check("optional:api", True, "FastAPI/uvicorn 已安装（serve 可用）"))
    except ImportError:
        checks.append(_check("optional:api", True, "未安装（serve 不可用；CLI 仍可用）"))

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: F401
        checks.append(_check("optional:sqlite-checkpointer", True, "已安装（原生 durable interrupt 可用）"))
    except ImportError:
        checks.append(_check("optional:sqlite-checkpointer", True, "未安装（supervisor 回退任务 checkpoint）"))

    from .llm import llm_configured
    checks.append(_check(
        "optional:llm",
        True,
        "已配置（--creative 可用）" if llm_configured() else "未配置（--creative 不可用；默认确定性模式）",
    ))

    return {
        "ok": all(item["ok"] for item in checks),
        "version": __version__,
        "checks": checks,
    }
