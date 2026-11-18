import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.storage import InMemoryStore

try:
    from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: F401
    HAS_SQLITE_CHECKPOINTER = True
except Exception:  # pragma: no cover - 取决于环境
    HAS_SQLITE_CHECKPOINTER = False


class TraceApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(
            create_app(
                store=InMemoryStore(),
                executor="sequential",
                checkpointer="memory",
            )
        )

    def test_trace_events(self):
        created = self.client.post(
            "/api/tasks", json={"request": "广告 ROAS 太低，怎么降预算"}
        ).json()
        self.assertEqual(created["status"], "interrupted")
        thread_id = created["thread_id"]
        resumed = self.client.post(
            f"/api/tasks/{thread_id}/resume", json={"decision": "approve"}
        )
        self.assertEqual(resumed.status_code, 200)

        response = self.client.get(f"/api/tasks/{thread_id}/trace")
        self.assertEqual(response.status_code, 200)
        trace = response.json()
        self.assertEqual(trace["thread_id"], thread_id)
        self.assertEqual(trace["status"], "completed")
        types = [event["type"] for event in trace["events"]]
        self.assertIn("route", types)
        self.assertIn("plan", types)
        self.assertIn("slice", types)
        self.assertIn("audit", types)
        agents = {
            event.get("agent")
            for event in trace["events"]
            if event["type"] == "slice"
        }
        self.assertIn("advertising", agents)
        ats = [str(event.get("at") or "") for event in trace["events"]]
        self.assertEqual(ats, sorted(ats))
        self.assertEqual(len(trace["audits"]), 1)

    def test_trace_missing_task(self):
        self.assertEqual(
            self.client.get("/api/tasks/missing/trace").status_code, 404
        )
        self.assertEqual(
            self.client.get("/api/tasks/missing/checkpoints").status_code, 404
        )

    def test_checkpoints_without_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.db"
            client = TestClient(
                create_app(
                    store=InMemoryStore(),
                    executor="sequential",
                    checkpointer="memory",
                    checkpoint_db=str(missing),
                )
            )
            created = client.post(
                "/api/tasks", json={"request": "看类目市场容量"}
            ).json()
            data = client.get(
                f"/api/tasks/{created['thread_id']}/checkpoints"
            ).json()
            self.assertFalse(data["available"])
            self.assertEqual(data["snapshots"], [])
            self.assertTrue(data["reason"])
            self.assertEqual(data["task_status"], created["status"])


@unittest.skipUnless(HAS_SQLITE_CHECKPOINTER, "需要 langgraph-checkpoint-sqlite")
class SqliteCheckpointTest(unittest.TestCase):
    def test_checkpoint_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "checkpoints.db"
            app = create_app(
                store=InMemoryStore(),
                executor="sequential",
                engine_type="supervisor",
                checkpointer="sqlite",
                checkpoint_db=str(db),
            )
            with TestClient(app) as client:
                created = client.post(
                    "/api/tasks",
                    json={"request": "广告 ROAS 太低，怎么降预算"},
                ).json()
                self.assertEqual(created["status"], "interrupted")
                thread_id = created["thread_id"]

                data = client.get(
                    f"/api/tasks/{thread_id}/checkpoints"
                ).json()
                self.assertTrue(data["available"])
                self.assertEqual(data["checkpointer"], "sqlite")
                self.assertGreaterEqual(len(data["snapshots"]), 1)
                self.assertEqual(data["task_status"], "interrupted")
                self.assertTrue(data["task_checkpoint"])

                first = data["snapshots"][0]
                self.assertTrue(first["checkpoint_id"])
                self.assertIn("step", first)
                self.assertIn("state", first)
                self.assertTrue(
                    any(snapshot["has_interrupt"] for snapshot in data["snapshots"])
                )


if __name__ == "__main__":
    unittest.main()
