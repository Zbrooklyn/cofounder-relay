"""End-to-end tests for cofounder-relay against MockTransport (no Discord creds).

Two layers:
  A. Direct mode (nodeless): send --now / check --direct over a shared mock channel.
  B. Node mode (mesh): a standing node pulls inbound to a local inbox and flushes
     the outbox to the channel; the live CLI talks only to inbox/outbox.

Each "machine" gets its own repo-state by running with an isolated REPO copy of
the scripts dir on its own state, sharing only the mock channel dir.

Run: python tests/test_relay.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

FAILS = []


def check(cond, label):
    print(("PASS" if cond else "FAIL"), "-", label)
    if not cond:
        FAILS.append(label)


def make_machine(tmp: Path, name: str, identity: str, mock_dir: Path) -> dict:
    """An isolated 'machine': its own working dir (=> own .relay-state.json,
    inbox/outbox) but the SAME mock_dir so it shares the channel."""
    d = tmp / name
    d.mkdir()
    cfg = d / "relay.config.json"
    cfg.write_text(json.dumps({
        "identity": identity,
        "transport": "mock",
        "mock_dir": str(mock_dir),
        "channels": {"deal-x": {}},
    }), encoding="utf-8")
    return {"dir": d, "config": cfg, "identity": identity}


def run(machine, script, *args, env_extra=None):
    env = dict(os.environ)
    env["RELAY_CONFIG"] = str(machine["config"])
    env["RELAY_CHANNEL"] = "deal-x"
    # Force repo-root state files (state/inbox/outbox/heartbeat) under the machine dir
    # by copying the scripts to run with cwd-independent ROOT: we point a per-machine
    # symlink-free ROOT via RELAY_STATE_ROOT-style override is not supported, so we
    # rely on each machine using a distinct REPO clone-lite: scripts import config
    # which computes ROOT from the scripts location. To isolate, we run the REAL
    # scripts but redirect ROOT-derived files by running from the machine dir AND
    # giving each machine its own copy of scripts.
    cp = subprocess.run(
        [sys.executable, str(machine["scripts"] / script), *args],
        capture_output=True, text=True, env=env, cwd=str(machine["dir"]),
    )
    if cp.returncode != 0:
        raise AssertionError(f"{script} {args} failed:\n{cp.stdout}\n{cp.stderr}")
    return cp.stdout.strip()


def clone_scripts(machine):
    """Give each machine its own scripts dir so ROOT-derived state (inbox/outbox/
    .relay-state.json/.node_alive) is isolated per machine."""
    import shutil
    dst = machine["dir"] / "scripts"
    shutil.copytree(SCRIPTS, dst)
    machine["scripts"] = dst
    # config lives at repo-root = machine dir; move config there
    (machine["dir"] / "relay.config.json").write_text(
        machine["config"].read_text(encoding="utf-8"), encoding="utf-8")
    machine["config"] = machine["dir"] / "relay.config.json"


def main():
    tmp = Path(tempfile.mkdtemp(prefix="relay-test-"))
    mock_dir = tmp / "shared-channel"
    mock_dir.mkdir()

    ed = make_machine(tmp, "edward", "Edward", mock_dir)
    pa = make_machine(tmp, "partner", "David", mock_dir)
    clone_scripts(ed)
    clone_scripts(pa)

    # ---- A. Direct mode (nodeless) ----
    run(ed, "relay.py", "send", "--now", "Direct: can your Claude pull Q3?")
    out = run(pa, "relay.py", "check", "--direct", "--json")
    msgs = json.loads(out)
    check(any("pull Q3" in m["text"] for m in msgs), "direct: partner receives message")
    check(all(m["identity"] != "David" for m in msgs), "direct: partner excludes own posts")

    # ---- B. Node mode (mesh) ----
    # Edward queues an outbound via the CLI; Edward's node flushes it to the channel.
    run(ed, "relay.py", "send", "Node: invoice total please")
    run(ed, "node.py", "run", "--max-iterations", "1")  # flush outbox -> channel
    # Partner's node pulls inbound from the channel into the partner inbox.
    run(pa, "node.py", "run", "--max-iterations", "1")
    out = run(pa, "relay.py", "check", "--json")
    msgs = json.loads(out)
    check(any("invoice total" in m["text"] for m in msgs), "node: partner inbox got Edward's queued msg")
    check(all("David" not in m["identity"] for m in msgs), "node: partner excludes own posts")

    # check again -> inbox read cursor advanced, nothing new
    out = run(pa, "relay.py", "check", "--json")
    check(json.loads(out) == [], "node: inbox read-cursor advances (no repeats)")

    # Partner replies via node; Edward's node pulls it; Edward sees it, not his own.
    run(pa, "relay.py", "send", "Node: total is $4,200")
    run(pa, "node.py", "run", "--max-iterations", "1")
    run(ed, "node.py", "run", "--max-iterations", "1")
    out = run(ed, "relay.py", "check", "--json")
    msgs = json.loads(out)
    check(any("4,200" in m["text"] for m in msgs), "node: Edward receives partner reply")
    check(all("Edward" not in m["identity"] for m in msgs), "node: Edward excludes own posts")

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S): {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
