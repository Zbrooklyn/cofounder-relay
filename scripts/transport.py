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
        self.guild_id = str(cfg.get("guild_id", ""))
        self.channels = cfg.get("channels", {})

    def _bot_headers(self) -> dict:
        if not self.bot_token:
            raise TransportError("discord_bot_token required for this operation")
        return {"Authorization": f"Bot {self.bot_token}"}

    def create_channel(self, name: str, topic: str = "") -> dict:
        """Create a text channel in the configured guild. Needs the bot to have
        the Manage Channels permission. Returns the created channel object."""
        if not self.guild_id:
            raise TransportError("guild_id missing from config — cannot create a channel")
        payload: dict = {"name": name, "type": 0}  # 0 = GUILD_TEXT
        if topic:
            payload["topic"] = topic
        return self._http(
            "POST", f"{DISCORD_API}/guilds/{self.guild_id}/channels", payload,
            headers=self._bot_headers(),
        )

    def create_webhook(self, channel_id: str, name: str = "relay") -> str:
        """Create a webhook on a channel and return its full URL. Needs the bot
        to have the Manage Webhooks permission."""
        body = self._http(
            "POST", f"{DISCORD_API}/channels/{channel_id}/webhooks", {"name": name},
            headers=self._bot_headers(),
        )
        wid, wtoken = body.get("id"), body.get("token")
        if not wid or not wtoken:
            raise TransportError(f"webhook create returned no token: {body}")
        return f"https://discord.com/api/webhooks/{wid}/{wtoken}"

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

    def _http(self, method: str, url: str, payload: dict | None, headers: dict | None = None, tries: int = 3):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        endpoint = url.split("?")[0]
        for attempt in range(tries):
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
                body = e.read().decode("utf-8", "replace")
                # 429 rate limit: honor retry_after and retry
                if e.code == 429 and attempt < tries - 1:
                    try:
                        retry_after = float(json.loads(body).get("retry_after", 1))
                    except Exception:
                        retry_after = 1.0
                    time.sleep(min(retry_after + 0.1, 5))
                    continue
                raise TransportError(f"Discord {method} {endpoint} -> {e.code}: {body}")
            except urllib.error.URLError as e:
                if attempt < tries - 1:  # transient network blip — one retry
                    time.sleep(1)
                    continue
                raise TransportError(f"network error calling Discord {endpoint}: {e}")


# --------------------------------------------------------------------------- #
# Mock (keyless local testing) — a JSON file is the "channel"
# --------------------------------------------------------------------------- #
class MockTransport:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.dir = Path(cfg.get("mock_dir") or (Path(__file__).resolve().parent.parent / ".mock"))
        self.dir.mkdir(exist_ok=True)

    def create_channel(self, name: str, topic: str = "") -> dict:
        # Keyless stand-in: mint a monotonic-ish id from the clock.
        return {"id": str(int(time.time() * 1000)), "name": name, "topic": topic}

    def create_webhook(self, channel_id: str, name: str = "relay") -> str:
        return f"mock://webhook/{channel_id}/{name}"

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
