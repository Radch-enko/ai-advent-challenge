import asyncio
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError

from code_assistance.config import AppConfig
from code_assistance.errors import BranchUnavailableError, GitUnavailableError
from code_assistance.models import BranchContext, GitEvidence, ToolDefinition

SAFE_MCP_ENVIRONMENT = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    }
)
COMMIT_PATTERN = re.compile(r"[0-9a-fA-F]{7,64}")


class MCPBranchProvider:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def available_tools(self, repository_root: Path) -> list[ToolDefinition]:
        if self.config.mcp_command is None:
            raise GitUnavailableError("No Git MCP server is configured.")
        try:
            return asyncio.run(self._list_tools(repository_root))
        except (TimeoutError, OSError, MCPError, RuntimeError, ValueError) as exc:
            raise GitUnavailableError("The configured Git MCP server is unavailable.") from exc

    async def _list_tools(self, repository_root: Path) -> list[ToolDefinition]:
        command = self.config.mcp_command
        assert command is not None
        environment = {
            key: value for key, value in os.environ.items() if key in SAFE_MCP_ENVIRONMENT
        }
        server = StdioServerParameters(
            command=command[0], args=list(command[1:]), env=environment, cwd=repository_root
        )
        allowed = {self.config.mcp_tool_name, "get_status", "get_recent_commits", "get_diff"}
        async with asyncio.timeout(self.config.mcp_timeout_seconds):
            async with Client(server) as client:
                listing = await client.list_tools()
        definitions = []
        for tool in listing.tools:
            if tool.name not in allowed:
                continue
            schema = tool.input_schema
            if not isinstance(schema, dict) or schema.get("type") != "object":
                raise GitUnavailableError("The Git MCP tool schema is invalid.")
            properties = schema.get("properties", {})
            if not isinstance(properties, dict):
                raise GitUnavailableError("The Git MCP tool schema is invalid.")
            repo_schema = properties.get("repo_path")
            if not isinstance(repo_schema, dict) or repo_schema.get("type") != "string":
                raise GitUnavailableError("The Git MCP tool schema has no repository path.")
            exposed = {key: value for key, value in properties.items() if key != "repo_path"}
            if exposed:
                raise GitUnavailableError("The Git MCP tool schema has unsupported arguments.")
            required = schema.get("required", [])
            if not isinstance(required, list):
                raise GitUnavailableError("The Git MCP tool schema is invalid.")
            parameters: dict[str, object] = {
                "type": "object",
                "properties": exposed,
                "required": [key for key in required if key != "repo_path"],
                "additionalProperties": False,
            }
            definitions.append(ToolDefinition(tool.name, tool.description or "", parameters))
        return definitions

    def call_evidence(self, name: str, repository_root: Path) -> list[GitEvidence]:
        if name == self.config.mcp_tool_name:
            try:
                branch = self.current_branch(repository_root)
            except BranchUnavailableError as exc:
                raise GitUnavailableError(str(exc)) from exc
            text = (
                f"HEAD is detached at {branch.commit_sha}."
                if branch.detached
                else f"Current branch: {branch.branch}; commit: {branch.commit_sha}."
            )
            return [GitEvidence("Git branch", text)]
        if name == "get_status":
            return self.status(repository_root)
        if name == "get_recent_commits":
            return self.recent_commits(repository_root)
        if name == "get_diff":
            return self.diff(repository_root)
        raise GitUnavailableError("The model requested an unavailable Git tool.")

    def current_branch(self, repository_root: Path) -> BranchContext:
        if self.config.mcp_command is None:
            raise BranchUnavailableError(
                "No Git MCP server is configured. Add [git_mcp].command to "
                f"{self.config.config_path}."
            )
        try:
            return asyncio.run(self._call_tool(repository_root))
        except BranchUnavailableError:
            raise
        except (TimeoutError, OSError, MCPError, RuntimeError, ValueError) as exc:
            raise BranchUnavailableError(
                "The configured Git MCP server is unavailable or returned an invalid response."
            ) from exc

    def status(self, repository_root: Path) -> list[GitEvidence]:
        data = self._read_git_tool(repository_root, "get_status")
        entries = data.get("entries")
        if not isinstance(entries, list) or not isinstance(data.get("truncated"), bool):
            raise GitUnavailableError("The Git MCP status response is invalid.")
        evidence = []
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("path"), str)
                or not isinstance(entry.get("status"), str)
            ):
                raise GitUnavailableError("The Git MCP status response is invalid.")
            path = _safe_reference_path(entry["path"])
            evidence.append(GitEvidence(f"Git status: {path}", f"{entry['status']} {path}"))
        if not evidence:
            evidence.append(
                GitEvidence("Git status", "No reportable changes; excluded paths may exist.")
            )
        if data["truncated"]:
            evidence.append(GitEvidence("Git status", "Status output was truncated."))
        return evidence

    def recent_commits(self, repository_root: Path) -> list[GitEvidence]:
        data = self._read_git_tool(repository_root, "get_recent_commits")
        commits = data.get("commits")
        if not isinstance(commits, list):
            raise GitUnavailableError("The Git MCP history response is invalid.")
        evidence = []
        for commit in commits:
            if (
                not isinstance(commit, dict)
                or not isinstance(commit.get("sha"), str)
                or not isinstance(commit.get("subject"), str)
            ):
                raise GitUnavailableError("The Git MCP history response is invalid.")
            sha = commit["sha"]
            if COMMIT_PATTERN.fullmatch(sha) is None:
                raise GitUnavailableError("The Git MCP history response contains an invalid SHA.")
            evidence.append(GitEvidence(f"commit {sha}", f"{sha} {commit['subject'][:500]}"))
        return evidence or [GitEvidence("Git history", "No commits exist yet.")]

    def diff(self, repository_root: Path) -> list[GitEvidence]:
        files, truncated = self.diff_entries(repository_root)
        evidence = [GitEvidence(f"{path} ({kind} diff)", patch) for path, kind, patch in files]
        if not evidence:
            evidence.append(
                GitEvidence("Git diff", "No reportable tracked changes; excluded paths may exist.")
            )
        if truncated:
            evidence.append(GitEvidence("Git diff", "Diff output was truncated."))
        return evidence

    def diff_entries(self, repository_root: Path) -> tuple[list[tuple[str, str, str]], bool]:
        data = self._read_git_tool(repository_root, "get_diff")
        files = data.get("files")
        if not isinstance(files, list) or not isinstance(data.get("truncated"), bool):
            raise GitUnavailableError("The Git MCP diff response is invalid.")
        entries = []
        for item in files:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(key), str) for key in ("path", "kind", "patch")
            ):
                raise GitUnavailableError("The Git MCP diff response is invalid.")
            path = _safe_reference_path(item["path"])
            kind = item["kind"]
            if kind not in ("staged", "unstaged"):
                raise GitUnavailableError("The Git MCP diff response has an invalid kind.")
            entries.append((path, kind, item["patch"][:16_384]))
        return entries, data["truncated"]

    def _read_git_tool(self, repository_root: Path, name: str) -> dict[str, Any]:
        if self.config.mcp_command is None:
            raise GitUnavailableError("No Git MCP server is configured.")
        try:
            data = asyncio.run(self._call_named_tool(repository_root, name))
        except (TimeoutError, OSError, MCPError, RuntimeError, ValueError) as exc:
            raise GitUnavailableError(
                "The configured Git MCP server is unavailable or returned an invalid response."
            ) from exc
        if not isinstance(data, dict):
            raise GitUnavailableError("The Git MCP tool did not return structured data.")
        return data

    async def _call_named_tool(self, repository_root: Path, name: str) -> Any:
        command = self.config.mcp_command
        assert command is not None
        environment = {
            key: value for key, value in os.environ.items() if key in SAFE_MCP_ENVIRONMENT
        }
        server = StdioServerParameters(
            command=command[0], args=list(command[1:]), env=environment, cwd=repository_root
        )
        async with asyncio.timeout(self.config.mcp_timeout_seconds):
            async with Client(server) as client:
                result = await client.call_tool(name, {"repo_path": str(repository_root.resolve())})
        if result.is_error:
            raise GitUnavailableError("The configured Git MCP tool returned an error.")
        return result.structured_content

    async def _call_tool(self, repository_root: Path) -> BranchContext:
        command = self.config.mcp_command
        if command is None:
            raise BranchUnavailableError("No Git MCP server is configured.")
        environment = {
            key: value for key, value in os.environ.items() if key in SAFE_MCP_ENVIRONMENT
        }
        server = StdioServerParameters(
            command=command[0],
            args=list(command[1:]),
            env=environment,
            cwd=repository_root,
        )
        async with asyncio.timeout(self.config.mcp_timeout_seconds):
            async with Client(server) as client:
                result = await client.call_tool(
                    self.config.mcp_tool_name,
                    {"repo_path": str(repository_root.resolve())},
                )
        if result.is_error:
            raise BranchUnavailableError("The configured Git MCP tool returned an error.")
        return self._parse_result(result.structured_content)

    @staticmethod
    def _parse_result(value: Any) -> BranchContext:
        if not isinstance(value, dict):
            raise BranchUnavailableError(
                "The Git MCP tool must return structured branch, detached, and commit_sha fields."
            )
        branch_value = value.get("branch")
        detached_value = value.get("detached")
        commit_value = value.get("commit_sha")
        if branch_value is not None and not isinstance(branch_value, str):
            raise BranchUnavailableError("The Git MCP tool returned an invalid branch name.")
        if not isinstance(detached_value, bool):
            raise BranchUnavailableError("The Git MCP tool returned an invalid detached status.")
        if commit_value is not None and not isinstance(commit_value, str):
            raise BranchUnavailableError("The Git MCP tool returned an invalid commit SHA.")

        branch = _printable(branch_value) if branch_value is not None else None
        commit_sha = _printable(commit_value) if commit_value is not None else None
        if branch == "":
            branch = None
        if commit_sha is not None and COMMIT_PATTERN.fullmatch(commit_sha) is None:
            raise BranchUnavailableError("The Git MCP tool returned an invalid commit SHA.")
        if not detached_value and branch is None:
            raise BranchUnavailableError("The Git MCP tool omitted the current branch name.")
        if detached_value and commit_sha is None:
            raise BranchUnavailableError("The Git MCP tool omitted the detached HEAD commit SHA.")
        return BranchContext(branch=branch, detached=detached_value, commit_sha=commit_sha)


def _printable(value: str) -> str:
    return "".join(
        character for character in value if not unicodedata.category(character).startswith("C")
    ).strip()


def _safe_reference_path(value: str) -> str:
    path = Path(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or any(ord(char) < 32 for char in value)
    ):
        raise GitUnavailableError("The Git MCP tool returned an unsafe file path.")
    return value
