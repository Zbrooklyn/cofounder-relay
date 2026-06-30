#!/usr/bin/env python3
"""cofounder-relay CLI — agent-to-agent relay over Discord.

Two modes:
  Mode 1 (invoked):  relay send "<text>"   /   relay check
  Mode 2 (watcher):  relay watch            (live, in-conversation poll loop)

Channel binding (which conversation this session is): --channel > RELAY_CHANNEL
env > ./.relay-channel file.

Run:  python scripts/relay.py <verb> [args]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import config as cfg_mod
import transport as transport_mod
import node as node_mod

ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = cfg_mod.INBOX_DIR


def _own_label(msg: dict, identity: str) -> bool:
    return transport_mod.own_message(msg, identity)


def _fmt(msg: dict) -> str:
    return f"  [{msg['id']}] {msg.get('author', '?')}: {msg.get('text', '')}"


def _get_transport_and_channel(args):
    cfg = cfg_mod.load_config()
    channel = cfg_mod.resolve_channel(getattr(args, "channel", None))
    return cfg, transport_mod.make_transport(cfg), channel


# --------------------------------------------------------------------------- #
# Verbs
# --------------------------------------------------------------------------- #
def cmd_send(args):
    cfg, tp, channel = _get_transport_and_channel(args)
    text = args.text if args.text else sys.stdin.read().strip()
    if not text:
        raise SystemExit("nothing to send (empty message)")
    if args.now:
        # Nodeless direct send (no standing node required).
        msg_id = tp.send(channel, text, cfg["identity"])
        print(f"sent to '{channel}' directly as {cfg['identity']}'s Claude (id={msg_id})")
        return
    # Default: hand to the local node via the outbox; the node delivers to Discord.
    node_mod.queue_outbound(channel, text, cfg["identity"])
    if cfg_mod.node_alive():
        print(f"queued to '{channel}' — node will deliver shortly")
    else:
        print(
            f"queued to '{channel}', but the node is DOWN — start it to deliver:\n"
            "  python scripts/node.py run   (or re-send with --now for a direct send)"
        )


def _read_inbox(channel: str) -> list[dict]:
    f = INBOX_DIR / f"{channel}.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def cmd_check(args):
    cfg, tp, channel = _get_transport_and_channel(args)
    if args.direct:
        # Nodeless: poll Discord directly using the read cursor.
        last = cfg_mod.get_last_seen(channel)
        msgs = tp.fetch_since(channel, last, limit=args.limit)
        new = [m for m in msgs if not _own_label(m, cfg["identity"])]
        if msgs and not args.peek:
            cfg_mod.set_last_seen(channel, msgs[-1]["id"])
    else:
        # Default: read the node-populated local inbox.
        lines = _read_inbox(channel)
        read = cfg_mod.get_inbox_read(channel)
        new = lines[read:]
        if not args.peek:
            cfg_mod.set_inbox_read(channel, len(lines))
            flag = INBOX_DIR / f"{channel}.new"
            if flag.exists():
                flag.unlink()

    if args.json:
        print(json.dumps(new, indent=2))
    elif not new:
        print(f"no new messages in '{channel}'")
    else:
        print(f"{len(new)} new message(s) in '{channel}':")
        for m in new:
            print(_fmt(m))


def cmd_watch(args):
    cfg, tp, channel = _get_transport_and_channel(args)
    INBOX_DIR.mkdir(exist_ok=True)
    inbox = INBOX_DIR / f"{channel}.jsonl"
    flag = INBOX_DIR / f"{channel}.new"
    print(
        f"watching '{channel}' every {args.interval}s as {cfg['identity']}'s Claude "
        f"(Ctrl-C to stop)\n  inbox: {inbox}\n  flag:  {flag}",
        flush=True,
    )
    iterations = 0
    try:
        while True:
            last = cfg_mod.get_last_seen(channel)
            msgs = tp.fetch_since(channel, last, limit=args.limit)
            fresh = [m for m in msgs if not _own_label(m, cfg["identity"])]
            if fresh:
                with inbox.open("a", encoding="utf-8") as fh:
                    for m in fresh:
                        fh.write(json.dumps(m) + "\n")
                flag.write_text(str(len(fresh)), encoding="utf-8")
                print(f"[{time.strftime('%H:%M:%S')}] {len(fresh)} new in '{channel}':", flush=True)
                for m in fresh:
                    print(_fmt(m), flush=True)
            if msgs:
                cfg_mod.set_last_seen(channel, msgs[-1]["id"])
            iterations += 1
            if args.max_iterations and iterations >= args.max_iterations:
                print(f"reached max-iterations={args.max_iterations}, stopping", flush=True)
                return
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nwatch stopped", flush=True)


def cmd_bind(args):
    channel = args.channel.strip()
    if args.session:
        owner = cfg_mod.room_owner(channel)
        if owner and owner.get("session_id") != args.session and not args.force:
            raise SystemExit(
                f"room '{channel}' is already attached to a different conversation "
                f"(session {owner.get('session_id')}). Re-run with --force to take it over."
            )
        if args.force and owner and owner.get("session_id") != args.session:
            cfg_mod.release_room(channel)
        status, _ = cfg_mod.claim_room(channel, args.session, getattr(args, "transcript", None))
        print(f"conversation {args.session} attached to room '{channel}' ({status})")
        return
    marker = Path.cwd() / ".relay-channel"
    marker.write_text(channel + "\n", encoding="utf-8")
    print(f"bound this directory to channel '{channel}' ({marker})")


def cmd_whoami(args):
    """Show which room (if any) the current conversation owns."""
    sid = cfg_mod.current_session_id()
    if not sid:
        print("no session id (set RELAY_SESSION_ID); cannot resolve owned room")
        return
    room = cfg_mod.owned_room(sid)
    print(f"session {sid}: {'owns room ' + room if room else 'owns no room'}")


def cmd_channels(args):
    cfg = cfg_mod.load_config()
    chans = cfg.get("channels", {})
    if not chans:
        print("no channels configured")
        return
    print(f"transport={cfg['transport']} identity={cfg['identity']}")
    for key, c in chans.items():
        has_hook = "webhook" if c.get("webhook_url") else "NO-webhook"
        has_id = c.get("channel_id", "NO-id")
        print(f"  {key}: id={has_id} {has_hook}")


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="relay", description="agent-to-agent relay over Discord")
    p.add_argument("--channel", help="channel key (overrides env / .relay-channel)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("send", help="post a message to this conversation's channel")
    s.add_argument("text", nargs="?", help="message text (or pipe via stdin)")
    s.add_argument("--now", action="store_true", help="send directly, bypassing the node")
    s.set_defaults(func=cmd_send)

    c = sub.add_parser("check", help="show new messages (from the local inbox)")
    c.add_argument("--limit", type=int, default=50)
    c.add_argument("--json", action="store_true", help="emit JSON")
    c.add_argument("--peek", action="store_true", help="don't advance the read cursor")
    c.add_argument("--direct", action="store_true", help="poll Discord directly, bypassing the node")
    c.set_defaults(func=cmd_check)

    w = sub.add_parser("watch", help="live poll loop (Mode 2)")
    w.add_argument("--interval", type=int, default=15, help="seconds between polls")
    w.add_argument("--limit", type=int, default=50)
    w.add_argument("--max-iterations", type=int, default=0, help="stop after N polls (0=forever)")
    w.set_defaults(func=cmd_watch)

    b = sub.add_parser("bind", help="attach this conversation/dir to a channel key")
    b.add_argument("channel")
    b.add_argument("--session", help="attach a Claude session id (else binds the current directory)")
    b.add_argument("--transcript", help="transcript path of the conversation (recorded with the binding)")
    b.add_argument("--force", action="store_true", help="take over a room owned by another conversation")
    b.set_defaults(func=cmd_bind)

    ch = sub.add_parser("channels", help="list configured channels")
    ch.set_defaults(func=cmd_channels)

    wi = sub.add_parser("whoami", help="show which room this conversation owns")
    wi.set_defaults(func=cmd_whoami)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
