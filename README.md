# cofounder-relay

> A lightweight **agent-to-agent relay** between two cofounder setups — your Claude ↔ your partner's Claude — over Discord. One channel per conversation. You direct your Claude to send; the other Claude picks it up from inside its own live session.

This is **not** the heavy `telegram-bridge` (a standalone always-on bot). It's a
thin skill the live session calls. No daemon required.

## Status (2026-06-30)
Built and **tested end-to-end against a keyless mock** — send, check (with read
cursor), self-message filtering, and the live watcher all verified. **Going live
needs Discord credentials** (see `docs/DISCORD-SETUP.md`) — the only outstanding
step.

## Quick start (keyless, right now)
```bash
cp relay.config.example.json relay.config.json
# edit relay.config.json: set "transport": "mock"
export RELAY_CHANNEL=deal-x          # or: python scripts/relay.py bind deal-x
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
scripts/relay.py        CLI: send / check / watch / bind / channels
scripts/transport.py    DiscordTransport (live) + MockTransport (keyless)
scripts/config.py       config + channel-binding + read-cursor state
skill/SKILL.md          how the live Claude invokes it
tests/test_relay.py     end-to-end against the mock (no creds)
docs/DISCORD-SETUP.md   the one Edward-side action
```
