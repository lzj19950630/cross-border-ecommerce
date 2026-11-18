import unittest

from runtime.actions import (
    DEFAULT_ACTION_REGISTRY,
    DEFAULT_ACTIONS,
    Action,
    ActionRegistry,
    ApprovalEnvelope,
)
from runtime.contracts import RiskLevel


def valid_envelope() -> ApprovalEnvelope:
    return ApprovalEnvelope(
        envelope_id="ad-20261118-001",
        module="06",
        action_type="ad_budget",
        risk=RiskLevel.APPROVAL,
        actions=[
            Action(
                action="ad.set_budget",
                target="campaign:123",
                before={"budget": 200},
                after={"budget": 120},
                reason="ROAS 低于盈亏线 0.5×，P0 止血",
                evidence=["ad-report#row-18", "fee-preset#shopee_br"],
                rollback="恢复 budget=200",
            )
        ],
    )


class ActionRegistryTest(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(DEFAULT_ACTION_REGISTRY.classify("market.read"), RiskLevel.AUTO)
        self.assertEqual(DEFAULT_ACTION_REGISTRY.classify("ad.set_budget"), RiskLevel.APPROVAL)
        self.assertEqual(DEFAULT_ACTION_REGISTRY.classify("ad.pause"), RiskLevel.FORBIDDEN)
        self.assertEqual(DEFAULT_ACTION_REGISTRY.classify("unknown.action"), RiskLevel.FORBIDDEN)

    def test_metadata_and_agent_actions(self):
        metadata = DEFAULT_ACTION_REGISTRY.metadata()
        self.assertTrue(any(item["action"] == "ad.set_budget" for item in metadata))
        actions = DEFAULT_ACTION_REGISTRY.for_agent("advertising")
        self.assertTrue(any(item.action == "ad.set_budget" for item in actions))

    def test_duplicate_registration_rejected(self):
        with self.assertRaises(ValueError):
            ActionRegistry(DEFAULT_ACTIONS + (DEFAULT_ACTIONS[0],))


class ApprovalEnvelopeTest(unittest.TestCase):
    def test_valid_envelope(self):
        envelope = valid_envelope()
        self.assertEqual(envelope.validate(DEFAULT_ACTION_REGISTRY), [])

    def test_missing_evidence(self):
        envelope = valid_envelope()
        envelope.actions[0].evidence = []
        errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
        self.assertTrue(any("evidence" in error for error in errors))

    def test_auto_action_rejected(self):
        envelope = valid_envelope()
        envelope.actions[0].action = "market.read"
        errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
        self.assertTrue(any("不能进审批信封" in error for error in errors))

    def test_unknown_action_rejected(self):
        envelope = valid_envelope()
        envelope.actions[0].action = "foo.bar"
        errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
        self.assertTrue(any("未知" in error for error in errors))

    def test_forbidden_action_rejected(self):
        envelope = valid_envelope()
        envelope.actions[0].action = "ad.pause"
        errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
        self.assertTrue(any("不能进审批信封" in error for error in errors))

    def test_approved_requires_decided_by(self):
        envelope = valid_envelope()
        envelope.decision = "approved"
        errors = envelope.validate(DEFAULT_ACTION_REGISTRY)
        self.assertTrue(any("decided_by" in error for error in errors))

    def test_drift_detection(self):
        envelope = valid_envelope()
        self.assertEqual(envelope.check_drift({"campaign:123": {"budget": 200}}), [])
        errors = envelope.check_drift({"campaign:123": {"budget": 180}})
        self.assertTrue(any("快照漂移" in error for error in errors))

    def test_roundtrip(self):
        envelope = valid_envelope()
        restored = ApprovalEnvelope.from_dict(envelope.to_dict())
        self.assertEqual(restored.envelope_id, envelope.envelope_id)
        self.assertEqual(restored.risk, RiskLevel.APPROVAL)
        self.assertEqual(restored.actions[0].before, {"budget": 200})


if __name__ == "__main__":
    unittest.main()
