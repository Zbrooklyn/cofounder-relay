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
   - otherwise → compose the message in the user's voice/intent, show the one-line
     version, then `relay.py send "<message>"`. Send is human-triggered — only what the
     user asked.

4. **Report** what you sent and/or what came in. If the partner may be offline, note the
   message waits in Discord until they open their conversation and run `/discord`.

Rules: speak AS the user's cofounder; never impersonate the partner or their Claude.
Never print secrets from `relay.config.json`. On later turns while this conversation is
open, glance at the inbox `.new` flag and surface anything fresh.

Request: $ARGUMENTS
