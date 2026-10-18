"""Bounded, policy-checked file tools for an interactive coding agent."""

import difflib
import hashlib
import json
import os
import stat
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from code_assistance.config import AppConfig
from code_assistance.errors import AgentFileError
from code_assistance.file_policy import is_hard_excluded
from code_assistance.models import ToolDefinition

MAX_AGENT_FILE_BYTES = 131_072
MAX_LISTED_FILES = 200
MAX_SEARCHED_FILES = 2_000
MAX_SEARCHED_BYTES = 5_242_880
MAX_SEARCH_MATCHES = 30
MAX_CHANGED_FILES = 12


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _utf8(value: str) -> bytes:
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AgentFileError("Only UTF-8 text is supported.") from exc


def _patched_content(patch: str, current: bytes | None) -> tuple[str, bytes]:
    encoded = _utf8(patch)
    if len(encoded) > MAX_AGENT_FILE_BYTES * 2 or "\0" in patch or "\r" in patch:
        raise AgentFileError("Patch is binary or exceeds the size limit.")
    if not patch.endswith("\n"):
        raise AgentFileError("Invalid patch envelope.")
    lines = patch.split("\n")[:-1]
    if len(lines) < 4 or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise AgentFileError("Invalid patch envelope.")
    header = lines[1]
    if header.startswith("*** Add File: "):
        path = header[len("*** Add File: ") :]
        if (
            current is not None
            or not lines[2:-1]
            or any(not line.startswith("+") for line in lines[2:-1])
        ):
            raise AgentFileError("Invalid new-file patch.")
        return path, _utf8("\n".join(line[1:] for line in lines[2:-1]) + "\n")
    if not header.startswith("*** Update File: ") or current is None:
        raise AgentFileError("Invalid update-file patch.")
    path = header[len("*** Update File: ") :]
    source = current.decode("utf-8")
    original_lines = source.split("\n")
    if source.endswith("\n"):
        original_lines.pop()
    output: list[str] = []
    cursor = 0
    body = lines[2:-1]
    if not body or body[0] != "@@":
        raise AgentFileError("Patch requires an @@ hunk.")
    hunks: list[list[str]] = []
    for line in body:
        if line == "@@":
            hunks.append([])
        elif not hunks or not line or line[0] not in " +-":
            raise AgentFileError("Invalid patch hunk.")
        else:
            hunks[-1].append(line)
    for hunk in hunks:
        if not hunk or not any(line[0] in "+-" for line in hunk):
            raise AgentFileError("Patch hunk has no changes.")
        old = [line[1:] for line in hunk if line[0] != "+"]
        new = [line[1:] for line in hunk if line[0] != "-"]
        if not old:
            raise AgentFileError("Insertion needs a context line.")
        positions = [
            index
            for index in range(cursor, len(original_lines) - len(old) + 1)
            if original_lines[index : index + len(old)] == old
        ]
        if len(positions) != 1:
            raise AgentFileError("Patch context is missing or ambiguous.")
        position = positions[0]
        output.extend(original_lines[cursor:position])
        output.extend(new)
        cursor = position + len(old)
    output.extend(original_lines[cursor:])
    result = "\n".join(output) + ("\n" if source.endswith("\n") else "")
    return path, _utf8(result)


@dataclass(frozen=True)
class ProposedFile:
    original: bytes | None
    content: bytes


class AgentFileWorkspace:
    def __init__(self, root: Path, config: AppConfig) -> None:
        self.root = root.resolve(strict=True)
        self.config = config
        self.proposals: dict[str, ProposedFile] = {}
        if not all(
            (
                config.agent_read_roots,
                config.agent_write_roots,
                config.agent_read_extensions,
                config.agent_write_extensions,
            )
        ):
            raise AgentFileError("Configure [agent.files] allowlists before using /agent.")

    def _relative(self, raw: str, write: bool = False) -> Path:
        _utf8(raw)
        path = Path(raw)
        if (
            not raw
            or raw != path.as_posix()
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in raw
            or any(ord(char) < 32 for char in raw)
            or any(part.startswith(".") for part in path.parts if part != ".")
            or is_hard_excluded(path)
        ):
            raise AgentFileError("File access denied by path policy.")
        roots = self.config.agent_write_roots if write else self.config.agent_read_roots
        extensions = (
            self.config.agent_write_extensions if write else self.config.agent_read_extensions
        )
        if not any(
            root == "." or path == Path(root) or Path(root) in path.parents for root in roots
        ):
            raise AgentFileError("File access denied by directory allowlist.")
        if path.suffix.casefold() not in extensions:
            raise AgentFileError("File access denied by extension allowlist.")
        return path

    def _is_ignored(self, path: Path) -> bool:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.root),
                    "check-ignore",
                    "--no-index",
                    "--quiet",
                    "--",
                    path.as_posix(),
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AgentFileError("Cannot check Git ignore rules.") from exc
        if result.returncode not in (0, 1):
            raise AgentFileError("Cannot check Git ignore rules.")
        return result.returncode == 0

    @contextmanager
    def _parent_fd(self, path: Path) -> Iterator[int]:
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        descriptors: list[int] = []
        try:
            descriptor = os.open(self.root, flags)
            descriptors.append(descriptor)
            for component in path.parts[:-1]:
                descriptor = os.open(component, flags, dir_fd=descriptor)
                descriptors.append(descriptor)
            yield descriptor
        except OSError as exc:
            raise AgentFileError("File path is unavailable or contains a symbolic link.") from exc
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def _read_disk(self, path: Path, allow_missing: bool = False) -> bytes | None:
        if self._is_ignored(path):
            raise AgentFileError("File access denied by Git ignore rules.")
        with self._parent_fd(path) as parent:
            try:
                descriptor = os.open(
                    path.name,
                    os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent,
                )
            except FileNotFoundError as exc:
                if allow_missing:
                    return None
                raise AgentFileError("File does not exist.") from exc
            except OSError as exc:
                raise AgentFileError("File cannot be opened safely.") from exc
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise AgentFileError("Only regular, non-linked files are supported.")
                if metadata.st_size > MAX_AGENT_FILE_BYTES:
                    raise AgentFileError("File exceeds the agent size limit.")
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    content = source.read(MAX_AGENT_FILE_BYTES + 1)
            finally:
                os.close(descriptor)
        if len(content) > MAX_AGENT_FILE_BYTES or b"\0" in content:
            raise AgentFileError("Binary or oversized files are not supported.")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AgentFileError("Only UTF-8 text files are supported.") from exc
        return content

    def _read(self, raw: str, *, write: bool = False, allow_missing: bool = False) -> bytes | None:
        path = self._relative(raw, write=write)
        if not write and raw in self.proposals:
            actual = self._read_disk(path, allow_missing=True)
            if actual != self.proposals[raw].original:
                raise AgentFileError("A file changed after the proposal.")
            return self.proposals[raw].content
        return self._read_disk(path, allow_missing=allow_missing)

    def _prefix(self, raw: str) -> str:
        _utf8(raw)
        if raw == ".":
            return ""
        path = Path(raw)
        if (
            not raw
            or raw != path.as_posix()
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in raw
            or any(ord(char) < 32 for char in raw)
            or any(part.startswith(".") for part in path.parts)
            or is_hard_excluded(path)
        ):
            raise AgentFileError("Search prefix is not a safe relative directory.")
        return path.as_posix() + "/"

    def _candidate_files(self, prefix: str) -> Iterator[str]:
        selected_prefix = self._prefix(prefix)
        for current, directories, names in os.walk(self.root, followlinks=False):
            current_path = Path(current)
            directories[:] = sorted(
                name
                for name in directories
                if not name.startswith(".")
                and not is_hard_excluded(Path(name))
                and not (current_path / name).is_symlink()
            )
            for name in sorted(names):
                relative = (current_path / name).relative_to(self.root)
                relative_name = relative.as_posix()
                if not relative_name.startswith(selected_prefix):
                    continue
                try:
                    self._relative(relative_name)
                    if (current_path / name).is_symlink() or self._is_ignored(relative):
                        continue
                except AgentFileError:
                    continue
                yield relative_name
        for path in sorted(self.proposals):
            if path.startswith(selected_prefix) and not (self.root / path).exists():
                yield path

    def list_files(self, prefix: str = ".") -> dict[str, object]:
        files: list[str] = []
        for name in self._candidate_files(prefix):
            try:
                self._read(name)
            except AgentFileError:
                continue
            if len(files) == MAX_LISTED_FILES:
                return {"files": files, "truncated": True}
            files.append(name)
        return {"files": files, "truncated": False}

    def search_text(self, query: str, prefix: str = ".") -> dict[str, object]:
        _utf8(query)
        if not query or len(query) > 200 or "\0" in query:
            raise AgentFileError("Search query must contain 1 to 200 text characters.")
        matches: list[dict[str, object]] = []
        searched_files = 0
        searched_bytes = 0
        for name in self._candidate_files(prefix):
            try:
                content = self._read(name)
            except AgentFileError:
                continue
            assert content is not None
            if (
                searched_files == MAX_SEARCHED_FILES
                or searched_bytes + len(content) > MAX_SEARCHED_BYTES
            ):
                return {"matches": matches, "truncated": True}
            searched_files += 1
            searched_bytes += len(content)
            for number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
                if query.casefold() in line.casefold():
                    matches.append({"path": name, "line": number, "text": line[:300]})
                    if len(matches) == MAX_SEARCH_MATCHES:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    def read_file(self, path: str) -> dict[str, object]:
        content = self._read(path)
        assert content is not None
        return {"path": path, "sha256": _digest(content), "content": content.decode("utf-8")}

    def permits_read(self, path: str) -> bool:
        try:
            self._read(path)
        except AgentFileError:
            return False
        return True

    def apply_patch(self, patch: str, expected_sha256: str | None) -> dict[str, object]:
        encoded = _utf8(patch)
        if len(encoded) > MAX_AGENT_FILE_BYTES * 2 or "\0" in patch or "\r" in patch:
            raise AgentFileError("Patch is binary or exceeds the size limit.")
        lines = patch.split("\n")
        if len(lines) < 2:
            raise AgentFileError("Invalid patch envelope.")
        header = lines[1]
        if header.startswith("*** Update File: "):
            path = header[len("*** Update File: ") :]
        elif header.startswith("*** Add File: "):
            path = header[len("*** Add File: ") :]
        else:
            raise AgentFileError("Invalid patch file header.")
        relative = self._relative(path, write=True)
        self._relative(path)
        if path not in self.proposals and len(self.proposals) == MAX_CHANGED_FILES:
            raise AgentFileError("Too many proposed files.")
        current = self._read(path, allow_missing=True)
        actual = _digest(current) if current is not None else None
        if actual != expected_sha256:
            raise AgentFileError("File hash differs from the proposed base.")
        parsed_path, encoded = _patched_content(patch, current)
        if parsed_path != path or len(encoded) > MAX_AGENT_FILE_BYTES or b"\0" in encoded:
            raise AgentFileError("Patched file is binary or exceeds the size limit.")
        original = self.proposals[path].original if path in self.proposals else current
        self.proposals[path] = ProposedFile(original, encoded)
        return {"path": relative.as_posix(), "staged": True}

    def diff(self) -> str:
        chunks: list[str] = []
        for path, proposal in sorted(self.proposals.items()):
            old = (proposal.original or b"").decode("utf-8").splitlines(keepends=True)
            new = proposal.content.decode("utf-8").splitlines(keepends=True)
            chunks.extend(difflib.unified_diff(old, new, fromfile=f"a/{path}", tofile=f"b/{path}"))
        return "".join(chunks)

    def apply(self) -> list[str]:
        for name, proposal in sorted(self.proposals.items()):
            self._relative(name, write=True)
            actual = self._read_disk(Path(name), allow_missing=True)
            if actual != proposal.original:
                raise AgentFileError("A file changed after the proposal; no changes were applied.")
        changed: list[str] = []
        for name, proposal in sorted(self.proposals.items()):
            if proposal.original == proposal.content:
                continue
            relative = Path(name)
            temporary = f".code-assistance-{uuid.uuid4().hex}.tmp"
            try:
                with self._parent_fd(relative) as parent:
                    actual = self._read_disk(relative, allow_missing=True)
                    if actual != proposal.original:
                        detail = ", ".join(changed) if changed else "none"
                        raise AgentFileError(
                            f"A file changed during apply. Files already changed: {detail}."
                        )
                    if not os.access(".", os.W_OK, dir_fd=parent):
                        raise AgentFileError("Target directory is not writable.")
                    mode = 0o600
                    if proposal.original is not None:
                        metadata = os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
                        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                            raise AgentFileError("File is no longer a regular, non-linked file.")
                        if not os.access(
                            relative.name, os.W_OK, dir_fd=parent, follow_symlinks=False
                        ):
                            raise AgentFileError("Target file is not writable.")
                        mode = stat.S_IMODE(metadata.st_mode)
                    descriptor = os.open(
                        temporary,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                        mode,
                        dir_fd=parent,
                    )
                    try:
                        with os.fdopen(descriptor, "wb") as target:
                            target.write(proposal.content)
                            target.flush()
                            os.fsync(target.fileno())
                        if proposal.original is None:
                            os.link(
                                temporary,
                                relative.name,
                                src_dir_fd=parent,
                                dst_dir_fd=parent,
                                follow_symlinks=False,
                            )
                        else:
                            os.replace(
                                temporary, relative.name, src_dir_fd=parent, dst_dir_fd=parent
                            )
                    finally:
                        try:
                            os.unlink(temporary, dir_fd=parent)
                        except FileNotFoundError:
                            pass
                changed.append(name)
            except (OSError, AgentFileError) as exc:
                detail = ", ".join(changed) if changed else "none"
                raise AgentFileError(
                    f"Could not apply changes. Files already changed: {detail}."
                ) from exc
        return changed


def file_tool_definitions() -> list[ToolDefinition]:
    def schema(properties: dict[str, object], required: list[str]) -> dict[str, object]:
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    string = {"type": "string"}
    return [
        ToolDefinition(
            "list_files",
            "List permitted project files, optionally within a directory.",
            schema({"prefix": string}, []),
        ),
        ToolDefinition(
            "search_text",
            "Search permitted files for literal text with line numbers.",
            schema({"query": string, "prefix": string}, ["query"]),
        ),
        ToolDefinition(
            "read_file",
            "Read a permitted UTF-8 file and its SHA-256.",
            schema({"path": string}, ["path"]),
        ),
        ToolDefinition(
            "apply_patch",
            "Stage one exact, contextual patch in memory. Use *** Begin Patch, "
            "*** Update File: path or *** Add File: path, @@ hunks with space/-/+ "
            "lines, and *** End Patch. Existing files require their current SHA-256. "
            "Patches must end with a newline.",
            schema(
                {
                    "expected_sha256": {"type": ["string", "null"]},
                    "patch": string,
                },
                ["expected_sha256", "patch"],
            ),
        ),
    ]


def call_file_tool(workspace: AgentFileWorkspace, name: str, arguments: dict[str, object]) -> str:
    try:
        if name == "list_files" and (
            not arguments or (set(arguments) == {"prefix"} and isinstance(arguments["prefix"], str))
        ):
            result = workspace.list_files(cast(str, arguments.get("prefix", ".")))
        elif (
            name == "search_text"
            and set(arguments) in ({"query"}, {"query", "prefix"})
            and isinstance(arguments["query"], str)
            and isinstance(arguments.get("prefix", "."), str)
        ):
            result = workspace.search_text(
                arguments["query"], cast(str, arguments.get("prefix", "."))
            )
        elif (
            name == "read_file"
            and set(arguments) == {"path"}
            and isinstance(arguments["path"], str)
        ):
            result = workspace.read_file(arguments["path"])
        elif (
            name == "apply_patch"
            and set(arguments) == {"expected_sha256", "patch"}
            and isinstance(arguments["patch"], str)
            and (
                arguments["expected_sha256"] is None
                or isinstance(arguments["expected_sha256"], str)
            )
        ):
            result = workspace.apply_patch(arguments["patch"], arguments["expected_sha256"])
        else:
            raise AgentFileError("Invalid file tool call.")
        return json.dumps(result, ensure_ascii=False)
    except AgentFileError as exc:
        return json.dumps({"error": str(exc)})
