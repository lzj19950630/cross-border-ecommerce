import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.providers import ProviderService, TenantLLMResolver
from runtime.storage import InMemoryStore
from runtime.llm import FakeLLM
from runtime.agent_runners import AgentContext
from runtime.contracts import Slice

HEADERS = {"Authorization": "Bearer acme-key"}


class ProviderServiceTest(unittest.TestCase):
    def test_encrypt_and_mask(self):
        store = InMemoryStore()
        service = ProviderService(store, secret_key="test-secret")
        masked = service.save(
            tenant_id="acme",
            name="default",
            base_url="https://api.example.com",
            model="gpt-test",
            api_key="sk-secret-1234",
            updated_by="alice",
        )
        self.assertTrue(masked["api_key_set"])
        self.assertEqual(masked["api_key_last4"], "1234")
        self.assertNotIn("api_key_enc", masked)

        raw = store.get_provider_config("acme", "default")
        self.assertNotIn("sk-secret-1234", raw["api_key_enc"])
        self.assertEqual(service.list("acme")[0]["model"], "gpt-test")
        self.assertIsNotNone(service.llm_for("acme"))

    def test_tenant_resolver(self):
        service = ProviderService(InMemoryStore(), secret_key="test-secret")
        fake = FakeLLM([{"ok": True}])
        resolver = TenantLLMResolver(service, fallback=fake)
        context = AgentContext(
            thread_id="t1", request="x", slice=Slice(1, "listing_creative", "x"),
            tenant_id="acme",
        )
        self.assertIs(resolver(context), fake)


class ProviderApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            api_keys={"acme-key": "acme:alice:admin"},
            secret_key="test-secret",
        ))

    def test_crud(self):
        self.assertEqual(self.client.get("/api/providers", headers=HEADERS).json()["providers"], [])
        saved = self.client.put(
            "/api/providers/default",
            json={
                "base_url": "https://api.example.com",
                "model": "gpt-test",
                "api_key": "sk-secret-1234",
            },
            headers=HEADERS,
        )
        self.assertEqual(saved.status_code, 200)
        self.assertNotIn("api_key_enc", saved.json())
        self.assertEqual(saved.json()["api_key_last4"], "1234")

        listed = self.client.get("/api/providers", headers=HEADERS).json()["providers"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["model"], "gpt-test")

        with patch.object(ProviderService, "test", return_value={"ok": True}):
            tested = self.client.post("/api/providers/default/test", headers=HEADERS)
        self.assertEqual(tested.status_code, 200)
        self.assertTrue(tested.json()["ok"])

        deleted = self.client.delete("/api/providers/default", headers=HEADERS)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/providers", headers=HEADERS).json()["providers"], [])

    def test_requires_tenant(self):
        client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            api_keys={"global-key": "alice:admin"},
            secret_key="test-secret",
        ))
        response = client.get(
            "/api/providers", headers={"Authorization": "Bearer global-key"}
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
