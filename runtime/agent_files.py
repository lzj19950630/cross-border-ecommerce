"""Agent 文件管理：SKILL.md / prompts / references / templates 的查看与编辑。

安全边界：
- 只允许 Agents/<agent>/ 下的白名单路径（顶层 SKILL.md/README.md，或
  prompts/、references/、templates/ 子目录里的 .md/.yaml/.yml/.json/.txt）；
- 只允许覆盖已存在的文件，不提供创建/删除/重命名；
- 每次写入前自动备份到 .runtime/agent_backups/<agent>/，并追加编辑日志
  .runtime/agent_backups/edits.jsonl；
- 读 512KB / 写 256KB 上限，UTF-8。
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import shutil
import threading
from typing import Any

from .agent_registry import AgentRegistry, DEFAULT_REGISTRY


# Agent key → Agents/ 下的目录名。新增 Agent 时同步维护；测试会校验覆盖完整性。
AGENT_DIRS: dict[str, str] = {
    "market_research": "01_Market_Research_Agent",
    "product_strategy": "02_Product_Strategy_Agent",
    "listing_creative": "03_Listing_Creative_Agent",
    "product_image": "04_Product_Image_Agent",
    "product_video": "05_Product_Video_Agent",
    "advertising": "06_Advertising_Optimization_Agent",
    "review_analysis": "07_Review_Analysis_Agent",
}

ALLOWED_TOP_FILES = frozenset({"SKILL.md", "README.md"})
ALLOWED_SUBDIRS = frozenset({"prompts", "references", "templates"})
ALLOWED_SUFFIXES = frozenset({".md", ".yaml", ".yml", ".json", ".txt"})
MAX_READ_BYTES = 512 * 1024
MAX_WRITE_BYTES = 256 * 1024
MAX_BACKUPS_PER_AGENT = 30


class AgentFileError(Exception):
    """Agent 文件操作的业务异常，带 HTTP 状态码。"""

    status_code = 400


class UnknownAgentError(AgentFileError):
    status_code = 404


class InvalidAgentPath(AgentFileError):
    status_code = 400


class AgentFileNotFound(AgentFileError):
    status_code = 404


class AgentFileTooLarge(AgentFileError):
    status_code = 413


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AgentFileService:
    """对一个 Agents/ 根目录做安全的列举/读取/写入。"""

    def __init__(
        self,
        root: str | Path | None = None,
        backup_dir: str | Path | None = None,
        registry: AgentRegistry = DEFAULT_REGISTRY,
    ) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        self.root = Path(root) if root is not None else repo_root / "Agents"
        self.backup_dir = (
            Path(backup_dir)
            if backup_dir is not None
            else repo_root / ".runtime" / "agent_backups"
        )
        self.registry = registry
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 查询
    def list_agents(self) -> list[dict[str, Any]]:
        return [self.get_agent(spec.key) for spec in self.registry.all()]

    def get_agent(self, key: str) -> dict[str, Any]:
        spec = self._spec(key)
        agent_dir = self._agent_dir(key)
        data = spec.to_dict()
        data.update(
            {
                "dir": AGENT_DIRS[key],
                "dir_exists": agent_dir.is_dir(),
                "files": self._list_files(agent_dir),
            }
        )
        return data

    def read(self, key: str, rel_path: str) -> dict[str, Any]:
        rel = self._normalize(key, rel_path)
        target = self._resolve(key, rel)
        size = target.stat().st_size
        if size > MAX_READ_BYTES:
            raise AgentFileTooLarge(
                f"文件超过读取上限（{size} > {MAX_READ_BYTES} bytes）：{rel}"
            )
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AgentFileError(f"文件不是 UTF-8 文本：{rel}") from exc
        return {
            "agent": key,
            "path": rel,
            "content": content,
            "size": size,
            "editable": True,
            "updated_at": self._mtime(target),
        }

    def write(
        self, key: str, rel_path: str, content: str, user: str = "anonymous"
    ) -> dict[str, Any]:
        rel = self._normalize(key, rel_path)
        target = self._resolve(key, rel)
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_WRITE_BYTES:
            raise AgentFileTooLarge(
                f"内容超过写入上限（{len(encoded)} > {MAX_WRITE_BYTES} bytes）"
            )
        with self._lock:
            backup = self._backup(key, rel, target)
            with target.open("w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            self._log_edit(
                key=key, rel=rel, user=user, size=len(encoded), backup=backup
            )
            self._prune_backups(key)
        return {
            "agent": key,
            "path": rel,
            "size": len(encoded),
            "backup": str(backup),
            "updated_at": self._mtime(target),
        }

    def edits(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        log_path = self.backup_dir / "edits.jsonl"
        if not log_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        with log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return list(reversed(rows[-limit:]))

    # ------------------------------------------------------------------ 内部
    def _spec(self, key: str):
        try:
            return self.registry.get(key)
        except KeyError as exc:
            raise UnknownAgentError(f"未知 Agent：{key}") from exc

    def _agent_dir(self, key: str) -> Path:
        self._spec(key)
        return self.root / AGENT_DIRS[key]

    def _list_files(self, agent_dir: Path) -> list[dict[str, Any]]:
        if not agent_dir.is_dir():
            return []
        entries: dict[str, dict[str, Any]] = {}
        for name in sorted(ALLOWED_TOP_FILES):
            path = agent_dir / name
            if path.is_file():
                entries[name] = self._entry(agent_dir, path)
        for sub in sorted(ALLOWED_SUBDIRS):
            base = agent_dir / sub
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(agent_dir).as_posix()
                if self._is_allowed_rel(rel):
                    entries[rel] = self._entry(agent_dir, path)
        return [entries[name] for name in sorted(entries)]

    def _entry(self, agent_dir: Path, path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "path": path.relative_to(agent_dir).as_posix(),
            "size": stat.st_size,
            "updated_at": self._mtime(path),
            "editable": True,
        }

    def _normalize(self, key: str, rel_path: str) -> str:
        self._spec(key)
        return self._normalize_rel(rel_path)

    @staticmethod
    def _normalize_rel(rel_path: str) -> str:
        if not isinstance(rel_path, str) or not rel_path.strip():
            raise InvalidAgentPath("path 不能为空")
        raw = rel_path.strip()
        if "\x00" in raw or "\\" in raw or ":" in raw:
            raise InvalidAgentPath(f"非法路径：{rel_path}")
        path = PurePosixPath(raw)
        if path.is_absolute():
            raise InvalidAgentPath(f"非法路径：{rel_path}")
        parts = path.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise InvalidAgentPath(f"非法路径：{rel_path}")
        if len(parts) == 1:
            if parts[0] not in ALLOWED_TOP_FILES:
                raise InvalidAgentPath(f"不允许访问的文件：{rel_path}")
        elif parts[0] not in ALLOWED_SUBDIRS:
            raise InvalidAgentPath(f"不允许访问的目录：{rel_path}")
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise InvalidAgentPath(f"不允许的文件类型：{rel_path}")
        return path.as_posix()

    def _is_allowed_rel(self, rel: str) -> bool:
        try:
            self._normalize_rel(rel)
        except AgentFileError:
            return False
        return True

    def _resolve(self, key: str, rel: str) -> Path:
        agent_dir = self._agent_dir(key).resolve()
        target = (agent_dir / PurePosixPath(rel)).resolve()
        try:
            target.relative_to(agent_dir)
        except ValueError as exc:
            raise InvalidAgentPath(f"路径越界：{rel}") from exc
        if not target.is_file():
            raise AgentFileNotFound(f"文件不存在：{rel}")
        return target

    def _backup(self, key: str, rel: str, target: Path) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe = rel.replace("/", "__")
        folder = self.backup_dir / key
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / f"{stamp}__{safe}"
        shutil.copy2(target, backup)
        return backup

    def _log_edit(
        self, key: str, rel: str, user: str, size: int, backup: Path
    ) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "at": _now(),
            "agent": key,
            "path": rel,
            "user": user,
            "bytes": size,
            "backup": str(backup),
        }
        with (self.backup_dir / "edits.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _prune_backups(self, key: str) -> None:
        folder = self.backup_dir / key
        if not folder.is_dir():
            return
        files = sorted(
            (path for path in folder.iterdir() if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in files[MAX_BACKUPS_PER_AGENT:]:
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _mtime(path: Path) -> str:
        return datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        ).isoformat(timespec="seconds")
