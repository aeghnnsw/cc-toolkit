# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Codex SessionStart hook wrapper for task-loop agent sync."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def summarize_agents(agents: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for agent in agents:
        name = str(agent.get("name", "unknown"))
        status = str(agent.get("status", "unknown"))
        reason = agent.get("reason")
        if reason:
            parts.append(f"{name} {status} ({reason})")
        else:
            parts.append(f"{name} {status}")
    return ", ".join(parts)


def parse_json(text: str) -> dict[str, object]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    root = plugin_root()
    sync_script = root / "scripts" / "sync_codex_agents.py"

    try:
        result = subprocess.run(
            ["uv", "run", "--no-project", str(sync_script)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(root),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0

    data = parse_json(result.stdout)
    agents = data.get("agents", [])
    if not isinstance(agents, list):
        agents = []

    if result.returncode != 0:
        details = summarize_agents(agents) or data.get("error") or result.stderr.strip()[:200]
        print(json.dumps({"systemMessage": f"task-loop agent sync failed: {details}"}))
        return 0

    if not agents:
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": f"task-loop agents synced: {summarize_agents(agents)}",
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
