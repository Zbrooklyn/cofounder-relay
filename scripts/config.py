"""Config, channel-binding, and state resolution for cofounder-relay.

Stdlib only. Secrets live in relay.config.json (gitignored). State lives in
.relay-state.json (gitignored). Channel binding ties a Claude session to the
Discord channel for "this conversation".
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Repo root = parent of scripts/
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("RELAY_CONFIG") or (ROOT / "relay.config.json"))
STATE_PATH = ROOT / ".relay-state.json"

# Local-node interface: the live Claude talks to these files, the node talks to Discord.
INBOX_DIR = ROOT / "inbox"      # node writes inbound here; `check` reads it
OUTBOX_DIR = ROOT / "outbox"    # `send` writes here; node flushes to Discord
HEARTBEAT_PATH = ROOT / ".node_alive"
NODE_STALE_SECONDS = 90         # node considered down if heartbeat older than this


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    # utf-8-sig: tolerate a BOM (known Windows gotcha)
    return json.loads(path.read_text(encoding="utf-8-sig") or "{}")


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic on the same volume


def load_config() -> dict:
    cfg = _read_json(CONFIG_PATH, {})
    if not cfg:
        raise SystemExit(
            f"No config found at {CONFIG_PATH}.\n"
            "Copy relay.config.example.json -> relay.config.json and fill it in,\n"
            'or set "transport": "mock" for keyless local testing.'
        )
    cfg.setdefault("identity", os.environ.get("RELAY_IDENTITY", "me"))
    cfg.setdefault("transport", "discord")
    cfg.setdefault("channels", {})
    return cfg


def resolve_channel(cli_channel: str | None) -> str:
    """Which channel is THIS conversation bound to.

    Order: --channel flag > session binding > RELAY_CHANNEL env > ./.relay-channel
    file > error. Never guesses.
    """
    if cli_channel:
        return cli_channel
    bound = session_channel()
    if bound:
        return bound
    env = os.environ.get("RELAY_CHANNEL")
    if env:
        return env
    marker = Path.cwd() / ".relay-channel"
    if marker.exists():
        name = marker.read_text(encoding="utf-8-sig").strip()
        if name:
            return name
    raise SystemExit(
        "No channel bound. Pass --channel <key>, set RELAY_CHANNEL, or put the "
        "channel key in a .relay-channel file in this project directory."
    )


# ---- per-channel last-seen state -------------------------------------------

def get_last_seen(channel: str) -> str | None:
    state = _read_json(STATE_PATH, {})
    return state.get(channel, {}).get("last_seen_id")


def set_last_seen(channel: str, message_id: str) -> None:
    state = _read_json(STATE_PATH, {})
    state.setdefault(channel, {})["last_seen_id"] = str(message_id)
    _write_json(STATE_PATH, state)


# ---- inbox read cursor (how far `check` has shown the local inbox) ----------

def get_inbox_read(channel: str) -> int:
    state = _read_json(STATE_PATH, {})
    return int(state.get(channel, {}).get("inbox_read", 0))


def set_inbox_read(channel: str, n: int) -> None:
    state = _read_json(STATE_PATH, {})
    state.setdefault(channel, {})["inbox_read"] = int(n)
    _write_json(STATE_PATH, state)


# ---- node liveness ----------------------------------------------------------

def node_alive() -> bool:
    if not HEARTBEAT_PATH.exists():
        return False
    age = time.time() - HEARTBEAT_PATH.stat().st_mtime
    return age < NODE_STALE_SECONDS


def touch_heartbeat() -> None:
    HEARTBEAT_PATH.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")


# ---- session-scoped channel binding ----------------------------------------
# Ties a Claude conversation (by session id) to its room, so multiple
# conversations launched from the same directory each answer from their own
# channel without a manual --channel.

def _session_bindings() -> dict:
    return _read_json(ROOT / ".relay-sessions.json", {})


def bind_session(session_id: str, channel: str) -> None:
    b = _session_bindings()
    b[session_id] = channel
    _write_json(ROOT / ".relay-sessions.json", b)


def session_channel() -> str | None:
    sid = os.environ.get("RELAY_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")
    if not sid:
        return None
    return _session_bindings().get(sid)
