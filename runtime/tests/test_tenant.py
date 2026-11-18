import unittest

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.storage import InMemoryStore

ACME = {"Authorization": "Bearer acme-key"}
BETA = {"Authorization": "Bearer beta-key"}


class TenantTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            api_keys={
                "acme-key": "acme:alice:admin",
                "beta-key": "beta:bob:admin",
            },
        ))

    def test_tenant_isolation(self):
        acme_task = self.client.post(
            "/api/tasks", json={"request": "看类目市场容量"}, headers=ACME
        ).json()
        beta_task = self.client.post(
            "/api/tasks", json={"request": "看类目市场容量"}, headers=BETA
        ).json()
        self.assertEqual(acme_task["tenant_id"], "acme")
        self.assertEqual(beta_task["tenant_id"], "beta")

        acme_list = self.client.get("/api/tasks", headers=ACME).json()["tasks"]
        beta_list = self.client.get("/api/tasks", headers=BETA).json()["tasks"]
        self.assertEqual(len(acme_list), 1)
        self.assertEqual(len(beta_list), 1)
        self.assertEqual(acme_list[0]["thread_id"], acme_task["thread_id"])
        self.assertEqual(beta_list[0]["thread_id"], beta_task["thread_id"])

        self.assertEqual(
            self.client.get(f"/api/tasks/{acme_task['thread_id']}", headers=BETA).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(f"/api/tasks/{acme_task['thread_id']}", headers=ACME).status_code,
            200,
        )


if __name__ == "__main__":
    unittest.main()
