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
import base64
import json
import re
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
    rooms = cfg_mod.owned_rooms(sid)
    print(f"session {sid}: {'owns ' + ', '.join(rooms) if rooms else 'owns no room'}")


def cmd_init(args):
    """Interactive setup wizard — writes relay.config.json. Run once per machine."""
    path = cfg_mod.CONFIG_PATH
    existing = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8-sig") or "{}")

    def ask(prompt, default=None):
        suffix = f" [{default}]" if default else ""
        return input(f"{prompt}{suffix}: ").strip() or (default or "")

    print("cofounder-relay setup — Enter keeps the [default].")
    cfg = {
        "identity": ask("Your name (labels your outbound messages)", existing.get("identity")),
        "transport": ask("Transport (discord/mock)", existing.get("transport", "discord")),
        "channels": dict(existing.get("channels", {})),
    }
    if cfg["transport"] == "discord":
        cfg["discord_bot_token"] = ask(
            "Discord bot token (reads messages)", existing.get("discord_bot_token")
        )
        gid = ask("Discord server (guild) id — enables one-command channel creation; optional",
                  existing.get("guild_id", ""))
        if gid:
            cfg["guild_id"] = gid
    print("\nAdd channels — one per conversation/room. Blank channel key to finish.")
    print("(Joining a partner's channel? Paste the key + channel_id + webhook_url they sent.)")
    while True:
        name = input("  channel key (e.g. steady-imports), blank to skip: ").strip()
        if not name:
            break
        cfg["channels"][name] = {
            "channel_id": input("    channel_id: ").strip(),
            "webhook_url": input("    webhook_url: ").strip(),
        }
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"\nwrote {path}")
    print("Next steps:")
    print("  • Add the bot to your server:   python scripts/relay.py invite-url")
    print("  • Create a fresh channel:       python scripts/relay.py new-channel \"My Project\"")
    print("  • Prove it works:               python scripts/relay.py validate")


def cmd_validate(args):
    """Handshake test: post a probe and read it back, per channel — proves this
    node can both post (webhook) and read (bot token) each room end-to-end."""
    cfg = cfg_mod.load_config()
    tp = transport_mod.make_transport(cfg)
    channels = [args.channel] if args.channel else list(cfg.get("channels", {}).keys())
    if not channels:
        raise SystemExit("no channels to validate")
    all_ok = True
    for ch in channels:
        probe = f"relay online check {time.strftime('%H:%M:%S')}"
        try:
            tp.send(ch, probe, cfg["identity"])
            seen = False
            for _ in range(3):  # webhook posts can take a beat to appear
                msgs = tp.fetch_since(ch, None, limit=20)
                if any(probe in m.get("text", "") for m in msgs):
                    seen = True
                    break
                time.sleep(1)
            print(f"  {ch}: {'PASS — post + read OK' if seen else 'FAIL — posted but could not read back'}")
            all_ok = all_ok and seen
        except Exception as e:
            print(f"  {ch}: FAIL — {e}")
            all_ok = False
    print("validate:", "ALL PASS" if all_ok else "FAILURES — fix config and retry")
    if not all_ok:
        raise SystemExit(1)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s[:90] or "channel"


def cmd_new_channel(args):
    """Create a Discord channel + webhook via the bot and add it to the config —
    no browser needed. Requires transport=discord, a guild_id, and the bot to
    have Manage Channels + Manage Webhooks."""
    cfg = cfg_mod.load_config()
    if cfg.get("transport") == "discord" and not cfg.get("guild_id"):
        raise SystemExit(
            "guild_id missing from relay.config.json — add your server id, e.g.\n"
            '  "guild_id": "1522660014404407356"'
        )
    key = args.key or _slugify(args.name)
    if key in cfg.get("channels", {}):
        raise SystemExit(f"channel key {key!r} already in config — pick another --key or remove it first")
    tp = transport_mod.make_transport(cfg)
    slug = _slugify(args.name)
    ch = tp.create_channel(slug, topic=args.topic or "")
    cid = str(ch.get("id", ""))
    if not cid:
        raise SystemExit(f"channel create returned no id: {ch}")
    hook = tp.create_webhook(cid, name=f"relay-{key}")
    cfg_mod.add_channel(key, cid, hook)
    print(f"created #{slug}  (config key: {key})")
    print(f"  channel_id : {cid}")
    print(f"  webhook_url: {hook}")
    print("added to relay.config.json — restart the node (node.py run) to watch it.")
    print("partner joins the same room with the SAME key + channel_id + webhook_url.")


def cmd_add_channel(args):
    """Join a channel someone else already created — one command, no JSON editing.
    Give it the key + the channel_id + webhook_url your partner sent you."""
    cfg_mod.add_channel(args.key, args.channel_id, args.webhook_url)
    print(f"joined channel '{args.key}' (id={args.channel_id})")
    print(f"verify it: python scripts/relay.py --channel {args.key} validate")


def cmd_announce(args):
    """Broadcast a standardized UPDATE notice to the updates channel so partners'
    AIs know to pull + reinstall. Called automatically by the git pre-push hook;
    can also be run by hand. Silent no-op if no updates channel is configured
    (so it never blocks a push)."""
    try:
        cfg = cfg_mod.load_config()
    except SystemExit:
        return
    chans = cfg.get("channels", {})
    ch = args.channel or cfg.get("updates_channel")
    if not ch or ch not in chans:
        ch = "setup-and-debugging" if "setup-and-debugging" in chans else None
    if not ch:
        return  # nowhere to announce — stay silent
    summary = (args.summary or "").strip() or "new changes on main"
    msg = (
        f"[RELAY UPDATE] {summary}\n"
        f"Other AIs: pull + reinstall to stay in sync, then verify. "
        f"Steps: `git pull` in the cofounder-relay repo, then "
        f"`powershell -ExecutionPolicy Bypass -File .\\install.ps1`, then confirm "
        f"HEAD matches, resume hook registered, and `relay.py channels` looks right. "
        f"Reply here once you're updated + verified."
    )
    try:
        transport_mod.make_transport(cfg).send(ch, msg, cfg["identity"])
        print(f"announced update on #{ch}")
    except Exception as e:
        print(f"(could not announce update: {e})")  # never blocks the push


def cmd_invite_url(args):
    """Print the bot's install URL (with the permissions the relay needs) so you can
    add it to a server without hunting through the Discord Developer Portal. The
    client id is derived from the bot token."""
    cfg = cfg_mod.load_config()
    tok = cfg.get("discord_bot_token", "")
    if not tok:
        raise SystemExit("no discord_bot_token in config — run: python scripts/relay.py init")
    first = tok.split(".")[0]
    try:
        client_id = base64.urlsafe_b64decode(first + "=" * (-len(first) % 4)).decode()
        int(client_id)  # sanity: it should be a numeric snowflake
    except Exception:
        raise SystemExit("couldn't derive the client id from the bot token — check the token")
    # View Channels + Read Message History + Manage Channels + Manage Webhooks
    perms = 536937488
    print("Open this, pick your server, Authorize:")
    print(f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions={perms}&scope=bot")


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

    nc = sub.add_parser("new-channel", help="create a Discord channel + webhook via the bot and add it to config (no browser)")
    nc.add_argument("name", help="human channel name, e.g. 'setup and debugging'")
    nc.add_argument("--key", help="config key to store it under (default: slug of name)")
    nc.add_argument("--topic", help="channel topic/description")
    nc.set_defaults(func=cmd_new_channel)

    ac = sub.add_parser("add-channel", help="join a channel a partner already created (no JSON editing)")
    ac.add_argument("key", help="channel key, e.g. steady-imports")
    ac.add_argument("channel_id", help="the channel_id your partner sent")
    ac.add_argument("webhook_url", help="the webhook_url your partner sent")
    ac.set_defaults(func=cmd_add_channel)

    iu = sub.add_parser("invite-url", help="print the bot install URL (derived from the token) to add it to a server")
    iu.set_defaults(func=cmd_invite_url)

    wi = sub.add_parser("whoami", help="show which room this conversation owns")
    wi.set_defaults(func=cmd_whoami)

    ini = sub.add_parser("init", help="interactive setup wizard (writes relay.config.json)")
    ini.set_defaults(func=cmd_init)

    va = sub.add_parser("validate", help="handshake test: post a probe and read it back")
    va.set_defaults(func=cmd_validate)

    an = sub.add_parser("announce", help="broadcast a standardized UPDATE notice so partners' AIs pull + reinstall (auto-fired by the git pre-push hook)")
    an.add_argument("summary", nargs="?", default="", help="one-line summary of what changed")
    an.add_argument("--channel", help="channel key to announce on (default: updates_channel, else setup-and-debugging)")
    an.set_defaults(func=cmd_announce)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
