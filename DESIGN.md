# cofounder-relay — Design

> A lightweight **agent-to-agent relay** between two cofounder setups (Edward's Claude ↔ partner's Claude) over Discord. Built 2026-06-30.

## Intent (locked with Edward)

Edward and a business partner each run their own Claude Code cofounder. Today, sharing context means copy-pasting. `relay` lets each person **direct their own Claude to send a message/request to the other side**, where the other person's Claude **picks it up from inside its live working session** — so replies come "from that conversation's mindset," carrying real context.

This is **not** the heavy `telegram-bridge` (a separate always-on bot with its own brain). It is a thin **skill/CLI the live session calls**. The Claude that sends and the Claude that replies is the one you are already working with.

### What's locked
- **Direction:** agent-to-agent, for the most part. Humans stay in the loop.
- **Send:** human-triggered. "Tell my Claude to send this," like telling an employee to send an email. No autonomous outbound.
- **Transport:** **Discord.** Per-conversation **channel** (one channel per project/topic) is Discord's native primitive and avoids Telegram's bot-privacy-mode and forum-topic friction. Telegram/Beeper stays Edward's separate personal phone channel.
- **Form:** a small `relay` skill installed symmetrically on both machines. ~Two verbs + a watcher. No daemon required for v1.
- **Membership:** one Discord server; each channel contains both humans + a relay identity. Agents post through a webhook labeled by identity ("🤖 Edward's Claude: …"). Both humans see all traffic and can type in directly. Human visibility *is* the safety layer.

## Two modes

### Mode 1 — Invoked (manual)
The live Claude calls the CLI on request.
- `relay send "<text>"` → posts to *this conversation's* channel as the caller's labeled identity.
- `relay check` → pulls messages received since last check into the session, so Claude replies in-context.

This is the default, lowest-risk mode: nothing runs in the background; Edward says "reply to David that…" and Claude sends; Edward says "any messages?" and Claude checks.

### Mode 2 — Live watcher (in-conversation)
While a session is actively working, `relay watch` runs a poll loop (background task) that:
- polls the bound channel every N seconds,
- appends any new inbound message to `inbox/<channel>.jsonl`,
- raises a signal (notify hook / flag file) so the live session surfaces it on its next turn.

**Honest limitation:** a Claude Code session only acts on *turns*; it cannot be interrupted mid-idle to "auto-speak." So "live within the conversation" means: the watcher captures messages the instant they arrive and makes them available, and the session surfaces them at the next turn / loop tick (pairs naturally with `/loop`). True instant push to an idle session, and a fully always-on cross-machine daemon, are **roadmap** (see below) — Edward deferred always-on for v1, then asked for the in-conversation watcher as the second mode; this delivers the in-conversation half without standing up a separate service.

## Architecture

```
cofounder-relay/
├── DESIGN.md
├── README.md
├── scripts/
│   ├── relay.py            # CLI: send / check / watch (entry point)
│   ├── transport.py        # DiscordTransport (live) + MockTransport (keyless testing)
│   └── config.py           # config + channel-binding + state resolution
├── skill/
│   └── SKILL.md            # how the live Claude invokes both modes
├── tests/
│   └── test_relay.py       # end-to-end against MockTransport (no creds)
├── docs/
│   └── DISCORD-SETUP.md     # the one Edward-side action: server/bot/webhook creation
├── relay.config.example.json
└── .gitignore               # ignores real config, state, inbox, .venv
```

### Transport interface (so live vs mock are swappable)
```
send(channel_key, text, identity)        -> message_id
fetch_since(channel_key, last_id, limit) -> [ {id, author, identity, text, ts}, ... ]
```
- **DiscordTransport:** `send` via the channel's **webhook URL** (sets username/avatar = identity, no bot needed to post). `fetch_since` via REST `GET /channels/{id}/messages?after={last_id}` using a **bot token** (webhooks can't read). One bot in the server is enough for both sides to read.
- **MockTransport:** a local JSON file (`.mock/<channel>.json`) acting as a shared channel, so the whole skill is testable with zero Discord credentials. Lets us prove send→check→watch before any key handover.

### Config model — `relay.config.json` (gitignored, per machine)
```json
{
  "identity": "Edward",
  "transport": "discord",
  "discord_bot_token": "<bot token, read>",
  "channels": {
    "steady-imports": { "channel_id": "...", "webhook_url": "https://discord.com/api/webhooks/..." },
    "eeg":            { "channel_id": "...", "webhook_url": "..." }
  }
}
```
- Secrets live only here (gitignored). `transport: "mock"` switches to the keyless backend.

### Channel binding — "this conversation"
Resolution order for which channel a session is bound to:
1. `--channel <key>` flag (explicit),
2. `RELAY_CHANNEL` env var,
3. a `.relay-channel` file in the current working directory (per-project default),
4. error if none — never guesses.

This is what ties a Claude session to the right channel so it answers each thread from the right headspace.

### State — `.relay-state.json` (gitignored)
Per-channel `last_seen_id`, so `check`/`watch` only return genuinely new messages and survive restarts.

## Security
- Bot token + webhook URLs are credentials → only in gitignored `relay.config.json`; never committed. `.gitignore` blocks config, state, inbox, `.mock`, `.venv`.
- Send is human-triggered; receive is human-visible (both principals sit in every channel). No autonomous cross-machine action in v1.
- Identity labels are cosmetic/honesty aids, not auth — the auth boundary is "who is in the Discord server."

## Roadmap (explicitly deferred)
- **Always-on cross-machine pickup** — a managed watcher that survives session close (the v1 watcher lives with the session).
- **Instant push to an idle session** — needs harness-level re-invocation (ScheduleWakeup / a host hook).
- **Receive-side autonomy** — let the receiving Claude *act* on a request, not just surface it (gated; v1 surfaces for the human).
- **Structured task envelopes** — typed handoffs (task/file/decision) vs plain text.
- **More than two participants / per-channel roles.**

## Non-goals (v1)
No daemon/supervisor, no multi-user tiers, no voice/photo, no Trello coupling. Small and reversible.
