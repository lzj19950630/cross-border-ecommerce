import tempfile
import unittest
from pathlib import Path

from runtime.executors import SequentialLayerExecutor, langgraph_available
from runtime.storage import InMemoryStore, SQLiteStore
from runtime.supervisor import LangGraphSupervisor


@unittest.skipUnless(langgraph_available(), "langgraph not installed")
class SupervisorTest(unittest.TestCase):
    def setUp(self):
        self.supervisor = LangGraphSupervisor(
            store=InMemoryStore(),
            executor=SequentialLayerExecutor(),
            checkpointer="memory",
        )

    def test_single_agent_completed(self):
        task = self.supervisor.run("帮我看下巴西站滑板车类目的市场容量和价格带")
        self.assertEqual(task.status, "completed")
        self.assertIn("market_research", task.artifacts)

    def test_advertising_interrupt_and_approve(self):
        task = self.supervisor.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "interrupted")
        self.assertTrue(task.pending_envelopes)
        envelope_id = task.pending_envelopes[0]

        resumed = self.supervisor.resume(task.thread_id, decision="approve", comment="ok")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.pending_envelopes, [])
        self.assertEqual(resumed.envelopes[envelope_id]["decision"], "approved")

    def test_full_chain_interrupt_and_resume(self):
        task = self.supervisor.run("走一遍完整链路")
        self.assertEqual(task.status, "interrupted")
        self.assertEqual(
            [item["agent"] for item in task.slices],
            [
                "market_research", "product_strategy", "listing_creative",
                "product_image", "product_video", "advertising",
            ],
        )
        resumed = self.supervisor.resume(task.thread_id, decision="approve")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(len(resumed.artifacts), 7)
        self.assertEqual(resumed.slices[-1]["agent"], "review_analysis")

    def test_reject(self):
        task = self.supervisor.run("广告 ROAS 太低，怎么降预算")
        resumed = self.supervisor.resume(task.thread_id, decision="reject", comment="不动")
        self.assertEqual(resumed.status, "rejected")

    def test_clarify(self):
        task = self.supervisor.run("今天天气怎么样")
        self.assertEqual(task.status, "clarify")

    def test_cross_store_resume_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "runtime.db")
            store1 = SQLiteStore(db)
            sup1 = LangGraphSupervisor(
                store=store1, executor=SequentialLayerExecutor(), checkpointer="memory"
            )
            task = sup1.run("广告 ROAS 太低，怎么降预算")
            self.assertEqual(task.status, "interrupted")
            store1.close()

            store2 = SQLiteStore(db)
            sup2 = LangGraphSupervisor(
                store=store2, executor=SequentialLayerExecutor(), checkpointer="memory"
            )
            resumed = sup2.resume(task.thread_id, decision="approve")
            self.assertEqual(resumed.status, "completed")
            self.assertTrue(any("checkpoint" in message for message in resumed.messages))
            store2.close()

    def test_native_sqlite_checkpointer(self):
        try:
            import langgraph.checkpoint.sqlite  # noqa: F401
        except ImportError:
            self.skipTest("langgraph-checkpoint-sqlite 未安装")
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "runtime.db")
            cp = str(Path(td) / "checkpoints.db")
            store1 = SQLiteStore(db)
            sup1 = LangGraphSupervisor(
                store=store1, executor=SequentialLayerExecutor(),
                checkpointer="sqlite", checkpoint_db=cp,
            )
            task = sup1.run("广告 ROAS 太低，怎么降预算")
            self.assertEqual(task.status, "interrupted")
            sup1.close()
            store1.close()

            store2 = SQLiteStore(db)
            sup2 = LangGraphSupervisor(
                store=store2, executor=SequentialLayerExecutor(),
                checkpointer="sqlite", checkpoint_db=cp,
            )
            self.assertTrue(sup2._graph.get_state(sup2._config(task.thread_id)).values)
            resumed = sup2.resume(task.thread_id, decision="approve")
            self.assertEqual(resumed.status, "completed")
            self.assertFalse(any("checkpoint" in m for m in resumed.messages))
            sup2.close()
            store2.close()

    def test_resume_without_pending(self):
        task = self.supervisor.run("看类目市场容量")
        with self.assertRaises(ValueError):
            self.supervisor.resume(task.thread_id)


if __name__ == "__main__":
    unittest.main()
