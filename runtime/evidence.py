"""证据链与引用校验（机械防伪引）。

对齐底座 Multi-Agent-E-commerce-System 的引用设计：
- 每个结论/数字都挂证据（来源 + 定位）；
- 正文里的 [n] 必须能解析到证据清单；
- 解析不到 = 疑似伪造，直接报错；
- 没有证据时判「不适用」，而不是「通过」。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

ALLOWED_EVIDENCE_TYPES = {
    "spec_table",
    "data_file",
    "ad_report",
    "review",
    "fee_rule",
    "platform_rule",
    "metric_report",
    "manual",
}

_CITATION = re.compile(r"\[(\d+)\]")


@dataclass
class EvidenceItem:
    claim_id: str
    claim: str
    evidence_type: str
    source: str
    locator: str
    retrieved_at: str = ""
    confidence: float | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.claim_id.strip():
            errors.append("claim_id 不能为空")
        if not self.claim.strip():
            errors.append(f"{self.claim_id}: claim 不能为空")
        if self.evidence_type not in ALLOWED_EVIDENCE_TYPES:
            errors.append(
                f"{self.claim_id}: evidence_type 非法（{self.evidence_type}；"
                f"可用 {sorted(ALLOWED_EVIDENCE_TYPES)}）"
            )
        if not self.source.strip():
            errors.append(f"{self.claim_id}: source 不能为空")
        if not self.locator.strip():
            errors.append(f"{self.claim_id}: locator 不能为空")
        if self.retrieved_at:
            try:
                date.fromisoformat(self.retrieved_at)
            except ValueError:
                errors.append(f"{self.claim_id}: retrieved_at 必须是 YYYY-MM-DD")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            errors.append(f"{self.claim_id}: confidence 必须在 0~1")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceItem":
        raw_confidence = data.get("confidence")
        return cls(
            claim_id=str(data.get("claim_id", "")),
            claim=str(data.get("claim", "")),
            evidence_type=str(data.get("evidence_type", "")),
            source=str(data.get("source", "")),
            locator=str(data.get("locator", "")),
            retrieved_at=str(data.get("retrieved_at", "")),
            confidence=float(raw_confidence) if raw_confidence is not None else None,
        )


@dataclass
class EvidenceBlock:
    items: list[EvidenceItem] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.items:
            errors.append("证据块为空：没有证据的结论不许交付")
        seen: set[str] = set()
        for item in self.items:
            errors.extend(item.validate())
            if item.claim_id in seen:
                errors.append(f"claim_id 重复：{item.claim_id}")
            seen.add(item.claim_id)
        return errors

    def by_claim(self, claim_id: str) -> EvidenceItem | None:
        for item in self.items:
            if item.claim_id == claim_id:
                return item
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.to_dict() for item in self.items]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceBlock":
        raw = data.get("items") if isinstance(data, dict) else data
        return cls(items=[EvidenceItem.from_dict(item) for item in (raw or [])])


@dataclass(frozen=True)
class CitationCheck:
    ok: bool
    used_indices: tuple[int, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "used_indices": list(self.used_indices),
            "errors": list(self.errors),
        }


def extract_citation_markers(text: str) -> tuple[int, ...]:
    """提取正文里的 [n] 编号（按出现顺序去重）。"""
    seen: list[int] = []
    for match in _CITATION.finditer(text or ""):
        number = int(match.group(1))
        if number not in seen:
            seen.append(number)
    return tuple(seen)


def check_citations(
    text: str,
    block: EvidenceBlock,
    *,
    require_all_cited: bool = False,
) -> CitationCheck:
    """机械校验：正文引用 [n] 必须解析到证据清单第 n 条。"""
    errors = list(block.validate())
    markers = extract_citation_markers(text)
    total = len(block.items)

    for number in markers:
        if number < 1 or number > total:
            errors.append(f"引用 [{number}] 解析不到：证据清单只有 {total} 条")

    if require_all_cited:
        uncovered = [
            item.claim_id
            for index, item in enumerate(block.items, start=1)
            if index not in markers
        ]
        if uncovered:
            errors.append(f"以下证据未被正文引用：{uncovered}")

    return CitationCheck(ok=not errors, used_indices=markers, errors=tuple(errors))


def check_claim_traceability(
    claims: dict[str, str],
    block: EvidenceBlock,
) -> CitationCheck:
    """按 claim_id 校验：每个声明都必须有证据，且证据里的 claim 文案一致。"""
    errors = list(block.validate())
    for claim_id, claim_text in claims.items():
        item = block.by_claim(claim_id)
        if item is None:
            errors.append(f"声明 {claim_id} 缺证据")
            continue
        if item.claim.strip() != claim_text.strip():
            errors.append(f"声明 {claim_id} 与证据文案不一致")
    return CitationCheck(ok=not errors, used_indices=(), errors=tuple(errors))
