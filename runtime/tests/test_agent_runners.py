import unittest

from runtime.agent_runners import (
    AdvertisingRunner,
    AgentContext,
    ListingCreativeRunner,
    MarketResearchRunner,
    ProductImageRunner,
    ProductStrategyRunner,
    ProductVideoRunner,
    ReviewAnalysisRunner,
    StubRunner,
)
from runtime.contracts import Slice


def context(agent: str, **inputs) -> AgentContext:
    return AgentContext(
        thread_id="test-thread",
        request="test",
        slice=Slice(1, agent, "test"),
        inputs=inputs,
    )


class RunnerTest(unittest.TestCase):
    def test_market_research(self):
        result = MarketResearchRunner().run(context("market_research"))
        self.assertEqual(result.status, "ok", result.error)
        self.assertIn("market_capacity", result.artifact)
        self.assertEqual(result.evidence.validate(), [])
        self.assertIsNone(result.envelope)

    def test_product_strategy(self):
        result = ProductStrategyRunner().run(context("product_strategy"))
        self.assertEqual(result.status, "ok", result.error)
        self.assertEqual(len(result.artifact["skus"]), 4)
        self.assertEqual(result.evidence.validate(), [])
        self.assertIsNone(result.envelope)

    def test_advertising_envelope(self):
        result = AdvertisingRunner().run(context("advertising"))
        self.assertEqual(result.status, "ok", result.error)
        self.assertIsNotNone(result.envelope)
        envelope = result.envelope
        assert envelope is not None
        self.assertEqual(envelope.validate(), [])
        self.assertEqual(envelope.risk.value, "approval")
        self.assertTrue(envelope.actions)
        self.assertEqual(envelope.actions[0].action, "ad.set_bid")
        self.assertEqual(envelope.actions[0].before, {"cpc": 0.25})

    def test_listing_creative(self):
        result = ListingCreativeRunner().run(context("listing_creative"))
        self.assertEqual(result.status, "ok", result.error)
        self.assertTrue(result.artifact["title_lint"]["ok"])
        self.assertTrue(result.artifact["spec_consistency"]["ok"])
        self.assertEqual(result.evidence.validate(), [])

    def test_product_image(self):
        result = ProductImageRunner().run(context("product_image"))
        self.assertEqual(result.status, "ok", result.error)
        self.assertTrue(result.artifact["compliance_ok"])
        self.assertEqual(len(result.artifact["image_plan"]), 9)
        self.assertEqual(result.evidence.validate(), [])

    def test_product_video(self):
        result = ProductVideoRunner().run(context("product_video"))
        self.assertEqual(result.status, "ok", result.error)
        self.assertTrue(result.artifact["within_tolerance"])
        self.assertEqual(result.evidence.validate(), [])

    def test_review_analysis(self):
        result = ReviewAnalysisRunner().run(context("review_analysis"))
        self.assertEqual(result.status, "ok", result.error)
        self.assertEqual(result.artifact["reviews"]["attribution_mismatch"], 0)
        self.assertEqual(result.evidence.validate(), [])

    def test_stub_runner_blocks(self):
        result = StubRunner().run(context("listing_creative"))
        self.assertEqual(result.status, "blocked")
        self.assertIn("Phase 2", result.error)


if __name__ == "__main__":
    unittest.main()
