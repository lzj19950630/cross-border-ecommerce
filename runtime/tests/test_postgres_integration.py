import os
import unittest

from runtime.engine import RuntimeEngine
from runtime.executors import SequentialLayerExecutor
from runtime.integrations.sqlalchemy_store import SQLAlchemyStore
from runtime.supervisor import LangGraphSupervisor

PG_URL = os.environ.get("RUNTIME_TEST_POSTGRES_URL")
PG_DSN = os.environ.get("RUNTIME_TEST_POSTGRES_DSN")


@unittest.skipUnless(PG_URL, "RUNTIME_TEST_POSTGRES_URL 未设置")
class PostgresStoreIntegrationTest(unittest.TestCase):
    def test_cross_engine_resume(self):
        store1 = SQLAlchemyStore(PG_URL)
        engine1 = RuntimeEngine(store=store1)
        task = engine1.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "interrupted")
        store1.close()

        store2 = SQLAlchemyStore(PG_URL)
        engine2 = RuntimeEngine(store=store2)
        resumed = engine2.resume(task.thread_id, decision="approve")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(len(store2.list_audits(task.thread_id)), 1)
        store2.close()


@unittest.skipUnless(PG_DSN, "RUNTIME_TEST_POSTGRES_DSN 未设置")
class PostgresCheckpointerIntegrationTest(unittest.TestCase):
    def test_native_durable_resume(self):
        store1 = SQLAlchemyStore(PG_URL)
        sup1 = LangGraphSupervisor(
            store=store1,
            executor=SequentialLayerExecutor(),
            checkpointer="postgres",
            checkpoint_db=PG_DSN,
        )
        task = sup1.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "interrupted")
        sup1.close()
        store1.close()

        store2 = SQLAlchemyStore(PG_URL)
        sup2 = LangGraphSupervisor(
            store=store2,
            executor=SequentialLayerExecutor(),
            checkpointer="postgres",
            checkpoint_db=PG_DSN,
        )
        self.assertEqual(sup2.checkpointer_name, "postgres")
        self.assertTrue(sup2._graph.get_state(sup2._config(task.thread_id)).values)
        resumed = sup2.resume(task.thread_id, decision="approve")
        self.assertEqual(resumed.status, "completed")
        sup2.close()
        store2.close()


if __name__ == "__main__":
    unittest.main()
