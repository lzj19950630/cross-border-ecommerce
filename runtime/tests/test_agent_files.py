import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from runtime.agent_files import (
    AGENT_DIRS,
    MAX_WRITE_BYTES,
    AgentFileNotFound,
    AgentFileService,
    AgentFileTooLarge,
    InvalidAgentPath,
    UnknownAgentError,
)
from runtime.agent_registry import DEFAULT_REGISTRY
from runtime.api import create_app
from runtime.storage import InMemoryStore

ADMIN = {"Authorization": "Bearer admin-key"}
OP = {"Authorization": "Bearer op-key"}


def _make_service(tmp: Path) -> AgentFileService:
    root = tmp / "Agents"
    for dirname in AGENT_DIRS.values():
        agent_dir = root / dirname
        (agent_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (agent_dir / "references").mkdir(parents=True, exist_ok=True)
        (agent_dir / "SKILL.md").write_text(f"# {dirname}\n", encoding="utf-8")
        (agent_dir / "prompts" / "00_system.md").write_text("system", encoding="utf-8")
        (agent_dir / "references" / "notes.md").write_text("notes", encoding="utf-8")
    return AgentFileService(root=root, backup_dir=tmp / ".runtime" / "agent_backups")


class AgentFileServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.service = _make_service(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_dirs_cover_registry(self):
        self.assertEqual(set(AGENT_DIRS), set(DEFAULT_REGISTRY.keys()))

    def test_list_agents(self):
        agents = self.service.list_agents()
        self.assertEqual(len(agents), 7)
        first = agents[0]
        self.assertTrue(first["dir_exists"])
        paths = {item["path"] for item in first["files"]}
        self.assertIn("SKILL.md", paths)
        self.assertIn("prompts/00_system.md", paths)
        self.assertIn("references/notes.md", paths)

    def test_read_and_write_with_backup(self):
        before = self.service.read("product_image", "prompts/00_system.md")
        self.assertEqual(before["content"], "system")
        result = self.service.write(
            "product_image", "prompts/00_system.md", "新系统提示词", user="alice"
        )
        self.assertEqual(result["size"], len("新系统提示词".encode("utf-8")))
        self.assertTrue(Path(result["backup"]).is_file())
        self.assertEqual(
            self.service.read("product_image", "prompts/00_system.md")["content"],
            "新系统提示词",
        )
        edits = self.service.edits()
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["user"], "alice")
        self.assertEqual(edits[0]["path"], "prompts/00_system.md")

    def test_path_traversal_rejected(self):
        for path in (
            "../outside.md",
            "prompts/../../runtime/api.py",
            "/etc/passwd",
            "C:/Windows/win.ini",
            "prompts/evil.exe",
            "random.md",
            "SKILL.md.bak",
        ):
            with self.assertRaises(InvalidAgentPath, msg=path):
                self.service.read("product_image", path)

    def test_unknown_agent(self):
        with self.assertRaises(UnknownAgentError):
            self.service.read("nope", "SKILL.md")

    def test_missing_file(self):
        with self.assertRaises(AgentFileNotFound):
            self.service.read("product_image", "prompts/missing.md")

    def test_write_size_limit(self):
        with self.assertRaises(AgentFileTooLarge):
            self.service.write(
                "product_image", "SKILL.md", "x" * (MAX_WRITE_BYTES + 1)
            )


class AgentFileApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.service = _make_service(self.tmp)
        self.client = TestClient(
            create_app(
                store=InMemoryStore(),
                executor="sequential",
                checkpointer="memory",
                agent_service=self.service,
                api_keys={"admin-key": "alice:admin", "op-key": "bob:operator"},
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_list_and_read(self):
        agents = self.client.get("/api/agents", headers=ADMIN)
        self.assertEqual(agents.status_code, 200)
        self.assertEqual(len(agents.json()["agents"]), 7)
        response = self.client.get(
            "/api/agents/product_image/file",
            params={"path": "SKILL.md"},
            headers=OP,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("content", response.json())

    def test_only_admin_can_write(self):
        payload = {"path": "SKILL.md", "content": "# updated\n"}
        denied = self.client.put(
            "/api/agents/product_image/file", json=payload, headers=OP
        )
        self.assertEqual(denied.status_code, 403)
        saved = self.client.put(
            "/api/agents/product_image/file", json=payload, headers=ADMIN
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(Path(saved.json()["backup"]).is_file())
        edits = self.client.get("/api/agents/edits", headers=ADMIN)
        self.assertEqual(edits.status_code, 200)
        self.assertEqual(edits.json()["edits"][0]["user"], "alice")

    def test_invalid_path_and_unknown_agent(self):
        traversal = self.client.get(
            "/api/agents/product_image/file",
            params={"path": "../runtime/api.py"},
            headers=ADMIN,
        )
        self.assertEqual(traversal.status_code, 400)
        unknown = self.client.get(
            "/api/agents/nope/file", params={"path": "SKILL.md"}, headers=ADMIN
        )
        self.assertEqual(unknown.status_code, 404)


if __name__ == "__main__":
    unittest.main()
