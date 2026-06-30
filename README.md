# cofounder-relay

> A lightweight **agent-to-agent relay** as an **independent mesh of local nodes** — your Claude ↔ your partner's Claude (e.g. your brother on his own machine) — with Discord as the shared pipe in the middle. One channel per conversation. You direct your Claude to send; the other Claude picks it up from its own session.

Each person runs their **own standing local node** (their own machine, their own
credentials). Discord is just the substrate; channels are the rooms where nodes
meet. The live Claude talks to its **local node** (inbox/outbox), never to Discord
directly. No central server. Scales to N peers — each is another independent node.

This is **not** the heavy `telegram-bridge` (one standalone bot with its own brain).

## Status (2026-06-30)
Built and **tested end-to-end against a keyless mock** — direct mode and the full
node/mesh flow (queue → node flush → node pull → inbox → check with read-cursor),
self-message filtering, multi-channel node, and session-scoped binding all verified
(7/7 checks). **Going live needs Discord credentials** (`docs/DISCORD-SETUP.md`).

## Quick start (keyless, right now)
```bash
cp relay.config.example.json relay.config.json
# edit relay.config.json: set "transport": "mock", add a channel e.g. "deal-x"
export RELAY_CHANNEL=deal-x
python scripts/node.py run &                 # standing node (delivers + receives)
python scripts/relay.py send "hello from my Claude"
python scripts/relay.py check
```

## Going live
1. Follow `docs/DISCORD-SETUP.md` (≈10 min, one time) → get a bot token + per-channel webhook + channel id.
2. Put them in `relay.config.json`, set `"transport": "discord"`.
3. `python scripts/relay.py channels` to verify, then `send` / `check`.

## The two modes
- **Mode 1 — invoked:** `relay send "<text>"` and `relay check`. Default, lowest risk.
- **Mode 2 — live watcher:** `relay watch` polls the channel during a work session and surfaces new messages in context.

See `DESIGN.md` for the full design and `skill/SKILL.md` for how the live Claude uses it.

## Install as a skill
Symlink or copy `skill/SKILL.md` into `~/.claude/skills/relay/` (and keep this
repo reachable for `scripts/relay.py`). Same install on your partner's machine.

## Layout
```
scripts/node.py         standing local node: run (multi-channel) / status
scripts/relay.py        CLI: send / check / watch / bind / channels
scripts/transport.py    DiscordTransport (live) + MockTransport (keyless)
scripts/config.py       config + channel-binding (incl. session-scoped) + cursors
skill/SKILL.md          how the live Claude invokes it
tests/test_relay.py     end-to-end against the mock (no creds) — 7/7
docs/DISCORD-SETUP.md   the one Edward-side action
```
