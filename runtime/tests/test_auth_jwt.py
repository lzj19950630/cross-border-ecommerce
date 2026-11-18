import unittest

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.auth import encode_jwt, hash_password, hash_password_bcrypt
from runtime.storage import InMemoryStore

ADMIN = {"Authorization": "Bearer admin-key"}
OP = {"Authorization": "Bearer op-key"}


class JwtTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            jwt_secret="jwt-secret",
            users={"alice": {
                "password_sha256": hash_password("pw"),
                "role": "admin",
            }},
        ))

    def test_login_and_token(self):
        self.assertEqual(self.client.get("/api/tasks").status_code, 401)
        self.assertEqual(
            self.client.post("/api/auth/login", json={"username": "alice", "password": "bad"}).status_code,
            401,
        )
        response = self.client.post(
            "/api/auth/login", json={"username": "alice", "password": "pw"}
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]
        self.assertEqual(
            self.client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"}).status_code,
            200,
        )

    def test_refresh_token(self):
        login = self.client.post(
            "/api/auth/login", json={"username": "alice", "password": "pw"}
        ).json()
        refreshed = self.client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {login['token']}"},
        )
        self.assertEqual(refreshed.status_code, 200)
        token = refreshed.json()["token"]
        self.assertEqual(
            self.client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"}).status_code,
            200,
        )

    def test_logout_revokes_token(self):
        login = self.client.post(
            "/api/auth/login", json={"username": "alice", "password": "pw"}
        ).json()
        headers = {"Authorization": f"Bearer {login['token']}"}
        self.assertEqual(self.client.get("/api/tasks", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/tasks", headers=headers).status_code, 401)

    def test_refresh_rotates_token(self):
        login = self.client.post(
            "/api/auth/login", json={"username": "alice", "password": "pw"}
        ).json()
        old_headers = {"Authorization": f"Bearer {login['token']}"}
        refreshed = self.client.post("/api/auth/refresh", headers=old_headers)
        self.assertEqual(refreshed.status_code, 200)
        new_headers = {"Authorization": f"Bearer {refreshed.json()['token']}"}
        self.assertEqual(self.client.get("/api/tasks", headers=old_headers).status_code, 401)
        self.assertEqual(self.client.get("/api/tasks", headers=new_headers).status_code, 200)

    def test_expired_token(self):
        token = encode_jwt("jwt-secret", {"sub": "alice", "role": "admin"}, ttl=-1)
        self.assertEqual(
            self.client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"}).status_code,
            401,
        )


class BcryptLoginTest(unittest.TestCase):
    def test_bcrypt_login(self):
        client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            jwt_secret="jwt-secret",
            users={"alice": {
                "password_bcrypt": hash_password_bcrypt("pw"),
                "role": "admin",
            }},
        ))
        response = client.post(
            "/api/auth/login", json={"username": "alice", "password": "pw"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())


class ActionPolicyTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(
            store=InMemoryStore(),
            executor="sequential",
            checkpointer="memory",
            api_keys={"admin-key": "alice:admin", "op-key": "bob:operator"},
            action_roles={"listing.update_title": ["admin"]},
        ))

    def _create_listing(self, headers):
        return self.client.post(
            "/api/tasks",
            json={
                "request": "帮我写一个商品标题",
                "inputs": {"proposed_title": "Carregador Portátil 20000mAh 45W 3 Saídas"},
            },
            headers=headers,
        )

    def test_operator_cannot_approve_admin_only_action(self):
        task = self._create_listing(OP).json()
        self.assertEqual(task["status"], "interrupted")
        denied = self.client.post(
            f"/api/tasks/{task['thread_id']}/resume",
            json={"decision": "approve"},
            headers=OP,
        )
        self.assertEqual(denied.status_code, 403)
        self.assertIn("listing.update_title", denied.json()["detail"])

        allowed = self.client.post(
            f"/api/tasks/{task['thread_id']}/resume",
            json={"decision": "approve"},
            headers=ADMIN,
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
