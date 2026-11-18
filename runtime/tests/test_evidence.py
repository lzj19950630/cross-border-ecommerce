import unittest

from runtime.evidence import (
    EvidenceBlock,
    EvidenceItem,
    check_citations,
    check_claim_traceability,
    extract_citation_markers,
)


def block() -> EvidenceBlock:
    return EvidenceBlock(items=[
        EvidenceItem(
            claim_id="C-06-01",
            claim="该组 CTR 为 1.2%，低于 2% 基准",
            evidence_type="ad_report",
            source="sample-ad-report.csv",
            locator="row 18 / group=G2",
            retrieved_at="2026-11-18",
            confidence=1.0,
        ),
        EvidenceItem(
            claim_id="C-06-02",
            claim="Shopee BR 佣金按价格分档",
            evidence_type="fee_rule",
            source="platform_fees.json",
            locator="shopee_br.tiers",
            retrieved_at="2026-11-18",
        ),
    ])


class EvidenceTest(unittest.TestCase):
    def test_valid_block(self):
        self.assertEqual(block().validate(), [])

    def test_duplicate_claim_id(self):
        data = block()
        data.items[1].claim_id = data.items[0].claim_id
        errors = data.validate()
        self.assertTrue(any("claim_id 重复" in error for error in errors))

    def test_invalid_type(self):
        data = block()
        data.items[0].evidence_type = "vibes"
        errors = data.validate()
        self.assertTrue(any("evidence_type 非法" in error for error in errors))

    def test_invalid_date_and_confidence(self):
        data = block()
        data.items[0].retrieved_at = "18/11/2026"
        data.items[0].confidence = 1.5
        errors = data.validate()
        self.assertTrue(any("YYYY-MM-DD" in error for error in errors))
        self.assertTrue(any("confidence" in error for error in errors))

    def test_citations_ok(self):
        result = check_citations("结论 A [1]，结论 B [2]。", block())
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.used_indices, (1, 2))

    def test_citation_out_of_range(self):
        result = check_citations("结论 A [1]，结论 C [3]。", block())
        self.assertFalse(result.ok)
        self.assertTrue(any("解析不到" in error for error in result.errors))

    def test_require_all_cited(self):
        result = check_citations("只有结论 A [1]。", block(), require_all_cited=True)
        self.assertFalse(result.ok)
        self.assertTrue(any("未被正文引用" in error for error in result.errors))

    def test_empty_block(self):
        result = check_citations("没有任何引用。", EvidenceBlock())
        self.assertFalse(result.ok)
        self.assertTrue(any("证据块为空" in error for error in result.errors))

    def test_extract_markers(self):
        self.assertEqual(extract_citation_markers("[1] [2] [1] [3]"), (1, 2, 3))

    def test_claim_traceability(self):
        claims = {
            "C-06-01": "该组 CTR 为 1.2%，低于 2% 基准",
            "C-06-02": "Shopee BR 佣金按价格分档",
        }
        result = check_claim_traceability(claims, block())
        self.assertTrue(result.ok, result.errors)

    def test_claim_traceability_missing(self):
        result = check_claim_traceability({"C-06-99": "没有证据的结论"}, block())
        self.assertFalse(result.ok)
        self.assertTrue(any("缺证据" in error for error in result.errors))

    def test_claim_traceability_mismatch(self):
        result = check_claim_traceability({"C-06-01": "与证据不一致的文案"}, block())
        self.assertFalse(result.ok)
        self.assertTrue(any("不一致" in error for error in result.errors))

    def test_roundtrip(self):
        restored = EvidenceBlock.from_dict(block().to_dict())
        self.assertEqual(len(restored.items), 2)
        self.assertEqual(restored.items[0].claim_id, "C-06-01")


if __name__ == "__main__":
    unittest.main()
