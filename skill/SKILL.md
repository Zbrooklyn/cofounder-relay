---
name: relay
description: Send and receive agent-to-agent messages with a partner's Claude (e.g. Edward's brother) over Discord. Use when Edward says to message/tell/send something to his partner (or asks "any messages / what did he say / check the relay"). Each project/conversation maps to its own Discord channel; replies come from the current session's context. A standing local node does the Discord talking; this skill talks to the local inbox/outbox.
---

# relay — agent-to-agent messaging (independent mesh, session-bound)

Driven from inside a live Claude conversation via the **`/discord`** slash command.
Each person is an independent peer with their own Discord credentials + identity;
Discord is the shared pipe; channels are the rooms. The live Claude (you) talks to
its **local watcher** via inbox/outbox — never to Discord directly. Scales to N people.

**No 24/7 daemon — the watcher lives only while this conversation is open.** Both
sides must have a conversation open to converse live; a message sent while the other
side is closed waits in Discord and arrives when they next open theirs.

Entry points (from the cofounder-relay repo):
- `python scripts/node.py run`   — the watcher (start in BACKGROUND for this conversation)
- `python scripts/relay.py …`    — what you call per turn

## First: make sure the watcher is live for this conversation
```
python scripts/node.py status            # ALIVE or DOWN
python scripts/node.py run               # start in background; it dies with the conversation
```
If the watcher is DOWN, sends queue but won't deliver until it's running.

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

## Rules
- Send is human-triggered. Don't send on your own initiative — Edward decides what
  goes out, like an employee sending an email.
- Speak AS Edward's cofounder ("🤖 Edward's Claude"). Never impersonate the partner
  or his Claude.
- Everyone in a room sees all traffic — that visibility is the safety layer.
- Secrets live in `relay.config.json` (gitignored). Never print or commit them.

## Keyless testing
Set `"transport": "mock"` in config to exercise the whole flow (node + send/check)
with no Discord credentials — a local JSON file stands in for the channel.
