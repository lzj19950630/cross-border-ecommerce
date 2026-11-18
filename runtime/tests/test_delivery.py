import io
import unittest
import zipfile

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.delivery import archive_bytes, machine_review
from runtime.engine import RuntimeEngine
from runtime.storage import InMemoryStore


class DeliveryUnitTest(unittest.TestCase):
    def test_machine_review_and_archive(self):
        engine = RuntimeEngine(store=InMemoryStore())
        task = engine.run("帮我看下巴西站滑板车类目的市场容量和价格带")
        review = machine_review(task)
        self.assertTrue(review["passed"], review["violations"])

        with self.assertRaises(ValueError):
            archive_bytes(task)

        task.delivery_status = "passed"
        task.delivery_review = {"machine": review, "human": {"decision": "approved"}}
        engine.store.save_task(task)
        data = archive_bytes(task, audits=engine.store.list_audits(task.thread_id))
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        self.assertIn("manifest.json", names)
        self.assertIn("summary.md", names)
        self.assertIn("task.json", names)

    def test_interrupted_task_fails_machine_review(self):
        engine = RuntimeEngine(store=InMemoryStore())
        task = engine.run("广告 ROAS 太低，怎么降预算")
        review = machine_review(task)
        self.assertFalse(review["passed"])
        self.assertTrue(any(c["name"] == "task_status" and not c["ok"] for c in review["checks"]))


class DeliveryApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(
            store=InMemoryStore(), executor="sequential", checkpointer="memory"
        ))

    def test_review_decision_archive(self):
        task = self.client.post(
            "/api/tasks", json={"request": "帮我看下巴西站滑板车类目的市场容量和价格带"}
        ).json()
        thread_id = task["thread_id"]
        self.assertEqual(task["delivery_status"], "not_reviewed")

        archive = self.client.get(f"/api/tasks/{thread_id}/archive")
        self.assertEqual(archive.status_code, 409)

        reviewed = self.client.post(f"/api/tasks/{thread_id}/delivery/review")
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(reviewed.json()["delivery_status"], "pending")

        approved = self.client.post(
            f"/api/tasks/{thread_id}/delivery/decision",
            json={"decision": "approve", "note": "ok"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["delivery_status"], "passed")

        archive = self.client.get(f"/api/tasks/{thread_id}/archive")
        self.assertEqual(archive.status_code, 200)
        self.assertEqual(archive.headers["content-type"], "application/zip")
        self.assertIn("manifest.json", zipfile.ZipFile(io.BytesIO(archive.content)).namelist())

    def test_decision_requires_machine_review(self):
        task = self.client.post(
            "/api/tasks", json={"request": "帮我看下巴西站滑板车类目的市场容量和价格带"}
        ).json()
        response = self.client.post(
            f"/api/tasks/{task['thread_id']}/delivery/decision",
            json={"decision": "approve"},
        )
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
