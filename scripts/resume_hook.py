#!/usr/bin/env python3
"""SessionStart(resume) hook for cofounder-relay.

Fires ONLY when a conversation is *resumed* (not on brand-new conversations).
If the resumed conversation owns a relay room, it reattaches: starts the local
node/watcher (if one isn't already running) and tells Claude to catch up on
messages that arrived while the conversation was closed.

No-op (silent) for: non-resume sources, conversations that own no room, or when
the node is already alive. Reads the hook JSON from stdin.

Wire into ~/.claude/settings.json under hooks.SessionStart with matcher "resume".
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import config as cfg_mod  # noqa: E402


def _start_node_detached():
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    log = open(REPO / "node.out", "a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, str(SCRIPTS / "node.py"), "run"],
        stdout=log, stderr=log, stdin=subprocess.DEVNULL,
        creationflags=flags, close_fds=True, cwd=str(REPO),
    )


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # malformed / no input — stay silent
    if data.get("source") != "resume":
        return  # resume-only, per Edward
    sid = data.get("session_id")
    if not sid:
        return
    room = cfg_mod.owned_room(sid)
    if not room:
        return  # not a relay conversation — nothing to do
    if not cfg_mod.node_alive():
        try:
            _start_node_detached()
        except Exception as e:
            print(f"[relay] could not start the watcher automatically: {e}", flush=True)
    print(
        f"[relay] This conversation owns room '{room}'. The watcher is "
        f"reattached — run `/discord check` to surface any messages received "
        f"while it was closed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
