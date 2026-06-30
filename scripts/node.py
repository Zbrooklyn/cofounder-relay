#!/usr/bin/env python3
"""cofounder-relay — standing local node (mesh peer).

Always-on, on the owner's machine only. Owns this side's Discord credentials and
identity. For every channel this node belongs to it:
  - pulls inbound messages into inbox/<channel>.jsonl (caught even with no Claude
    session open),
  - flushes outbound messages queued in outbox/<channel>/ to Discord.

The live Claude talks to inbox/outbox (via relay.py), never to Discord directly.
Safe to run continuously — nothing is exposed; it only talks out to Discord.

Run:    python scripts/node.py run [--interval 15] [--max-iterations N]
Status: python scripts/node.py status
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import config as cfg_mod
import transport as transport_mod

INBOX = cfg_mod.INBOX_DIR
OUTBOX = cfg_mod.OUTBOX_DIR


def _outbox_dir(channel: str) -> Path:
    d = OUTBOX / channel
    d.mkdir(parents=True, exist_ok=True)
    return d


def queue_outbound(channel: str, text: str, identity: str) -> Path:
    """Append a pending outbound message (one file per message — no write races)."""
    d = _outbox_dir(channel)
    path = d / f"{time.time_ns()}.json"
    path.write_text(json.dumps({"text": text, "identity": identity}), encoding="utf-8")
    return path


def _pull_inbound(tp, channel: str, identity: str) -> int:
    last = cfg_mod.get_last_seen(channel)
    msgs = tp.fetch_since(channel, last, limit=50)
    fresh = [m for m in msgs if not transport_mod.own_message(m, identity)]
    if fresh:
        INBOX.mkdir(exist_ok=True)
        with (INBOX / f"{channel}.jsonl").open("a", encoding="utf-8") as fh:
            for m in fresh:
                fh.write(json.dumps(m) + "\n")
        (INBOX / f"{channel}.new").write_text(str(len(fresh)), encoding="utf-8")
    if msgs:
        cfg_mod.set_last_seen(channel, msgs[-1]["id"])
    return len(fresh)


def _flush_outbound(tp, channel: str) -> int:
    d = _outbox_dir(channel)
    sent = 0
    for path in sorted(d.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        tp.send(channel, rec["text"], rec["identity"])
        path.unlink()  # delete only after a successful send
        sent += 1
    return sent


def cmd_run(args):
    cfg = cfg_mod.load_config()
    tp = transport_mod.make_transport(cfg)
    identity = cfg["identity"]
    channels = list(cfg.get("channels", {}).keys())
    if not channels:
        raise SystemExit("no channels configured — nothing to watch")
    print(
        f"node up: identity={identity} transport={cfg['transport']} "
        f"channels={channels} interval={args.interval}s",
        flush=True,
    )
    iterations = 0
    try:
        while True:
            for ch in channels:
                try:
                    got = _pull_inbound(tp, ch, identity)
                    out = _flush_outbound(tp, ch)
                    if got or out:
                        print(
                            f"[{time.strftime('%H:%M:%S')}] {ch}: +{got} in, {out} out",
                            flush=True,
                        )
                except transport_mod.TransportError as e:
                    print(f"[{time.strftime('%H:%M:%S')}] {ch}: ERROR {e}", flush=True)
            cfg_mod.touch_heartbeat()
            iterations += 1
            if args.max_iterations and iterations >= args.max_iterations:
                print(f"reached max-iterations={args.max_iterations}, stopping", flush=True)
                return
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nnode stopped", flush=True)


def cmd_status(args):
    alive = cfg_mod.node_alive()
    print(f"node: {'ALIVE' if alive else 'DOWN'}")
    if cfg_mod.HEARTBEAT_PATH.exists():
        print(f"  last heartbeat: {cfg_mod.HEARTBEAT_PATH.read_text(encoding='utf-8').strip()}")
    # pending outbound count
    if OUTBOX.exists():
        for d in sorted(OUTBOX.iterdir()):
            if d.is_dir():
                n = len(list(d.glob("*.json")))
                if n:
                    print(f"  outbox {d.name}: {n} pending")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="node", description="cofounder-relay standing local node")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the node loop")
    r.add_argument("--interval", type=int, default=15)
    r.add_argument("--max-iterations", type=int, default=0, help="stop after N loops (0=forever)")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("status", help="show node liveness + pending outbox")
    s.set_defaults(func=cmd_status)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
