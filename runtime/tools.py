"""工具箱 → 运行时工具桥接。

把现有 7 个 Agent 的确定性脚本包装成可调用工具：
- 只允许白名单脚本，不执行任意 shell；
- 参数以列表传递，避免注入；
- 脚本仍是真源，runtime 只负责调用与收集结果。
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ToolSpec:
    name: str
    script: str
    description: str
    owner_agent: str
    network_required: bool = False
    default_timeout: int = 180

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "shaduola_parser",
        "Agents/01_Market_Research_Agent/scripts/shaduola_parser.py",
        "类目导出 CSV → 标准化 JSON",
        "market_research",
    ),
    ToolSpec(
        "market_metrics",
        "Agents/01_Market_Research_Agent/scripts/market_metrics.py",
        "容量/集中度/价格带/配置交叉表",
        "market_research",
    ),
    ToolSpec(
        "sku_pricing",
        "Agents/02_Product_Strategy_Agent/scripts/sku_pricing.py",
        "净利率/盈亏价/目标价/券余量矩阵",
        "product_strategy",
    ),
    ToolSpec(
        "title_lint",
        "Agents/03_Listing_Creative_Agent/scripts/title_lint.py",
        "标题字符/禁用词/堆砌检测",
        "listing_creative",
    ),
    ToolSpec(
        "spec_consistency",
        "Agents/03_Listing_Creative_Agent/scripts/spec_consistency.py",
        "参数溯源一致性校验",
        "listing_creative",
    ),
    ToolSpec(
        "check_main_image",
        "Agents/04_Product_Image_Agent/scripts/check_main_image.py",
        "像素级图片合规校验",
        "product_image",
    ),
    ToolSpec(
        "render_openai",
        "Agents/04_Product_Image_Agent/scripts/render_openai.py",
        "单张图片渲染（OpenAI 兼容 API）",
        "product_image",
        network_required=True,
    ),
    ToolSpec(
        "render_prompt_pack",
        "Agents/04_Product_Image_Agent/scripts/render_prompt_pack.py",
        "批量图包渲染（跳过 layout/photo_required）",
        "product_image",
        network_required=True,
    ),
    ToolSpec(
        "video_timing",
        "Agents/05_Product_Video_Agent/scripts/video_timing.py",
        "视频时长/字幕行长校验",
        "product_video",
    ),
    ToolSpec(
        "ad_metrics",
        "Agents/06_Advertising_Optimization_Agent/scripts/ad_metrics.py",
        "广告盈亏线/可承受 CPC/P0-P2 分级",
        "advertising",
    ),
    ToolSpec(
        "review_stats",
        "Agents/07_Review_Analysis_Agent/scripts/review_stats.py",
        "评论归因聚合/可修复率/卖点排行",
        "review_analysis",
    ),
)


@dataclass(frozen=True)
class ToolResult:
    name: str
    returncode: int
    stdout: str
    stderr: str
    command: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "command": list(self.command),
        }

    def json(self) -> Any:
        """尝试把 stdout 解析为 JSON；失败抛 ValueError。"""
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{self.name} 的输出不是有效 JSON：{exc}") from exc


class ToolRegistry:
    """工具白名单：运行时只能调用这里注册的脚本。"""

    def __init__(self, tools: tuple[ToolSpec, ...] = TOOLS) -> None:
        self._tools: dict[str, ToolSpec] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"工具重复注册：{tool.name}")
            self._tools[tool.name] = tool

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def all(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools.values())

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"未注册的工具：{name}（可用：{', '.join(self._tools)}）") from None

    def for_agent(self, agent_key: str) -> tuple[ToolSpec, ...]:
        return tuple(tool for tool in self._tools.values() if tool.owner_agent == agent_key)

    def run(
        self,
        name: str,
        args: list[str] | None = None,
        *,
        timeout: int | None = None,
    ) -> ToolResult:
        tool = self.get(name)
        script = (PROJECT_ROOT / tool.script).resolve()
        if not script.is_file():
            raise FileNotFoundError(f"工具脚本不存在：{script}")
        command = (sys.executable, str(script), *(args or []))
        try:
            proc = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or tool.default_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult(
                name=name,
                returncode=124,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=f"超时（{timeout or tool.default_timeout}s）",
                command=command,
            )
        return ToolResult(
            name=name,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=command,
        )


DEFAULT_TOOL_REGISTRY = ToolRegistry()
