import unittest
from pathlib import Path

from runtime.contracts import EvalCase
from runtime.evals import CHECKS, load_cases, run_cases
from runtime.llm import FakeLLM

ROOT = Path(__file__).resolve().parents[2]


class EvalTest(unittest.TestCase):
    def test_load_template(self):
        cases = load_cases(ROOT / "Templates" / "eval_case.yaml")
        self.assertEqual(len(cases), 7)
        self.assertEqual(cases[0].id, "patinete-market-01")

    def test_template_cases_pass(self):
        cases = load_cases(ROOT / "Templates" / "eval_case.yaml")
        report = run_cases(cases)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["passed"], 7)
        self.assertEqual(report["failed"], 0)

    def test_unknown_check_fails(self):
        case = EvalCase(
            id="bad-check",
            surface="01 市场分析",
            input="看类目市场容量",
            rubric=("x",),
            deterministic_checks=("not_a_check",),
        )
        report = run_cases([case])
        self.assertFalse(report["ok"])
        self.assertIn("未知检查项", report["cases"][0]["checks"][0]["detail"])

    def test_judge_pass(self):
        cases = load_cases(ROOT / "Templates" / "eval_case.yaml")
        responses = [
            {"scores": [{"rubric": rubric, "pass": True, "reason": "ok"} for rubric in case.rubric]}
            for case in cases
        ]
        report = run_cases(cases, judge=FakeLLM(responses))
        self.assertTrue(report["ok"], report)
        self.assertEqual(len(report["cases"][0]["judge"]), len(cases[0].rubric))

    def test_judge_fail(self):
        cases = load_cases(ROOT / "Templates" / "eval_case.yaml")
        responses = []
        for index, case in enumerate(cases):
            scores = [{"rubric": rubric, "pass": True, "reason": "ok"} for rubric in case.rubric]
            if index == 0:
                scores[0]["pass"] = False
            responses.append({"scores": scores})
        report = run_cases(cases, judge=FakeLLM(responses))
        self.assertFalse(report["ok"])
        self.assertFalse(report["cases"][0]["passed"])

    def test_judge_malformed(self):
        cases = load_cases(ROOT / "Templates" / "eval_case.yaml")
        report = run_cases(cases, judge=FakeLLM([{"scores": []}] * len(cases)))
        self.assertFalse(report["ok"])
        self.assertIn("判据数量不符", report["cases"][0]["judge_error"])

    def test_check_registry(self):
        self.assertIn("evidence_present", CHECKS)
        self.assertIn("action_envelope_valid", CHECKS)
        self.assertIn("attribution_sum", CHECKS)


if __name__ == "__main__":
    unittest.main()
