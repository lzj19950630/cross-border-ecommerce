"""跨 Agent 的共享契约（纯标准库）。

设计来源：Multi-Agent-E-commerce-System 的 SlicePlan / AgentSpec / 审批 / 引用思路，
但按本工具箱的 7 个 Agent 重新建模。这里只放数据结构与校验，不放编排实现。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """动作风险三级分类（对齐底座的三层风险）。"""

    AUTO = "auto"           # 只读 / 内部草稿：免审
    APPROVAL = "approval"   # 对外状态变更：必须人工审批
    FORBIDDEN = "forbidden" # 禁止动作：工具不暴露


class Intent(str, Enum):
    """7 个 Agent + 复合任务 + 澄清。"""

    MARKET_RESEARCH = "market_research"
    PRODUCT_STRATEGY = "product_strategy"
    LISTING_CREATIVE = "listing_creative"
    PRODUCT_IMAGE = "product_image"
    PRODUCT_VIDEO = "product_video"
    ADVERTISING = "advertising"
    REVIEW_ANALYSIS = "review_analysis"
    MULTI_AGENT = "multi_agent"
    CLARIFY = "clarify"
    UNKNOWN = "unknown"


def _to_intent(value: Any) -> Intent:
    """字符串/枚举 → Intent；未知值落 UNKNOWN（不静默吞错，上层可据 UNKNOWN 追问）。"""
    if isinstance(value, Intent):
        return value
    try:
        return Intent(str(value))
    except ValueError:
        return Intent.UNKNOWN


@dataclass(frozen=True)
class AgentSpec:
    """一个 Agent 的完整能力卡（路由/编排/工具/审批都读它）。"""

    key: str
    name: str
    intent: Intent
    description: str
    keywords: tuple[str, ...]
    tools: tuple[str, ...]
    approval_policy: str
    requires_approval: bool
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    upstream: tuple[str, ...] = ()
    downstream: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["intent"] = self.intent.value
        return data


@dataclass
class RouteDecision:
    """意图路由结果：一个或多个意图 + 置信度 + 缺槽 + 理由。"""

    intents: tuple[Intent, ...]
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    missing_slots: tuple[str, ...] = ()
    reason: str = ""
    compound: bool = False

    def primary(self) -> Intent:
        return self.intents[0] if self.intents else Intent.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "intents": [intent.value for intent in self.intents],
            "confidence": round(float(self.confidence), 4),
            "entities": self.entities,
            "missing_slots": list(self.missing_slots),
            "reason": self.reason,
            "compound": self.compound,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RouteDecision":
        raw_intents = data.get("intents") or []
        if isinstance(raw_intents, str):
            raw_intents = [raw_intents]
        intents = tuple(_to_intent(item) for item in raw_intents) or (Intent.UNKNOWN,)
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        return cls(
            intents=intents,
            confidence=confidence,
            entities=dict(data.get("entities") or {}),
            missing_slots=tuple(str(x) for x in (data.get("missing_slots") or [])),
            reason=str(data.get("reason") or ""),
            compound=bool(data.get("compound", len(intents) > 1)),
        )


@dataclass
class Slice:
    """执行切片：一段可由单个 Agent 独立完成的工作。"""

    no: int
    agent: str
    description: str
    depends_on: list[int] = field(default_factory=list)
    approval_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Slice":
        # YAML 1.1 会把未加引号的 no 解析成布尔 False；这里兼容两种写法。
        if "no" in data:
            raw_no = data["no"]
        elif False in data:
            raw_no = data[False]
        elif "slice_no" in data:
            raw_no = data["slice_no"]
        else:
            raise ValueError("切片缺 no（YAML 中建议写成 \"no\"，避免被解析成布尔值）")
        return cls(
            no=int(raw_no),
            agent=str(data["agent"]),
            description=str(data["description"]),
            depends_on=[int(x) for x in (data.get("depends_on") or [])],
            approval_points=[str(x) for x in (data.get("approval_points") or [])],
        )


@dataclass
class SlicePlan:
    """Manager 规划产物：切片 + 依赖声明。

    校验规则对齐底座：编号唯一、Agent 合法、依赖存在且无环、写动作必须有审批点。
    切片上限默认 7（本工具箱有 7 个 Agent；底座原值是 5，可配置）。
    """

    slices: list[Slice]

    def to_dict(self) -> dict[str, Any]:
        return {"slices": [item.to_dict() for item in self.slices]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SlicePlan":
        raw = data.get("slices") or []
        if not isinstance(raw, list) or not raw:
            raise ValueError("slices 缺失或为空")
        return cls(slices=[Slice.from_dict(item) for item in raw])

    def validate(self, agents: dict[str, AgentSpec], max_slices: int = 7) -> None:
        """结构 + 依赖 + 审批点校验；失败抛 ValueError（调用方不许静默通过）。"""
        if not self.slices:
            raise ValueError("切片计划为空")
        if len(self.slices) > max_slices:
            raise ValueError(f"切片数超上限（{len(self.slices)} > {max_slices}）")

        seen: set[int] = set()
        by_no: dict[int, Slice] = {}
        for item in self.slices:
            if item.no <= 0:
                raise ValueError(f"切片 no 非法：{item.no}")
            if item.no in seen:
                raise ValueError(f"切片 no 重复：{item.no}")
            if item.agent not in agents:
                raise ValueError(f"切片 {item.no} 的 Agent 未知：{item.agent}")
            if not item.description.strip():
                raise ValueError(f"切片 {item.no} 缺 description")
            spec = agents[item.agent]
            if spec.requires_approval and not item.approval_points:
                raise ValueError(
                    f"切片 {item.no}（{spec.name}）含对外动作，approval_points 不得为空"
                )
            seen.add(item.no)
            by_no[item.no] = item

        for item in self.slices:
            for dep in item.depends_on:
                if dep == item.no:
                    raise ValueError(f"切片 {item.no} 依赖自身")
                if dep not in by_no:
                    raise ValueError(f"切片 {item.no} 依赖不存在的切片 {dep}")

        self._check_acyclic(by_no)

    @staticmethod
    def _check_acyclic(by_no: dict[int, Slice]) -> None:
        indegree = {no: len(set(item.depends_on)) for no, item in by_no.items()}
        ready = [no for no, degree in indegree.items() if degree == 0]
        visited = 0
        while ready:
            no = ready.pop()
            visited += 1
            for item in by_no.values():
                if no in item.depends_on:
                    indegree[item.no] -= 1
                    if indegree[item.no] == 0:
                        ready.append(item.no)
        if visited != len(by_no):
            raise ValueError("切片依赖存在环")

    def execution_order(self) -> list[list[int]]:
        """拓扑分层：同层可并行，层间串行。"""
        remaining = {item.no: set(item.depends_on) for item in self.slices}
        layers: list[list[int]] = []
        while remaining:
            ready = sorted(no for no, deps in remaining.items() if not deps)
            if not ready:
                raise ValueError("切片依赖存在环")
            layers.append(ready)
            for no in ready:
                del remaining[no]
            for deps in remaining.values():
                deps.difference_update(ready)
        return layers


@dataclass
class EvalCase:
    """金标评测场景：固定输入 + rubric + 机械检查项。"""

    id: str
    surface: str
    input: str
    rubric: tuple[str, ...]
    deterministic_checks: tuple[str, ...] = ()
    note: str = ""

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("eval id 不能为空")
        if not self.surface.strip():
            raise ValueError(f"{self.id} 缺 surface")
        if not self.input.strip():
            raise ValueError(f"{self.id} 缺 input")
        if not self.rubric:
            raise ValueError(f"{self.id} 的 rubric 不能为空")
        if len(set(self.rubric)) != len(self.rubric):
            raise ValueError(f"{self.id} 的 rubric 含重复判据")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalCase":
        return cls(
            id=str(data.get("id", "")),
            surface=str(data.get("surface", "")),
            input=str(data.get("input", "")),
            rubric=tuple(str(x) for x in (data.get("rubric") or [])),
            deterministic_checks=tuple(str(x) for x in (data.get("deterministic_checks") or [])),
            note=str(data.get("note", "")),
        )
