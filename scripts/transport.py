"""Transport backends for cofounder-relay.

Common interface (so live Discord and the keyless Mock are swappable):
    send(channel_key, text, identity)        -> message_id (str)
    fetch_since(channel_key, last_id, limit) -> list[dict]  (oldest-first)

Each message dict: {id, author, identity, text, ts}

DiscordTransport uses stdlib urllib only (no third-party deps):
  - send  : POST to the channel's webhook URL (username = identity)
  - read  : GET /channels/{id}/messages?after={last_id} with a bot token
MockTransport: a local JSON file acts as a shared channel, for testing with
no Discord credentials.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

DISCORD_API = "https://discord.com/api/v10"
IDENTITY_PREFIX = "\U0001F916"  # 🤖, prefixed to author name on outbound posts


class TransportError(RuntimeError):
    pass


def own_message(msg: dict, identity: str) -> bool:
    """True if a message was sent by our own side (so we never ingest our own posts)."""
    if msg.get("identity") == identity:
        return True
    author = msg.get("author", "")
    return bool(identity) and identity.lower() in author.lower() and bool(msg.get("is_bot"))


def make_transport(cfg: dict):
    kind = cfg.get("transport", "discord")
    if kind == "mock":
        return MockTransport(cfg)
    if kind == "discord":
        return DiscordTransport(cfg)
    raise TransportError(f"unknown transport: {kind!r}")


# --------------------------------------------------------------------------- #
# Discord (live)
# --------------------------------------------------------------------------- #
class DiscordTransport:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.bot_token = cfg.get("discord_bot_token", "")
        self.channels = cfg.get("channels", {})

    def _chan(self, key: str) -> dict:
        c = self.channels.get(key)
        if not c:
            raise TransportError(f"channel {key!r} not in config.channels")
        return c

    def send(self, channel_key: str, text: str, identity: str) -> str:
        hook = self._chan(channel_key).get("webhook_url")
        if not hook:
            raise TransportError(f"channel {channel_key!r} has no webhook_url")
        payload = {
            "username": f"{IDENTITY_PREFIX} {identity}'s Claude",
            "content": text,
        }
        # ?wait=true makes Discord return the created message (so we get its id)
        body = self._http("POST", hook + "?wait=true", payload)
        return str(body.get("id", ""))

    def fetch_since(self, channel_key: str, last_id: str | None, limit: int = 50) -> list[dict]:
        if not self.bot_token:
            raise TransportError("discord_bot_token required to read messages")
        cid = self._chan(channel_key).get("channel_id")
        if not cid:
            raise TransportError(f"channel {channel_key!r} has no channel_id")
        url = f"{DISCORD_API}/channels/{cid}/messages?limit={limit}"
        if last_id:
            url += f"&after={last_id}"
        raw = self._http(
            "GET", url, None, headers={"Authorization": f"Bot {self.bot_token}"}
        )
        # Discord returns newest-first; we want oldest-first for sequential processing
        msgs = []
        for m in reversed(raw):
            author = m.get("author", {})
            msgs.append(
                {
                    "id": str(m.get("id")),
                    "author": author.get("username", "?"),
                    "identity": author.get("username", "?"),
                    "text": m.get("content", ""),
                    "ts": m.get("timestamp", ""),
                    "is_bot": bool(author.get("bot")),
                }
            )
        return msgs

    def _http(self, method: str, url: str, payload: dict | None, headers: dict | None = None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "cofounder-relay/1.0")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise TransportError(f"Discord {method} {url.split('?')[0]} -> {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise TransportError(f"network error calling Discord: {e}")


# --------------------------------------------------------------------------- #
# Mock (keyless local testing) — a JSON file is the "channel"
# --------------------------------------------------------------------------- #
class MockTransport:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.dir = Path(cfg.get("mock_dir") or (Path(__file__).resolve().parent.parent / ".mock"))
        self.dir.mkdir(exist_ok=True)

    def _file(self, channel_key: str) -> Path:
        return self.dir / f"{channel_key}.json"

    def _load(self, channel_key: str) -> list[dict]:
        f = self._file(channel_key)
        if not f.exists():
            return []
        return json.loads(f.read_text(encoding="utf-8") or "[]")

    def send(self, channel_key: str, text: str, identity: str) -> str:
        msgs = self._load(channel_key)
        # Monotonic integer ids, as strings (mirrors Discord snowflake ordering)
        next_id = str((int(msgs[-1]["id"]) + 1) if msgs else 1000)
        msg = {
            "id": next_id,
            "author": f"{identity}'s Claude",
            "identity": identity,
            "text": text,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "is_bot": True,
        }
        msgs.append(msg)
        self._file(channel_key).write_text(json.dumps(msgs, indent=2), encoding="utf-8")
        return next_id

    def fetch_since(self, channel_key: str, last_id: str | None, limit: int = 50) -> list[dict]:
        msgs = self._load(channel_key)
        if last_id is None:
            return msgs[-limit:]
        return [m for m in msgs if int(m["id"]) > int(last_id)][:limit]
