import unittest

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.storage import InMemoryStore

ADMIN = {"Authorization": "Bearer admin-key"}


class AccountApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            api_keys={"admin-key": "alice:admin"},
            jwt_secret="jwt-secret",
            secret_key="secret-key",
        ))

    def _create_tenant(self, tenant_id: str, name: str):
        return self.client.post(
            "/api/tenants", json={"id": tenant_id, "name": name}, headers=ADMIN
        )

    def _create_user(self, tenant_id: str, username: str, role: str = "admin"):
        return self.client.post(
            "/api/users",
            json={"tenant_id": tenant_id, "username": username, "password": "pw", "role": role},
            headers=ADMIN,
        )

    def test_tenant_user_login_and_isolation(self):
        self.assertEqual(self._create_tenant("acme", "Acme").status_code, 200)
        self.assertEqual(self._create_tenant("beta", "Beta").status_code, 200)
        self.assertEqual(self._create_user("acme", "bob").status_code, 200)
        self.assertEqual(self._create_user("beta", "carol").status_code, 200)

        login = self.client.post(
            "/api/auth/login", json={"username": "bob", "password": "pw"}
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["tenant"], "acme")
        bob = {"Authorization": f"Bearer {login.json()['token']}"}

        created = self.client.post(
            "/api/tasks", json={"request": "看类目市场容量"}, headers=bob
        ).json()
        self.assertEqual(created["tenant_id"], "acme")
        self.assertEqual(created["owner"], "bob")

        users = self.client.get("/api/users", headers=bob).json()["users"]
        self.assertEqual([user["username"] for user in users], ["bob"])
        self.assertNotIn("password_bcrypt", users[0])

        self.assertEqual(
            self.client.post(
                "/api/tenants", json={"id": "gamma", "name": "Gamma"}, headers=bob
            ).status_code,
            403,
        )

    def test_reset_password_and_self_delete(self):
        self._create_tenant("acme", "Acme")
        self._create_user("acme", "bob")
        login = self.client.post(
            "/api/auth/login", json={"username": "bob", "password": "pw"}
        ).json()
        bob = {"Authorization": f"Bearer {login['token']}"}
        self.assertEqual(
            self.client.put(
                "/api/users/bob/password", json={"password": "newpw"}, headers=bob
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/login", json={"username": "bob", "password": "newpw"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete("/api/users/bob", headers=bob).status_code,
            409,
        )


if __name__ == "__main__":
    unittest.main()
