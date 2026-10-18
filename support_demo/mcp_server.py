"""Read-only MCP tools for the fixed support-demo JSON files."""

import argparse
import json
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

SERVER = MCPServer("support-demo")
DATA_DIR = Path(__file__).parent / "data"


def _records(filename: str) -> list[dict[str, Any]]:
    path = DATA_DIR / filename
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65_536:
        raise ValueError("Support data file is unavailable or too large.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("Support data must be a JSON array of objects.")
    lines = path.read_text(encoding="utf-8").splitlines()
    results = []
    for item in value:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Support record has no valid ID.")
        token = json.dumps(identifier, ensure_ascii=False)
        matches = [number for number, line in enumerate(lines, 1) if token in line]
        if len(matches) != 1:
            raise ValueError("Support record source is ambiguous.")
        results.append({**item, "source": f"{path.resolve()}:L{matches[0]}"})
    return results


@SERVER.tool()
def list_users() -> dict[str, object]:
    """List demo identities for the CLI's simulated sign-in."""
    users = _records("users.json")
    return {"users": [{"id": user["id"], "name": user["name"]} for user in users]}


@SERVER.tool()
def get_user(user_id: str) -> dict[str, object]:
    """Read the selected demo user's profile."""
    user = next((item for item in _records("users.json") if item["id"] == user_id), None)
    if user is None:
        raise ValueError("Selected user does not exist.")
    return {"user": user}


@SERVER.tool()
def list_visible_tickets(user_id: str) -> dict[str, object]:
    """Read only this user's tickets and shared incidents."""
    if not any(item["id"] == user_id for item in _records("users.json")):
        raise ValueError("Selected user does not exist.")
    tickets = [
        item
        for item in _records("tickets.json")
        if item.get("scope") == "global"
        or (item.get("scope") == "personal" and item.get("user_id") == user_id)
    ]
    return {"tickets": tickets}


def main() -> None:
    global DATA_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    DATA_DIR = args.data_dir.resolve(strict=True)
    SERVER.run(transport="stdio")


if __name__ == "__main__":
    main()
