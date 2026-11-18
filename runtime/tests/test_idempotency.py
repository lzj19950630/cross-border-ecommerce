import unittest

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.storage import InMemoryStore


class IdempotencyTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(
            store=InMemoryStore(), executor="sequential", checkpointer="memory"
        ))

    def test_same_key_returns_same_task(self):
        headers = {"Idempotency-Key": "key-1"}
        first = self.client.post(
            "/api/tasks", json={"request": "看类目市场容量"}, headers=headers
        ).json()
        second = self.client.post(
            "/api/tasks", json={"request": "看类目市场容量"}, headers=headers
        ).json()
        self.assertEqual(first["thread_id"], second["thread_id"])
        self.assertTrue(second["idempotent_replay"])

    def test_different_key_creates_new_task(self):
        first = self.client.post(
            "/api/tasks", json={"request": "看类目市场容量"},
            headers={"Idempotency-Key": "key-1"},
        ).json()
        second = self.client.post(
            "/api/tasks", json={"request": "看类目市场容量"},
            headers={"Idempotency-Key": "key-2"},
        ).json()
        self.assertNotEqual(first["thread_id"], second["thread_id"])


if __name__ == "__main__":
    unittest.main()
