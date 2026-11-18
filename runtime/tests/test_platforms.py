import hashlib
import hmac
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from runtime.actions import Action, ApprovalEnvelope
from runtime.contracts import RiskLevel
from runtime.engine import RuntimeEngine
from runtime.platforms import MappingAdapter, PlatformAdapterError
from runtime.storage import InMemoryStore


class _Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    fail_remaining = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        _Handler.requests.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": json.loads(body) if body else None,
            "raw": body,
        })
        if _Handler.fail_remaining > 0:
            _Handler.fail_remaining -= 1
            payload = b'{"error":"temporary"}'
            self.send_response(500)
        else:
            payload = json.dumps({"ok": True}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _envelope() -> ApprovalEnvelope:
    return ApprovalEnvelope(
        envelope_id="env-1",
        module="06",
        action_type="ad_bid",
        risk=RiskLevel.APPROVAL,
        actions=[Action(
            action="ad.set_bid",
            target="campaign:123",
            before={"cpc": 0.25},
            after={"cpc": 0.0844},
            reason="ROAS 低",
            evidence=["ad-report#1"],
            rollback="restore",
        )],
    )


class PlatformAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.requests.clear()
        _Handler.fail_remaining = 0
        self.config = {
            "name": "mock",
            "base_url": self.url,
            "auth": {"type": "bearer", "token_env": "TEST_TOKEN"},
            "actions": {
                "ad.set_bid": {
                    "method": "POST",
                    "path": "/campaigns/{target}/bid",
                    "body": {
                        "campaign": "{target}",
                        "bid": "{after.cpc}",
                        "reason": "{reason}",
                    },
                }
            },
        }

    def test_execute_mapping(self):
        adapter = MappingAdapter(self.config, env={"TEST_TOKEN": "secret"})
        result = adapter.execute(_envelope())
        self.assertTrue(result["applied"])
        self.assertEqual(result["mode"], "adapter:mock")
        self.assertEqual(len(_Handler.requests), 1)
        request = _Handler.requests[0]
        self.assertEqual(request["path"], "/campaigns/campaign%3A123/bid")
        self.assertEqual(request["body"]["bid"], 0.0844)
        self.assertEqual(request["body"]["reason"], "ROAS 低")
        self.assertEqual(request["headers"]["Authorization"], "Bearer secret")

    def test_missing_mapping(self):
        config = dict(self.config)
        config["actions"] = {}
        with self.assertRaises(PlatformAdapterError):
            MappingAdapter(config)

    def test_missing_token(self):
        adapter = MappingAdapter(self.config, env={})
        with self.assertRaises(PlatformAdapterError):
            adapter.execute(_envelope())

    def test_retry(self):
        config = dict(self.config)
        config["retry"] = {"attempts": 3, "backoff": 0}
        adapter = MappingAdapter(config, env={"TEST_TOKEN": "secret"})
        _Handler.fail_remaining = 2
        result = adapter.execute(_envelope())
        self.assertTrue(result["applied"])
        self.assertEqual(len(_Handler.requests), 3)

    def test_idempotency_header(self):
        config = dict(self.config)
        config["idempotency_header"] = "Idempotency-Key"
        adapter = MappingAdapter(config, env={"TEST_TOKEN": "secret"})
        adapter.execute(_envelope())
        self.assertEqual(
            _Handler.requests[0]["headers"]["Idempotency-Key"],
            "env-1:1:ad.set_bid",
        )

    def test_hmac_signature(self):
        config = dict(self.config)
        config["signing"] = {
            "type": "hmac_sha256",
            "secret_env": "SIGN_KEY",
            "header": "X-Signature",
        }
        adapter = MappingAdapter(config, env={"TEST_TOKEN": "secret", "SIGN_KEY": "sign-secret"})
        adapter.execute(_envelope())
        raw = _Handler.requests[0]["raw"].encode()
        expected = "sha256=" + hmac.new(b"sign-secret", raw, hashlib.sha256).hexdigest()
        self.assertEqual(_Handler.requests[0]["headers"]["X-Signature"], expected)

    def test_engine_with_adapter(self):
        adapter = MappingAdapter(self.config, env={"TEST_TOKEN": "secret"})
        engine = RuntimeEngine(store=InMemoryStore(), apply_fn=adapter.as_apply_fn())
        task = engine.run("广告 ROAS 太低，怎么降预算")
        resumed = engine.resume(task.thread_id, decision="approve")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(engine.store.audits[0]["apply"]["mode"], "adapter:mock")
        self.assertEqual(len(_Handler.requests), 1)


if __name__ == "__main__":
    unittest.main()
