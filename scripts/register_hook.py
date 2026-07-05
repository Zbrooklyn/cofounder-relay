#!/usr/bin/env python3
"""Register the cofounder-relay SessionStart(resume) hook in ~/.claude/settings.json.

Done in Python (not PowerShell) on purpose: Python's json preserves unicode
(ensure_ascii=False) and every existing key/value, so it won't escape em-dashes or
otherwise mangle a user's existing settings the way a PowerShell JSON round-trip
does. Idempotent: if the resume hook is already registered, it changes nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK_CMD = f'python "{SCRIPTS / "resume_hook.py"}"'


def main() -> None:
    settings = {}
    if SETTINGS.exists():
        try:
            settings = json.loads(SETTINGS.read_text(encoding="utf-8-sig") or "{}")
        except Exception as e:
            print(f"could not parse {SETTINGS}: {e}\nleaving it untouched — register the resume hook manually.")
            return

    hooks = settings.setdefault("hooks", {})
    session_start = hooks.setdefault("SessionStart", [])

    # Idempotent: bail if any SessionStart hook already runs resume_hook.py
    for entry in session_start:
        for h in entry.get("hooks", []):
            if "resume_hook.py" in (h.get("command") or ""):
                print("resume hook already registered")
                return

    session_start.append({
        "matcher": "resume",
        "hooks": [{"type": "command", "command": HOOK_CMD}],
    })
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    print("registered resume hook -> the relay auto-reattaches when you /resume a bound conversation")


if __name__ == "__main__":
    main()
