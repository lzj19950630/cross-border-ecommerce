import unittest

from runtime.agent_registry import AGENTS, DEFAULT_REGISTRY, WORKFLOW_ORDER
from runtime.contracts import Intent


class AgentRegistryTest(unittest.TestCase):
    def test_seven_agents(self):
        self.assertEqual(len(AGENTS), 7)
        self.assertEqual(len(DEFAULT_REGISTRY.keys()), 7)

    def test_keys_and_intents_unique(self):
        keys = [spec.key for spec in AGENTS]
        intents = [spec.intent for spec in AGENTS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(intents), len(set(intents)))

    def test_each_agent_has_contract_and_tools(self):
        for spec in AGENTS:
            self.assertTrue(spec.key)
            self.assertTrue(spec.name)
            self.assertTrue(spec.keywords, spec.key)
            self.assertTrue(spec.tools, spec.key)
            self.assertTrue(spec.input_schema, spec.key)
            self.assertTrue(spec.output_schema, spec.key)
            self.assertIn("evidence", spec.output_schema, spec.key)

    def test_workflow_order_covers_all_agents(self):
        self.assertEqual(set(WORKFLOW_ORDER), set(DEFAULT_REGISTRY.keys()))

    def test_unknown_agent_raises(self):
        with self.assertRaises(KeyError):
            DEFAULT_REGISTRY.get("unknown_agent")

    def test_intent_lookup(self):
        spec = DEFAULT_REGISTRY.by_intent(Intent.ADVERTISING)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, "advertising")


if __name__ == "__main__":
    unittest.main()
