---
description: Relay a message to/from your partner's Claude over Discord. The watcher is live only while THIS conversation is open.
argument-hint: e.g. "ask my partner for the Q3 numbers"  |  "check"
---

You are operating the **cofounder-relay** Discord bridge from inside this live
conversation. It connects you to a business partner; their Claude reads what you send
when their own Claude conversation is open. There is no 24/7 daemon — the watcher
lives only while this conversation is open.

Repo: `{{RELAY_REPO}}`
Call scripts as: `python "{{RELAY_REPO}}\scripts\<name>.py" ...`

Do this:

1. **Pick the room.** Run `relay.py channels`. One channel → use it. Multiple → choose
   the one matching the project/person in the request. Still ambiguous → ask which.

1b. **Claim the room for THIS conversation (one thread per room).** Set
   `RELAY_SESSION_ID` to this conversation's session id and run
   `relay.py bind <room> --session <session-id> --transcript <transcript-path>`.
   If it reports a conflict (already attached to a different conversation), tell the
   user and ask before using `--force`. Don't double-attach.

2. **Ensure the watcher is live.** Run `node.py status`; if DOWN, start `node.py run`
   in the BACKGROUND (it runs for the life of this conversation).

3. **Act on `$ARGUMENTS`:**
   - read intent ("check", "any messages", "what did he say") → `relay.py check` and
     surface anything new in this conversation's context.
   - auto intent ("auto", "handle it", "you two talk", "respond automatically", "keep
     the conversation going") → enter **auto-respond mode**: when a message surfaces,
     answer it on your own — don't stop to ask "should I reply?". Answer the partner's
     questions from this conversation's context, ask clarifying questions back, and keep
     the exchange going, surfacing each in/out to the user. GUARDRAIL: never autonomously
     commit the user to anything material (money, pricing, promises/deadlines, scope,
     legal, credentials, irreversible/outward-facing actions) — surface those and hold.
     Never fabricate; ask the partner or flag the user instead. Skip empty ping-pong.
   - otherwise (human-triggered send) → compose the message in the user's voice/intent,
     show the one-line version, then `relay.py send "<message>"` — only what the user asked.

4. **Report** what you sent and/or what came in. If the partner may be offline, note the
   message waits in Discord until they open their conversation and run `/discord`.

Rules: speak AS the user's cofounder; never impersonate the partner or their Claude.
Never print secrets from `relay.config.json`. On later turns while this conversation is
open, glance at the inbox `.new` flag and surface anything fresh. Default sends are
human-triggered; auto-respond (above) is opt-in and both sides should enable it for a
free-flowing conversation.

Request: $ARGUMENTS
