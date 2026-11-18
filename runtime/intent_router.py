"""意图识别与路由（规则优先，LLM 兜底）。

对齐底座 Multi-Agent-E-commerce-System 的做法：
- Manager 负责"复杂任务切片"，本 Router 负责"先判断这是哪件事"；
- 规则关键词优先（便宜、确定、可测），LLM 只在无命中/歧义时兜底；
- LLM 失败或置信度低 → 返回 CLARIFY，让上层追问，不硬路由。
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .agent_registry import DEFAULT_REGISTRY, WORKFLOW_ORDER, AgentRegistry
from .contracts import Intent, RouteDecision

LLMRouter = Callable[[str, dict[str, Any]], dict[str, Any]]

COMPOUND_MARKERS = (
    "然后", "接着", "再", "并且", "同时", "最后", "之后", "顺便",
    "全流程", "完整链路", "一条龙", "从选品到", "从市场到",
)

EXPLICIT_MULTI = (
    "全流程", "完整链路", "一条龙", "从选品到", "从市场到", "整套",
)


def _keyword_present(text: str, keyword: str) -> bool:
    """中文按子串；英文按词边界（避免 ad 命中 read）。"""
    keyword = keyword.strip()
    if not keyword:
        return False
    if keyword.isascii():
        pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
        return re.search(pattern, text.lower()) is not None
    return keyword in text


class IntentRouter:
    """规则优先的意图路由器。"""

    def __init__(
        self,
        registry: AgentRegistry = DEFAULT_REGISTRY,
        llm_router: LLMRouter | None = None,
        threshold: float = 0.6,
    ) -> None:
        self.registry = registry
        self.llm_router = llm_router
        self.threshold = threshold

    def route(self, text: str, context: dict[str, Any] | None = None) -> RouteDecision:
        text = (text or "").strip()
        if not text:
            return RouteDecision(
                intents=(Intent.CLARIFY,),
                confidence=0.0,
                reason="输入为空",
            )

        scores, matched = self._score(text)
        if not scores:
            # 显式"全流程/完整链路"但没有具体 Agent 关键词 → 路由到全部 7 个 Agent
            if any(marker in text for marker in EXPLICIT_MULTI):
                specs = [self.registry.get(key) for key in WORKFLOW_ORDER]
                return RouteDecision(
                    intents=tuple(spec.intent for spec in specs if spec is not None),
                    confidence=0.9,
                    reason="显式全流程请求，路由到全部 Agent",
                    compound=True,
                )
            return self._llm_or_clarify(text, context, "无关键词命中")

        ordered = sorted(
            scores.items(),
            key=lambda item: (-item[1], self._order_index(item[0])),
        )
        top_key, top_score = ordered[0]
        second_key, second_score = ordered[1] if len(ordered) > 1 else (None, 0)

        explicit_multi = any(marker in text for marker in EXPLICIT_MULTI)
        compound_marker = any(marker in text for marker in COMPOUND_MARKERS)

        if explicit_multi or (compound_marker and second_score > 0):
            intents = self._intents_for(ordered)
            return RouteDecision(
                intents=intents,
                confidence=min(0.95, 0.5 + 0.1 * len(intents)),
                entities={"matched_keywords": matched},
                reason="命中复合任务标记，转 Manager 切片",
                compound=True,
            )

        if second_score > 0 and top_score <= second_score:
            return self._llm_or_clarify(
                text,
                context,
                f"意图并列：{top_key} / {second_key}",
                candidates=self._candidate_payload(ordered),
            )

        confidence = 1.0 if second_score == 0 else top_score / (top_score + second_score)
        if confidence < self.threshold:
            return self._llm_or_clarify(
                text,
                context,
                f"置信度不足：{confidence:.2f}",
                candidates=self._candidate_payload(ordered),
            )

        spec = self.registry.get(top_key)
        return RouteDecision(
            intents=(spec.intent,),
            confidence=round(confidence, 4),
            entities={"matched_keywords": matched.get(top_key, [])},
            reason=f"关键词命中：{top_key}（{top_score} 个）",
        )

    def _score(self, text: str) -> tuple[dict[str, int], dict[str, list[str]]]:
        scores: dict[str, int] = {}
        matched: dict[str, list[str]] = {}
        for spec in self.registry.all():
            hits = [keyword for keyword in spec.keywords if _keyword_present(text, keyword)]
            if hits:
                scores[spec.key] = len(hits)
                matched[spec.key] = hits
        return scores, matched

    def _intents_for(self, ordered: list[tuple[str, int]]) -> tuple[Intent, ...]:
        intents: list[Intent] = []
        for key, _score in ordered:
            spec = self.registry.get(key)
            if spec.intent not in intents:
                intents.append(spec.intent)
        return tuple(intents)

    def _candidate_payload(self, ordered: list[tuple[str, int]]) -> list[dict[str, Any]]:
        return [
            {"agent": key, "intent": self.registry.get(key).intent.value, "score": score}
            for key, score in ordered
        ]

    def _llm_or_clarify(
        self,
        text: str,
        context: dict[str, Any] | None,
        reason: str,
        candidates: list[dict[str, Any]] | None = None,
    ) -> RouteDecision:
        if self.llm_router is not None:
            try:
                raw = self.llm_router(text, context or {})
                decision = RouteDecision.from_dict(raw)
                if Intent.UNKNOWN in decision.intents or Intent.CLARIFY in decision.intents:
                    return self._clarify(reason + "；LLM 也未能确定", candidates)
                if decision.confidence < self.threshold:
                    return self._clarify(
                        f"{reason}；LLM 置信度不足（{decision.confidence:.2f}）",
                        candidates,
                    )
                return RouteDecision(
                    intents=decision.intents,
                    confidence=decision.confidence,
                    entities=decision.entities,
                    missing_slots=decision.missing_slots,
                    reason=f"LLM 路由：{decision.reason}",
                    compound=decision.compound,
                )
            except Exception as exc:  # LLM 失败 → 澄清，不硬路由
                return self._clarify(f"{reason}；LLM 路由失败：{type(exc).__name__}", candidates)
        return self._clarify(reason, candidates)

    @staticmethod
    def _clarify(reason: str, candidates: list[dict[str, Any]] | None) -> RouteDecision:
        return RouteDecision(
            intents=(Intent.CLARIFY,),
            confidence=0.0,
            entities={"candidates": candidates or []},
            reason=reason,
        )

    @staticmethod
    def _order_index(agent_key: str) -> int:
        try:
            return WORKFLOW_ORDER.index(agent_key)
        except ValueError:
            return len(WORKFLOW_ORDER)
