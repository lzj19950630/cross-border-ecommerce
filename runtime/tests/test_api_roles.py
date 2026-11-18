import unittest

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.storage import InMemoryStore

ADMIN = {"Authorization": "Bearer admin-key"}
OP = {"Authorization": "Bearer op-key"}
VIEWER = {"Authorization": "Bearer view-key"}


class RoleApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            api_keys={
                "admin-key": "alice:admin",
                "op-key": "bob:operator",
                "view-key": "carol:viewer",
            },
        ))

    def _create(self, headers, request="看类目市场容量"):
        return self.client.post("/api/tasks", json={"request": request}, headers=headers)

    def test_viewer_cannot_create(self):
        self.assertEqual(self._create(VIEWER).status_code, 403)

    def test_owner_and_list_filtering(self):
        op_task = self._create(OP).json()
        admin_task = self._create(ADMIN).json()
        self.assertEqual(op_task["owner"], "bob")
        self.assertEqual(admin_task["owner"], "alice")

        admin_list = self.client.get("/api/tasks", headers=ADMIN).json()["tasks"]
        op_list = self.client.get("/api/tasks", headers=OP).json()["tasks"]
        viewer_list = self.client.get("/api/tasks", headers=VIEWER).json()["tasks"]
        self.assertEqual(len(admin_list), 2)
        self.assertEqual(len(op_list), 1)
        self.assertEqual(len(viewer_list), 0)

    def test_operator_cannot_read_other_task(self):
        admin_task = self._create(ADMIN).json()
        thread_id = admin_task["thread_id"]
        self.assertEqual(
            self.client.get(f"/api/tasks/{thread_id}", headers=OP).status_code, 403
        )
        self.assertEqual(
            self.client.get(f"/api/tasks/{thread_id}", headers=ADMIN).status_code, 200
        )

    def test_operator_resume_own_task(self):
        task = self._create(OP, "广告 ROAS 太低，怎么降预算").json()
        self.assertEqual(task["status"], "interrupted")
        resumed = self.client.post(
            f"/api/tasks/{task['thread_id']}/resume",
            json={"decision": "approve"},
            headers=OP,
        )
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["status"], "completed")
        audits = self.client.get(
            f"/api/audits/{task['thread_id']}", headers=OP
        ).json()["audits"]
        self.assertEqual(audits[0]["decided_by"], "bob")

    def test_viewer_cannot_resume_or_eval(self):
        task = self._create(ADMIN, "广告 ROAS 太低，怎么降预算").json()
        self.assertEqual(
            self.client.post(
                f"/api/tasks/{task['thread_id']}/resume",
                json={"decision": "approve"},
                headers=VIEWER,
            ).status_code,
            403,
        )
        self.assertEqual(self.client.post("/api/evals", headers=VIEWER).status_code, 403)
        self.assertEqual(self.client.post("/api/evals", headers=OP).status_code, 200)

    def test_operator_cancel_own_task(self):
        task = self._create(OP, "广告 ROAS 太低，怎么降预算").json()
        cancelled = self.client.post(
            f"/api/tasks/{task['thread_id']}/cancel", headers=OP
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        self.assertEqual(cancelled.json()["pending_envelopes"], [])

    def test_viewer_cannot_cancel(self):
        task = self._create(ADMIN, "广告 ROAS 太低，怎么降预算").json()
        response = self.client.post(
            f"/api/tasks/{task['thread_id']}/cancel", headers=VIEWER
        )
        self.assertEqual(response.status_code, 403)

    def test_health_stays_public(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_proxy_auth(self):
        client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            proxy_auth_secret="proxy-secret",
        ))
        admin = {
            "X-Proxy-Auth": "proxy-secret",
            "X-Auth-Request-User": "alice",
            "X-Auth-Request-Role": "admin",
        }
        viewer = {
            "X-Proxy-Auth": "proxy-secret",
            "X-Auth-Request-User": "carol",
            "X-Auth-Request-Role": "viewer",
        }
        self.assertEqual(client.get("/api/tasks").status_code, 401)
        self.assertEqual(client.get("/api/tasks", headers=admin).status_code, 200)
        self.assertEqual(
            client.post("/api/tasks", json={"request": "看类目"}, headers=admin).status_code,
            200,
        )
        self.assertEqual(
            client.post("/api/tasks", json={"request": "看类目"}, headers=viewer).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
