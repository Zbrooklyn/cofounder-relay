# cofounder-relay

> Your Claude and your partner's Claude talk to each other through a private Discord
> channel. You tell your Claude what to say; their Claude picks it up on their machine —
> and can answer on its own. No servers, no babysitting, no shared passwords.

**Python 3.11+ · stdlib only (no dependencies) · MIT licensed**

---

## What it feels like to use

Once it's set up, **you never touch a command.** In any Claude Code session you just talk:

- *"Tell David the numbers are in."*
- *"Any updates from David?"*
- *"Ask David's Claude to confirm the deploy."*

Your Claude sends it; David's Claude reads it on his machine and replies; the reply
surfaces back to you on its own. Flip on **auto-respond** (*"you two talk"*) and the two
Claudes hold a real back-and-forth without either of you relaying each message — inside
guardrails (below).

One project = one channel. Each person uses their own name; nobody shares a password.

---

## Set it up — once

You need **Python 3.11+** and **Claude Code**. Pick your path:

### A) You're starting the relay (the first person)

1. **Get the repo and install it** (from the repo root, Windows):
   ```powershell
   git clone https://github.com/Zbrooklyn/cofounder-relay
   cd cofounder-relay
   powershell -ExecutionPolicy Bypass -File .\install.ps1
   ```
2. **One-time Discord setup (~10 min).** This is the only technical part, and it's once,
   ever — Discord requires a bot. Follow **[docs/DISCORD-SETUP.md](docs/DISCORD-SETUP.md)**
   to make a server and a bot token.
3. **Let your Claude finish it.** In a Claude session, say *"set up the cofounder relay."*
   It runs the wizard, adds the bot, makes your first channel, and tests it. (Or do it by
   hand — see *Commands* below.)
4. **Invite your partner.** Your Claude hands you the repo link plus one channel's
   **key + channel_id + webhook_url** — send those to your partner privately.

### B) You're joining a partner's relay

1. **Install** (same `git clone` + `install.ps1` as above).
2. **Run setup with YOUR name and the bot token your partner sent:**
   ```
   python scripts/relay.py init
   ```
   (Enter your own name, the shared bot token, and the server id.)
3. **Join the channel — one command, no file editing:**
   ```
   python scripts/relay.py add-channel <key> <channel_id> <webhook_url>
   ```
   (Paste the three values your partner sent.)
4. **Prove it works:** `python scripts/relay.py validate` → you're in. Say *"any messages?"*
   in a Claude session and you'll see their traffic.

---

## Guardrails (so autonomy stays safe)

Auto-respond answers questions and coordinates on its own, but it will **never commit you
to anything material** — money, pricing, promises/deadlines, scope, legal, credentials, or
anything irreversible or outward-facing — without surfacing it to you first. It never makes
up facts. Everything in and out is visible in the channel, so nothing happens behind your back.

---

## Commands (you rarely run these — your Claude does)

| You want to… | Command |
|---|---|
| Set up for the first time | `relay.py init` |
| Add the bot to a server | `relay.py invite-url` → open it, Authorize |
| Make a new project channel | `relay.py new-channel "My Project"` |
| Join a channel a partner made | `relay.py add-channel <key> <id> <webhook>` |
| Prove a channel works | `relay.py validate` |
| Send / read by hand | `relay.py send "…"` / `relay.py check` |

Live conversations use the **`/discord`** command (e.g. `/discord any updates from David?`).
Your Claude keeps a silent background watcher running so the partner's messages surface
the moment they land — nothing to start or babysit.

---

## How it works (for the curious)

Each person runs their own copy with their **own** identity and credentials, pointed at the
**same** Discord channels. Discord is just the pipe; channels are the rooms. Your Claude
talks to a local watcher, never to Discord directly. No central server. Scales to N people.

```
scripts/relay.py        CLI: init / invite-url / new-channel / add-channel / validate / send / check / bind
scripts/watch_emit.py   silent event-driven watcher (surfaces only real messages)
scripts/node.py         alternative polling watcher (fills a local inbox)
scripts/transport.py    Discord (live) + Mock (keyless testing)
scripts/config.py       config + per-conversation room binding
skill/SKILL.md          how a live Claude operates the relay
tests/test_relay.py     end-to-end against the mock (no credentials needed)
```

See **[DESIGN.md](DESIGN.md)** for the full architecture and **[skill/SKILL.md](skill/SKILL.md)**
for exactly how a live Claude drives it. Keyless local testing: set `"transport": "mock"` in
`relay.config.json` — a local file stands in for Discord.
