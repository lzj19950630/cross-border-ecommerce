import json
import tempfile
import unittest
from pathlib import Path

from runtime.engine import RuntimeEngine
from runtime.export import export_task


class ExportTest(unittest.TestCase):
    def test_export_interrupted_task(self):
        engine = RuntimeEngine()
        task = engine.run("广告 ROAS 太低，怎么降预算")
        with tempfile.TemporaryDirectory() as td:
            result = export_task(task, td)
            out = Path(result["out_dir"])
            self.assertTrue((out / "task.json").is_file())
            self.assertTrue((out / "summary.md").is_file())
            self.assertTrue((out / "artifacts" / "advertising.json").is_file())
            self.assertTrue((out / "evidence" / "advertising.json").is_file())
            self.assertTrue(list((out / "envelopes").glob("*.json")))
            summary = (out / "summary.md").read_text(encoding="utf-8")
            self.assertIn("interrupted", summary)
            self.assertIn("advertising", summary)
            data = json.loads((out / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(data["thread_id"], task.thread_id)

    def test_export_includes_audits(self):
        engine = RuntimeEngine()
        task = engine.run("广告 ROAS 太低，怎么降预算")
        engine.resume(task.thread_id, decision="approve")
        audits = engine.store.list_audits(task.thread_id)
        with tempfile.TemporaryDirectory() as td:
            export_task(task, td, audits=audits)
            path = Path(td) / "audits.json"
            self.assertTrue(path.is_file())
            self.assertIn("approve", path.read_text(encoding="utf-8"))

    def test_export_completed_task(self):
        engine = RuntimeEngine()
        task = engine.run("帮我看下巴西站滑板车类目的市场容量和价格带")
        with tempfile.TemporaryDirectory() as td:
            export_task(task, td)
            summary = (Path(td) / "summary.md").read_text(encoding="utf-8")
            self.assertIn("completed", summary)
            self.assertIn("market_research", summary)


if __name__ == "__main__":
    unittest.main()
