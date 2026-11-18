import unittest

from runtime.contracts import Intent
from runtime.intent_router import IntentRouter


class IntentRouterTest(unittest.TestCase):
    def setUp(self):
        self.router = IntentRouter()

    def test_market_research(self):
        decision = self.router.route("帮我看下巴西站电动滑板车类目的市场容量和价格带")
        self.assertEqual(decision.intents, (Intent.MARKET_RESEARCH,))
        self.assertGreaterEqual(decision.confidence, 0.6)

    def test_product_strategy(self):
        decision = self.router.route("这个产品成本 100，帮我算定价和盈亏线")
        self.assertEqual(decision.intents, (Intent.PRODUCT_STRATEGY,))

    def test_advertising(self):
        decision = self.router.route("广告 ROAS 太低，预算怎么降")
        self.assertEqual(decision.intents, (Intent.ADVERTISING,))

    def test_compound_request(self):
        decision = self.router.route("先分析类目市场，然后定价，再做主图和广告")
        self.assertTrue(decision.compound)
        self.assertEqual(
            decision.intents,
            (
                Intent.MARKET_RESEARCH,
                Intent.PRODUCT_STRATEGY,
                Intent.PRODUCT_IMAGE,
                Intent.ADVERTISING,
            ),
        )

    def test_explicit_full_chain_routes_all_agents(self):
        decision = self.router.route("走一遍完整链路")
        self.assertTrue(decision.compound)
        self.assertEqual(len(decision.intents), 7)
        self.assertEqual(decision.intents[0], Intent.MARKET_RESEARCH)

    def test_unknown_goes_clarify(self):
        decision = self.router.route("今天天气怎么样")
        self.assertEqual(decision.intents, (Intent.CLARIFY,))
        self.assertEqual(decision.confidence, 0.0)

    def test_ambiguous_goes_clarify_with_candidates(self):
        decision = self.router.route("类目和配置怎么弄")
        self.assertEqual(decision.intents, (Intent.CLARIFY,))
        self.assertTrue(decision.entities.get("candidates"))

    def test_llm_fallback(self):
        def fake_llm(text, context):
            return {
                "intents": ["review_analysis"],
                "confidence": 0.92,
                "entities": {"source": "llm"},
                "reason": "looks like review work",
            }

        router = IntentRouter(llm_router=fake_llm)
        decision = router.route("帮我处理一下这个买家的问题")
        self.assertEqual(decision.intents, (Intent.REVIEW_ANALYSIS,))
        self.assertIn("LLM 路由", decision.reason)

    def test_llm_failure_goes_clarify(self):
        def bad_llm(text, context):
            raise RuntimeError("llm down")

        router = IntentRouter(llm_router=bad_llm)
        decision = router.route("帮我处理一下这个买家的问题")
        self.assertEqual(decision.intents, (Intent.CLARIFY,))
        self.assertIn("LLM 路由失败", decision.reason)

    def test_empty_input(self):
        decision = self.router.route("")
        self.assertEqual(decision.intents, (Intent.CLARIFY,))

    def test_english_word_boundary(self):
        # "ad" 不能命中 "read" / "report"
        decision = self.router.route("please read the report")
        self.assertEqual(decision.intents, (Intent.CLARIFY,))


if __name__ == "__main__":
    unittest.main()
