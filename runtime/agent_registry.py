"""7 个 Agent 的能力注册表（路由/编排/工具/审批的单一事实来源）。

对齐底座 Multi-Agent-E-commerce-System 的 Agent 注册思路：
- 新增 Agent 只改这里，不改路由/编排/前端标签；
- 每个 Agent 声明关键词、工具、输入输出契约、审批策略；
- 未知 Agent 一律不可路由（与底座「未知动作默认 forbidden」同哲学）。
"""
from __future__ import annotations

from .contracts import AgentSpec, Intent, SlicePlan


AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec(
        key="market_research",
        name="01 市场分析",
        intent=Intent.MARKET_RESEARCH,
        description="类目前置判断、市场容量、集中度、价格带、配置组合",
        keywords=(
            "市场", "类目", "容量", "集中度", "价格带", "选品", "竞品", "趋势",
            "能不能做", "值不值得做", "市场分析", "机会点", "配置组合",
            "market", "category", "demand", "competitor", "trend", "price band",
        ),
        tools=("shaduola_parser", "market_metrics"),
        approval_policy="read_only",
        requires_approval=False,
        input_schema={
            "category": "类目名",
            "platform": "目标平台",
            "target_market": "目标市场",
            "metrics_report": "类目导出数据/标准化 JSON",
        },
        output_schema={
            "go_no_go": "前置判断结论",
            "market_capacity": "容量指标",
            "price_bands": "价格带与波谷",
            "config_opportunities": "配置机会",
            "evidence": "证据块",
        },
        downstream=("product_strategy",),
    ),
    AgentSpec(
        key="product_strategy",
        name="02 产品策略",
        intent=Intent.PRODUCT_STRATEGY,
        description="定位、配置、主卖点收敛、定价、SKU 四角色、盈亏线",
        keywords=(
            "定价", "毛利", "净利", "盈亏", "盈亏线", "优惠券", "券", "sku",
            "主推", "卖点", "产品策略", "配置", "成本", "目标价", "价格阶梯",
            "pricing", "margin", "breakeven", "coupon", "positioning",
        ),
        tools=("sku_pricing",),
        approval_policy="approval_price_coupon",
        requires_approval=True,
        input_schema={
            "decision_approved": "人已确认的选品决策",
            "target_price_range": "来自 01 的目标价格带",
            "recommended_config": "来自 01 的推荐配置",
            "cost_structure": "采购/头程/尾程/佣金/退货/税",
        },
        output_schema={
            "product_requirement": "产品需求表",
            "core_selling_point": "唯一主卖点",
            "sku_structure": "SKU 四角色",
            "price_ladder": "价格阶梯",
            "breakeven_roas_by_sku": "各 SKU 盈亏线 ROAS",
            "action_envelope": "改价/发券审批信封（如有）",
            "evidence": "证据块",
        },
        upstream=("market_research",),
        downstream=("listing_creative",),
    ),
    AgentSpec(
        key="listing_creative",
        name="03 Listing 创意",
        intent=Intent.LISTING_CREATIVE,
        description="关键词分类、标题、详情页、卖点/参数、合规扫描",
        keywords=(
            "标题", "详情页", "listing", "文案", "关键词", "描述", "卖点提炼",
            "商品内容", "五点描述", "title", "description", "keywords", "copy",
        ),
        tools=("title_lint", "spec_consistency"),
        approval_policy="approval_listing_change",
        requires_approval=True,
        input_schema={
            "core_selling_point": "来自 02 的唯一主卖点",
            "spec_table": "参数表",
            "forbidden_words": "禁用词清单",
            "platform": "目标平台",
        },
        output_schema={
            "title_final": "最终标题",
            "description": "详情页",
            "secondary_points": "次级卖点",
            "spec_table": "参数表（透传）",
            "compliance_scan": "合规扫描结果",
            "action_envelope": "改标题/详情审批信封（如有）",
            "evidence": "证据块",
        },
        upstream=("product_strategy",),
        downstream=("product_image", "product_video"),
    ),
    AgentSpec(
        key="product_image",
        name="04 商品图",
        intent=Intent.PRODUCT_IMAGE,
        description="9 图规划、风格锁、出图 Prompt、像素级合规校验、可选渲染",
        keywords=(
            "主图", "图片", "详情图", "白底", "场景图", "9图", "九图", "做图",
            "出图", "图片合规", "换背景", "sku 换色", "image", "main image",
            "photo", "visual", "pdp image", "render",
        ),
        tools=("check_main_image", "render_openai", "render_prompt_pack"),
        approval_policy="approval_main_image",
        requires_approval=True,
        input_schema={
            "core_selling_point": "来自 02 的唯一主卖点",
            "spec_table": "参数表",
            "platform": "目标平台",
            "product_photo": "产品实拍参考图",
        },
        output_schema={
            "image_plan": "9 图规划",
            "campaign_style_lock": "多图风格锁",
            "prompts": "逐图 Prompt",
            "compliance_scan": "图片合规扫描",
            "action_envelope": "换主图审批信封（如有）",
            "evidence": "证据块",
        },
        upstream=("listing_creative",),
    ),
    AgentSpec(
        key="product_video",
        name="05 商品视频",
        intent=Intent.PRODUCT_VIDEO,
        description="15s/30s 脚本、分镜、AI 视频 Prompt、配音字幕、时长校验",
        keywords=(
            "视频", "短视频", "分镜", "脚本", "配音", "字幕", "口播", "15秒",
            "30秒", "video", "storyboard", "voiceover", "subtitle",
        ),
        tools=("video_timing",),
        approval_policy="draft_only",
        requires_approval=False,
        input_schema={
            "core_selling_point": "来自 02 的唯一主卖点",
            "spec_table": "参数表",
            "usage_scope": "使用场景",
        },
        output_schema={
            "script": "15s/30s 脚本",
            "storyboard": "分镜表",
            "video_prompts": "AI 视频 Prompt",
            "subtitles": "字幕",
            "timing_check": "时长校验结果",
            "evidence": "证据块",
        },
        upstream=("listing_creative",),
    ),
    AgentSpec(
        key="advertising",
        name="06 广告优化",
        intent=Intent.ADVERTISING,
        description="四类漏斗诊断、盈亏线核算、P0/P1/P2 动作、审批信封",
        keywords=(
            "广告", "roas", "acos", "预算", "出价", "投放", "广告诊断",
            "广告亏钱", "广告费", "cpc", "ctr", "转化率", "campaign", "bid", "budget",
        ),
        tools=("ad_metrics",),
        approval_policy="approval_budget_bid",
        requires_approval=True,
        input_schema={
            "ad_report": "广告导出 CSV",
            "price": "售价",
            "product_cost": "产品成本",
            "platform": "平台费率预设",
        },
        output_schema={
            "funnel_diagnosis": "四类漏斗诊断",
            "breakeven_roas": "盈亏线 ROAS/ACOS",
            "actions": "P0/P1/P2 动作",
            "action_envelope": "预算/出价审批信封",
            "evidence": "证据块",
        },
        upstream=("product_strategy", "listing_creative"),
    ),
    AgentSpec(
        key="review_analysis",
        name="07 评论分析",
        intent=Intent.REVIEW_ANALYSIS,
        description="八类归因、误解型识别、可修复率、卖点排行、详情页修补建议",
        keywords=(
            "评论", "差评", "好评", "评价", "归因", "误解型", "可修复",
            "review", "negative review", "feedback", "rating", "testimonial",
        ),
        tools=("review_stats",),
        approval_policy="approval_listing_patch",
        requires_approval=True,
        input_schema={
            "reviews": "评论 CSV（rating 必填）",
            "spec_table": "参数表",
            "package_content": "包装清单",
        },
        output_schema={
            "attribution": "八类归因",
            "fixable_rate": "可修复率",
            "selling_points_ranked": "卖点排行",
            "patch_suggestions": "详情页修补建议",
            "action_envelope": "Listing 修补审批信封（如有）",
            "evidence": "证据块",
        },
        upstream=("listing_creative", "product_image"),
        downstream=("listing_creative", "product_image"),
    ),
)


class AgentRegistry:
    """Agent 注册表：新增 Agent 只改一处。"""

    def __init__(self, specs: tuple[AgentSpec, ...] = AGENTS) -> None:
        self._specs: dict[str, AgentSpec] = {}
        self._by_intent: dict[Intent, AgentSpec] = {}
        for spec in specs:
            if spec.key in self._specs:
                raise ValueError(f"Agent key 重复：{spec.key}")
            if spec.intent in self._by_intent:
                raise ValueError(f"Agent intent 重复：{spec.intent}")
            self._specs[spec.key] = spec
            self._by_intent[spec.intent] = spec

    def get(self, key: str) -> AgentSpec:
        try:
            return self._specs[key]
        except KeyError:
            raise KeyError(f"未知 Agent：{key}（可用：{', '.join(self._specs)}）") from None

    def all(self) -> tuple[AgentSpec, ...]:
        return tuple(self._specs.values())

    def keys(self) -> tuple[str, ...]:
        return tuple(self._specs.keys())

    def by_intent(self, intent: Intent) -> AgentSpec | None:
        return self._by_intent.get(intent)

    def for_intents(self, intents: tuple[Intent, ...]) -> tuple[AgentSpec, ...]:
        specs: list[AgentSpec] = []
        for intent in intents:
            spec = self.by_intent(intent)
            if spec is not None and spec not in specs:
                specs.append(spec)
        return tuple(specs)

    def validate_plan(self, plan: SlicePlan, max_slices: int = 7) -> None:
        plan.validate(self._specs, max_slices=max_slices)


DEFAULT_REGISTRY = AgentRegistry()


# 固定工作流顺序（用于复合任务的切片排序；不是依赖图的唯一来源）
WORKFLOW_ORDER: tuple[str, ...] = (
    "market_research",
    "product_strategy",
    "listing_creative",
    "product_image",
    "product_video",
    "advertising",
    "review_analysis",
)


# 上游关系：只有双方都出现在计划里，才建立依赖
UPSTREAM: dict[str, tuple[str, ...]] = {
    "market_research": (),
    "product_strategy": ("market_research",),
    "listing_creative": ("product_strategy",),
    "product_image": ("listing_creative",),
    "product_video": ("listing_creative",),
    "advertising": ("product_strategy", "listing_creative"),
    "review_analysis": ("listing_creative", "product_image"),
}
