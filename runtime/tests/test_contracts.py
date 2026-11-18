import unittest

from runtime.contracts import EvalCase, Intent, RouteDecision, Slice, SlicePlan


class ContractTest(unittest.TestCase):
    def test_route_decision_roundtrip(self):
        decision = RouteDecision(
            intents=(Intent.MARKET_RESEARCH, Intent.PRODUCT_STRATEGY),
            confidence=0.82,
            entities={"platform": "shopee"},
            missing_slots=("cost_structure",),
            reason="test",
            compound=True,
        )
        restored = RouteDecision.from_dict(decision.to_dict())
        self.assertEqual(restored.intents, decision.intents)
        self.assertAlmostEqual(restored.confidence, 0.82)
        self.assertTrue(restored.compound)

    def test_unknown_intent_falls_back(self):
        restored = RouteDecision.from_dict({
            "intents": ["not_an_intent"],
            "confidence": 2.0,
        })
        self.assertEqual(restored.intents, (Intent.UNKNOWN,))
        self.assertEqual(restored.confidence, 1.0)

    def test_slice_plan_roundtrip(self):
        plan = SlicePlan(slices=[Slice(1, "market_research", "看市场")])
        restored = SlicePlan.from_dict(plan.to_dict())
        self.assertEqual(restored.slices[0].agent, "market_research")

    def test_eval_case_validation(self):
        case = EvalCase(
            id="case-1",
            surface="01 市场分析",
            input="分析类目",
            rubric=("判据 1", "判据 2"),
        )
        case.validate()
        bad = EvalCase(id="case-2", surface="01", input="x", rubric=("重复", "重复"))
        with self.assertRaises(ValueError):
            bad.validate()

    def test_eval_case_roundtrip(self):
        raw = {
            "id": "case-1",
            "surface": "06 广告诊断",
            "input": "诊断广告",
            "rubric": ["判据 1"],
            "deterministic_checks": ["number_traceable"],
        }
        case = EvalCase.from_dict(raw)
        self.assertEqual(case.deterministic_checks, ("number_traceable",))


if __name__ == "__main__":
    unittest.main()
