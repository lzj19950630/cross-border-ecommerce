#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量渲染 04 的输出图包（output_image_prompt_pack.yaml / .json）。

三条硬规则（与 04 SKILL.md 一致）：
    1. 只渲染 AI 可生成的图位 —— type=layout（设计排版）与 type=photo_required（必须实拍）
       一律跳过，不交给图像模型。
    2. 图内文字（overlay_copy）不送入图像模型 —— 仍由设计工具后期叠字，
       避免 PT-BR 变音符号（ã / ç / õ）被画错。
    3. 出图后跑像素校验 —— 默认只校验 slot 1 主图（其余图位背景/构图本来就不同，
       用主图标准检查会产生假失败）；需要全查时加 --check-all。

依赖：
    - 本脚本自身只用标准库
    - 读 .yaml 需要 PyYAML；没有 PyYAML 时请把图包另存为 .json
    - 像素校验需要 Pillow（check_main_image.py 的依赖）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

RENDER_SCRIPT = Path(__file__).with_name("render_openai.py")
CHECK_SCRIPT = Path(__file__).with_name("check_main_image.py")
CHECK_PLATFORMS = {"shopee", "mercadolivre", "amazon"}
PLATFORM_ALIASES = {
    "ml": "mercadolivre",
    "mercado-livre": "mercadolivre",
    "mercado_libre": "mercadolivre",
    "mercado livre": "mercadolivre",
}
SKIP_TYPES = {"layout", "photo_required"}
DEFAULT_SIZE = "1024x1024"


def fail(message: str, exit_code: int = 1) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def slugify(value: str, fallback: str = "product") -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return ascii_text or fallback


def normalize_platform(value: str | None) -> str:
    text = (value or "").strip().lower()
    return PLATFORM_ALIASES.get(text, text)


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "是"}
    if value is None:
        return default
    return bool(value)


def slot_number(prompt: dict[str, Any], index: int) -> int:
    try:
        return int(prompt.get("slot", index))
    except (TypeError, ValueError):
        return index


def skip_reason(prompt: dict[str, Any]) -> str | None:
    kind = str(prompt.get("type") or "ai").strip().lower()
    if kind in SKIP_TYPES:
        return kind
    if prompt.get("renderable") is False:
        return "renderable=false"
    if not str(prompt.get("prompt") or "").strip():
        return "prompt 为空"
    return None


def reference_needed(prompt: dict[str, Any], slot: int) -> bool:
    if "reference_image_needed" in prompt:
        return as_bool(prompt.get("reference_image_needed"), default=False)
    return slot in {1, 2, 4, 5, 6}


def asset_type_for(prompt: dict[str, Any], slot: int) -> str:
    explicit = str(prompt.get("asset_type") or "").strip().lower()
    if explicit in {"main", "detail", "extras", "custom", "angle-sheet"}:
        return explicit
    return "main" if slot == 1 else "detail"


def resolve_size(prompt: dict[str, Any], override: str | None) -> str:
    for candidate in (override, prompt.get("recommended_size"), DEFAULT_SIZE):
        text = str(candidate or "").strip()
        if re.fullmatch(r"\d{2,5}x\d{2,5}", text):
            return text
    return DEFAULT_SIZE


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        fail(f"无法写入文件 {path}：{exc}")


def load_pack(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"图包文件不存在：{path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"无法读取 JSON 图包：{exc}")
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError:
            fail(
                "读取 YAML 需要 PyYAML（可选依赖）。\n"
                "  安装：pip install pyyaml\n"
                "  或把图包另存为 .json 后再跑。"
            )
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:  # type: ignore[attr-defined]
            fail(f"无法读取 YAML 图包：{exc}")
    else:
        fail("图包只支持 .yaml / .yml / .json。")

    if not isinstance(data, dict):
        fail("图包顶层必须是对象（包含 meta / prompts）。")
    return data


def run_renderer(cmd: list[str]) -> tuple[int, dict[str, Any] | None, str, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    data: dict[str, Any] | None = None
    try:
        parsed = json.loads(proc.stdout.strip())
        if isinstance(parsed, dict):
            data = parsed
    except json.JSONDecodeError:
        data = None
    return proc.returncode, data, proc.stdout, proc.stderr


def run_check(image: Path, platform: str, fix: bool) -> dict[str, Any] | None:
    if not CHECK_SCRIPT.is_file():
        return None
    cmd = [sys.executable, str(CHECK_SCRIPT), str(image), "--platform", platform, "--json"]
    fixed_path = image.with_name(f"{image.stem}.fixed{image.suffix}")
    if fix:
        cmd.extend(["--fix", str(fixed_path)])
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        parsed = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return {
            "image": str(image),
            "ok": False,
            "error": f"校验脚本输出不可解析：{proc.stdout[:300]}{proc.stderr[:300]}",
        }
    if isinstance(parsed, dict):
        parsed["image"] = str(image)
        if fix:
            parsed["fixed_path"] = str(fixed_path)
        return parsed
    return None


def print_list(rows: list[dict[str, Any]]) -> None:
    print(f"{'slot':<5} {'图位':<16} {'类型':<15} {'可渲染':<6} 说明")
    for row in rows:
        print(
            f"{row['slot']:<5} {str(row['role'])[:16]:<16} {row['type']:<15} "
            f"{'yes' if row['renderable'] else 'no':<6} {row['reason'] or ''}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量渲染 04 图包（跳过 layout / photo_required，出图后校验主图）"
    )
    parser.add_argument("pack", help="output_image_prompt_pack.yaml 或 .json")
    parser.add_argument("--platform", help="覆盖 meta.platform（shopee / mercadolivre / amazon）")
    parser.add_argument("--job-dir", help="输出根目录；默认 generated-images/<slug>-pack-<时间>")
    parser.add_argument("--reference", help="产品参考图；用于锁产品身份（/images/edits）")
    parser.add_argument("--allow-no-reference", action="store_true", help="允许参考图缺失时继续（不推荐）")
    parser.add_argument("--only", help="只渲染指定 slot，逗号分隔，例如 1,2,4")
    parser.add_argument("--list", action="store_true", help="只列出图位与可渲染状态，不执行")
    parser.add_argument("--dry-run", action="store_true", help="只打印执行计划，不调用渲染器（仍会落盘 Prompt 与 manifest）")
    parser.add_argument(
        "--render-mode", choices=("auto", "prompt", "image"), default="auto",
        help="透传给 render_openai.py：auto 无配置时降级为 Prompt；prompt 只输出；image 强制出图",
    )
    parser.add_argument("--no-check", dest="check", action="store_false", help="出图后不跑像素校验")
    parser.add_argument("--check-all", action="store_true", help="校验全部 1:1 出图（默认只校验 slot 1）")
    parser.add_argument("--fix", action="store_true", help="校验失败时用 check_main_image.py --fix 生成修复副本")
    parser.add_argument("--size", help="覆盖所有图位的尺寸，例如 1024x1024 / 1200x1200")
    parser.add_argument("--model", help="透传给 render_openai.py，覆盖环境变量里的模型名")
    parser.add_argument("--env-file", help="透传给 render_openai.py 的 .env 路径")
    parser.add_argument("--quality", help="图片质量参数，例如 low / medium / high")
    parser.add_argument("--n", type=int, default=1, help="每个图位生成张数，默认 1")
    parser.add_argument("--format", choices=("png", "jpeg", "webp"), help="图片格式")
    parser.add_argument("--timeout", type=int, default=180, help="单张请求超时秒数")
    parser.add_argument("--json", action="store_true", help="输出完整 manifest JSON")
    args = parser.parse_args()
    if args.n < 1:
        fail("--n 必须大于等于 1。")
    return args


def main() -> None:
    args = parse_args()
    pack = load_pack(Path(args.pack))
    meta = pack.get("meta") if isinstance(pack.get("meta"), dict) else {}
    render_cfg = pack.get("render") if isinstance(pack.get("render"), dict) else {}
    platform = normalize_platform(args.platform or meta.get("platform") or render_cfg.get("platform"))

    prompts_raw = pack.get("prompts")
    if not isinstance(prompts_raw, list) or not prompts_raw:
        fail("图包缺少 prompts 列表。")

    only: set[int] = set()
    if args.only:
        for part in args.only.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                only.add(int(part))
            except ValueError:
                fail(f"--only 里有非法 slot：{part}")

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(prompts_raw, start=1):
        if not isinstance(item, dict):
            fail(f"prompts 第 {index} 项不是对象。")
        slot = slot_number(item, index)
        reason = skip_reason(item)
        if reason is None and only and slot not in only:
            reason = "未在 --only 中"
        rows.append({
            "slot": slot,
            "role": str(item.get("role") or f"图位 {slot}"),
            "type": str(item.get("type") or "ai"),
            "renderable": reason is None,
            "reason": reason,
            "prompt": item,
        })

    if args.list:
        print_list(rows)
        return

    selected = [row for row in rows if row["renderable"]]
    if not selected:
        fail("没有可渲染的图位（prompt 为空，或全部是 layout / photo_required）。")

    reference = (
        args.reference
        or render_cfg.get("reference_image")
        or (pack.get("angle_sheet") if isinstance(pack.get("angle_sheet"), dict) else {}).get("reference_image")
    )
    if reference:
        ref_path = Path(str(reference))
        if not ref_path.is_file():
            fail(f"参考图不存在：{ref_path}")
        reference = str(ref_path)

    warnings: list[str] = []
    ref_required = [row["slot"] for row in selected if reference_needed(row["prompt"], row["slot"])]
    if ref_required and not reference:
        if not args.allow_no_reference:
            fail(
                "[INPUT_MISSING] 以下图位需要产品参考图（reference_image_needed=true）："
                + ", ".join(str(s) for s in ref_required)
                + "。请用 --reference 指定产品图；或显式加 --allow-no-reference（不推荐）。"
            )
        warnings.append(f"参考图缺失，已允许继续：slot {ref_required}。产品身份可能跑偏。")

    style_lock = pack.get("campaign_style_lock") if isinstance(pack.get("campaign_style_lock"), dict) else {}
    if len(selected) > 1 and as_bool(style_lock.get("enabled"), True):
        if not str(style_lock.get("style_lock_prompt") or "").strip():
            warnings.append("campaign_style_lock.style_lock_prompt 为空：多图一致性可能不足。")
    if pack.get("overlay_copy"):
        warnings.append("overlay_copy 不会送进图像模型；图内文字仍由设计工具后期叠字。")

    render_mode = args.render_mode
    if render_mode == "auto":
        pack_mode = str(render_cfg.get("mode") or "").strip().lower()
        if pack_mode in {"auto", "prompt", "image"}:
            render_mode = pack_mode
    size_override = args.size or str(render_cfg.get("size_override") or "").strip() or None
    do_check = args.check and as_bool(render_cfg.get("check_main_image"), default=True)
    check_all = args.check_all or as_bool(render_cfg.get("check_all"), default=False)

    product_name = str(meta.get("product_name") or "product")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    if args.job_dir:
        job_dir = Path(args.job_dir)
    elif str(render_cfg.get("job_dir") or "").strip():
        job_dir = Path(str(render_cfg.get("job_dir")).strip())
    else:
        job_dir = Path("generated-images") / f"{slugify(product_name)}-pack-{timestamp}"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "prompts").mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "tool": "render_prompt_pack",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pack": str(Path(args.pack)),
        "platform": platform or None,
        "job_dir": str(job_dir),
        "render_mode": render_mode,
        "reference_image": reference,
        "slots": [],
        "skipped": [],
        "warnings": warnings,
    }
    check_failed = False
    errors = False

    for row in selected:
        prompt = row["prompt"]
        slot = row["slot"]
        role = row["role"]
        text = str(prompt.get("prompt") or "").strip()
        negative = str(prompt.get("negative_prompt") or "").strip()
        asset_type = asset_type_for(prompt, slot)
        size = resolve_size(prompt, size_override)
        needs_ref = reference_needed(prompt, slot)

        # 适配器直接合成最终 Prompt：保证没有 API 时落盘的 Prompt 也含否定清单。
        # 因此不再把 negative 单独传给 render_openai.py，避免二次合并。
        final_prompt = text
        if negative:
            final_prompt = (
                text.rstrip()
                + "\n\nAvoid / negative constraints (must not appear):\n"
                + negative
            )
        prompt_file = job_dir / "prompts" / f"slot-{slot:02d}-{asset_type}-{slugify(role, 'image')}.txt"
        write_text(prompt_file, final_prompt + "\n")
        if negative:
            write_text(job_dir / "prompts" / f"slot-{slot:02d}-negative.txt", negative + "\n")

        cmd = [
            sys.executable, str(RENDER_SCRIPT),
            "--prompt-file", str(prompt_file),
            "--job-dir", str(job_dir),
            "--asset-type", asset_type,
            "--size", size,
            "--mode", render_mode,
            "--json",
            "--no-save-prompt",
            "--timeout", str(args.timeout),
        ]
        if reference and needs_ref:
            cmd.extend(["--image", reference])
        if args.model:
            cmd.extend(["--model", args.model])
        if args.env_file:
            cmd.extend(["--env-file", args.env_file])
        if args.quality:
            cmd.extend(["--quality", args.quality])
        if args.n != 1:
            cmd.extend(["--n", str(args.n)])
        if args.format:
            cmd.extend(["--format", args.format])

        entry: dict[str, Any] = {
            "slot": slot,
            "role": role,
            "asset_type": asset_type,
            "size": size,
            "reference": reference if needs_ref and reference else None,
            "status": "",
            "images": [],
            "checks": [],
            "warnings": [],
        }

        if args.dry_run:
            entry["status"] = "planned"
            entry["command"] = cmd
        else:
            code, data, stdout, stderr = run_renderer(cmd)
            if code != 0 or data is None:
                entry["status"] = "error"
                entry["error"] = (stderr or stdout)[-1500:]
                errors = True
            else:
                entry["render_status"] = data.get("status")
                entry["images"] = data.get("images") or []
                entry["prompt_saved"] = data.get("prompt_saved")
                entry["status"] = "rendered" if data.get("status") == "ok" else "prompt_only"
                if data.get("status") != "ok":
                    entry["warnings"].append("未配置图片 API，已只输出 Prompt。")
                if entry["images"] and do_check and platform in CHECK_PLATFORMS:
                    aspect = str(prompt.get("aspect_ratio") or "1:1").strip()
                    if aspect == "1:1" and (slot == 1 or check_all):
                        for image in entry["images"]:
                            report = run_check(Path(image), platform, args.fix)
                            if report is None:
                                entry["warnings"].append("未找到 check_main_image.py，跳过像素校验。")
                                break
                            entry["checks"].append(report)
                            if not (report.get("ok") or report.get("after_fix_ok")):
                                check_failed = True
        manifest["slots"].append(entry)

    for row in rows:
        if not row["renderable"]:
            manifest["skipped"].append({
                "slot": row["slot"], "role": row["role"],
                "type": row["type"], "reason": row["reason"],
            })

    manifest["check_failed"] = check_failed
    manifest["errors"] = errors
    write_text(job_dir / "render_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"任务目录：{job_dir}")
        print(f"平台：{platform or '(未指定)'}")
        for entry in manifest["slots"]:
            suffix = f"（{len(entry['images'])} 张）" if entry["images"] else ""
            print(f"  slot {entry['slot']} · {entry['role']} → {entry['status']}{suffix}")
            for check in entry["checks"]:
                ok = check.get("ok") or check.get("after_fix_ok")
                print(f"      校验：{'✅ 通过' if ok else '❌ 未通过'} · {check.get('image')}")
            if entry.get("error"):
                print(f"      错误：{entry['error'][:300]}")
        if manifest["skipped"]:
            print("跳过：")
            for item in manifest["skipped"]:
                print(f"  slot {item['slot']} · {item['role']} → {item['reason']}")
        if warnings:
            print("警告：")
            for message in warnings:
                print(f"  - {message}")
        print(f"Manifest：{job_dir / 'render_manifest.json'}")

    sys.exit(1 if (errors or check_failed) else 0)


if __name__ == "__main__":
    main()
