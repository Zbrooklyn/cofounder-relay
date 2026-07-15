#!/usr/bin/env python3
"""Silent event-emitter watcher for cofounder-relay.

Runs as a Monitor's command: polls every configured channel for NEW inbound
messages from the partner and prints ONE line per new message to stdout (which
the Monitor turns into a single chat notification). Between messages it prints
nothing — dead silent. It never replays history: on first sight of a channel it
anchors to the latest message id and only emits what arrives after.

State (last-seen id per channel) is persisted to .watch-emit-state.json so a
restart resumes where it left off instead of skipping or replaying.

Stdout = event stream (per new message). Stderr = diagnostics only.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg_mod           # noqa: E402
import transport as transport_mod  # noqa: E402

POLL_SECONDS = 12


def _state_path(channels: list) -> Path:
    # One state file per channel set, so multiple watchers on the same machine
    # (one per conversation/room) never clobber each other's cursor.
    slug = "-".join(sorted(channels)) or "all"
    return cfg_mod.ROOT / f".watch-emit-{slug}.json"


def _load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8-sig") or "{}")
        except Exception:
            return {}
    return {}


def _save_state(path: Path, state: dict) -> None:
    try:
        path.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass  # best-effort; losing a save just means a possible re-emit


def main() -> None:
    cfg = cfg_mod.load_config()
    identity = cfg["identity"]
    all_ch = list(cfg.get("channels", {}).keys())
    # Optional channel filter: `watch_emit.py <chanA> <chanB>` watches only those
    # (so one conversation owns its room and ignores others). No args = watch all.
    requested = [a for a in sys.argv[1:] if not a.startswith("-")]
    if requested:
        channels = [c for c in requested if c in all_ch]
        missing = [c for c in requested if c not in all_ch]
        if missing:
            print(f"[watch] ignoring unknown channels: {missing}", file=sys.stderr, flush=True)
    else:
        channels = all_ch
    state_path = _state_path(channels)
    state = _load_state(state_path)
    print(f"[watch] up: watching {channels} as {identity} (state {state_path.name})", file=sys.stderr, flush=True)

    while True:
        for ch in channels:
            try:
                tp = transport_mod.make_transport(cfg)  # fresh each pass (cheap, robust)
                last = state.get(ch)
                if last is None:
                    # Anchor to newest existing message; do not replay history.
                    msgs = tp.fetch_since(ch, None, limit=1)
                    state[ch] = msgs[-1]["id"] if msgs else "0"
                    _save_state(state_path, state)
                    continue
                msgs = tp.fetch_since(ch, last, limit=50)
                if not msgs:
                    continue
                for m in msgs:
                    if not transport_mod.own_message(m, identity):
                        text = (m.get("text") or "").replace("\n", " ").strip()
                        line = f"{ch} | {m.get('author', '?')}: {text}"
                        # Surface file attachments so they never sit unread again —
                        # Discord holds the file; this exposes its download URL.
                        for a in m.get("attachments", []):
                            line += f"  [FILE: {a.get('filename')} -> {a.get('url')}]"
                        print(line, flush=True)
                state[ch] = msgs[-1]["id"]
                _save_state(state_path, state)
            except Exception as e:  # transient API/network — skip this pass, keep going
                print(f"[watch] {ch} poll error: {e}", file=sys.stderr, flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
