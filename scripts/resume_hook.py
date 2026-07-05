#!/usr/bin/env python3
"""SessionStart(resume) hook for cofounder-relay.

Fires ONLY when a conversation is *resumed* (not on brand-new conversations).
If the resumed conversation owns a relay room (i.e. this conversation used the
relay before), it injects a directive telling Claude to auto-reattach: re-arm the
silent event watcher for that room and resume auto-respond — with no action from
the human. The watcher resumes from its saved position, so any messages that
arrived while the conversation was closed surface on reattach; nothing is lost.

No-op (silent) for: non-resume sources (brand-new conversations don't turn this
on), and conversations that own no room. Reads the hook JSON from stdin.

Wire into ~/.claude/settings.json under hooks.SessionStart with matcher "resume".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import config as cfg_mod  # noqa: E402


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # malformed / no input — stay silent
    if data.get("source") != "resume":
        return  # resume-only: brand-new conversations do NOT auto-start the relay
    sid = data.get("session_id")
    if not sid:
        return
    rooms = cfg_mod.owned_rooms(sid)
    if not rooms:
        return  # not a relay conversation — nothing to do, stay silent

    watch = SCRIPTS / "watch_emit.py"
    room_args = " ".join(rooms)
    label = "room '" + rooms[0] + "'" if len(rooms) == 1 else "rooms " + ", ".join(rooms)
    print(
        f"[cofounder-relay] This resumed conversation is bound to relay {label}. "
        f"AUTO-REATTACH NOW, without waiting for the user: arm a persistent background "
        f"Monitor running  python \"{watch}\" {room_args}  — it resumes from its saved "
        f"position, so any messages received while this conversation was closed will "
        f"surface. Then operate in AUTO-RESPOND mode for these rooms per the relay skill "
        f"(answer the partner's messages on your own within the skill's guardrails, "
        f"surfacing each in/out to the user). Surface anything that comes through.",
        flush=True,
    )


if __name__ == "__main__":
    main()
