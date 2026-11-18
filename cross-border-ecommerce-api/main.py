"""API 入口（方便 IDE / uvicorn 直接启动）。

推荐仍使用：
    python -m runtime serve --port 8000
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from runtime.api import create_app  # noqa: E402

app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
