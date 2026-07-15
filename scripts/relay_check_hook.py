"""UserPromptSubmit hook: surface new relay messages into the live session.

Why this exists: the relay's live delivery was designed around a standing
background node (node.py) that polls Discord into a local inbox. In harnesses
that kill background processes each turn (and when the node is simply down), no
inbound message ever surfaces — the human has to keep asking "check discord".

This hook closes that gap without a cron or a standing process. It fires on
every UserPromptSubmit, but only does work when THIS session owns a relay room
(so it is zero-cost in unrelated projects/sessions). For each owned room it does
a direct Discord read since the last-seen cursor, prints any new messages (which
Claude Code injects into the model's context), and advances the cursor so each
message surfaces exactly once. It never blocks the prompt: all failure paths
exit 0, and a short socket timeout prevents a slow network call from hanging.
"""
import sys, os, json, socket

socket.setdefaulttimeout(6)  # never hang a prompt on a slow Discord call
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}

sid = (payload.get("session_id")
       or os.environ.get("RELAY_SESSION_ID")
       or os.environ.get("CLAUDE_SESSION_ID"))
if not sid:
    sys.exit(0)

try:
    import config as c, transport as t
    cfg = c.load_config()
except SystemExit:
    sys.exit(0)
except Exception:
    sys.exit(0)

if cfg.get("transport") != "discord":
    sys.exit(0)

rooms = c.owned_rooms(sid)          # only active if this session owns a room
if not rooms:
    sys.exit(0)

try:
    tp = t.make_transport(cfg)
except Exception:
    sys.exit(0)

ident = cfg.get("identity", "")
channels = cfg.get("channels", {})
out = []
for ch in rooms:
    if ch not in channels:
        continue
    last = c.get_last_seen(ch)
    try:
        msgs = tp.fetch_since(ch, last, limit=25)
    except Exception:
        continue
    if not msgs:
        continue
    c.set_last_seen(ch, msgs[-1]["id"])          # advance cursor past everything read
    for m in msgs:
        if t.own_message(m, ident):              # skip our own posts
            continue
        line = f"[#{ch}] {m['author']}: {m['text']}"
        for a in m.get("attachments", []):       # Discord-held files: expose the URL
            line += f"\n    [FILE: {a.get('filename')} -> {a.get('url')}]"
        out.append(line)

if out:
    print("[RELAY] New message(s) arrived since the last turn — surface these to Edward:")
    print("\n".join(out))

sys.exit(0)
