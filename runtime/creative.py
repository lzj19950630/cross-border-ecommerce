"""LLM 创意层：在确定性 Runner 之上生成标题/详情/图片 Prompt/脚本/修补建议。

原则：
- 默认关闭；需要显式注入 LLMClient；
- LLM 失败 → 回退确定性结果并记录消息，不影响任务继续；
- LLM 产出仍要过确定性校验（title_lint / spec_consistency / video_timing）；
- 证据块不把 LLM 输出当证据。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from .agent_runners import (
    AgentContext,
    AgentResult,
    DEFAULT_RUNNER_REGISTRY,
    ListingCreativeRunner,
    ProductImageRunner,
    ProductVideoRunner,
    ReviewAnalysisRunner,
    RunnerRegistry,
)
from .delivery import artifact_compliance
from .llm import LLMClient, LLMError

MergeFn = Callable[[Any, AgentResult, dict[str, Any], AgentContext], AgentResult]
PromptFn = Callable[[AgentContext, AgentResult], str]


def _context_json(context: AgentContext, result: AgentResult) -> str:
    payload = {
        "request": context.request,
        "inputs": context.inputs,
        "upstream_artifacts": context.upstream_artifacts,
        "deterministic_result": result.artifact,
    }
    return json.dumps(payload, ensure_ascii=False)[:6000]


class LLMCreativeRunner:
    def __init__(
        self,
        base,
        llm: LLMClient | Callable[[AgentContext], LLMClient],
        system: str,
        user: PromptFn,
        merge: MergeFn,
        max_retries: int = 2,
    ) -> None:
        self.base = base
        self.llm = llm
        self.system = system
        self.user = user
        self.merge = merge
        self.max_retries = max_retries

    def run(self, context: AgentContext) -> AgentResult:
        base_result = self.base.run(context)
        if base_result.status != "ok":
            return base_result

        forbidden = context.inputs.get("forbidden_words") if isinstance(context.inputs, dict) else None
        words = [str(item) for item in forbidden] if isinstance(forbidden, list) else []
        feedback = ""
        last_result = base_result

        llm = self.llm(context) if callable(self.llm) else self.llm
        for attempt in range(self.max_retries + 1):
            try:
                data = llm.complete_json(
                    self.system, self.user(context, base_result) + feedback
                )
            except LLMError as exc:
                if attempt == 0:
                    base_result.messages.append(f"LLM 创意层失败，保留确定性结果：{exc}")
                    return base_result
                return last_result

            result = self.merge(self.base, base_result, data, context)
            result.retries = attempt
            if result.status == "ok":
                report = artifact_compliance(result.artifact, words)
                result.artifact["compliance_report"] = report
                if report["passed"]:
                    return result
                result.status = "failed"
                result.error = "合规硬阻断：" + "；".join(report["violations"])
                result.messages.append(result.error)

            last_result = result
            feedback = (
                "\n\n上一轮校验失败：\n"
                + (result.error or "未通过校验")
                + "\n请修正后重新输出 JSON。"
            )
        return last_result


def _failed(base: AgentResult, error: str) -> AgentResult:
    return AgentResult(
        agent=base.agent,
        status="failed",
        artifact=base.artifact,
        evidence=base.evidence,
        envelope=base.envelope,
        messages=base.messages + [f"LLM 创意层校验失败：{error}"],
        error=error,
    )


LISTING_SYSTEM = """你是 Shopee 巴西站 Listing 专家。基于输入生成 PT-BR 标题、详情页、次级卖点。
只输出 JSON：{"title": "...", "description": "...", "secondary_points": ["..."]}
要求：
- 标题用巴西葡语，<= 120 字符，主关键词前置；
- 不写促销词/绝对化用语/未授权品牌；
- 所有参数必须来自输入，不得编造；
- 详情页用简短段落，不写无法举证的承诺。"""


def _listing_user(context: AgentContext, result: AgentResult) -> str:
    return _context_json(context, result)


def _merge_listing(base_runner: Any, base: AgentResult, data: dict[str, Any], context: AgentContext) -> AgentResult:
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    secondary = data.get("secondary_points")
    if not title or not description:
        return _failed(base, "LLM 未返回 title/description")
    if not isinstance(secondary, list):
        secondary = []

    tools = getattr(base_runner, "tools", None)
    if tools is None:
        return _failed(base, "内部错误：base runner 没有 tools")

    platform = str(context.inputs.get("platform") or "shopee")
    lint = tools.run("title_lint", [title, "--platform", platform, "--json"])
    if not lint.ok:
        return _failed(base, lint.stderr or lint.stdout)
    lint_data = lint.json()
    if not lint_data.get("ok"):
        return _failed(base, "LLM 标题未通过平台字符校验")

    spec_path = str(base.artifact.get("spec_file") or "")
    if spec_path:
        spec = tools.run("spec_consistency", ["--spec", spec_path, "--title", title, "--json"])
        if not spec.ok:
            return _failed(base, spec.stderr or spec.stdout)
        spec_data = spec.json()
        if not spec_data.get("ok"):
            return _failed(base, "LLM 标题参数无法溯源到 spec_table")
    else:
        spec_data = {}

    artifact = dict(base.artifact)
    artifact.update({
        "title_final": title,
        "description": description,
        "secondary_points": [str(x) for x in secondary],
        "creative_source": "llm",
        "llm_title_lint": lint_data,
        "llm_spec_consistency": spec_data,
    })
    return AgentResult(
        agent=base.agent,
        status="ok",
        artifact=artifact,
        evidence=base.evidence,
        envelope=base.envelope,
        messages=base.messages + [f"LLM 创意层：标题 {lint_data.get('chars')}/{lint_data.get('limit')} 字符"],
    )


IMAGE_SYSTEM = """你是跨境电商商品图策划。基于输入生成 9 图规划与逐图英文出图 Prompt。
只输出 JSON：{"image_plan": [{"slot":1,"role":"主图","message":"..."}], "prompts": [{"slot":1,"prompt":"..."}]}
要求：
- 9 个图位：主图/核心卖点/参数/场景A/场景B/细节/尺寸对比/包装清单/售后；
- Prompt 用英文，包含产品身份、构图、光影、平台参数、否定清单；
- 图内文字不要写进 Prompt（后期叠字）；
- 包装清单图标记必须实拍。"""


def _image_user(context: AgentContext, result: AgentResult) -> str:
    return _context_json(context, result)


def _merge_image(_base_runner: Any, base: AgentResult, data: dict[str, Any], _context: AgentContext) -> AgentResult:
    plan = data.get("image_plan")
    prompts = data.get("prompts")
    if not isinstance(plan, list) or not plan:
        return _failed(base, "LLM 未返回 image_plan")
    if not isinstance(prompts, list) or not prompts:
        return _failed(base, "LLM 未返回 prompts")
    artifact = dict(base.artifact)
    artifact.update({
        "image_plan": plan,
        "prompts": prompts,
        "creative_source": "llm",
    })
    return AgentResult(
        agent=base.agent,
        status="ok",
        artifact=artifact,
        evidence=base.evidence,
        envelope=base.envelope,
        messages=base.messages + [f"LLM 创意层：{len(plan)} 个图位 / {len(prompts)} 条 Prompt"],
    )


VIDEO_SYSTEM = """你是巴西站短视频编导。基于输入生成 15s/30s PT-BR 配音稿、分镜、字幕。
只输出 JSON：{"script": ["台词1","台词2"], "storyboard": [{"shot":1,"visual":"..."}], "subtitles": "SRT 或逐句字幕"}
要求：
- 台词用巴西葡语，数字必须来自输入；
- 30s 约 65 词，15s 约 30 词；
- 不写无法举证的承诺；
- 第一句是钩子，不要"大家好"。"""


def _video_user(context: AgentContext, result: AgentResult) -> str:
    return _context_json(context, result)


def _merge_video(base_runner: Any, base: AgentResult, data: dict[str, Any], _context: AgentContext) -> AgentResult:
    script = data.get("script")
    if isinstance(script, str):
        script_lines = [line for line in script.splitlines() if line.strip()]
    elif isinstance(script, list):
        script_lines = [str(x) for x in script if str(x).strip()]
    else:
        script_lines = []
    if not script_lines:
        return _failed(base, "LLM 未返回有效 script")

    storyboard = data.get("storyboard") or []
    subtitles = data.get("subtitles") or ""
    target = int(float(base.artifact.get("target") or 30))
    tools = getattr(base_runner, "tools", None)
    if tools is None:
        return _failed(base, "内部错误：base runner 没有 tools")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as handle:
            handle.write("\n".join(script_lines))
            tmp_path = Path(handle.name)
        timing = tools.run(
            "video_timing",
            ["--script", str(tmp_path), "--target", str(target), "--format", "json"],
        )
        if not timing.ok:
            return _failed(base, timing.stderr or timing.stdout)
        timing_data = timing.json()
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    artifact = dict(base.artifact)
    artifact.update({
        "llm_script": script_lines,
        "llm_storyboard": storyboard,
        "llm_subtitles": subtitles,
        "llm_timing": timing_data,
        "creative_source": "llm",
    })
    return AgentResult(
        agent=base.agent,
        status="ok",
        artifact=artifact,
        evidence=base.evidence,
        envelope=base.envelope,
        messages=base.messages + [
            f"LLM 创意层：{len(script_lines)} 句台词，时长 {timing_data.get('meta', {}).get('total_seconds')}s"
        ],
    )


REVIEW_SYSTEM = """你是巴西站评论分析专家。基于输入输出差评修补建议与卖点排行。
只输出 JSON：{"patch_suggestions": ["PT-BR 可直接粘贴的修补文案"], "selling_points_ranked": ["卖点"]}
要求：
- 修补文案用 PT-BR，正面陈述、给边界、不说做不到；
- 不编造评论/销量/认证；
- 误解型差评优先补详情页说明。"""


def _review_user(context: AgentContext, result: AgentResult) -> str:
    return _context_json(context, result)


def _merge_review(_base_runner: Any, base: AgentResult, data: dict[str, Any], _context: AgentContext) -> AgentResult:
    patches = data.get("patch_suggestions")
    selling = data.get("selling_points_ranked")
    if not isinstance(patches, list) or not patches:
        return _failed(base, "LLM 未返回 patch_suggestions")
    if not isinstance(selling, list):
        selling = []
    artifact = dict(base.artifact)
    artifact.update({
        "patch_suggestions": [str(x) for x in patches],
        "selling_points_ranked": [str(x) for x in selling],
        "creative_source": "llm",
    })
    return AgentResult(
        agent=base.agent,
        status="ok",
        artifact=artifact,
        evidence=base.evidence,
        envelope=base.envelope,
        messages=base.messages + [f"LLM 创意层：{len(patches)} 条修补建议"],
    )


def build_creative_registry(
    llm: LLMClient | Callable[[AgentContext], LLMClient],
    base: RunnerRegistry = DEFAULT_RUNNER_REGISTRY,
) -> RunnerRegistry:
    runners = {key: base.get(key) for key in base.registered()}
    runners["listing_creative"] = LLMCreativeRunner(
        runners["listing_creative"], llm, LISTING_SYSTEM, _listing_user, _merge_listing
    )
    runners["product_image"] = LLMCreativeRunner(
        runners["product_image"], llm, IMAGE_SYSTEM, _image_user, _merge_image
    )
    runners["product_video"] = LLMCreativeRunner(
        runners["product_video"], llm, VIDEO_SYSTEM, _video_user, _merge_video
    )
    runners["review_analysis"] = LLMCreativeRunner(
        runners["review_analysis"], llm, REVIEW_SYSTEM, _review_user, _merge_review
    )
    return RunnerRegistry(runners)
