"""Phase 2 Agent Runner：先接通 01 / 02 / 06 三个确定性链路。

每个 Runner 的职责：
    slice + inputs → 调工具 → artifact + evidence（+ 审批信封）
模型/叙事层暂不接 LLM；先把"工具调用 + 产物 + 证据 + 审批"跑通。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from .actions import Action, ApprovalEnvelope, DEFAULT_ACTION_REGISTRY
from .contracts import RiskLevel, Slice
from .evidence import EvidenceBlock, EvidenceItem
from .tools import DEFAULT_TOOL_REGISTRY, ToolRegistry

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_METRICS = (
    "Agents/01_Market_Research_Agent/samples/sample_patinete_eletrico.metrics.json"
)
DEFAULT_SKUS = "Agents/02_Product_Strategy_Agent/examples/sample-skus.csv"
DEFAULT_AD_REPORT = (
    "Agents/06_Advertising_Optimization_Agent/examples/sample-ad-report.csv"
)


def _today() -> str:
    return date.today().isoformat()


def _resolve(path_value: str | None, default: str) -> Path:
    raw = Path(path_value or default)
    return raw if raw.is_absolute() else (PROJECT_ROOT / raw)


@dataclass
class AgentContext:
    thread_id: str
    request: str
    slice: Slice
    tenant_id: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    upstream_artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    agent: str
    status: str  # ok | blocked | failed
    artifact: dict[str, Any] = field(default_factory=dict)
    evidence: EvidenceBlock = field(default_factory=EvidenceBlock)
    envelope: ApprovalEnvelope | None = None
    messages: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: str = ""
    finished_at: str = ""
    elapsed_ms: int = 0
    retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "artifact": self.artifact,
            "evidence": self.evidence.to_dict(),
            "envelope": self.envelope.to_dict() if self.envelope else None,
            "messages": self.messages,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_ms": self.elapsed_ms,
            "retries": self.retries,
        }


class AgentRunner(Protocol):
    def run(self, context: AgentContext) -> AgentResult: ...


class StubRunner:
    """Phase 2 尚未接入的 Agent：明确 blocked，不静默假装成功。"""

    def __init__(self, reason: str = "Phase 2 暂未接入该 Agent（先跑通 01/02/06）") -> None:
        self.reason = reason

    def run(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent=context.slice.agent,
            status="blocked",
            messages=[self.reason],
            error=f"{context.slice.agent}: {self.reason}",
        )


class MarketResearchRunner:
    """01 市场分析：读指标报告 → 产物 + 证据。"""

    def __init__(self, tools: ToolRegistry = DEFAULT_TOOL_REGISTRY) -> None:
        self.tools = tools

    def run(self, context: AgentContext) -> AgentResult:
        path = _resolve(context.inputs.get("metrics_path"), DEFAULT_METRICS)
        if not path.is_file():
            return AgentResult(
                agent="market_research",
                status="blocked",
                error=f"指标报告不存在：{path}",
                messages=["请先运行 market_metrics.py 生成指标 JSON"],
            )
        try:
            metrics = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return AgentResult(
                agent="market_research",
                status="failed",
                error=f"指标报告解析失败：{exc}",
            )

        capacity = metrics.get("market_capacity") or {}
        brand = metrics.get("brand_concentration") or {}
        seller = metrics.get("seller_concentration") or {}
        bands = metrics.get("price_bands") or {}
        artifact = {
            "agent": "market_research",
            "source": str(path),
            "market_capacity": capacity,
            "brand_concentration": brand,
            "seller_concentration": seller,
            "price_bands": bands,
            "config_matrix": metrics.get("config_matrix") or {},
        }
        evidence = EvidenceBlock(items=[
            EvidenceItem(
                claim_id="C-01-01",
                claim=f"类目月销量为 {capacity.get('total_monthly_sales')}",
                evidence_type="metric_report",
                source=str(path),
                locator="market_capacity.total_monthly_sales",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-01-02",
                claim=f"品牌 CR10 为 {brand.get('cr10')}",
                evidence_type="metric_report",
                source=str(path),
                locator="brand_concentration.cr10",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-01-03",
                claim=f"建议价格带数量为 {len(bands.get('suggested_bands') or [])}",
                evidence_type="metric_report",
                source=str(path),
                locator="price_bands.suggested_bands",
                retrieved_at=_today(),
            ),
        ])
        errors = evidence.validate()
        if errors:
            return AgentResult(
                agent="market_research",
                status="failed",
                artifact=artifact,
                evidence=evidence,
                error="；".join(errors),
            )
        return AgentResult(
            agent="market_research",
            status="ok",
            artifact=artifact,
            evidence=evidence,
            messages=[f"已读取指标报告：{path}"],
        )


class ProductStrategyRunner:
    """02 产品策略：调 sku_pricing matrix → 产物 + 证据。"""

    def __init__(self, tools: ToolRegistry = DEFAULT_TOOL_REGISTRY) -> None:
        self.tools = tools

    def run(self, context: AgentContext) -> AgentResult:
        path = _resolve(context.inputs.get("sku_file"), DEFAULT_SKUS)
        if not path.is_file():
            return AgentResult(
                agent="product_strategy",
                status="blocked",
                error=f"SKU 文件不存在：{path}",
            )
        platform = str(context.inputs.get("platform") or "shopee_br")
        result = self.tools.run(
            "sku_pricing",
            ["matrix", "--file", str(path), "--platform", platform, "--json"],
        )
        if not result.ok:
            return AgentResult(
                agent="product_strategy",
                status="failed",
                error=result.stderr or result.stdout,
                messages=["sku_pricing.py matrix 执行失败"],
            )
        try:
            data = result.json()
        except ValueError as exc:
            return AgentResult(
                agent="product_strategy",
                status="failed",
                error=str(exc),
            )

        skus = data.get("skus") or []
        artifact = {
            "agent": "product_strategy",
            "source": str(path),
            "platform": data.get("platform"),
            "target_margin": data.get("target_margin"),
            "skus": skus,
            "price_ladder": data.get("price_ladder") or [],
            "notes": data.get("notes") or [],
        }
        items = [
            EvidenceItem(
                claim_id="C-02-01",
                claim=f"目标净利率为 {data.get('target_margin')}%",
                evidence_type="metric_report",
                source="sku_pricing.py matrix --json",
                locator="target_margin",
                retrieved_at=_today(),
            )
        ]
        for index, sku in enumerate(skus[:3], start=1):
            items.append(EvidenceItem(
                claim_id=f"C-02-SKU-{index}",
                claim=f"{sku.get('sku')} 的净利率为 {sku.get('net_rate')}",
                evidence_type="metric_report",
                source="sku_pricing.py matrix --json",
                locator=f"skus[{index - 1}].net_rate",
                retrieved_at=_today(),
            ))
        evidence = EvidenceBlock(items=items)
        errors = evidence.validate()
        if errors:
            return AgentResult(
                agent="product_strategy",
                status="failed",
                artifact=artifact,
                evidence=evidence,
                error="；".join(errors),
            )
        return AgentResult(
            agent="product_strategy",
            status="ok",
            artifact=artifact,
            evidence=evidence,
            messages=[
                f"已计算 {len(skus)} 个 SKU",
                *[str(note) for note in (data.get("notes") or [])],
            ],
        )


def _num(inputs: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(inputs.get(key, default))
    except (TypeError, ValueError):
        return default


class AdvertisingRunner:
    """06 广告：调 ad_metrics diagnose → 诊断 + 证据 + 审批信封。"""

    def __init__(self, tools: ToolRegistry = DEFAULT_TOOL_REGISTRY) -> None:
        self.tools = tools

    def run(self, context: AgentContext) -> AgentResult:
        path = _resolve(context.inputs.get("ad_report"), DEFAULT_AD_REPORT)
        if not path.is_file():
            return AgentResult(
                agent="advertising",
                status="blocked",
                error=f"广告报表不存在：{path}",
            )
        price = _num(context.inputs, "price", 113.40)
        product_cost = _num(context.inputs, "product_cost", 55.0)
        commission = _num(context.inputs, "commission", 14.0)
        return_rate = _num(context.inputs, "return_rate", 2.0)
        tax = _num(context.inputs, "tax", 0.0)
        target_acos = _num(context.inputs, "target_acos", 25.0)
        min_impressions = int(_num(context.inputs, "min_impressions", 1000))

        args = [
            "diagnose",
            "--file", str(path),
            "--price", str(price),
            "--product-cost", str(product_cost),
            "--commission", str(commission),
            "--return", str(return_rate),
            "--tax", str(tax),
            "--target-acos", str(target_acos),
            "--min-impressions", str(min_impressions),
            "--json",
        ]
        platform = context.inputs.get("platform")
        if platform:
            args.extend(["--platform", str(platform)])
        result = self.tools.run("ad_metrics", args)
        if not result.ok:
            return AgentResult(
                agent="advertising",
                status="failed",
                error=result.stderr or result.stdout,
                messages=["ad_metrics.py diagnose 执行失败"],
            )
        try:
            data = result.json()
        except ValueError as exc:
            return AgentResult(
                agent="advertising",
                status="failed",
                error=str(exc),
            )

        cost_model = data.get("cost_model") or {}
        total = data.get("total") or {}
        campaigns = data.get("campaigns") or []
        p0 = [campaign for campaign in campaigns if campaign.get("grade") == "P0"]
        p1 = [campaign for campaign in campaigns if campaign.get("grade") == "P1"]
        artifact = {
            "agent": "advertising",
            "source": str(path),
            "cost_model": cost_model,
            "target_acos": data.get("target_acos"),
            "total": total,
            "campaigns": campaigns,
            "p0_campaigns": [campaign.get("campaign") for campaign in p0],
            "p1_campaigns": [campaign.get("campaign") for campaign in p1],
        }
        evidence = EvidenceBlock(items=[
            EvidenceItem(
                claim_id="C-06-01",
                claim=f"整体 ROAS 为 {total.get('roas')}",
                evidence_type="ad_report",
                source=str(path),
                locator="ad_metrics.total.roas",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-06-02",
                claim=f"盈亏线 ROAS 为 {cost_model.get('break_even_roas')}",
                evidence_type="metric_report",
                source="ad_metrics.py diagnose --json",
                locator="cost_model.break_even_roas",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-06-03",
                claim=f"P0 广告组数量为 {len(p0)}",
                evidence_type="ad_report",
                source=str(path),
                locator="campaigns[grade=P0]",
                retrieved_at=_today(),
            ),
        ])
        errors = evidence.validate()
        if errors:
            return AgentResult(
                agent="advertising",
                status="failed",
                artifact=artifact,
                evidence=evidence,
                error="；".join(errors),
            )

        envelope = self._build_envelope(context, p0)
        if envelope is not None:
            envelope_errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
            if envelope_errors:
                return AgentResult(
                    agent="advertising",
                    status="failed",
                    artifact=artifact,
                    evidence=evidence,
                    error="审批信封校验失败：" + "；".join(envelope_errors),
                )

        messages = [
            f"整体 ROAS {total.get('roas')}，盈亏线 ROAS {cost_model.get('break_even_roas')}",
            f"P0 广告组 {len(p0)} 个，P1 广告组 {len(p1)} 个",
        ]
        if envelope is not None:
            messages.append(f"已生成审批信封：{envelope.envelope_id}")
        else:
            messages.append("没有 P0 广告组，未生成审批信封")
        return AgentResult(
            agent="advertising",
            status="ok",
            artifact=artifact,
            evidence=evidence,
            envelope=envelope,
            messages=messages,
        )

    def _build_envelope(
        self,
        context: AgentContext,
        campaigns: list[dict[str, Any]],
    ) -> ApprovalEnvelope | None:
        actions: list[Action] = []
        for campaign in campaigns:
            name = campaign.get("campaign")
            cpc = campaign.get("cpc")
            affordable = campaign.get("affordable_cpc")
            if not name or cpc is None or affordable is None:
                continue
            reason = (campaign.get("actions") or ["P0 止血：降低出价"])[0]
            actions.append(Action(
                action="ad.set_bid",
                target=f"campaign:{name}",
                before={"cpc": cpc},
                after={"cpc": affordable},
                reason=str(reason),
                evidence=[f"ad-report#{name}", "ad-metrics#affordable_cpc"],
                rollback=f"恢复 cpc={cpc}",
            ))
        if not actions:
            return None
        return ApprovalEnvelope(
            envelope_id=f"ad-{context.thread_id[:8]}-{uuid.uuid4().hex[:6]}",
            module="06",
            action_type="ad_bid",
            risk=RiskLevel.APPROVAL,
            actions=actions,
            requested_by="advertising",
        )





DEFAULT_TITLE = (
    "Carregador Portátil 20000mAh 45W Turbo Carga Rápida 3 Saídas "
    "com Display Digital para Celular Viagem"
)
DEFAULT_SPEC = "Agents/03_Listing_Creative_Agent/examples/spec_table.csv"
DEFAULT_IMAGE = "Agents/04_Product_Image_Agent/tests/shopee_fixed.png"
DEFAULT_NARRATION = "Agents/05_Product_Video_Agent/examples/narration_airfryer.txt"
DEFAULT_REVIEWS = "Agents/07_Review_Analysis_Agent/examples/sample-reviews.csv"


class ListingCreativeRunner:
    """03 Listing：title_lint + spec_consistency 确定性校验。"""

    def __init__(self, tools: ToolRegistry = DEFAULT_TOOL_REGISTRY) -> None:
        self.tools = tools

    def run(self, context: AgentContext) -> AgentResult:
        title = str(context.inputs.get("title") or DEFAULT_TITLE)
        platform = str(context.inputs.get("platform") or "shopee")
        spec_path = _resolve(context.inputs.get("spec_file"), DEFAULT_SPEC)
        if not spec_path.is_file():
            return AgentResult(
                agent="listing_creative",
                status="blocked",
                error=f"spec_table 不存在：{spec_path}",
            )

        lint_result = self.tools.run(
            "title_lint", [title, "--platform", platform, "--json"]
        )
        if not lint_result.ok:
            return AgentResult(
                agent="listing_creative",
                status="failed",
                error=lint_result.stderr or lint_result.stdout,
            )
        try:
            lint = lint_result.json()
        except ValueError as exc:
            return AgentResult(agent="listing_creative", status="failed", error=str(exc))

        spec_result = self.tools.run(
            "spec_consistency",
            ["--spec", str(spec_path), "--title", title, "--json"],
        )
        if not spec_result.ok:
            return AgentResult(
                agent="listing_creative",
                status="failed",
                error=spec_result.stderr or spec_result.stdout,
            )
        try:
            spec = spec_result.json()
        except ValueError as exc:
            return AgentResult(agent="listing_creative", status="failed", error=str(exc))

        artifact = {
            "agent": "listing_creative",
            "mode": "validation_only",
            "title": title,
            "platform": platform,
            "title_lint": lint,
            "spec_consistency": spec,
            "spec_file": str(spec_path),
            "note": "Phase 3 只做确定性校验；文案生成待接 LLM/上游主卖点",
        }
        evidence = EvidenceBlock(items=[
            EvidenceItem(
                claim_id="C-03-01",
                claim=f"标题 {lint.get('chars')}/{lint.get('limit')} 字符",
                evidence_type="metric_report",
                source="title_lint.py --json",
                locator="chars/limit",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-03-02",
                claim=f"未溯源数字 {len(spec.get('untraceable') or [])} 个",
                evidence_type="spec_table",
                source=str(spec_path),
                locator="spec_consistency.untraceable",
                retrieved_at=_today(),
            ),
        ])
        if not lint.get("ok"):
            return AgentResult(
                agent="listing_creative",
                status="failed",
                artifact=artifact,
                evidence=evidence,
                error="标题未通过平台字符校验",
            )
        if not spec.get("ok"):
            return AgentResult(
                agent="listing_creative",
                status="failed",
                artifact=artifact,
                evidence=evidence,
                error="标题参数无法全部溯源到 spec_table",
            )

        envelope = None
        proposed = context.inputs.get("proposed_title")
        if proposed and str(proposed) != title:
            proposed_lint = self.tools.run(
                "title_lint", [str(proposed), "--platform", platform, "--json"]
            )
            if not proposed_lint.ok:
                return AgentResult(
                    agent="listing_creative",
                    status="failed",
                    artifact=artifact,
                    evidence=evidence,
                    error=proposed_lint.stderr or proposed_lint.stdout,
                )
            envelope = ApprovalEnvelope(
                envelope_id=f"listing-{context.thread_id[:8]}-{uuid.uuid4().hex[:6]}",
                module="03",
                action_type="listing_title",
                risk=RiskLevel.APPROVAL,
                actions=[Action(
                    action="listing.update_title",
                    target="listing:current",
                    before={"title": title},
                    after={"title": str(proposed)},
                    reason="标题 A/B 测试候选",
                    evidence=["title-lint#chars/limit", f"spec-table#{spec_path.name}"],
                    rollback=f"恢复标题：{title}",
                )],
                requested_by="listing_creative",
            )
            errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
            if errors:
                return AgentResult(
                    agent="listing_creative",
                    status="failed",
                    artifact=artifact,
                    evidence=evidence,
                    error="审批信封校验失败：" + "；".join(errors),
                )

        return AgentResult(
            agent="listing_creative",
            status="ok",
            artifact=artifact,
            evidence=evidence,
            envelope=envelope,
            messages=[
                f"标题 {lint.get('chars')}/{lint.get('limit')} 字符",
                f"未溯源数字 {len(spec.get('untraceable') or [])} 个",
            ],
        )


class ProductImageRunner:
    """04 商品图：像素级校验 + 9 图骨架（Phase 3 不出图）。"""

    def __init__(self, tools: ToolRegistry = DEFAULT_TOOL_REGISTRY) -> None:
        self.tools = tools

    def run(self, context: AgentContext) -> AgentResult:
        image_path = _resolve(context.inputs.get("image_path"), DEFAULT_IMAGE)
        platform = str(context.inputs.get("platform") or "shopee")
        if not image_path.is_file():
            return AgentResult(
                agent="product_image",
                status="blocked",
                error=f"图片不存在：{image_path}",
            )
        result = self.tools.run(
            "check_main_image", [str(image_path), "--platform", platform, "--json"]
        )
        if not result.ok and not result.stdout.strip():
            return AgentResult(
                agent="product_image",
                status="failed",
                error=result.stderr or result.stdout,
            )
        try:
            report = result.json()
        except ValueError as exc:
            return AgentResult(agent="product_image", status="failed", error=str(exc))

        upstream = context.upstream_artifacts.get("product_strategy") or {}
        core = (
            context.inputs.get("core_selling_point")
            or upstream.get("core_selling_point")
            or "（待上游主卖点）"
        )
        image_plan = [
            {"slot": 1, "role": "主图", "message": "产品识别"},
            {"slot": 2, "role": "核心卖点图", "message": core},
            {"slot": 3, "role": "参数规格图", "message": "spec_table 可视化"},
            {"slot": 4, "role": "使用场景图 A", "message": "主场景"},
            {"slot": 5, "role": "使用场景图 B", "message": "次场景"},
            {"slot": 6, "role": "细节特写图", "message": "材质/做工"},
            {"slot": 7, "role": "尺寸/对比图", "message": "消除尺寸误解"},
            {"slot": 8, "role": "包装清单图", "message": "含/不含配件（必须实拍）"},
            {"slot": 9, "role": "售后/保修图", "message": "信任要素"},
        ]
        metrics = report.get("metrics") or {}
        artifact = {
            "agent": "product_image",
            "mode": "validation_only",
            "image_path": str(image_path),
            "platform": platform,
            "check_report": report,
            "compliance_ok": bool(report.get("ok")),
            "image_plan": image_plan,
            "core_selling_point": core,
            "note": "Phase 3 只做像素校验与 9 图骨架；出图 Prompt 由 04 的 Prompt 层生成",
        }
        evidence = EvidenceBlock(items=[
            EvidenceItem(
                claim_id="C-04-01",
                claim=f"图片尺寸 {metrics.get('width')}×{metrics.get('height')}（{platform}）",
                evidence_type="manual",
                source=str(image_path),
                locator="check_main_image.metrics",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-04-02",
                claim=f"主体占比 {metrics.get('coverage')}",
                evidence_type="manual",
                source=str(image_path),
                locator="check_main_image.metrics.coverage",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-04-03",
                claim=f"平台校验结论：{'通过' if report.get('ok') else '未通过'}",
                evidence_type="manual",
                source="check_main_image.py --json",
                locator="check_main_image.ok",
                retrieved_at=_today(),
            ),
        ])

        if not report.get("ok"):
            return AgentResult(
                agent="product_image",
                status="blocked",
                artifact=artifact,
                evidence=evidence,
                error=f"图片未通过 {platform} 平台校验，不许交付",
            )

        envelope = None
        proposed = context.inputs.get("proposed_main_image")
        if proposed:
            envelope = ApprovalEnvelope(
                envelope_id=f"image-{context.thread_id[:8]}-{uuid.uuid4().hex[:6]}",
                module="04",
                action_type="main_image",
                risk=RiskLevel.APPROVAL,
                actions=[Action(
                    action="image.replace_main",
                    target="listing:main_image",
                    before={"image": str(image_path)},
                    after={"image": str(proposed)},
                    reason="更换主图（A/B 测试或 iterate）",
                    evidence=[f"check-main-image#{image_path.name}"],
                    rollback=f"恢复主图：{image_path}",
                )],
                requested_by="product_image",
            )
            errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
            if errors:
                return AgentResult(
                    agent="product_image",
                    status="failed",
                    artifact=artifact,
                    evidence=evidence,
                    error="审批信封校验失败：" + "；".join(errors),
                )

        return AgentResult(
            agent="product_image",
            status="ok",
            artifact=artifact,
            evidence=evidence,
            envelope=envelope,
            messages=[
                f"图片校验通过：{metrics.get('width')}×{metrics.get('height')}",
                f"已生成 9 图骨架（核心卖点：{core}）",
            ],
        )


class ProductVideoRunner:
    """05 视频：video_timing 确定性校验（Phase 3 只做脚本/时长校验）。"""

    def __init__(self, tools: ToolRegistry = DEFAULT_TOOL_REGISTRY) -> None:
        self.tools = tools

    def run(self, context: AgentContext) -> AgentResult:
        script_path = _resolve(context.inputs.get("script_file"), DEFAULT_NARRATION)
        target = int(_num(context.inputs, "target", 30))
        if not script_path.is_file():
            return AgentResult(
                agent="product_video",
                status="blocked",
                error=f"配音稿不存在：{script_path}",
            )
        result = self.tools.run(
            "video_timing",
            ["--script", str(script_path), "--target", str(target), "--format", "json"],
        )
        if not result.ok:
            return AgentResult(
                agent="product_video",
                status="failed",
                error=result.stderr or result.stdout,
            )
        try:
            data = result.json()
        except ValueError as exc:
            return AgentResult(agent="product_video", status="failed", error=str(exc))

        meta = data.get("meta") or {}
        total = float(meta.get("total_seconds") or 0)
        target_seconds = float(meta.get("target") or target)
        tolerance = abs(total - target_seconds) / target_seconds if target_seconds else 0
        within = tolerance <= 0.15
        flags = [
            line for line in (data.get("timeline") or [])
            if line.get("flag")
        ]
        artifact = {
            "agent": "product_video",
            "mode": "validation_only",
            "script_file": str(script_path),
            "target": target_seconds,
            "total_seconds": total,
            "tolerance": round(tolerance, 4),
            "within_tolerance": within,
            "timeline": data.get("timeline") or [],
            "flags": flags,
            "note": "Phase 3 只做时长/字幕校验；脚本/分镜由 05 的 Prompt 层生成",
        }
        evidence = EvidenceBlock(items=[
            EvidenceItem(
                claim_id="C-05-01",
                claim=f"配音总时长为 {total}s（目标 {target_seconds}s）",
                evidence_type="metric_report",
                source="video_timing.py --format json",
                locator="meta.total_seconds",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-05-02",
                claim=f"台词共 {meta.get('lines')} 句",
                evidence_type="metric_report",
                source="video_timing.py --format json",
                locator="meta.lines",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-05-03",
                claim=f"字幕/时长告警 {len(flags)} 条",
                evidence_type="metric_report",
                source="video_timing.py --format json",
                locator="timeline[flag]",
                retrieved_at=_today(),
            ),
        ])
        if not within:
            return AgentResult(
                agent="product_video",
                status="blocked",
                artifact=artifact,
                evidence=evidence,
                error=f"时长偏差 {tolerance:.0%} 超过 ±15%，需删词或补句",
            )
        return AgentResult(
            agent="product_video",
            status="ok",
            artifact=artifact,
            evidence=evidence,
            messages=[
                f"时长 {total}s / 目标 {target_seconds}s（偏差 {tolerance:.0%}）",
                f"字幕/时长告警 {len(flags)} 条",
            ],
        )


class ReviewAnalysisRunner:
    """07 评论：review_stats 聚合 + 归因一致性校验。"""

    def __init__(self, tools: ToolRegistry = DEFAULT_TOOL_REGISTRY) -> None:
        self.tools = tools

    def run(self, context: AgentContext) -> AgentResult:
        reviews_path = _resolve(context.inputs.get("reviews_file"), DEFAULT_REVIEWS)
        if not reviews_path.is_file():
            return AgentResult(
                agent="review_analysis",
                status="blocked",
                error=f"评论文件不存在：{reviews_path}",
            )
        args = ["--file", str(reviews_path), "--format", "json"]
        if context.inputs.get("fixable"):
            args.extend(["--fixable", str(context.inputs["fixable"])])
        if context.inputs.get("points"):
            args.extend(["--points", str(context.inputs["points"])])
        result = self.tools.run("review_stats", args)
        if not result.ok:
            return AgentResult(
                agent="review_analysis",
                status="failed",
                error=result.stderr or result.stdout,
            )
        try:
            data = result.json()
        except ValueError as exc:
            return AgentResult(agent="review_analysis", status="failed", error=str(exc))

        reviews = data.get("reviews") or {}
        artifact = {
            "agent": "review_analysis",
            "mode": "aggregation_only",
            "reviews_file": str(reviews_path),
            "reviews": reviews,
            "selling_points": data.get("selling_points"),
            "note": "Phase 3 只做统计/归因聚合；修补文案由 07 的 Prompt 层生成",
        }
        evidence = EvidenceBlock(items=[
            EvidenceItem(
                claim_id="C-07-01",
                claim=f"评论共 {reviews.get('total')} 条，差评 {reviews.get('bad')} 条",
                evidence_type="review",
                source=str(reviews_path),
                locator="review_stats.reviews.total/bad",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-07-02",
                claim=(
                    f"归因合计 {reviews.get('attribution_total')} 条，"
                    f"校验差异 {reviews.get('attribution_mismatch')} 条"
                ),
                evidence_type="review",
                source=str(reviews_path),
                locator="review_stats.reviews.attribution_total",
                retrieved_at=_today(),
            ),
            EvidenceItem(
                claim_id="C-07-03",
                claim=f"可修复率 {reviews.get('fixable_rate')}",
                evidence_type="review",
                source=str(reviews_path),
                locator="review_stats.reviews.fixable_rate",
                retrieved_at=_today(),
            ),
        ])
        if reviews.get("attribution_mismatch"):
            return AgentResult(
                agent="review_analysis",
                status="failed",
                artifact=artifact,
                evidence=evidence,
                error="归因合计与差评数不一致，先修数据再下结论",
            )

        envelope = None
        patch = context.inputs.get("patch_listing")
        if isinstance(patch, dict):
            envelope = ApprovalEnvelope(
                envelope_id=f"review-{context.thread_id[:8]}-{uuid.uuid4().hex[:6]}",
                module="07",
                action_type="listing_patch",
                risk=RiskLevel.APPROVAL,
                actions=[Action(
                    action="review.patch_listing",
                    target=str(patch.get("target") or "listing:description"),
                    before=dict(patch.get("before") or {}),
                    after=dict(patch.get("after") or {}),
                    reason=str(patch.get("reason") or "按评论归因修补 Listing"),
                    evidence=[str(x) for x in (patch.get("evidence") or [f"reviews#{reviews_path.name}"])],
                    rollback=str(patch.get("rollback") or "恢复修补前的 Listing 片段"),
                )],
                requested_by="review_analysis",
            )
            errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
            if errors:
                return AgentResult(
                    agent="review_analysis",
                    status="failed",
                    artifact=artifact,
                    evidence=evidence,
                    error="审批信封校验失败：" + "；".join(errors),
                )

        return AgentResult(
            agent="review_analysis",
            status="ok",
            artifact=artifact,
            evidence=evidence,
            envelope=envelope,
            messages=[
                f"评论 {reviews.get('total')} 条，差评率 {reviews.get('bad_rate')}",
                f"可修复率 {reviews.get('fixable_rate')}",
            ],
        )


class RunnerRegistry:
    """Agent Runner 注册表；未注册的 Agent 交给 StubRunner（明确 blocked）。"""

    def __init__(self, runners: dict[str, AgentRunner] | None = None) -> None:
        self._runners = runners or {
            "market_research": MarketResearchRunner(),
            "product_strategy": ProductStrategyRunner(),
            "listing_creative": ListingCreativeRunner(),
            "product_image": ProductImageRunner(),
            "product_video": ProductVideoRunner(),
            "advertising": AdvertisingRunner(),
            "review_analysis": ReviewAnalysisRunner(),
        }
        self._stub = StubRunner()

    def get(self, agent_key: str) -> AgentRunner:
        return self._runners.get(agent_key, self._stub)

    def registered(self) -> tuple[str, ...]:
        return tuple(self._runners)


DEFAULT_RUNNER_REGISTRY = RunnerRegistry()
