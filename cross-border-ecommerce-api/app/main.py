"""uvicorn 入口（在 cross-border-ecommerce-api/ 目录下启动）：

    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

装配参数优先读环境变量，其次读 .env 文件（仓库根目录 / 本目录），
对应 python -m runtime serve 的常用参数：
    RUNTIME_ENGINE=supervisor          # simple | supervisor
    RUNTIME_EXECUTOR=langgraph         # auto | sequential | langgraph
    RUNTIME_CHECKPOINTER=sqlite        # auto | memory | sqlite
    RUNTIME_CHECKPOINT_DB=...          # 默认 <仓库根>/.runtime/checkpoints.db
    RUNTIME_CREATIVE=1                 # 启用 LLM 创意层

默认数据目录锚定到仓库根目录的 .runtime/，即使从本目录启动也与
python -m runtime serve 使用同一份数据。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _load_env_files() -> None:
    """加载 .env（真实环境变量优先，不覆盖）。"""
    try:
        from dotenv import load_dotenv
    except ImportError:  # 无 python-dotenv 时用最小解析器
        load_dotenv = None
    for env_file in (REPO_ROOT / ".env", API_DIR / ".env"):
        if not env_file.is_file():
            continue
        if load_dotenv is not None:
            load_dotenv(env_file, override=False)
            continue
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env_files()

# 默认状态库锚定到仓库根目录 .runtime/runtime.db（env 显式设置时优先）
os.environ.setdefault("RUNTIME_DB", str(REPO_ROOT / ".runtime" / "runtime.db"))

from runtime.api import create_app  # noqa: E402

app = create_app(
    engine_type=os.environ.get("RUNTIME_ENGINE", "simple"),
    executor=os.environ.get("RUNTIME_EXECUTOR", "auto"),
    checkpointer=os.environ.get("RUNTIME_CHECKPOINTER", "auto"),
    checkpoint_db=os.environ.get(
        "RUNTIME_CHECKPOINT_DB", str(REPO_ROOT / ".runtime" / "checkpoints.db")
    ),
    creative=os.environ.get("RUNTIME_CREATIVE", "").lower() in {"1", "true", "yes", "on"},
)
