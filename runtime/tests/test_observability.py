import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from runtime.alerts import collect_alerts
from runtime.api import create_app
from runtime.metrics import collect_metrics, prometheus_text
from runtime.storage import InMemoryStore, TaskRecord


class _StubStore:
    def __init__(self, tasks, evals=None):
        self._tasks = tasks
        self._evals = evals or []

    def list_tasks(self):
        return self._tasks

    def list_eval_runs(self, limit=20):
        return self._evals[:limit]


class ObservabilityTest(unittest.TestCase):
    def test_alerts(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        tasks = [
            TaskRecord(thread_id="t1", request="x", status="failed", error="boom"),
            TaskRecord(thread_id="t2", request="y", status="interrupted", updated_at=old),
        ]
        alerts = collect_alerts(_StubStore(tasks), stale_minutes=30)
        kinds = {item["kind"] for item in alerts}
        self.assertIn("task_failed", kinds)
        self.assertIn("approval_stale", kinds)

    def test_metrics(self):
        tasks = [
            TaskRecord(thread_id="t1", request="x", status="completed"),
            TaskRecord(thread_id="t2", request="y", status="interrupted", pending_envelopes=["e1"]),
        ]
        metrics = collect_metrics(_StubStore(tasks, evals=[{"ok": True}]))
        self.assertEqual(metrics["tasks_total"], 2)
        self.assertEqual(metrics["pending_approvals"], 1)
        self.assertEqual(metrics["eval_runs"], 1)
        text = prometheus_text(metrics)
        self.assertIn("runtime_tasks_total 2", text)
        self.assertIn('runtime_tasks_by_status{status="completed"} 1', text)

    def test_api_metrics_and_alerts(self):
        store = InMemoryStore()
        store.tasks["t1"] = TaskRecord(thread_id="t1", request="x", status="failed", error="boom")
        client = TestClient(create_app(
            store=store, executor="sequential", checkpointer="memory"
        ))
        metrics = client.get("/api/metrics")
        self.assertEqual(metrics.status_code, 200)
        self.assertEqual(metrics.json()["tasks_total"], 1)
        self.assertIn("runtime_tasks_total", client.get("/metrics").text)
        alerts = client.get("/api/alerts")
        self.assertEqual(alerts.status_code, 200)
        self.assertEqual(len(alerts.json()["alerts"]), 1)


if __name__ == "__main__":
    unittest.main()
