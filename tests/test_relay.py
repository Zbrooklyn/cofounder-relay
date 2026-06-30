"""End-to-end test of cofounder-relay against MockTransport (no Discord creds).

Simulates two machines (Edward + partner) sharing one mock channel by pointing
both at the same mock dir but with different identities + separate state files.
Run: python tests/test_relay.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELAY = ROOT / "scripts" / "relay.py"


def run(identity, state_file, config_file, mock_dir, *args):
    """Invoke relay.py as a subprocess with an isolated config/state per 'machine'."""
    import os

    env = dict(os.environ)
    env["RELAY_CONFIG"] = str(config_file)
    env["RELAY_CHANNEL"] = "deal-x"
    # Each machine gets its own state file by pointing RELAY at its own repo-root
    # surrogate: we override STATE via a small shim — simplest is a per-identity cwd.
    cp = subprocess.run(
        [sys.executable, str(RELAY), *args],
        capture_output=True, text=True, env=env, cwd=str(state_file.parent),
    )
    if cp.returncode != 0:
        raise AssertionError(f"relay {args} failed:\n{cp.stdout}\n{cp.stderr}")
    return cp.stdout.strip()


def write_config(path, identity, mock_dir):
    path.write_text(json.dumps({
        "identity": identity,
        "transport": "mock",
        "mock_dir": str(mock_dir),
        "channels": {"deal-x": {}},
    }), encoding="utf-8")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="relay-test-"))
    mock_dir = tmp / "shared-channel"
    mock_dir.mkdir()

    # Two "machines": separate dirs (=> separate .relay-state.json) + configs,
    # but the SAME mock_dir so they share the channel.
    ed_dir = tmp / "edward"; ed_dir.mkdir()
    pa_dir = tmp / "partner"; pa_dir.mkdir()
    ed_cfg = ed_dir / "relay.config.json"
    pa_cfg = pa_dir / "relay.config.json"
    write_config(ed_cfg, "Edward", mock_dir)
    write_config(pa_cfg, "David", mock_dir)

    # relay.py resolves STATE relative to its own repo root, so both machines would
    # share .relay-state.json. To isolate, run each with cwd = its own dir AND copy
    # relay scripts' ROOT state there by setting RELAY_CONFIG; state still lives at
    # repo-root. For the test we instead assert via --peek + explicit cursors.
    fails = []

    def check(cond, label):
        print(("PASS" if cond else "FAIL"), "-", label)
        if not cond:
            fails.append(label)

    # 1. Edward sends -> partner sees it on check
    run("Edward", ed_cfg, ed_cfg, mock_dir, "send", "Can your Claude pull the Q3 numbers?")
    out = run("David", pa_cfg, pa_cfg, mock_dir, "check", "--json", "--peek")
    msgs = json.loads(out)
    check(any("Q3 numbers" in m["text"] for m in msgs), "partner receives Edward's message")
    check(all(m["identity"] != "David" for m in msgs), "partner does not see its own posts")

    # 2. Partner replies -> Edward sees it, and does NOT see his own original
    run("David", pa_cfg, pa_cfg, mock_dir, "send", "On it — sending the sheet in 5.")
    out = run("Edward", ed_cfg, ed_cfg, mock_dir, "check", "--json", "--peek")
    msgs = json.loads(out)
    check(any("sending the sheet" in m["text"] for m in msgs), "Edward receives partner reply")
    check(all("Edward" not in m["identity"] for m in msgs), "Edward filters out his own messages")

    # 3. Ordering: messages come back oldest-first
    ids = [int(m["id"]) for m in msgs]
    check(ids == sorted(ids), "messages returned in chronological order")

    print()
    if fails:
        print(f"{len(fails)} FAILURE(S): {fails}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
