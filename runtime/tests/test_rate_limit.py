import unittest

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.storage import InMemoryStore

HEADERS = {"Authorization": "Bearer k"}


class RateLimitTest(unittest.TestCase):
    def test_rate_limit(self):
        client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            api_key="k",
            rate_limit=2,
        ))
        self.assertEqual(client.get("/api/health").status_code, 200)
        self.assertEqual(client.get("/api/health").status_code, 200)
        self.assertEqual(client.get("/api/tasks", headers=HEADERS).status_code, 200)
        self.assertEqual(client.get("/api/tasks", headers=HEADERS).status_code, 200)
        limited = client.get("/api/tasks", headers=HEADERS)
        self.assertEqual(limited.status_code, 429)
        self.assertIn("Retry-After", limited.headers)

    def test_rate_limit_without_auth(self):
        client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            rate_limit=1,
        ))
        self.assertEqual(client.get("/api/tasks").status_code, 200)
        self.assertEqual(client.get("/api/tasks").status_code, 429)


if __name__ == "__main__":
    unittest.main()
