---
name: relay
description: Send and receive agent-to-agent messages with a partner's Claude (e.g. Edward's brother) over Discord. Use when Edward says to message/tell/send something to his partner (or asks "any messages / what did he say / check the relay"). Each project/conversation maps to its own Discord channel; replies come from the current session's context. A standing local node does the Discord talking; this skill talks to the local inbox/outbox.
---

# relay — agent-to-agent messaging (independent mesh, session-bound)

Driven from inside a live Claude conversation via the **`/discord`** slash command.
Each person is an independent peer with their own Discord credentials + identity;
Discord is the shared pipe; channels are the rooms. The live Claude (you) talks to
its **local watcher** via inbox/outbox — never to Discord directly. Scales to N people.

**Operating principle: YOU run all the mechanics; the human just talks.** The user says
"tell David X" / "any updates?" / "you two talk" in plain language — you translate that
into the `relay.py` calls, start/keep the watcher alive, bind the room, and surface what
comes in. Never make the human run a command, edit `relay.config.json`, or think about
channels/webhooks/watchers. If something isn't set up yet, guide them through it
conversationally using the commands below (`init` → `invite-url` → `new-channel` /
`add-channel` → `validate`) — one clear step at a time, not a wall of instructions.

**No 24/7 daemon — the watcher lives only while this conversation is open.** Both
sides must have a conversation open to converse live; a message sent while the other
side is closed waits in Discord and arrives when they next open theirs.

Entry points (from the cofounder-relay repo):
- `python scripts/node.py run`   — the watcher (start in BACKGROUND for this conversation)
- `python scripts/relay.py …`    — what you call per turn

## First: start the watcher for THIS conversation's room
Prefer the silent, event-driven watcher and arm it as a background Monitor scoped to
YOUR channel. It stays completely silent until a real message lands, then surfaces
exactly that one message — no timed-poll noise in the chat:
```
# arm as a persistent background Monitor, scoped to this conversation's room:
python scripts/watch_emit.py <your-channel-key>
```
Each new partner message becomes one event you surface (and, in auto-respond mode,
answer on your own). One watcher per conversation, each scoped to its own room, so
sessions on the same machine never cross streams.

Fallback if your harness has no Monitor primitive: run `python scripts/node.py run` in
the background (a silent poller that fills a local inbox you read with `relay.py check`).
If no watcher is running, sends still queue but inbound won't surface until one is.

## Bind this conversation to its room (once per conversation)
So this session answers from the right channel without passing --channel every time:
```
python scripts/relay.py bind <channel-key> --session <this-session-id>
```
Use the current Claude session id (set `RELAY_SESSION_ID` to it). After binding,
`send`/`check` resolve the channel automatically. (Resolution order: --channel >
session binding > RELAY_CHANNEL > ./.relay-channel file > error — it never guesses.)

## Mode 1 — Invoked (default)

**Send** — when Edward says "tell David…", "send him…", "reply to him…":
```
python scripts/relay.py send "the message text"
```
Compose in Edward's voice/intent → it queues to the node's outbox → the node posts
it to the room. (`--now` sends directly if the node is down.)

**Check** — when Edward asks "any messages?", "what did he say?", "check the relay":
```
python scripts/relay.py check
```
Reads new messages the node has pulled into the local inbox (excludes our own
posts). Respond from THIS conversation's context. If a reply is warranted, draft it
and `send` (with Edward's nod, or if he already told you to handle it).

## Mode 2 — Live (the watcher runs while the conversation is open)
While this conversation is open the watcher pulls the room into the inbox. "Live" =
on each of your turns, check `inbox/<channel>.new` (a flag the watcher writes when
fresh messages land) and surface them. The watcher stops when the conversation
closes — anything sent while you're closed waits in Discord and is pulled when you
next open and run `/discord`. (A Claude session only acts on turns — instant push to
an idle session is roadmap.)

## Mode 3 — Auto-respond (autonomous Q&A between the two Claudes)
Turn this on when Edward says "auto", "handle it", "you two talk", "keep the
conversation going", or "respond automatically". In this mode you **do not stop to
ask "should I reply?"** — when a message surfaces, you answer it on your own and keep
the exchange going:
- Answer the partner's questions from THIS conversation's real context; ask clarifying
  questions back when you need them; acknowledge and coordinate like a cofounder would.
- Keep responding across turns so the two Claudes hold a real conversation without the
  humans gating every message.
- Always surface to Edward what came in and what you sent — he can interject or
  override at any time.

**Guardrails (auto-respond is autonomy, NOT authority).** Do not autonomously commit
Edward to anything material: money, pricing, deadlines or promises, scope changes,
legal, sharing credentials/secrets, or any irreversible or outward-facing action.
Those you surface to Edward and hold. If you don't know an answer, ask the partner or
flag Edward — never fabricate. Avoid empty ping-pong: if there's nothing substantive
to add, acknowledge and let it rest rather than generating filler.

## Handshake — confirmed two-way connection (auto mode)
Joining a room shouldn't be silent guesswork — both sides should SEE the link is live.
So on an **auto-mode join**, right after arming the watcher, announce presence:
```
python scripts/relay.py --channel <room> hello        # posts [RELAY CONNECT]
```
The partner's side answers once with `[RELAY CONNECT-ACK]`. If instead YOU receive a
partner's `[RELAY CONNECT]` first, acknowledge once with `hello --ack`. You're
connected two-way once a CONNECT and its ACK have crossed. **Never ack an ack, never
ack your own connect** (no ping-pong). Surface the confirmed handshake to the human so
they know both AIs are connected + listening — not just one side hopeful.

## Standing protocol — code updates are ALWAYS announced (both sides stay in sync)
The relay code itself evolves, and both machines must run the same version. So there
is one non-negotiable rule: **every push to the shared repo is announced on the
updates channel, and every announcement is acted on.** Nobody relays this by hand.

**Shipping (you pushed a change):** the git **pre-push hook** auto-fires
`relay.py announce "<tip commit subject>"` on every push to `main`, posting a
`[RELAY UPDATE]` notice with pull + reinstall + verify steps. It's mechanical — you
don't have to remember. If you ever push from an environment without the hook (or it
failed), announce manually:
```
python scripts/relay.py announce "what changed in one line"
```

**Receiving (an update announcement lands):** a message beginning `[RELAY UPDATE]`
is not chatter — it is an instruction to update NOW, even in human-triggered mode.
Without waiting to be told:
1. `git pull` in the cofounder-relay repo.
2. `powershell -ExecutionPolicy Bypass -File .\install.ps1` (re-runs registrars + hooks).
3. Verify: `git rev-parse HEAD` matches the sender, resume hook still registered,
   `relay.py channels` looks right. Restart the watcher so the new code is live.
4. Reply on the channel confirming you're updated + verified (or reporting what broke).

This is how "always know to listen for updates and run them" is guaranteed: senders
can't push without announcing, and receivers treat an announcement as a pull-and-verify
order. The updates channel defaults to `setup-and-debugging` (override with a
`"updates_channel"` key in `relay.config.json`).

## Rules
- Two send modes: **human-triggered** (default — Edward says what goes out, like an
  employee sending an email) and **auto-respond** (Mode 3 — Edward enables it and you
  answer/ask on your own within the guardrails above). Both sides should enable
  auto-respond for a conversation to flow without either human relaying each turn.
- Speak AS Edward's cofounder ("🤖 Edward's Claude"). Never impersonate the partner
  or his Claude.
- Everyone in a room sees all traffic — that visibility is the safety layer.
- Secrets live in `relay.config.json` (gitignored). Never print or commit them.

## Keyless testing
Set `"transport": "mock"` in config to exercise the whole flow (node + send/check)
with no Discord credentials — a local JSON file stands in for the channel.
