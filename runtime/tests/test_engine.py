import unittest

from runtime.agent_runners import MarketResearchRunner, RunnerRegistry
from runtime.engine import RuntimeEngine


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = RuntimeEngine()

    def test_single_agent_completed(self):
        task = self.engine.run("帮我看下巴西站滑板车类目的市场容量和价格带")
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.slices[0]["agent"], "market_research")
        self.assertIn("market_research", task.artifacts)
        self.assertIn("market_research", task.evidence)
        self.assertIn("started_at", task.slices[0])
        self.assertIn("elapsed_ms", task.slices[0])

    def test_compound_plan_runs_in_order(self):
        task = self.engine.run("先分析类目市场，然后定价")
        self.assertEqual(task.status, "completed")
        self.assertEqual([item["agent"] for item in task.slices],
                         ["market_research", "product_strategy"])
        self.assertEqual(task.layers, [[1], [2]])

    def test_advertising_interrupt_and_approve(self):
        task = self.engine.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "interrupted")
        self.assertTrue(task.pending_envelopes)
        envelope_id = task.pending_envelopes[0]
        self.assertEqual(task.envelopes[envelope_id]["decision"], "pending")

        resumed = self.engine.resume(task.thread_id, decision="approve", comment="同意降出价")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.pending_envelopes, [])
        self.assertEqual(resumed.envelopes[envelope_id]["decision"], "approved")
        self.assertTrue(resumed.envelopes[envelope_id]["decided_by"])
        self.assertEqual(len(self.engine.store.audits), 1)
        self.assertEqual(self.engine.store.audits[0]["apply"]["mode"], "dry_run")

    def test_advertising_reject(self):
        task = self.engine.run("广告 ROAS 太低，怎么降预算")
        resumed = self.engine.resume(task.thread_id, decision="reject", comment="先观察")
        self.assertEqual(resumed.status, "rejected")
        self.assertEqual(resumed.pending_envelopes, [])
        self.assertEqual(self.engine.store.audits[0]["decision"], "reject")

    def test_drift_blocks_approval(self):
        task = self.engine.run("广告 ROAS 太低，怎么降预算")
        envelope_id = task.pending_envelopes[0]
        envelope = self.engine.store.get_envelope(envelope_id)
        target = envelope.actions[0].target
        with self.assertRaises(ValueError) as ctx:
            self.engine.resume(
                task.thread_id,
                decision="approve",
                current_snapshots={target: {"cpc": 0.99}},
            )
        self.assertIn("快照漂移", str(ctx.exception))
        self.assertEqual(self.engine.get_task(task.thread_id).status, "interrupted")

    def test_stub_agent_blocks(self):
        engine = RuntimeEngine(runners=RunnerRegistry({"market_research": MarketResearchRunner()}))
        task = engine.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "blocked")
        self.assertIn("advertising", task.error)

    def test_full_chain_interrupts_at_06_and_resumes(self):
        task = self.engine.run("走一遍完整链路")
        self.assertEqual(task.status, "interrupted")
        self.assertEqual(
            [item["agent"] for item in task.slices],
            [
                "market_research", "product_strategy", "listing_creative",
                "product_image", "product_video", "advertising",
            ],
        )
        self.assertTrue(task.pending_envelopes)

        resumed = self.engine.resume(task.thread_id, decision="approve", comment="同意")
        self.assertEqual(resumed.status, "completed")
        self.assertIn("review_analysis", [item["agent"] for item in resumed.slices])
        self.assertEqual(len(resumed.artifacts), 7)

    def test_clarify(self):
        task = self.engine.run("今天天气怎么样")
        self.assertEqual(task.status, "clarify")

    def test_cancel_interrupted_task(self):
        task = self.engine.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "interrupted")
        cancelled = self.engine.cancel(task.thread_id)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(cancelled.pending_envelopes, [])

    def test_custom_apply(self):
        applied = []

        def apply_fn(envelope):
            applied.append(envelope.envelope_id)
            return {"applied": True, "mode": "test"}

        engine = RuntimeEngine(apply_fn=apply_fn)
        task = engine.run("广告 ROAS 太低，怎么降预算")
        engine.resume(task.thread_id, decision="approve")
        self.assertEqual(len(applied), 1)


if __name__ == "__main__":
    unittest.main()
