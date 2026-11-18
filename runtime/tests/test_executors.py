import unittest

from runtime.agent_runners import AgentResult
from runtime.contracts import Slice
from runtime.executors import (
    LangGraphLayerExecutor,
    SequentialLayerExecutor,
    langgraph_available,
    make_default_executor,
    make_executor,
)


def run_slice(slice_):
    return AgentResult(agent=slice_.agent, status="ok", artifact={"agent": slice_.agent})


SLICES = [Slice(1, "market_research", "a"), Slice(2, "product_strategy", "b")]


class ExecutorTest(unittest.TestCase):
    def test_sequential(self):
        results = SequentialLayerExecutor().run(SLICES, run_slice)
        self.assertEqual(sorted(results), [1, 2])
        self.assertEqual(results[1].artifact["agent"], "market_research")

    @unittest.skipUnless(langgraph_available(), "langgraph not installed")
    def test_langgraph(self):
        results = LangGraphLayerExecutor().run(SLICES, run_slice)
        self.assertEqual(sorted(results), [1, 2])
        self.assertEqual(results[2].artifact["agent"], "product_strategy")

    def test_default_and_factory(self):
        self.assertIn(make_default_executor().name, {"langgraph", "sequential"})
        self.assertEqual(make_executor("sequential").name, "sequential")
        if langgraph_available():
            self.assertEqual(make_executor("langgraph").name, "langgraph")

    def test_empty_layer(self):
        self.assertEqual(SequentialLayerExecutor().run([], run_slice), {})


if __name__ == "__main__":
    unittest.main()
