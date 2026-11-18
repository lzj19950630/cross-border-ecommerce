#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""04 渲染链路自测（不需要真实 API Key）。

启动一个本地 mock 图片接口，验证：
  1. render_openai.py 的 /images/generations 路径
  2. render_openai.py 的 /images/edits 参考图路径
  3. render_prompt_pack.py 的图位筛选（layout / photo_required 跳过）
  4. 批量适配器输出 render_manifest.json

用法：
    python tests/test_render.py
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
AGENT_DIR = TESTS_DIR.parent
SCRIPTS_DIR = AGENT_DIR / "scripts"
RENDER = SCRIPTS_DIR / "render_openai.py"
PACK_RENDER = SCRIPTS_DIR / "render_prompt_pack.py"
SAMPLE_PACK = TESTS_DIR / "sample_prompt_pack.yaml"
REFERENCE = TESTS_DIR / "ml_pass.png"

# 1x1 透明 PNG
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/"
    "lK3Q6wAAAABJRU5ErkJggg=="
)

REQUESTS: list[tuple[str, str]] = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: ANN002
        pass

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        REQUESTS.append((self.path, self.headers.get("Content-Type", "")))
        payload = json.dumps({"data": [{"b64_json": PNG_B64}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )


def assert_true(condition: bool, message: str, failures: list[str]) -> None:
    if condition:
        print(f"  PASS  {message}")
    else:
        print(f"  FAIL  {message}")
        failures.append(message)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    env = os.environ.copy()
    env.update(IMAGE_API_BASE=base, IMAGE_MODEL="mock-model", IMAGE_API_KEY="mock-key")
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        print("[1] render_openai.py /images/generations")
        out1 = root / "single"
        proc = run([
            sys.executable, str(RENDER), "--mode", "image", "--prompt", "test",
            "--job-dir", str(out1), "--asset-type", "main", "--json",
        ], env)
        data = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
        assert_true(proc.returncode == 0, "exit 0", failures)
        assert_true(data.get("status") == "ok", "status=ok", failures)
        assert_true(len(list((out1 / "main").glob("*.png"))) == 1, "生成 1 张图", failures)

        print("[2] render_openai.py /images/edits（参考图）")
        out2 = root / "edit"
        proc = run([
            sys.executable, str(RENDER), "--mode", "image", "--prompt", "test",
            "--image", str(REFERENCE), "--job-dir", str(out2),
            "--asset-type", "detail", "--json",
        ], env)
        data = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
        assert_true(proc.returncode == 0, "exit 0", failures)
        assert_true(data.get("endpoint") == "images/edits", "走 edits 端点", failures)
        assert_true(len(list((out2 / "detail").glob("*.png"))) == 1, "生成 1 张图", failures)

        print("[3] render_prompt_pack.py 图位筛选 + manifest")
        out3 = root / "pack"
        proc = run([
            sys.executable, str(PACK_RENDER), str(SAMPLE_PACK),
            "--render-mode", "image", "--reference", str(REFERENCE),
            "--platform", "shopee", "--job-dir", str(out3), "--json",
        ], env)
        data = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
        slots = {s["slot"]: s for s in data.get("slots", [])}
        skipped = {s["slot"]: s["reason"] for s in data.get("skipped", [])}
        assert_true(set(slots) == {1, 2, 4}, "只渲染 slot 1/2/4", failures)
        assert_true(skipped.get(3) == "layout", "slot 3 跳过（layout）", failures)
        assert_true(skipped.get(8) == "photo_required", "slot 8 跳过（photo_required）", failures)
        assert_true((out3 / "render_manifest.json").is_file(), "manifest 已落盘", failures)

        print("[4] 批量模型是否把 overlay_copy 送进 Prompt")
        prompt_files = list((out3 / "prompts").glob("*.txt"))
        joined = "\n".join(p.read_text(encoding="utf-8") for p in prompt_files)
        assert_true("Carga rápida 45W" not in joined, "overlay_copy 未进入出图 Prompt", failures)

    print("[5] 请求端点")
    endpoints = {path for path, _ in REQUESTS}
    assert_true("/v1/images/generations" in endpoints, "调用过 generations", failures)
    assert_true("/v1/images/edits" in endpoints, "调用过 edits", failures)

    server.shutdown()
    if failures:
        print(f"\n失败 {len(failures)} 项")
        raise SystemExit(1)
    print("\n全部通过 ✅")


if __name__ == "__main__":
    main()
