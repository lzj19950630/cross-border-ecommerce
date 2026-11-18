"""API 入口（兼容旧用法）。

推荐在 cross-border-ecommerce-api/ 目录下用 uvicorn 启动：
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

本文件保留为兼容入口，等价于 app/main.py：
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    python main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app  # noqa: E402,F401

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
