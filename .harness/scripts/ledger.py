"""JSONL ledger & 3-Tier Knowledge promotion (_LOG.jsonl & _MEM.jsonl)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._core import append_jsonl, read_jsonl, utc_now
from scripts.guard import redact_secrets

LOG_STATUSES = ("DONE", "LIVE", "BACK", "FAIL")


def append_log(
    root: Path,
    task: str,
    exit_code: int = 0,
    track: str = "FLOW",
    note: str = "",
    strike: int = 0,
    status: str = "",
) -> dict[str, Any]:
    st = status.strip().upper() or ("DONE" if int(exit_code) == 0 else "FAIL")
    if st not in LOG_STATUSES:
        raise ValueError(f"Invalid status {status!r}; expected one of {LOG_STATUSES}")
    rec: dict[str, Any] = {
        "timestamp": utc_now(),
        "track": track.strip().upper() or "FLOW",
        "task": task.strip() or "-",
        "exit": int(exit_code),
        "status": st,
        "note": redact_secrets(note.strip()),
    }
    if strike > 0:
        rec["strike"] = int(strike)
    return append_jsonl(root / "_LOG.jsonl", rec)


def append_mem(root: Path, tag: str, rule: str) -> dict[str, Any]:
    t, r = tag.strip().lower(), redact_secrets(" ".join(rule.strip().split()))
    if not t or not r:
        raise ValueError("Both tag and rule are required.")
    return append_jsonl(root / "_MEM.jsonl", {"timestamp": utc_now(), "tag": t, "rule": r})


def query_ledger(root: Path, ledger: str = "mem", tag: str = "", keyword: str = "", limit: int = 10) -> list[dict[str, Any]]:
    rows = read_jsonl(root / ("_MEM.jsonl" if ledger.lower() == "mem" else "_LOG.jsonl"))
    tq, kq = tag.strip().lower(), keyword.strip().lower()
    out = [
        r for r in rows
        if (not tq or tq in str(r.get("tag") or r.get("track") or r.get("task") or "").lower())
        and (not kq or kq in json.dumps(r, ensure_ascii=False).lower())
    ]
    return out[-max(1, int(limit)) :]


def promote_gotchas(root: Path, min_occurrences: int = 2, max_rules: int = 15) -> list[str]:
    rows = read_jsonl(root / "_MEM.jsonl")
    counts = Counter(str(r.get("tag") or "").lower() for r in rows if r.get("tag") and r.get("rule"))
    hot_tags = {t for t, c in counts.items() if c >= min_occurrences}
    promoted: list[str] = []
    for r in rows:
        t = str(r.get("tag") or "").lower()
        item = f"[{t}] {str(r.get('rule') or '').strip()}"
        if t in hot_tags and item not in promoted:
            promoted.append(item)
    promoted = promoted[:max_rules]

    active = root / "_ACTIVE.md"
    if promoted and active.exists():
        txt = active.read_text(encoding="utf-8", errors="replace")
        line = "Rules: " + " | ".join(promoted)
        updated = re.sub(r"^Rules:\s*.*$", line, txt, count=1, flags=re.MULTILINE) if "Rules:" in txt else f"{txt.rstrip()}\n{line}\n"
        active.write_text(updated, encoding="utf-8")
    return promoted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="JSONL ledger & knowledge promotion tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("log")
    lg.add_argument("--track", default="FLOW")
    lg.add_argument("--task", required=True)
    lg.add_argument("--exit", type=int, default=0, dest="exit_code")
    lg.add_argument("--note", default="")
    lg.add_argument("--strike", type=int, default=0)
    lg.add_argument("--status", default="", choices=["", *LOG_STATUSES])
    lg.add_argument("--root", default=".")

    mm = sub.add_parser("mem")
    mm.add_argument("--tag", required=True)
    mm.add_argument("--rule", required=True)
    mm.add_argument("--root", default=".")

    qr = sub.add_parser("query")
    qr.add_argument("--ledger", choices=["mem", "log"], default="mem")
    qr.add_argument("--tag", default="")
    qr.add_argument("--kw", default="")
    qr.add_argument("--limit", type=int, default=10)
    qr.add_argument("--root", default=".")

    pr = sub.add_parser("promote")
    pr.add_argument("--min", type=int, default=2)
    pr.add_argument("--max-rules", type=int, default=15)
    pr.add_argument("--root", default=".")

    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if args.cmd == "log":
        print(json.dumps(append_log(root, args.task, args.exit_code, args.track, args.note, args.strike, args.status), ensure_ascii=False))
    elif args.cmd == "mem":
        print(json.dumps(append_mem(root, args.tag, args.rule), ensure_ascii=False))
    elif args.cmd == "query":
        for r in query_ledger(root, args.ledger, args.tag, args.kw, args.limit):
            print(json.dumps(r, ensure_ascii=False))
    elif args.cmd == "promote":
        for r in promote_gotchas(root, args.min, args.max_rules):
            print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
