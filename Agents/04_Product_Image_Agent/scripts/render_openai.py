#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAI 兼容图片渲染执行层（04 Product Image Agent · 可选通道 B）。

设计定位：
    04 的规划与 Prompt 是「大脑」，本脚本只是「画笔」。
    - 不决定画什么（Prompt 来自 04 的 yaml 包或人工填写）
    - 不校验画得对不对（出图后交给 check_main_image.py）
    - 不把图内文字交给模型（PT-BR 变音符号易错，仍由设计工具后期叠字）

只依赖 Python 标准库。配置从环境变量或 .env 读取：
    IMAGE_API_BASE / IMG_BASE_URL / OPENAI_BASE_URL / OPENAI_API_BASE
    IMAGE_MODEL    / IMG_MODEL    / OPENAI_IMAGE_MODEL / OPENAI_MODEL
    IMAGE_API_KEY  / IMG_API_KEY  / OPENAI_API_KEY

用法：
    # 没配置 API：只输出 Prompt（与 04 原流程完全兼容）
    python render_openai.py --mode prompt --prompt "studio packshot ..." --job-dir out

    # 配置 API：直接出图；--image 走 /images/edits 锁产品身份
    python render_openai.py --prompt-file prompt.txt --image product.png \
        --job-dir generated-images/pack-001 --asset-type main --size 1024x1024

    # 批量：读 04 的 output_image_prompt_pack.yaml
    python render_prompt_pack.py ../templates/output_image_prompt_pack.yaml \
        --reference product.png --platform shopee
"""
from __future__ import annotations

import argparse
import base64
import binascii
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# 配置项 → 兼容别名（越靠前优先级越高）
CONFIG_ALIASES: dict[str, tuple[str, ...]] = {
    "base_url": ("IMAGE_API_BASE", "IMG_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE"),
    "model": ("IMAGE_MODEL", "IMG_MODEL", "OPENAI_IMAGE_MODEL", "OPENAI_MODEL"),
    "api_key": ("IMAGE_API_KEY", "IMG_API_KEY", "OPENAI_API_KEY", "API_KEY"),
}

ASSET_DIRS = {
    "angle-sheet": "angle-sheet",
    "main": "main",
    "detail": "detail",
    "extras": "extras",
    "custom": "custom",
}

IMAGE_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def fail(message: str, exit_code: int = 1) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def find_env_file() -> Path | None:
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_env_file(env_file: Path | None) -> None:
    if env_file is None:
        return
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail(f"无法读取 .env 文件：{exc}")
    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            fail(f".env 第 {number} 行格式不正确，应为 KEY=value。")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            fail(f".env 第 {number} 行缺少变量名。")
        if key not in os.environ:
            os.environ[key] = strip_env_value(value)


def get_config(name: str, cli_value: str | None = None) -> str | None:
    if cli_value:
        return cli_value.strip()
    for candidate in CONFIG_ALIASES[name]:
        value = os.environ.get(candidate, "").strip()
        if value:
            return value
    return None


def collect_config(args: argparse.Namespace) -> tuple[dict[str, str], list[str]]:
    config: dict[str, str] = {}
    missing: list[str] = []
    for name in ("base_url", "model", "api_key"):
        value = get_config(name, getattr(args, f"{name}_override", None))
        if value:
            config[name] = value
        else:
            missing.append(name)
    return config, missing


def read_text(prompt: str | None, prompt_file: str | None, label: str) -> str:
    if prompt is not None:
        text = prompt.strip()
    else:
        try:
            text = Path(prompt_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            fail(f"无法读取 {label} 文件：{exc}")
    if not text:
        fail(f"{label} 不能为空。")
    return text


def compose_prompt(prompt: str, negative: str | None) -> str:
    """把 negative prompt 并入正文。

    OpenAI Images API 没有独立的 negative_prompt 字段；与其假装支持，
    不如显式写进 Prompt 末尾，让模型看到否定清单。
    """
    if not negative or not negative.strip():
        return prompt
    return (
        prompt.rstrip()
        + "\n\nAvoid / negative constraints (must not appear):\n"
        + negative.strip()
    )


def slugify(value: str, fallback: str = "prompt") -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return ascii_text or fallback


def save_prompt(prompt: str, args: argparse.Namespace) -> Path | None:
    if args.no_save_prompt or not args.job_dir:
        return None
    prompt_dir = Path(args.job_dir) / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.prompt_file).stem if args.prompt_file else "prompt"
    filename = (
        f"{ASSET_DIRS[args.asset_type]}-{slugify(stem)}-"
        f"{time.strftime('%Y%m%d-%H%M%S')}.txt"
    )
    path = prompt_dir / filename
    try:
        path.write_text(prompt + "\n", encoding="utf-8")
    except OSError as exc:
        fail(f"无法写入 Prompt 文件：{exc}")
    return path


def resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.job_dir:
        return Path(args.job_dir) / ASSET_DIRS[args.asset_type]
    return Path(args.output_dir)


def multipart_field(name: str, value: str, boundary: str) -> bytes:
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
    ).encode("utf-8")


def multipart_file(name: str, path: Path, boundary: str) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        fail(f"无法读取参考图片：{exc}")
    mime = IMAGE_MIME[path.suffix.lower().lstrip(".")]
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    return header + payload + b"\r\n"


def build_multipart(args: argparse.Namespace, prompt: str, model: str) -> tuple[bytes, str]:
    reference = Path(args.image)
    if not reference.is_file():
        fail(f"参考图片不存在：{args.image}")
    suffix = reference.suffix.lower().lstrip(".")
    if suffix not in IMAGE_MIME:
        fail(f"不支持的参考图片格式：.{suffix}（支持 {' / '.join(IMAGE_MIME)}）")

    boundary = f"----04-image-{int(time.time() * 1000)}-{os.urandom(6).hex()}"
    fields: list[bytes] = [
        multipart_field("model", model, boundary),
        multipart_field("prompt", prompt, boundary),
        multipart_field("n", str(args.n), boundary),
        multipart_field("size", args.size, boundary),
    ]
    if args.quality:
        fields.append(multipart_field("quality", args.quality, boundary))
    if args.format:
        fields.append(multipart_field("output_format", args.format, boundary))
    fields.append(multipart_file("image", reference, boundary))
    fields.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(fields), boundary


def post(url: str, api_key: str, body: bytes, content_type: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        fail(f"图片接口返回 HTTP {exc.code}：{detail}")
    except urllib.error.URLError as exc:
        fail(f"无法连接图片接口：{exc.reason}")
    except http.client.RemoteDisconnected:
        fail("图片接口远端断开连接，请稍后重试。")
    except TimeoutError:
        fail(f"图片接口请求超时（{timeout}s）。")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        fail(f"图片接口返回的不是有效 JSON：{raw[:500]}")
    if not isinstance(parsed, dict):
        fail("图片接口返回格式不正确：顶层结果不是对象。")
    return parsed


def suffix_from_url(url: str, fallback: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower().lstrip(".")
    if suffix == "jpeg":
        return "jpg"
    return suffix if suffix in {"png", "jpg", "webp"} else fallback


def save_b64(item: dict[str, Any], output_dir: Path, index: int, fmt: str) -> Path:
    encoded = item.get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        fail("图片结果缺少 b64_json。")
    try:
        payload = base64.b64decode(encoded)
    except (binascii.Error, ValueError) as exc:
        fail(f"无法解码 b64_json 图片：{exc}")
    # 按文件头修正扩展名：部分兼容服务返回 JPEG/WebP，即使请求的是 PNG
    actual = fmt
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        actual = "png"
    elif payload.startswith(b"\xff\xd8\xff"):
        actual = "jpg"
    elif payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        actual = "webp"
    path = output_dir / f"image-{time.strftime('%Y%m%d-%H%M%S')}-{index + 1:02d}.{actual}"
    try:
        path.write_bytes(payload)
    except OSError as exc:
        fail(f"无法写入图片文件：{exc}")
    return path


def save_url(item: dict[str, Any], output_dir: Path, index: int, fmt: str) -> Path:
    url = item.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        fail("图片结果缺少可下载的 url。")
    path = output_dir / (
        f"image-{time.strftime('%Y%m%d-%H%M%S')}-{index + 1:02d}."
        f"{suffix_from_url(url, fmt)}"
    )
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            payload = response.read()
    except urllib.error.URLError as exc:
        fail(f"无法下载图片 URL：{exc.reason}")
    except TimeoutError:
        fail("下载图片超时。")
    try:
        path.write_bytes(payload)
    except OSError as exc:
        fail(f"无法写入图片文件：{exc}")
    return path


def save_images(result: dict[str, Any], output_dir: Path, fmt: str) -> list[Path]:
    data = result.get("data")
    if not isinstance(data, list) or not data:
        fail("图片接口返回中没有 data 图片数组。")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            fail("图片接口返回格式不正确：data 中包含非对象项目。")
        if item.get("b64_json"):
            paths.append(save_b64(item, output_dir, index, fmt))
        elif item.get("url"):
            paths.append(save_url(item, output_dir, index, fmt))
        else:
            fail("图片结果既没有 b64_json，也没有 url。")
    return paths


def print_prompt_only(prompt: str, saved: Path | None, missing: list[str], as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "status": "prompt_only",
            "prompt": prompt,
            "prompt_saved": str(saved) if saved else None,
            "missing_config": missing,
        }, ensure_ascii=False, indent=2))
        return
    if missing:
        print("图片 API 配置不完整，已降级为只输出 Prompt。")
        print("缺少：" + " / ".join(CONFIG_ALIASES[name][0] for name in missing))
        print("补齐后同一命令会自动出图；也可显式用 --mode image 强制。")
    else:
        print("已按 prompt 模式只输出 Prompt。")
    if saved:
        print(f"Prompt 已保存：{saved}")
    print("Prompt：")
    print(prompt)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpenAI 兼容图片接口渲染器（只画，不决策、不校验）"
    )
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="直接传入出图 Prompt")
    prompt_group.add_argument("--prompt-file", help="从文本文件读取出图 Prompt")
    parser.add_argument("--negative-prompt", help="否定清单（会并入 Prompt 正文）")
    parser.add_argument("--negative-file", help="从文本文件读取否定清单")
    parser.add_argument(
        "--mode", choices=("auto", "prompt", "image"), default="auto",
        help="auto：配置齐全则出图，否则只输出 Prompt；prompt：只输出；image：强制出图",
    )
    parser.add_argument("--job-dir", help="单次任务根目录；按 --asset-type 自动归类")
    parser.add_argument("--asset-type", choices=tuple(ASSET_DIRS), default="custom")
    parser.add_argument("--output-dir", default="generated-images", help="未指定 --job-dir 时的输出目录")
    parser.add_argument("--env-file", help="指定 .env；默认从当前目录向上查找")
    parser.add_argument("--base-url", dest="base_url_override", help="覆盖 API 根地址")
    parser.add_argument("--model", dest="model_override", help="覆盖图片模型名")
    parser.add_argument("--size", default="1024x1024", help="图片尺寸，默认 1024x1024")
    parser.add_argument("--quality", help="质量参数，例如 low / medium / high")
    parser.add_argument("--format", choices=("png", "jpeg", "webp"), help="请求的输出格式（不填则由服务端决定）")
    parser.add_argument("--n", type=int, default=1, help="生成张数，默认 1")
    parser.add_argument("--image", help="参考产品图；传入后走 /images/edits")
    parser.add_argument("--timeout", type=int, default=180, help="请求超时秒数，默认 180")
    parser.add_argument("--no-save-prompt", action="store_true", help="不保存 Prompt 副本（供批量适配器使用）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果摘要")
    args = parser.parse_args()
    if args.n < 1:
        fail("--n 必须大于等于 1。")
    if args.negative_prompt and args.negative_file:
        fail("--negative-prompt 与 --negative-file 只能选一个。")
    return args


def main() -> None:
    args = parse_args()
    env_file = Path(args.env_file) if args.env_file else find_env_file()
    load_env_file(env_file)

    prompt = read_text(args.prompt, args.prompt_file, "Prompt")
    negative = read_text(None, args.negative_file, "否定清单") if args.negative_file else args.negative_prompt
    prompt = compose_prompt(prompt, negative)
    if args.image and not Path(args.image).is_file():
        fail(f"参考图片不存在：{args.image}")
    saved = save_prompt(prompt, args)
    config, missing = collect_config(args)

    if args.mode == "image" and missing:
        fail(
            "image 模式需要完整 API 配置，缺少："
            + " / ".join(CONFIG_ALIASES[name][0] for name in missing)
        )
    if args.mode == "prompt" or (args.mode == "auto" and missing):
        print_prompt_only(prompt, saved, missing if args.mode == "auto" else [], args.json)
        return

    base_url = config["base_url"].rstrip("/")
    model = config["model"]
    api_key = config["api_key"]
    fmt = args.format or "png"

    if args.image:
        endpoint = f"{base_url}/images/edits"
        body, boundary = build_multipart(args, prompt, model)
        result = post(endpoint, api_key, body, f"multipart/form-data; boundary={boundary}", args.timeout)
    else:
        endpoint = f"{base_url}/images/generations"
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": args.n,
            "size": args.size,
        }
        if args.quality:
            payload["quality"] = args.quality
        if args.format:
            payload["output_format"] = args.format
        result = post(
            endpoint,
            api_key,
            json.dumps(payload).encode("utf-8"),
            "application/json",
            args.timeout,
        )

    paths = save_images(result, resolve_output_dir(args), fmt)

    if args.json:
        print(json.dumps({
            "status": "ok",
            "images": [str(p) for p in paths],
            "prompt_saved": str(saved) if saved else None,
            "model": model,
            "size": args.size,
            "endpoint": "images/edits" if args.image else "images/generations",
        }, ensure_ascii=False, indent=2))
        return

    print("生成完成：")
    if saved:
        print(f"Prompt 已保存：{saved}")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
