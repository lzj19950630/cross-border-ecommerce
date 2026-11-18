import tempfile
import unittest
from pathlib import Path

from runtime.engine import RuntimeEngine
from runtime.integrations.sqlalchemy_store import SQLAlchemyStore


class SQLAlchemyStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.url = f"sqlite:///{Path(self.tmp.name) / 'runtime.db'}"

    def tearDown(self):
        self.tmp.cleanup()

    def test_cross_engine_resume(self):
        store1 = SQLAlchemyStore(self.url)
        engine1 = RuntimeEngine(store=store1)
        task = engine1.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "interrupted")
        store1.close()

        store2 = SQLAlchemyStore(self.url)
        engine2 = RuntimeEngine(store=store2)
        persisted = engine2.get_task(task.thread_id)
        self.assertEqual(persisted.status, "interrupted")
        resumed = engine2.resume(task.thread_id, decision="approve")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(len(store2.list_audits(task.thread_id)), 1)
        store2.close()

    def test_full_chain_and_list(self):
        store = SQLAlchemyStore(self.url)
        engine = RuntimeEngine(store=store)
        task = engine.run("走一遍完整链路")
        self.assertEqual(task.status, "interrupted")
        resumed = engine.resume(task.thread_id, decision="approve")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(len(resumed.artifacts), 7)
        self.assertEqual(len(store.list_tasks()), 1)
        store.close()


if __name__ == "__main__":
    unittest.main()
