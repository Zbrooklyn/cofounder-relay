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

STATE = cfg_mod.ROOT / ".watch-emit-state.json"
POLL_SECONDS = 12


def _load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8-sig") or "{}")
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass  # best-effort; losing a save just means a possible re-emit


def main() -> None:
    cfg = cfg_mod.load_config()
    identity = cfg["identity"]
    channels = list(cfg.get("channels", {}).keys())
    state = _load_state()
    print(f"[watch] up: watching {channels} as {identity}", file=sys.stderr, flush=True)

    while True:
        for ch in channels:
            try:
                tp = transport_mod.make_transport(cfg)  # fresh each pass (cheap, robust)
                last = state.get(ch)
                if last is None:
                    # Anchor to newest existing message; do not replay history.
                    msgs = tp.fetch_since(ch, None, limit=1)
                    state[ch] = msgs[-1]["id"] if msgs else "0"
                    _save_state(state)
                    continue
                msgs = tp.fetch_since(ch, last, limit=50)
                if not msgs:
                    continue
                for m in msgs:
                    if not transport_mod.own_message(m, identity):
                        text = (m.get("text") or "").replace("\n", " ").strip()
                        print(f"{ch} | {m.get('author', '?')}: {text}", flush=True)
                state[ch] = msgs[-1]["id"]
                _save_state(state)
            except Exception as e:  # transient API/network — skip this pass, keep going
                print(f"[watch] {ch} poll error: {e}", file=sys.stderr, flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
