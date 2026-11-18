import unittest

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.storage import InMemoryStore


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(store=InMemoryStore(), executor="sequential"))

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_create_interrupted_and_resume(self):
        response = self.client.post("/api/tasks", json={"request": "广告 ROAS 太低，怎么降预算"})
        self.assertEqual(response.status_code, 200)
        task = response.json()
        self.assertEqual(task["status"], "interrupted")
        thread_id = task["thread_id"]

        approvals = self.client.get(f"/api/tasks/{thread_id}/approvals")
        self.assertEqual(approvals.status_code, 200)
        self.assertEqual(len(approvals.json()["pending"]), 1)

        resumed = self.client.post(
            f"/api/tasks/{thread_id}/resume",
            json={"decision": "approve", "comment": "ok"},
        )
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["status"], "completed")

        audits = self.client.get(f"/api/audits/{thread_id}")
        self.assertEqual(audits.status_code, 200)
        self.assertEqual(len(audits.json()["audits"]), 1)

    def test_create_with_decision(self):
        response = self.client.post(
            "/api/tasks",
            json={"request": "广告 ROAS 太低，怎么降预算", "decision": "approve"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")

    def test_get_and_list(self):
        response = self.client.post("/api/tasks", json={"request": "看类目市场容量"})
        thread_id = response.json()["thread_id"]
        self.assertEqual(self.client.get(f"/api/tasks/{thread_id}").status_code, 200)
        self.assertEqual(self.client.get("/api/tasks").status_code, 200)
        self.assertEqual(self.client.get("/api/tasks/missing").status_code, 404)

    def test_resume_without_pending_is_422(self):
        response = self.client.post("/api/tasks", json={"request": "看类目市场容量"})
        thread_id = response.json()["thread_id"]
        resumed = self.client.post(
            f"/api/tasks/{thread_id}/resume", json={"decision": "approve"}
        )
        self.assertEqual(resumed.status_code, 422)

    def test_supervisor_engine(self):
        client = TestClient(create_app(
            store=InMemoryStore(), executor="sequential", engine_type="supervisor",
            checkpointer="memory",
        ))
        health = client.get("/api/health").json()
        self.assertEqual(health["engine"], "supervisor")

        created = client.post("/api/tasks", json={"request": "广告 ROAS 太低，怎么降预算"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["status"], "interrupted")

        thread_id = created.json()["thread_id"]
        resumed = client.post(f"/api/tasks/{thread_id}/resume", json={"decision": "approve"})
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["status"], "completed")

    def test_web_console(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AI Ecommerce Runtime", response.text)
        self.assertIn("运行评测", response.text)
        self.assertIn("评测历史", response.text)
        self.assertIn("全部状态", response.text)
        self.assertIn("取消任务", response.text)
        self.assertIn("任务状态分布", response.text)
        self.assertIn("metric-grid", response.text)
        self.assertIn("系统管理", response.text)
        self.assertIn("创建租户", response.text)
        self.assertIn("模型配置", response.text)
        self.assertIn("Agent 管理", response.text)
        self.assertIn("全链路追踪", response.text)
        self.assertIn("Checkpoint", response.text)
        self.assertEqual(self.client.get("/static/index.html").status_code, 200)

    def test_eval_endpoint(self):
        response = self.client.post("/api/evals")
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertTrue(report["ok"])
        self.assertEqual(report["passed"], 7)
        self.assertIn("created_at", report)

        history = self.client.get("/api/evals")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()["runs"]), 1)

    def test_api_key_auth(self):
        client = TestClient(create_app(
            store=InMemoryStore(), executor="sequential",
            checkpointer="memory", api_key="secret",
        ))
        self.assertEqual(client.get("/api/health").status_code, 200)
        self.assertEqual(client.get("/api/tasks").status_code, 401)
        self.assertEqual(
            client.get("/api/tasks", headers={"Authorization": "Bearer secret"}).status_code,
            200,
        )
        self.assertEqual(
            client.get("/api/tasks", headers={"X-API-Key": "secret"}).status_code,
            200,
        )
        self.assertEqual(client.get("/").status_code, 200)

    def test_cors(self):
        client = TestClient(create_app(
            store=InMemoryStore(), executor="sequential",
            checkpointer="memory", cors_origins=["http://example.com"],
        ))
        response = client.get("/api/health", headers={"Origin": "http://example.com"})
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://example.com")

    def test_task_export(self):
        response = self.client.post("/api/tasks", json={"request": "看类目市场容量"})
        thread_id = response.json()["thread_id"]
        export = self.client.get(f"/api/tasks/{thread_id}/export")
        self.assertEqual(export.status_code, 200)
        self.assertIn("attachment", export.headers.get("content-disposition", ""))
        self.assertEqual(export.json()["task"]["thread_id"], thread_id)

    def test_metadata(self):
        self.assertEqual(self.client.get("/api/tools").status_code, 200)
        self.assertEqual(self.client.get("/api/actions").status_code, 200)


if __name__ == "__main__":
    unittest.main()
