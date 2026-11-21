"""Shared KISS/DRY helpers for automation scripts (Single Repo, Monorepo, Polyglot Monorepo, Polyrepo)."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TEMPLATES_DIR = REPO_ROOT / "templates"

RO_FILES = {
    "SYSTEM.md",
    "FLOW.md",
    "PLAN.md",
    "BUILD.md",
    "VERIFY.md",
    "ORACLE.md",
    "STAGE.md",
    "INTENT.md",
    "LAW.md",
    "MANIFEST.md",
}
CORE_RW_FILES = {
    "_ACTIVE.md",
    "_LOG.jsonl",
    "_MEM.jsonl",
}
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".harness",
    "dist",
    "build",
    ".next",
    "target",
    "vendor",
}


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_git(cwd: Path, *args: str, timeout: int = 5) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.rstrip(), (proc.stderr or "").strip()
    except Exception as ex:
        return 1, "", str(ex)


def discover_git_roots(root: Path) -> list[Path]:
    """Return [root] if root is a git repo, else 1st/2nd-level child git repos (Polyrepo / Virtual Monorepo)."""
    resolved = root.resolve()
    if (resolved / ".git").exists():
        return [resolved]
    found: list[Path] = []
    try:
        for child in sorted(resolved.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir() or child.name.startswith(".") or child.name in SKIP_DIRS:
                continue
            if (child / ".git").exists():
                found.append(child)
                continue
            for sub in sorted(child.iterdir(), key=lambda p: p.name.lower()):
                if sub.is_dir() and not sub.name.startswith(".") and sub.name not in SKIP_DIRS:
                    if (sub / ".git").exists():
                        found.append(sub)
    except OSError:
        pass
    return found


def git_status_all(root: Path) -> list[dict[str, str]]:
    """Aggregate git status --porcelain across Single Repo, Monorepo, or Polyrepo."""
    resolved = root.resolve()
    git_roots = discover_git_roots(resolved)
    files: list[dict[str, str]] = []
    for gr in git_roots:
        prefix = "" if gr == resolved else f"{gr.relative_to(resolved).as_posix()}/"
        rc, out, _ = run_git(gr, "status", "--porcelain", "-uall")
        if rc != 0:
            continue
        for ln in out.splitlines():
            if len(ln) >= 4:
                xy = ln[:2].strip() or ln[:2]
                rel = ln[3:].split(" -> ")[-1].strip().strip('"').replace("\\", "/")
                if rel:
                    files.append({"status": xy, "path": f"{prefix}{rel}"})
    return files


def _prefix_unified_diff(diff_text: str, prefix: str) -> str:
    if not prefix or not diff_text:
        return diff_text
    out: list[str] = []
    for ln in diff_text.splitlines():
        if ln.startswith("diff --git a/") and " b/" in ln:
            parts = ln.split(" b/", 1)
            a_part = "diff --git a/" + prefix + parts[0][len("diff --git a/") :]
            b_part = " b/" + prefix + parts[1]
            out.append(a_part + b_part)
        elif ln.startswith("--- a/"):
            out.append("--- a/" + prefix + ln[6:])
        elif ln.startswith("+++ b/"):
            out.append("+++ b/" + prefix + ln[6:])
        else:
            out.append(ln)
    return "\n".join(out)


def git_diff_all(root: Path, stat_only: bool = False) -> str:
    """Aggregate git diff across Single Repo, Monorepo, or Polyrepo."""
    resolved = root.resolve()
    git_roots = discover_git_roots(resolved)
    if not git_roots:
        return "(not a git repository)"
    chunks: list[str] = []
    for gr in git_roots:
        prefix = "" if gr == resolved else f"{gr.relative_to(resolved).as_posix()}/"
        args = ("diff", "--stat", "HEAD") if stat_only else ("diff", "HEAD")
        rc, out, _ = run_git(gr, *args)
        if rc != 0:
            args_fb = ("diff", "--stat") if stat_only else ("diff",)
            rc, out, _ = run_git(gr, *args_fb)
        if rc == 0 and out.strip():
            if stat_only and prefix:
                prefixed_lines = [f"[{prefix.rstrip('/')}] {ln}" for ln in out.strip().splitlines()]
                chunks.append("\n".join(prefixed_lines))
            else:
                chunks.append(_prefix_unified_diff(out.strip(), prefix))
    return "\n\n".join(chunks)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except json.JSONDecodeError:
                pass
    return rows


def append_jsonl(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    prefix = "\n" if (path.exists() and path.stat().st_size > 0 and not path.read_bytes().endswith(b"\n")) else ""
    with path.open("ab") as f:
        f.write(f"{prefix}{line}\n".encode())
    return record


def parse_active(root: Path) -> dict[str, str]:
    info = {
        "State": "IDLE",
        "Task": "-",
        "Planner": "-",
        "Builder": "-",
        "Verifier": "-",
        "Strike": "0",
        "Cursor": "-",
    }
    aliases = {
        "current state": "State",
        "task id": "Task",
        "iteration count": "Strike",
    }
    p = root / "_ACTIVE.md"
    if not p.exists():
        return info
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("#") and not re.match(r"^##\s*0\.\s*State\b", s, re.IGNORECASE):
            break
        if ":" in s:
            raw_k, raw_v = s.split(":", 1)
            k = re.sub(r"^[-*\s]+", "", raw_k).strip("*` ")
            v = re.split(r"\s+\*?\(", raw_v.strip(), maxsplit=1)[0].strip().strip("*` ")
            k_low = k.lower()
            if k_low == "planner / builder / verifier" and "/" in v:
                parts = [pt.strip().strip("*` ") for pt in v.split("/")]
                if len(parts) >= 3:
                    info["Planner"], info["Builder"], info["Verifier"] = parts[0], parts[1], parts[2]
                continue
            target_k = next((ik for ik in info if ik.lower() == k_low), None) or aliases.get(k_low)
            if target_k:
                info[target_k] = v
    return info


def extract_task_contract(root: Path, task_id: str | None = None) -> dict[str, Any]:
    """Extract active Task's Scope, Target paths, Symbols, Contract, Steps, and Verify Command from _ACTIVE.md."""
    st = parse_active(root)
    raw_task = (task_id if task_id is not None else st["Task"]).strip()
    tid = raw_task.split()[0] if raw_task and raw_task not in ("-", "?") else ""

    scope = "."
    targets: list[str] = []
    symbols = ""
    contract_text = ""
    command = ""
    steps: list[str] = []

    def _add_targets(raw_str: str) -> None:
        cleaned = re.sub(r"\([^)]*\)", "", raw_str)
        for tok in re.split(r"[,|;\s]+", cleaned):
            t = tok.strip("*`").replace("\\", "/").strip()
            if (
                t
                and not t.startswith("<")
                and t.upper() not in ("-", "NONE", "N/A", "CREATE:", "MODIFY:", "DELETE:")
                and t not in targets
            ):
                targets.append(t)

    p = root / "_ACTIVE.md"
    if p.exists():
        in_task = not bool(tid)
        active_field: str | None = None
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.startswith("## "):
                heading = s[3:].strip()
                if tid:
                    in_task = heading.upper().startswith(tid.upper()) or bool(
                        re.match(r"^1\.\s*Blueprint\b", heading, re.IGNORECASE)
                    )
                elif re.match(r"^(T\d+|S-\d+|[A-Z]{3,4}-\d+|1\.\s*Blueprint)\b", heading, re.IGNORECASE):
                    in_task = True
                else:
                    in_task = False
                active_field = None
                continue
            if not in_task:
                continue
            is_bullet = bool(re.match(r"^[-*]\s+", s))
            s_clean = re.sub(r"^[-*]\s*", "", s).replace("**", "")
            if re.match(r"^Scope\s*:(?!:)", s_clean, re.IGNORECASE):
                active_field = None
                val = s_clean.split(":", 1)[1].strip().strip("`").replace("\\", "/").strip("/")
                if val and val not in ("-", ".", "<scope>", "<dir>", "<dir or .>"):
                    scope = val
            elif re.match(r"^Target(?:\s+Files)?(?:\s*\([^)]*\))?\s*:(?!:)", s_clean, re.IGNORECASE):
                active_field = "targets"
                _add_targets(s_clean.split(":", 1)[1])
            elif active_field == "targets" and re.match(r"^`?(?:CREATE|MODIFY|DELETE)(?:/[A-Z]+)*`?\s*:", s_clean, re.IGNORECASE):
                _add_targets(s_clean.split(":", 1)[1])
            elif active_field == "targets" and is_bullet and s_clean and not re.match(
                r"^(?:Symbols?|Contract|Command|Verify|Steps|Slices|Intent|Objective|Order|Risks|Tests|Known Non-Goals|YAGNI)\b",
                s_clean,
                re.IGNORECASE,
            ):
                _add_targets(s_clean.split()[0])
            elif re.match(r"^Symbols?(?:\s*/\s*Anchors)?\s*:(?!:)", s_clean, re.IGNORECASE):
                active_field = "symbols"
                val = s_clean.split(":", 1)[1].strip().strip("`")
                if val and not val.startswith("<") and val != "-":
                    symbols = val
            elif re.match(r"^Contract(?:\s*&\s*Edge\s*Cases)?\s*:(?!:)", s_clean, re.IGNORECASE):
                active_field = "contract"
                val = s_clean.split(":", 1)[1].strip().strip("`")
                if val and not val.startswith("<") and val != "-":
                    contract_text = val
            elif re.match(r"^(?:Command|Verify(?: Commands)?|Verification Commands)\s*:(?!:)", s_clean, re.IGNORECASE):
                active_field = None
                raw_cmd = s_clean.split(":", 1)[1].strip()
                m_bt = re.match(r"^`([^`]+)`", raw_cmd)
                val = m_bt.group(1).strip() if m_bt else raw_cmd.strip("`")
                if val and not val.startswith("<") and val != "-":
                    command = val
            elif re.match(r"^(?:Steps|(?:Implementation\s+)?Slices)\s*:(?!:)", s_clean, re.IGNORECASE):
                active_field = "steps"
            elif re.match(r"^(?:Intent|Objective|Order|Risks|Tests|Known Non-Goals|YAGNI(?: Cuts)?)\s*:(?!:)", s_clean, re.IGNORECASE):
                active_field = None
            elif active_field == "steps" and re.match(r"^[-*]\s*(?:\[[ xX/?!-]\]\s+)?", s):
                step_body = re.sub(r"^[-*]\s*(?:\[[ xX/?!-]\]\s+)?", "", s).strip()
                if step_body and not step_body.startswith("<"):
                    steps.append(step_body)
            elif active_field == "contract" and s and not s.startswith("#"):
                contract_text = f"{contract_text}\n{s}".strip() if contract_text else s
            elif active_field == "symbols" and s and not s.startswith("#"):
                symbols = f"{symbols} {s}".strip() if symbols else s

    return {
        "state": st["State"],
        "task": tid or "-",
        "scope": scope,
        "targets": targets,
        "symbols": symbols,
        "contract": contract_text,
        "command": command,
        "steps": steps,
    }


def validate_task_spec(root: Path, task_id: str | None = None) -> dict[str, Any]:
    """Validate the 5-point measurable spec completeness for an active/pending task in _ACTIVE.md."""
    c = extract_task_contract(root, task_id=task_id)
    missing: list[str] = []
    concrete_targets = [t for t in c["targets"] if t not in ("", ".", "-", "*")]
    if not concrete_targets:
        missing.append("Target")
    if not c["symbols"]:
        missing.append("Symbols")
    if not c["contract"]:
        missing.append("Contract")
    if not c["steps"]:
        missing.append("Steps")
    if not c["command"]:
        missing.append("Command")
    return {"ok": len(missing) == 0, "missing": missing, "task": c["task"]}


def is_path_within_contract(
    rel_path: str,
    scope: str,
    targets: list[str],
    *,
    require_explicit: bool = False,
) -> bool:
    """Return True if rel_path is a core RW file or falls inside allowed Target / Scope."""
    norm = rel_path.replace("\\", "/").strip("/")
    name = Path(norm).name
    if name in CORE_RW_FILES or name.startswith("_SNAP_") or norm == ".harness" or norm.startswith(".harness/"):
        return True
    allowed_prefixes: list[str] = []
    for t in targets:
        clean_t = t.replace("\\", "/").strip("/")
        if clean_t in ("", ".", "*"):
            if require_explicit:
                continue
            return True
        allowed_prefixes.append(clean_t)
    if not allowed_prefixes and scope and scope not in (".", "-", "*"):
        allowed_prefixes.append(scope.replace("\\", "/").strip("/"))
    if not allowed_prefixes:
        return not require_explicit
    return any(norm == pref or norm.startswith(pref + "/") for pref in allowed_prefixes)
