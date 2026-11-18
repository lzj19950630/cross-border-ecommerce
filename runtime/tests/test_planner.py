import unittest

from runtime.contracts import Intent, RouteDecision, Slice, SlicePlan
from runtime.planner import ManagerPlanner, PlanningError


def decision(*intents):
    return RouteDecision(intents=tuple(intents), confidence=1.0, compound=len(intents) > 1)


class PlannerTest(unittest.TestCase):
    def setUp(self):
        self.planner = ManagerPlanner()

    def test_single_read_only_agent_has_no_approval(self):
        plan = self.planner.plan("看类目市场", decision(Intent.MARKET_RESEARCH))
        self.assertEqual(len(plan.slices), 1)
        self.assertEqual(plan.slices[0].approval_points, [])

    def test_single_write_agent_requires_approval(self):
        plan = self.planner.plan("降广告预算", decision(Intent.ADVERTISING))
        self.assertEqual(len(plan.slices), 1)
        self.assertTrue(plan.slices[0].approval_points)

    def test_full_chain_dependencies_and_layers(self):
        plan = self.planner.plan_full_chain("完整链路")
        self.assertEqual(len(plan.slices), 7)
        self.assertEqual(plan.execution_order(), [[1], [2], [3], [4, 5, 6], [7]])
        by_no = {item.no: item for item in plan.slices}
        self.assertEqual(by_no[2].depends_on, [1])
        self.assertEqual(by_no[3].depends_on, [2])
        self.assertEqual(by_no[4].depends_on, [3])
        self.assertEqual(by_no[5].depends_on, [3])
        self.assertEqual(by_no[6].depends_on, [2, 3])
        self.assertEqual(by_no[7].depends_on, [3, 4])

    def test_compound_subset(self):
        plan = self.planner.plan(
            "分析市场然后定价做图",
            decision(Intent.MARKET_RESEARCH, Intent.PRODUCT_STRATEGY, Intent.PRODUCT_IMAGE),
        )
        self.assertEqual([item.agent for item in plan.slices],
                         ["market_research", "product_strategy", "product_image"])
        self.assertEqual(plan.slices[2].depends_on, [2])

    def test_clarify_raises(self):
        with self.assertRaises(PlanningError):
            self.planner.plan("不知道", decision(Intent.CLARIFY))

    def test_unknown_intent_raises(self):
        with self.assertRaises(PlanningError):
            self.planner.plan("不知道", decision(Intent.UNKNOWN))

    def test_slice_limit(self):
        with self.assertRaises(ValueError):
            self.planner.plan_full_chain("完整链路").validate(
                {spec.key: spec for spec in __import__("runtime.agent_registry", fromlist=["AGENTS"]).AGENTS},
                max_slices=3,
            )

    def test_cycle_detection(self):
        plan = SlicePlan([
            Slice(1, "market_research", "a", depends_on=[2]),
            Slice(2, "product_strategy", "b", depends_on=[1], approval_points=["审批"]),
        ])
        with self.assertRaises(ValueError):
            plan.validate(
                {spec.key: spec for spec in __import__("runtime.agent_registry", fromlist=["AGENTS"]).AGENTS}
            )

    def test_missing_dependency(self):
        plan = SlicePlan([
            Slice(1, "product_strategy", "b", depends_on=[9], approval_points=["审批"]),
        ])
        with self.assertRaises(ValueError):
            plan.validate(
                {spec.key: spec for spec in __import__("runtime.agent_registry", fromlist=["AGENTS"]).AGENTS}
            )


if __name__ == "__main__":
    unittest.main()
