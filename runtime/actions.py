"""动作风险注册表 + 审批信封（效果后置）。

对齐底座 Multi-Agent-E-commerce-System 的三层风险与审批批次：
- auto：只读 / 内部草稿，免审；
- approval：对外状态变更（改价、改预算、换主图、改 Listing），必须人工审批；
- forbidden：平台禁止或本项目明确不做的动作，工具不暴露。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .contracts import RiskLevel


@dataclass(frozen=True)
class ActionSpec:
    action: str
    risk: RiskLevel
    label: str
    owner_agent: str
    description: str = ""
    rollback: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk"] = self.risk.value
        return data


@dataclass
class Action:
    """一条待审批动作：目标 + 改前/改后快照 + 理由 + 证据 + 回滚。"""

    action: str
    target: str
    before: dict[str, Any]
    after: dict[str, Any]
    reason: str
    evidence: list[str] = field(default_factory=list)
    rollback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        return cls(
            action=str(data.get("action", "")),
            target=str(data.get("target", "")),
            before=dict(data.get("before") or {}),
            after=dict(data.get("after") or {}),
            reason=str(data.get("reason", "")),
            evidence=[str(x) for x in (data.get("evidence") or [])],
            rollback=str(data.get("rollback", "")),
        )


@dataclass
class ApprovalEnvelope:
    """一次审批批次：批内同进同退，快照漂移整批回滚。"""

    envelope_id: str
    module: str
    action_type: str
    risk: RiskLevel
    actions: list[Action]
    decision: str = "pending"
    drift_policy: str = "abort_whole_batch"
    requested_by: str = "agent"
    decided_by: str | None = None
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk"] = self.risk.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalEnvelope":
        try:
            risk = RiskLevel(str(data.get("risk", RiskLevel.APPROVAL.value)))
        except ValueError:
            risk = RiskLevel.FORBIDDEN
        return cls(
            envelope_id=str(data.get("envelope_id", "")),
            module=str(data.get("module", "")),
            action_type=str(data.get("action_type", "")),
            risk=risk,
            actions=[Action.from_dict(item) for item in (data.get("actions") or [])],
            decision=str(data.get("decision", "pending")),
            drift_policy=str(data.get("drift_policy", "abort_whole_batch")),
            requested_by=str(data.get("requested_by", "agent")),
            decided_by=data.get("decided_by"),
            comment=data.get("comment"),
        )

    def validate(self, registry: "ActionRegistry | None" = None) -> list[str]:
        """返回错误清单；空列表 = 可提交审批。"""
        errors: list[str] = []
        if not self.envelope_id.strip():
            errors.append("envelope_id 不能为空")
        if not self.module.strip():
            errors.append("module 不能为空")
        if not self.action_type.strip():
            errors.append("action_type 不能为空")
        if self.risk != RiskLevel.APPROVAL:
            errors.append(f"审批信封的 risk 必须是 approval，实际 {self.risk.value}")
        if not self.actions:
            errors.append("actions 不能为空（无动作就不需要审批信封）")
        if self.decision not in {"pending", "approved", "rejected"}:
            errors.append(f"decision 非法：{self.decision}")
        if self.decision == "approved" and not self.decided_by:
            errors.append("approved 必须记录 decided_by")
        if self.drift_policy not in {"abort_whole_batch", "apply_anyway"}:
            errors.append(f"drift_policy 非法：{self.drift_policy}")

        for index, action in enumerate(self.actions, start=1):
            prefix = f"actions[{index}]"
            if not action.action.strip():
                errors.append(f"{prefix}.action 不能为空")
            elif registry is not None:
                spec = registry.spec(action.action)
                if spec is None:
                    errors.append(f"{prefix}.action 未知：{action.action}")
                elif spec.risk != RiskLevel.APPROVAL:
                    errors.append(
                        f"{prefix}.action 风险为 {spec.risk.value}，不能进审批信封"
                    )
            if not action.target.strip():
                errors.append(f"{prefix}.target 不能为空")
            if not action.before:
                errors.append(f"{prefix}.before 不能为空（无法做漂移比对）")
            if not action.after:
                errors.append(f"{prefix}.after 不能为空")
            if not action.reason.strip():
                errors.append(f"{prefix}.reason 不能为空")
            if not action.evidence:
                errors.append(f"{prefix}.evidence 不能为空（动作必须有依据）")
            if not action.rollback.strip():
                errors.append(f"{prefix}.rollback 不能为空")
        return errors

    def check_drift(self, current: dict[str, dict[str, Any]]) -> list[str]:
        """用当前快照比对 before；任何漂移 → 整批不执行。"""
        errors: list[str] = []
        for index, action in enumerate(self.actions, start=1):
            if action.target not in current:
                errors.append(f"actions[{index}] 目标不存在：{action.target}")
                continue
            if current[action.target] != action.before:
                errors.append(
                    f"actions[{index}] 快照漂移：{action.target} "
                    f"before={action.before} current={current[action.target]}"
                )
        return errors


DEFAULT_ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec(
        action="market.read",
        risk=RiskLevel.AUTO,
        label="读取类目数据",
        owner_agent="market_research",
        description="只读分析，不改任何对外状态",
    ),
    ActionSpec(
        action="product.update_price",
        risk=RiskLevel.APPROVAL,
        label="修改售价",
        owner_agent="product_strategy",
        description="改价属于对外状态变更，必须人工审批",
        rollback="恢复 before 中的售价",
    ),
    ActionSpec(
        action="product.update_coupon",
        risk=RiskLevel.APPROVAL,
        label="修改优惠券",
        owner_agent="product_strategy",
        description="券面额/门槛影响成交价，必须审批",
        rollback="恢复 before 中的优惠券配置",
    ),
    ActionSpec(
        action="product.update_sku_structure",
        risk=RiskLevel.APPROVAL,
        label="调整 SKU 结构",
        owner_agent="product_strategy",
        description="新增/下架 SKU 影响链接结构，必须审批",
        rollback="恢复 before 中的 SKU 列表",
    ),
    ActionSpec(
        action="listing.update_title",
        risk=RiskLevel.APPROVAL,
        label="修改标题",
        owner_agent="listing_creative",
        description="标题影响搜索与权重，必须审批",
        rollback="恢复 before 中的标题",
    ),
    ActionSpec(
        action="listing.update_description",
        risk=RiskLevel.APPROVAL,
        label="修改详情页",
        owner_agent="listing_creative",
        description="详情页影响转化与合规，必须审批",
        rollback="恢复 before 中的详情页",
    ),
    ActionSpec(
        action="image.replace_main",
        risk=RiskLevel.APPROVAL,
        label="更换主图",
        owner_agent="product_image",
        description="主图直接影响点击率，必须审批",
        rollback="恢复 before 中的主图文件",
    ),
    ActionSpec(
        action="video.publish",
        risk=RiskLevel.APPROVAL,
        label="发布商品视频",
        owner_agent="product_video",
        description="视频对外可见，必须审批",
        rollback="撤回已发布视频",
    ),
    ActionSpec(
        action="ad.set_budget",
        risk=RiskLevel.APPROVAL,
        label="调整广告预算",
        owner_agent="advertising",
        description="预算影响花费，必须审批",
        rollback="恢复 before 中的预算",
    ),
    ActionSpec(
        action="ad.set_bid",
        risk=RiskLevel.APPROVAL,
        label="调整广告出价",
        owner_agent="advertising",
        description="出价影响 CPC 与花费，必须审批",
        rollback="恢复 before 中的出价",
    ),
    ActionSpec(
        action="ad.pause",
        risk=RiskLevel.FORBIDDEN,
        label="暂停广告",
        owner_agent="advertising",
        description="本项目明确不暂停广告（会破坏链接权重连续性），只降预算/出价",
    ),
    ActionSpec(
        action="review.patch_listing",
        risk=RiskLevel.APPROVAL,
        label="按评论修补 Listing",
        owner_agent="review_analysis",
        description="修补文案对外可见，必须审批",
        rollback="恢复 before 中的 Listing 片段",
    ),
    ActionSpec(
        action="review.request_removal",
        risk=RiskLevel.FORBIDDEN,
        label="要求删除评论",
        owner_agent="review_analysis",
        description="平台禁止的评价操纵，不提供工具",
    ),
    ActionSpec(
        action="review.synthetic_review",
        risk=RiskLevel.FORBIDDEN,
        label="生成模拟好评",
        owner_agent="review_analysis",
        description="虚假评价，平台禁止，不提供工具",
    ),
)


class ActionRegistry:
    """动作注册表：分类/标签/回滚一处维护；未知动作默认 forbidden。"""

    def __init__(self, specs: tuple[ActionSpec, ...] = DEFAULT_ACTIONS) -> None:
        self._specs: dict[str, ActionSpec] = {}
        for spec in specs:
            if spec.action in self._specs:
                raise ValueError(f"动作重复注册：{spec.action}")
            self._specs[spec.action] = spec

    def spec(self, action: str) -> ActionSpec | None:
        return self._specs.get(action)

    def classify(self, action: str) -> RiskLevel:
        spec = self._specs.get(action)
        return spec.risk if spec is not None else RiskLevel.FORBIDDEN

    def metadata(self) -> list[dict[str, Any]]:
        return [
            spec.to_dict()
            for spec in sorted(self._specs.values(), key=lambda item: item.action)
        ]

    def for_agent(self, agent_key: str) -> tuple[ActionSpec, ...]:
        return tuple(
            spec for spec in self._specs.values() if spec.owner_agent == agent_key
        )


DEFAULT_ACTION_REGISTRY = ActionRegistry()
