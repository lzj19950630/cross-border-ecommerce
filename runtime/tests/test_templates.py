import unittest
from pathlib import Path

import yaml

from runtime.actions import DEFAULT_ACTION_REGISTRY, ApprovalEnvelope
from runtime.agent_registry import DEFAULT_REGISTRY
from runtime.contracts import EvalCase, SlicePlan
from runtime.evidence import EvidenceBlock

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "Templates"


class TemplateContractTest(unittest.TestCase):
    def test_action_envelope_template(self):
        data = yaml.safe_load((TEMPLATES / "action_approval_envelope.yaml").read_text(encoding="utf-8"))
        envelope = ApprovalEnvelope.from_dict(data)
        self.assertEqual(envelope.validate(DEFAULT_ACTION_REGISTRY), [])

    def test_evidence_template(self):
        data = yaml.safe_load((TEMPLATES / "evidence_block.yaml").read_text(encoding="utf-8"))
        block = EvidenceBlock.from_dict(data)
        self.assertEqual(block.validate(), [])

    def test_workflow_plan_template(self):
        data = yaml.safe_load((TEMPLATES / "workflow_plan.yaml").read_text(encoding="utf-8"))
        plan = SlicePlan.from_dict(data)
        plan.validate({spec.key: spec for spec in DEFAULT_REGISTRY.all()})

    def test_eval_template(self):
        data = yaml.safe_load((TEMPLATES / "eval_case.yaml").read_text(encoding="utf-8"))
        for raw in data.get("scenarios") or []:
            EvalCase.from_dict(raw).validate()


if __name__ == "__main__":
    unittest.main()
