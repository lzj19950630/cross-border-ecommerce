import tempfile
import unittest
from pathlib import Path

from runtime.engine import RuntimeEngine
from runtime.storage import SQLiteStore, TaskRecord


class SQLiteStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "runtime.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_task_roundtrip(self):
        task = TaskRecord(thread_id="t1", request="demo", status="interrupted")
        task.artifacts["advertising"] = {"total": {"roas": 1.84}}
        restored = TaskRecord.from_dict(task.to_dict())
        self.assertEqual(restored.thread_id, "t1")
        self.assertEqual(restored.status, "interrupted")
        self.assertEqual(restored.artifacts["advertising"]["total"]["roas"], 1.84)

    def test_cross_engine_resume(self):
        store1 = SQLiteStore(self.db)
        engine1 = RuntimeEngine(store=store1)
        task = engine1.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "interrupted")
        store1.close()

        store2 = SQLiteStore(self.db)
        engine2 = RuntimeEngine(store=store2)
        persisted = engine2.get_task(task.thread_id)
        self.assertEqual(persisted.status, "interrupted")
        self.assertTrue(persisted.pending_envelopes)
        self.assertIn("advertising", persisted.artifacts)

        resumed = engine2.resume(task.thread_id, decision="approve")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.pending_envelopes, [])
        self.assertEqual(len(store2.list_audits(task.thread_id)), 1)
        store2.close()

    def test_full_chain_persists_all_artifacts(self):
        store1 = SQLiteStore(self.db)
        engine1 = RuntimeEngine(store=store1)
        task = engine1.run("走一遍完整链路")
        self.assertEqual(task.status, "interrupted")
        store1.close()

        store2 = SQLiteStore(self.db)
        engine2 = RuntimeEngine(store=store2)
        resumed = engine2.resume(task.thread_id, decision="approve")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(len(resumed.artifacts), 7)
        self.assertEqual(
            [item["agent"] for item in resumed.slices][-1],
            "review_analysis",
        )
        store2.close()

    def test_token_revocation(self):
        import time

        store = SQLiteStore(self.db)
        store.revoke_token("jti-1", time.time() + 60)
        self.assertTrue(store.is_token_revoked("jti-1"))
        self.assertFalse(store.is_token_revoked("jti-2"))
        store.close()

    def test_list_tasks(self):
        store = SQLiteStore(self.db)
        store.create_task("one")
        store.create_task("two")
        self.assertEqual(len(store.list_tasks()), 2)
        store.close()


if __name__ == "__main__":
    unittest.main()
