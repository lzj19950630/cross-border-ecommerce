import unittest

from runtime.actions import Action, ApprovalEnvelope
from runtime.agent_runners import AgentContext, AgentResult, RunnerRegistry
from runtime.contracts import RiskLevel
from runtime.engine import RuntimeEngine
from runtime.evidence import EvidenceBlock, EvidenceItem
from runtime.storage import TaskRecord


class NoEvidenceRunner:
    def run(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent=context.slice.agent,
            status="ok",
            artifact={"x": 1},
            evidence=EvidenceBlock(),
        )


class BadEnvelopeRunner:
    def run(self, context: AgentContext) -> AgentResult:
        evidence = EvidenceBlock(items=[EvidenceItem(
            claim_id="C-X-01",
            claim="test claim",
            evidence_type="manual",
            source="test",
            locator="test",
            retrieved_at="2026-11-18",
        )])
        envelope = ApprovalEnvelope(
            envelope_id="bad-env",
            module="06",
            action_type="test",
            risk=RiskLevel.APPROVAL,
            actions=[Action(
                action="ad.set_budget",
                target="campaign:1",
                before={"budget": 1},
                after={"budget": 2},
                reason="test",
                evidence=[],  # 故意缺失
                rollback="restore",
            )],
            requested_by="test",
        )
        return AgentResult(
            agent=context.slice.agent,
            status="ok",
            artifact={"x": 1},
            evidence=evidence,
            envelope=envelope,
        )


class EngineInvariantTest(unittest.TestCase):
    def test_no_evidence_blocks_delivery(self):
        engine = RuntimeEngine(runners=RunnerRegistry({"advertising": NoEvidenceRunner()}))
        task = engine.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "failed")
        self.assertIn("缺少证据", task.error)

    def test_invalid_envelope_blocks_delivery(self):
        engine = RuntimeEngine(runners=RunnerRegistry({"advertising": BadEnvelopeRunner()}))
        task = engine.run("广告 ROAS 太低，怎么降预算")
        self.assertEqual(task.status, "failed")
        self.assertIn("审批信封校验失败", task.error)

    def test_invalid_task_status_rejected(self):
        task = TaskRecord(thread_id="t1", request="x")
        with self.assertRaises(ValueError):
            task.set_status("not_a_status")

    def test_task_roundtrip_preserves_status(self):
        task = TaskRecord(thread_id="t1", request="x")
        task.set_status("interrupted")
        restored = TaskRecord.from_dict(task.to_dict())
        self.assertEqual(restored.status, "interrupted")


if __name__ == "__main__":
    unittest.main()
