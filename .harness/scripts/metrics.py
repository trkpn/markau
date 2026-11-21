"""SDLC & Token Economy telemetry reporter."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._core import read_jsonl


def compute_metrics(root: Path) -> dict[str, Any]:
    logs = read_jsonl(root / "_LOG.jsonl")
    mems = read_jsonl(root / "_MEM.jsonl")

    total = len(logs)
    passed = sum(1 for r in logs if int(r.get("exit", 0)) == 0)
    strikes = sum(1 for r in logs if int(r.get("strike") or 0) > 0 or int(r.get("exit", 0)) != 0)
    tracks = Counter(str(r.get("track") or "FLOW").upper() for r in logs)

    prompt_tok, cached_tok, comp_tok, sessions = 0, 0, 0, 0
    sdir = root / ".harness" / "runtime" / "sessions"
    if sdir.is_dir():
        for sf in sdir.glob("*.json"):
            try:
                d = json.loads(sf.read_text(encoding="utf-8"))
                sessions += 1
                prompt_tok += int(d.get("last_prompt_tokens") or 0)
                comp_tok += sum(int(m.get("tokens") or 0) for m in d.get("ui_messages") or [] if isinstance(m, dict))
            except Exception:
                pass

    bf = root / ".harness" / "runtime" / "oracle_thread.json"
    if bf.exists():
        try:
            bd = json.loads(bf.read_text(encoding="utf-8"))
            prompt_tok += int(bd.get("total_prompt_tokens") or 0)
            cached_tok += int(bd.get("total_cached_tokens") or 0)
        except Exception:
            pass

    return {
        "tasks_logged": total,
        "tasks_passed": passed,
        "first_pass_rate_pct": round((passed / total) * 100.0, 1) if total else 100.0,
        "rework_strike_rate_pct": round((strikes / total) * 100.0, 1) if total else 0.0,
        "tracks": dict(tracks),
        "mem_gotchas_total": len(mems),
        "sessions_total": sessions,
        "total_prompt_tokens": prompt_tok,
        "total_cached_tokens": cached_tok,
        "total_completion_tokens": comp_tok,
        "cache_hit_pct": round((cached_tok / prompt_tok) * 100.0, 1) if prompt_tok else 0.0,
    }


def format_metrics_markdown(m: dict[str, Any]) -> str:
    return (
        "# Project Metrics\n"
        f"- Logged Runs: {m['tasks_logged']} (Passed: {m['tasks_passed']})\n"
        f"- First-Pass Verify Rate: {m['first_pass_rate_pct']}%\n"
        f"- Rework / Strike Rate: {m['rework_strike_rate_pct']}%\n"
        f"- Prompt Tokens: {m['total_prompt_tokens']} (Cached: {m['total_cached_tokens']} · {m['cache_hit_pct']}%)\n"
        f"- Completion Tokens: {m['total_completion_tokens']}\n"
        f"- Gotchas Recorded: {m['mem_gotchas_total']}\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SDLC & token telemetry reporter")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)

    m = compute_metrics(Path(args.root).resolve())
    print(json.dumps(m, indent=2) if args.format == "json" else format_metrics_markdown(m), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
