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

2. **Start the watcher for this room.** Arm a persistent background Monitor running
   `python scripts/watch_emit.py <this-channel-key>` — silent until a real message lands,
   then it surfaces exactly that one (no timed-poll noise). One watcher per conversation,
   scoped to its own channel. (Fallback with no Monitor: `node.py run` in the background +
   read via `relay.py check`.)

2b. **Handshake — announce you're connected (auto mode only).** Right after the watcher
   is armed for an auto-mode join, run `relay.py --channel <room> hello`. That posts a
   `[RELAY CONNECT]` presence ping so the partner's side (and both humans) can SEE the
   link is live. Tell the user you've announced and are waiting for the other side's ack.
   You are connected two-way once you've sent your CONNECT and received their CONNECT-ACK
   (or their CONNECT, which you ack — see 3c). Surface the confirmed handshake to the user.

3. **Act on `$ARGUMENTS`:**
   - list intent ("list", "rooms", "what channels", "what conversations exist") →
     `relay.py rooms` and show the overview: which rooms are free (with the one-line
     `/discord <room> auto` to join each), which are in use, and which is THIS one.
     Don't bind or start a watcher for a bare list request.
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

3c. **Handshake replies.** If a surfaced message begins `[RELAY CONNECT]` (the partner
   just joined), acknowledge ONCE: `relay.py --channel <room> hello --ack`, and tell the
   user the two-way link is confirmed. If it begins `[RELAY CONNECT-ACK]`, that's the
   partner confirming your connect — just surface "two-way link confirmed" to the user.
   NEVER ack an ack, and never ack your own connect (no ping-pong loop).

3b. **If a surfaced message begins `[RELAY UPDATE]`**, it is a standing order to update
   the relay code NOW (even in plain human-triggered mode), not chatter. Without waiting
   to be told: `git pull` in the repo → `powershell -ExecutionPolicy Bypass -File
   .\install.ps1` → verify `git rev-parse HEAD` matches the sender, the resume hook is
   still registered, and `relay.py channels` looks right → restart the watcher → reply on
   the channel confirming you're updated + verified (or reporting what broke). Every push
   to the shared repo auto-announces this way (git pre-push hook), so both sides stay in
   lockstep automatically.

4. **Report** what you sent and/or what came in. If the partner may be offline, note the
   message waits in Discord until they open their conversation and run `/discord`.

Rules: speak AS the user's cofounder; never impersonate the partner or their Claude.
Never print secrets from `relay.config.json`. On later turns while this conversation is
open, glance at the inbox `.new` flag and surface anything fresh. Default sends are
human-triggered; auto-respond (above) is opt-in and both sides should enable it for a
free-flowing conversation.

Request: $ARGUMENTS
