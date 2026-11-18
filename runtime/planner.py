"""Manager 规划器：把路由结果变成可执行的切片计划。

对齐底座 Multi-Agent-E-commerce-System 的 SlicePlan：
- 切片带依赖声明（同层可并行、层间串行）；
- 对外动作切片必须有审批点；
- 依赖必须无环；
- 未知意图/需要澄清 → 抛 PlanningError，不硬编计划。
"""
from __future__ import annotations

from .agent_registry import DEFAULT_REGISTRY, UPSTREAM, WORKFLOW_ORDER, AgentRegistry
from .contracts import AgentSpec, Intent, RouteDecision, Slice, SlicePlan


class PlanningError(ValueError):
    """规划失败：需要澄清、意图未知、切片超限或依赖非法。"""


def _default_approval_point(spec: AgentSpec) -> str:
    return f"人工审批：{spec.name} 的对外动作"


class ManagerPlanner:
    """规则化 Manager：按 Agent 上游关系生成依赖，不依赖 LLM 也能跑。"""

    def __init__(self, registry: AgentRegistry = DEFAULT_REGISTRY, max_slices: int = 7) -> None:
        self.registry = registry
        self.max_slices = max_slices

    def plan(self, request: str, decision: RouteDecision) -> SlicePlan:
        if not decision.intents or Intent.CLARIFY in decision.intents:
            raise PlanningError("需要澄清：路由未确定意图")
        if Intent.UNKNOWN in decision.intents:
            raise PlanningError("需要澄清：存在未知意图")
        specs = self.registry.for_intents(decision.intents)
        if not specs:
            raise PlanningError(f"没有可用的 Agent：{decision.intents}")
        if len(specs) == 1:
            plan = self._single(request, specs[0])
        else:
            plan = self._multi(request, specs)
        self.registry.validate_plan(plan, max_slices=self.max_slices)
        return plan

    def plan_full_chain(self, request: str) -> SlicePlan:
        """全链路：01→02→03→04/05→06/07（按固定工作流顺序 + 上游依赖）。"""
        return self.plan(
            request,
            RouteDecision(
                intents=tuple(
                    self.registry.get(key).intent
                    for key in WORKFLOW_ORDER
                    if self.registry.get(key) is not None
                ),
                confidence=1.0,
                reason="显式全链路",
                compound=True,
            ),
        )

    def _single(self, request: str, spec: AgentSpec) -> SlicePlan:
        approval_points = [_default_approval_point(spec)] if spec.requires_approval else []
        return SlicePlan(
            slices=[
                Slice(
                    no=1,
                    agent=spec.key,
                    description=request.strip() or spec.description,
                    depends_on=[],
                    approval_points=approval_points,
                )
            ]
        )

    def _multi(self, request: str, specs: tuple[AgentSpec, ...]) -> SlicePlan:
        ordered = sorted(specs, key=lambda spec: self._order_index(spec.key))
        number_by_key = {spec.key: index for index, spec in enumerate(ordered, start=1)}
        slices: list[Slice] = []
        present = set(number_by_key)
        for index, spec in enumerate(ordered, start=1):
            upstream_keys = self._nearest_present(UPSTREAM.get(spec.key, ()), present, set())
            dependencies = [number_by_key[key] for key in upstream_keys]
            approval_points = [_default_approval_point(spec)] if spec.requires_approval else []
            slices.append(
                Slice(
                    no=index,
                    agent=spec.key,
                    description=f"{spec.description}（用户请求：{request.strip()[:120]}）",
                    depends_on=sorted(set(dependencies)),
                    approval_points=approval_points,
                )
            )
        return SlicePlan(slices=slices)

    def _nearest_present(
        self,
        upstream_keys: tuple[str, ...],
        present: set[str],
        seen: set[str],
    ) -> set[str]:
        """找"最近的在计划中的上游"：直接上游缺失时，沿上游链向上找。

        例：只做 02+04（跳过 03）时，04 的最近上游是 02，而不是无依赖。
        """
        found: set[str] = set()
        for key in upstream_keys:
            if key in seen:
                continue
            if key in present:
                found.add(key)
                continue
            found |= self._nearest_present(UPSTREAM.get(key, ()), present, seen | {key})
        return found

    def _order_index(self, agent_key: str) -> int:
        try:
            return WORKFLOW_ORDER.index(agent_key)
        except ValueError:
            return len(WORKFLOW_ORDER)
