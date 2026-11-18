import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from pathlib import Path

from runtime.cli import main

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "Templates"


def run_cli(*args):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(list(args))
    return code, buffer.getvalue()


class CliTest(unittest.TestCase):
    def test_route(self):
        code, output = run_cli("route", "帮我看下巴西站滑板车类目市场容量和价格带")
        self.assertEqual(code, 0)
        self.assertIn("market_research", output)

    def test_plan(self):
        code, output = run_cli("plan", "先分析类目市场，然后定价，再做主图和广告")
        self.assertEqual(code, 0)
        self.assertIn("execution_layers", output)
        self.assertIn("product_image", output)

    def test_run_single_agent(self):
        code, output = run_cli("run", "帮我看下巴西站滑板车类目的市场容量和价格带")
        self.assertEqual(code, 0)
        self.assertIn('"status": "completed"', output)
        self.assertIn("market_research", output)

    def test_run_advertising_interrupted(self):
        code, output = run_cli("run", "广告 ROAS 太低，怎么降预算")
        self.assertEqual(code, 2)
        self.assertIn('"status": "interrupted"', output)
        self.assertIn("ad.set_bid", output)

    def test_run_advertising_approve(self):
        code, output = run_cli("run", "广告 ROAS 太低，怎么降预算", "--decision", "approve")
        self.assertEqual(code, 0)
        self.assertIn('"status": "completed"', output)
        self.assertIn('"decision": "approved"', output)

    def test_run_full_chain_approve(self):
        code, output = run_cli("run", "走一遍完整链路", "--decision", "approve")
        self.assertEqual(code, 0)
        self.assertIn('"status": "completed"', output)
        self.assertIn("review_analysis", output)
        self.assertIn("product_video", output)

    def test_run_and_resume_across_commands(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "runtime.db")
            code, output = run_cli("run", "广告 ROAS 太低，怎么降预算", "--db", db)
            self.assertEqual(code, 2)
            thread_id = json.loads(output)["thread_id"]

            code, resumed = run_cli("resume", thread_id, "--decision", "approve", "--db", db)
            self.assertEqual(code, 0)
            self.assertIn('"status": "completed"', resumed)

            code, task = run_cli("task", thread_id, "--db", db)
            self.assertEqual(code, 0)
            self.assertIn('"status": "completed"', task)

    def test_run_listing_completed(self):
        code, output = run_cli("run", "帮我写一个商品标题")
        self.assertEqual(code, 0)
        self.assertIn('"status": "completed"', output)
        self.assertIn("listing_creative", output)

    def test_supervisor_engine_one_shot(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "runtime.db")
            code, output = run_cli(
                "run", "广告 ROAS 太低，怎么降预算",
                "--engine", "supervisor", "--decision", "approve", "--db", db,
            )
            self.assertEqual(code, 0)
            self.assertIn('"status": "completed"', output)

    def test_supervisor_cross_process_resume(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "runtime.db")
            code, output = run_cli(
                "run", "广告 ROAS 太低，怎么降预算", "--engine", "supervisor",
                "--checkpointer", "memory", "--db", db
            )
            self.assertEqual(code, 2)
            thread_id = json.loads(output)["thread_id"]
            code, resumed = run_cli(
                "resume", thread_id, "--engine", "supervisor",
                "--checkpointer", "memory", "--decision", "approve", "--db", db,
            )
            self.assertEqual(code, 0)
            self.assertIn('"status": "completed"', resumed)

    def test_eval_template(self):
        code, output = run_cli("eval", "Templates/eval_case.yaml")
        self.assertEqual(code, 0, output)
        self.assertIn('"ok": true', output)

    def test_eval_judge(self):
        from runtime.evals import load_cases
        from runtime.llm import FakeLLM
        cases = load_cases("Templates/eval_case.yaml")
        responses = [
            {"scores": [{"rubric": r, "pass": True, "reason": "ok"} for r in case.rubric]}
            for case in cases
        ]
        with patch("runtime.llm.load_llm_from_env", return_value=FakeLLM(responses)):
            code, output = run_cli("eval", "Templates/eval_case.yaml", "--judge")
        self.assertEqual(code, 0, output)
        self.assertIn('"judge"', output)

    def test_doctor(self):
        code, output = run_cli("doctor")
        self.assertEqual(code, 0)
        self.assertIn('"ok": true', output)

    def test_audits_and_export(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "runtime.db")
            out = str(Path(td) / "export")
            code, output = run_cli("run", "广告 ROAS 太低，怎么降预算", "--db", db)
            self.assertEqual(code, 2)
            thread_id = json.loads(output)["thread_id"]
            code, _ = run_cli("resume", thread_id, "--decision", "approve", "--db", db)
            self.assertEqual(code, 0)

            code, output = run_cli("audits", thread_id, "--db", db)
            self.assertEqual(code, 0)
            self.assertIn('"decision": "approve"', output)

            code, output = run_cli("export", thread_id, "--out", out, "--db", db)
            self.assertEqual(code, 0)
            self.assertTrue((Path(out) / "summary.md").is_file())
            self.assertTrue((Path(out) / "task.json").is_file())

    def test_tools(self):
        code, output = run_cli("tools")
        self.assertEqual(code, 0)
        self.assertIn("market_metrics", output)

    def test_actions(self):
        code, output = run_cli("actions")
        self.assertEqual(code, 0)
        self.assertIn("ad.set_budget", output)

    def test_check_envelope_template(self):
        code, output = run_cli("check-envelope", str(TEMPLATES / "action_approval_envelope.yaml"))
        self.assertEqual(code, 0, output)
        self.assertIn('"ok": true', output)

    def test_check_evidence_template(self):
        code, output = run_cli(
            "check-evidence",
            "--text", "CTR 1.2% [1]，佣金 14% [2]，盈亏线 ROAS 2.82 [3]",
            "--evidence", str(TEMPLATES / "evidence_block.yaml"),
        )
        self.assertEqual(code, 0, output)
        self.assertIn('"ok": true', output)

    def test_check_evidence_failure(self):
        code, output = run_cli(
            "check-evidence",
            "--text", "只有 [9]",
            "--evidence", str(TEMPLATES / "evidence_block.yaml"),
        )
        self.assertEqual(code, 1)
        self.assertIn("解析不到", output)


if __name__ == "__main__":
    unittest.main()
