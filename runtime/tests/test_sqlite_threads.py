import tempfile
import threading
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.storage import SQLiteStore


class SQLiteThreadSafetyTest(unittest.TestCase):
    def test_store_usable_from_another_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "runtime.db")
            store.create_task("主线程创建")
            result = {}

            def worker():
                try:
                    result["tasks"] = len(store.list_tasks())
                except Exception as exc:  # pragma: no cover - 回归失败时输出
                    result["error"] = exc

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()
            self.assertNotIn("error", result)
            self.assertEqual(result["tasks"], 1)
            store.close()

    def test_api_with_sqlite_store(self):
        # FastAPI 同步端点跑在线程池；这里覆盖“主线程建连接、工作线程请求”的场景。
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "runtime.db")
            app = create_app(
                store=store, executor="sequential", checkpointer="memory"
            )
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/tasks").status_code, 200)
                created = client.post(
                    "/api/tasks", json={"request": "看类目市场容量"}
                )
                self.assertEqual(created.status_code, 200)
                thread_id = created.json()["thread_id"]
                self.assertEqual(client.get("/api/tasks").status_code, 200)
                self.assertEqual(
                    client.get(f"/api/tasks/{thread_id}").status_code, 200
                )
                self.assertEqual(
                    client.get(f"/api/tasks/{thread_id}/trace").status_code, 200
                )
            store.close()


if __name__ == "__main__":
    unittest.main()
