import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from runtime.apply import ApplyError, DryRunExecutor, WebhookExecutor
from runtime.engine import RuntimeEngine
from runtime.storage import InMemoryStore


class _Handler(BaseHTTPRequestHandler):
    received: list[dict] = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _Handler.received.append(json.loads(body.decode("utf-8")))
        payload = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ApplyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/apply"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.received.clear()

    def test_dry_run(self):
        engine = RuntimeEngine(store=InMemoryStore(), apply_fn=DryRunExecutor().as_apply_fn())
        task = engine.run("广告 ROAS 太低，怎么降预算")
        engine.resume(task.thread_id, decision="approve")
        self.assertEqual(_Handler.received, [])
        self.assertEqual(engine.store.audits[0]["apply"]["mode"], "dry_run")

    def test_webhook_receives_envelope(self):
        engine = RuntimeEngine(
            store=InMemoryStore(),
            apply_fn=WebhookExecutor(self.url).as_apply_fn(),
        )
        task = engine.run("广告 ROAS 太低，怎么降预算")
        envelope_id = task.pending_envelopes[0]
        resumed = engine.resume(task.thread_id, decision="approve")

        self.assertEqual(resumed.status, "completed")
        self.assertEqual(len(_Handler.received), 1)
        payload = _Handler.received[0]
        self.assertEqual(payload["envelope_id"], envelope_id)
        self.assertEqual(payload["decision"], "approved")
        self.assertEqual(engine.store.audits[0]["apply"]["mode"], "webhook")

    def test_webhook_failure(self):
        executor = WebhookExecutor("http://127.0.0.1:1/apply", timeout=1)
        with self.assertRaises(ApplyError):
            executor.execute(_dummy_envelope())


def _dummy_envelope():
    from runtime.actions import Action, ApprovalEnvelope
    from runtime.contracts import RiskLevel

    return ApprovalEnvelope(
        envelope_id="env-1",
        module="06",
        action_type="ad_bid",
        risk=RiskLevel.APPROVAL,
        actions=[Action(
            action="ad.set_bid",
            target="campaign:1",
            before={"cpc": 1},
            after={"cpc": 0.5},
            reason="test",
            evidence=["test#1"],
            rollback="restore",
        )],
    )


if __name__ == "__main__":
    unittest.main()
