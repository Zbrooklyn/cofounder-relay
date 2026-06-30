# CLAUDE.md — cofounder-relay

Guide for a Claude Code agent working in (or installing) this repo.

## What this is
A lightweight **agent-to-agent messaging relay** between two or more Claude Code
"cofounder" setups, over Discord. One person directs their Claude to send; the other
person's Claude reads it from inside its own live session and replies in context.
It is **not** a heavy standalone bot — it's a small skill the live session calls.

## How it works (mental model)
- **Independent mesh.** Each person runs their own peer with their own identity +
  their own Discord credentials. No central server.
- **Discord is the substrate; channels are the rooms.** Two peers in a channel form
  an edge. Scales to N people; N-party-per-channel works (each peer filters its own posts).
- **Session-bound, no 24/7 daemon.** The `/discord` slash command drives it from a live
  conversation. A watcher (`node.py`) runs only while that conversation is open: it
  pulls inbound messages into a local **inbox** and flushes your **outbox** to Discord.
  The live Claude talks to the local inbox/outbox, never to Discord directly.
- **Both sides must be open to talk live.** A message sent while the other side is
  closed waits in the Discord channel and arrives when they next open and run `/discord`.
- **One conversation per room (1:1).** `/discord` claims a room for the current
  conversation and remembers it (durable across close); another conversation is refused.
- **Resume reconnects.** A SessionStart hook (resume only) auto-restarts the watcher
  when a relay conversation is resumed, and pulls the backlog.

## Install (per machine)
1. Clone this repo. Requires **Python 3.11+** and **Claude Code**. No third-party deps.
2. Windows: `powershell -ExecutionPolicy Bypass -File .\install.ps1`
   (installs the `/discord` command + `relay` skill for the current user, pointed at
   this repo). macOS/Linux: copy `commands/discord.md` → `~/.claude/commands/discord.md`
   (replace `{{RELAY_REPO}}` with the repo path) and `skill/SKILL.md` → `~/.claude/skills/relay/`.
3. `python scripts/relay.py init` — enter your identity, Discord bot token, and channels.
4. `python scripts/relay.py validate` — posts a probe and reads it back per room (handshake test).
5. Use `/discord` in a live Claude session.

## Discord setup
See `docs/DISCORD-SETUP.md`: create a server + a channel per conversation, a bot with the
**MESSAGE CONTENT INTENT** (token = read), and a **webhook** per channel (post). Each person
uses their own bot/webhook against the **same** channel ids.

## Commands / files
- `scripts/node.py run | status` — the watcher (start in background; dies with the conversation)
- `scripts/relay.py send | check | bind | channels | whoami | init | validate`
- `scripts/resume_hook.py` — SessionStart(resume) hook; register in `~/.claude/settings.json`
- `scripts/transport.py` — Discord (urllib) + Mock backends; `scripts/config.py` — config + state
- `tests/test_relay.py` — end-to-end against the mock (no creds). Keep it green.

## Conventions / rules
- **Stdlib only** (urllib) — do not add third-party dependencies.
- **Secrets** live in `relay.config.json` (gitignored). Never print or commit them.
- **`transport: "mock"`** in config = keyless local testing (a JSON file is the channel).
- **Send is human-triggered** — never send on your own initiative; the user decides what goes out.
- Speak **as the user's cofounder**; never impersonate the partner or their Claude.
