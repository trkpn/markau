"""Universal snapshot automation (.harness/runtime/snapshots/<TRACK>_<tag>.md).

Captures ground-truth git diff, _ACTIVE.md state, and verification evidence
without spending LLM tokens.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._core import git_diff_all, git_status_all, utc_now

SNAPSHOT_DIR = ".harness/runtime/snapshots"
SNAPSHOT_SUFFIX = ".md"


def _sanitize_token(value: str, upper: bool = False) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    if not cleaned:
        raise ValueError("Value must contain at least one alphanumeric character.")
    return cleaned.upper() if upper else cleaned


def _read_active_header(root: Path) -> str:
    active = root / "_ACTIVE.md"
    if not active.exists():
        return "(no _ACTIVE.md)"
    lines = active.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[:7]).strip() or "(empty _ACTIVE.md)"


def _seq_file(root: Path) -> Path:
    return root / SNAPSHOT_DIR / ".seq.json"


def _load_seq(root: Path) -> dict[str, int]:
    sf = _seq_file(root)
    if not sf.exists():
        return {}
    try:
        raw = json.loads(sf.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {str(k): int(v) for k, v in raw.items() if isinstance(v, int)}
    except Exception:
        pass
    return {}


def _next_snapshot_tag(root: Path, track: str) -> str:
    t = _sanitize_token(track, upper=True)
    seq = _load_seq(root)
    max_num = seq.get(t, 0)
    pat = re.compile(rf"^{re.escape(t)}_(\d+)\.md$")
    for p in list_snapshots(root, track=t):
        m = pat.match(p.name)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"{max_num + 1:02d}"


def _record_snapshot_seq(root: Path, track: str, tag: str) -> None:
    if not tag.isdigit():
        return
    t = _sanitize_token(track, upper=True)
    seq = _load_seq(root)
    num = int(tag)
    if num > seq.get(t, 0):
        seq[t] = num
        sf = _seq_file(root)
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps(seq, indent=2), encoding="utf-8")


def snapshot_path(root: Path, tag: str, track: str = "FLOW") -> Path:
    t = _sanitize_token(track, upper=True)
    g = _sanitize_token(tag, upper=False)
    return root / SNAPSHOT_DIR / f"{t}_{g}{SNAPSHOT_SUFFIX}"


def capture_snapshot(
    root: Path,
    tag: str | None = None,
    track: str = "FLOW",
    verify_cmd: str = "",
    exit_code: int | None = None,
    note: str = "",
) -> Path:
    """Write ground-truth git diff, _ACTIVE.md state, and verify evidence."""
    resolved_tag = tag if (tag and tag.strip()) else _next_snapshot_tag(root, track)
    target = snapshot_path(root, tag=resolved_tag, track=track)
    target.parent.mkdir(parents=True, exist_ok=True)
    ts = utc_now()
    st_items = git_status_all(root)
    status_out = "\n".join(f"{f['status']:>2} {f['path']}" for f in st_items) if st_items else "(clean)"
    diff_stat = git_diff_all(root, stat_only=True) or "(no unstaged diff)"
    active_header = _read_active_header(root)

    lines = [
        f"# {target.name}",
        f"- Timestamp: {ts}",
        f"- Track: {_sanitize_token(track, upper=True)}",
        f"- Tag: {tag}",
        f"- Verify Command: `{verify_cmd}`" if verify_cmd else "- Verify Command: (none)",
        f"- Exit Code: {exit_code}" if exit_code is not None else "- Exit Code: (n/a)",
    ]
    if note:
        lines.append(f"- Note: {note}")
    lines.extend([
        "",
        "## Active State",
        "```text",
        active_header,
        "```",
        "",
        "## Git Status",
        "```text",
        status_out,
        "```",
        "",
        "## Diff Stat",
        "```text",
        diff_stat,
        "```",
    ])

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _record_snapshot_seq(root, track, _sanitize_token(resolved_tag, upper=False))
    return target


def list_snapshots(root: Path, track: str | None = None) -> list[Path]:
    """Return sorted list of pending snapshots in .harness/runtime/snapshots/ (optionally filtered by track)."""
    sdir = root / SNAPSHOT_DIR
    if not sdir.is_dir():
        return []
    if track:
        t = _sanitize_token(track, upper=True)
        return sorted(sdir.glob(f"{t}_*{SNAPSHOT_SUFFIX}"))
    return sorted(sdir.glob(f"*{SNAPSHOT_SUFFIX}"))


def clean_snapshots(
    root: Path,
    tag: str | None = None,
    track: str | None = None,
    clean_all: bool = False,
) -> list[Path]:
    """Remove verified snapshots from .harness/runtime/snapshots/."""
    removed: list[Path] = []
    if clean_all or (track and not tag):
        for path in list_snapshots(root, track=None if clean_all else track):
            path.unlink(missing_ok=True)
            removed.append(path)
        return removed
    if tag:
        path = snapshot_path(root, tag=tag, track=track or "FLOW")
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Universal .harness/runtime/snapshots/<TRACK>_<tag>.md snapshot tool")
    sub = parser.add_subparsers(dest="action", required=True)

    cap = sub.add_parser("capture", help="Capture git, _ACTIVE.md, and verify evidence")
    cap.add_argument("--track", default="FLOW", help="Track name (e.g. FLOW, STAGE, BUILD)")
    cap.add_argument("--tag", default=None, help="Snapshot tag (auto-increments 01, 02... if omitted)")
    cap.add_argument("--cmd", default="", help="Verification command executed")
    cap.add_argument("--exit", type=int, default=None, dest="exit_code", help="Verification exit code")
    cap.add_argument("--note", default="", help="Optional 1-line note")
    cap.add_argument("--root", default=".", help="Repository root directory")

    ls = sub.add_parser("list", help="List pending snapshots in .harness/runtime/snapshots/")
    ls.add_argument("--track", default=None, help="Filter by track (e.g. FLOW, STAGE)")
    ls.add_argument("--root", default=".", help="Repository root directory")

    cln = sub.add_parser("clean", help="Remove verified snapshots from .harness/runtime/snapshots/")
    cln.add_argument("--track", default=None, help="Track to clean (e.g. FLOW, STAGE)")
    cln.add_argument("--tag", default=None, help="Specific tag to remove")
    cln.add_argument("--all", action="store_true", dest="clean_all", help="Remove all snapshot files")
    cln.add_argument("--root", default=".", help="Repository root directory")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.action == "capture":
        out = capture_snapshot(
            root,
            tag=args.tag,
            track=args.track,
            verify_cmd=args.cmd,
            exit_code=args.exit_code,
            note=args.note,
        )
        print(out.name)
        return 0
    if args.action == "list":
        for p in list_snapshots(root, track=args.track):
            print(p.name)
        return 0
    if args.action == "clean":
        removed = clean_snapshots(root, tag=args.tag, track=args.track, clean_all=args.clean_all)
        for p in removed:
            print(f"removed {p.name}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
