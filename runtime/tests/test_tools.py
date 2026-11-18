import unittest

from runtime.tools import DEFAULT_TOOL_REGISTRY, ToolRegistry


class ToolRegistryTest(unittest.TestCase):
    def test_registered_tools(self):
        names = DEFAULT_TOOL_REGISTRY.names()
        self.assertIn("market_metrics", names)
        self.assertIn("sku_pricing", names)
        self.assertIn("ad_metrics", names)
        self.assertIn("review_stats", names)
        self.assertEqual(len(names), len(set(names)))

    def test_agent_tool_mapping(self):
        tools = {tool.name for tool in DEFAULT_TOOL_REGISTRY.for_agent("advertising")}
        self.assertEqual(tools, {"ad_metrics"})
        image_tools = {tool.name for tool in DEFAULT_TOOL_REGISTRY.for_agent("product_image")}
        self.assertIn("check_main_image", image_tools)

    def test_unknown_tool_raises(self):
        with self.assertRaises(KeyError):
            DEFAULT_TOOL_REGISTRY.get("rm_rf")

    def test_run_help(self):
        result = DEFAULT_TOOL_REGISTRY.run("market_metrics", ["--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage", result.stdout.lower())
        self.assertTrue(result.ok)

    def test_run_title_lint_help(self):
        result = DEFAULT_TOOL_REGISTRY.run("title_lint", ["--help"])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_json_parse_failure(self):
        result = DEFAULT_TOOL_REGISTRY.run("market_metrics", ["--help"])
        with self.assertRaises(ValueError):
            result.json()

    def test_duplicate_tool_rejected(self):
        with self.assertRaises(ValueError):
            ToolRegistry((DEFAULT_TOOL_REGISTRY.get("market_metrics"),
                          DEFAULT_TOOL_REGISTRY.get("market_metrics")))


if __name__ == "__main__":
    unittest.main()
