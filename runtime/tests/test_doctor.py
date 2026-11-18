import unittest

from runtime.doctor import run_doctor
from runtime.tools import ToolRegistry, ToolSpec


class DoctorTest(unittest.TestCase):
    def test_default_environment_ok(self):
        result = run_doctor()
        self.assertTrue(result["ok"], [c for c in result["checks"] if not c["ok"]])
        self.assertGreaterEqual(len(result["checks"]), 10)

    def test_missing_script_fails(self):
        tools = ToolRegistry((
            ToolSpec("bogus", "Agents/__missing__.py", "missing", "market_research"),
        ))
        result = run_doctor(tools=tools)
        self.assertFalse(result["ok"])
        self.assertTrue(any(
            check["name"] == "tool:bogus" and not check["ok"]
            for check in result["checks"]
        ))


if __name__ == "__main__":
    unittest.main()
