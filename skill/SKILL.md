---
name: relay
description: Send and receive agent-to-agent messages with a business partner's Claude over Discord. Use when Edward says to message/tell/send something to his partner (or asks "any messages / what did he say / check the relay"), or wants to watch a conversation live. Each project/conversation maps to its own Discord channel; replies come from the current session's context.
---

# relay — agent-to-agent messaging with a partner's Claude

`relay` is a thin CLI over a per-conversation Discord channel. Edward directs his
Claude to send; the partner's Claude reads it from inside its own live session.
It is NOT a separate always-on bot — YOU (the live session) invoke it.

Entry point: `python "<repo>/scripts/relay.py" <verb>` where `<repo>` is the
cofounder-relay project. The channel for "this conversation" comes from
`--channel`, the `RELAY_CHANNEL` env var, or a `.relay-channel` file in the cwd.

## Mode 1 — Invoked (default)

**Send** — when Edward says "tell David that…", "send him…", "reply to him…":
```
python scripts/relay.py send "the message text"
```
Compose the message in Edward's voice/intent, then send. Confirm what you sent.

**Check** — when Edward asks "any messages?", "what did he say?", "check the relay":
```
python scripts/relay.py check
```
Returns only messages newer than the last check, excluding our own posts. Read
them, then respond from THIS conversation's context. If a reply is warranted,
draft it and (with Edward's nod, or if he already told you to handle it) `send`.

Bind a project directory once so you don't pass --channel every time:
```
python scripts/relay.py bind <channel-key>      # writes ./.relay-channel
python scripts/relay.py channels                 # list configured channels
```

## Mode 2 — Live watcher (in-conversation)

When Edward wants to "watch" a thread live during a work session, start the
poller as a background task:
```
python scripts/relay.py watch --interval 15
```
It polls the bound channel, appends new inbound messages to `inbox/<channel>.jsonl`,
and writes a `inbox/<channel>.new` flag. On each of your turns, check the flag /
read the inbox and surface anything new to Edward in context. (A Claude session
only acts on turns — the watcher captures instantly; you surface at the next turn.
Pairs well with `/loop`.) Stop it by ending the background task.

## Rules
- Send is human-triggered. Do not send on your own initiative — Edward (or the
  context he set) decides what goes out, like an employee sending an email.
- Speak AS Edward's cofounder; label is "🤖 Edward's Claude". Never impersonate
  the partner or his Claude.
- The partner and Edward both sit in every channel and see all traffic — that
  visibility is the safety layer. Nothing destructive happens via relay.
- Secrets live in `relay.config.json` (gitignored). Never print or commit them.

## Keyless testing
Set `"transport": "mock"` in config to exercise send/check/watch with no Discord
credentials (a local JSON file stands in for the channel).
