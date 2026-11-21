"""Deterministic Policy Engine: VERIFY gate, Blast-Radius guard, and Multi-Agent Hook adapter."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._core import (
    CORE_RW_FILES,
    RO_FILES,
    extract_task_contract,
    git_status_all,
    is_path_within_contract,
    parse_active,
)

SAFE_ENV_NAMES = {".env.example", ".env.sample", ".env.template"}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks")
SECRET_PREFIXES = ("id_rsa", "id_ed25519", "id_ecdsa")
ALWAYS_WRITABLE_ROOT = CORE_RW_FILES | {"AGENTS.md"}

SECRET_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openrouter_key", re.compile(r"\bsk-or-v1-[a-fA-F0-9]{32,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("tavily_key", re.compile(r"\btvly-[A-Za-z0-9_-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("stripe_live_key", re.compile(r"\bsk_live_[0-9A-Za-z]{20,}\b")),
)

_GENERIC_SECRET_ASSIGN_RE = re.compile(
    r"""(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|client[_-]?secret)\b"""
    r"""\s*[:=]\s*["']([^"'\s]{20,})["']"""
)
_PLACEHOLDER_MARKERS = (
    "your_",
    "your-",
    "example",
    "placeholder",
    "changeme",
    "replace_me",
    "dummy",
    "fake",
    "sample",
    "xxxx",
    "0000",
    "<",
    "${",
    "redacted",
)


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(value)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _is_placeholder_secret(value: str) -> bool:
    low = value.lower()
    if any(m in low for m in _PLACEHOLDER_MARKERS):
        return True
    if len(set(value)) <= 4:
        return True
    return False


def mask_secret_value(value: str) -> str:
    """Return a safe masked representation of a secret string."""
    s = value.strip()
    if len(s) <= 8:
        return "****"
    return f"{s[:4]}...{s[-4:]}"


def scan_text_for_secrets(text: str, source: str = "<text>") -> list[dict[str, Any]]:
    """Scan text for high-confidence secret leaks (zero-dependency)."""
    findings: list[dict[str, Any]] = []
    if not text:
        return findings
    for lineno, line in enumerate(text.splitlines(), start=1):
        matched_spans: list[tuple[int, int]] = []
        for rule_name, rx in SECRET_VALUE_PATTERNS:
            for m in rx.finditer(line):
                val = m.group(0)
                if _is_placeholder_secret(val):
                    continue
                matched_spans.append(m.span())
                findings.append(
                    {
                        "source": source,
                        "line": lineno,
                        "rule": rule_name,
                        "match": mask_secret_value(val),
                    }
                )
        for m in _GENERIC_SECRET_ASSIGN_RE.finditer(line):
            val = m.group(1)
            if any(a <= m.start(1) < b for a, b in matched_spans):
                continue
            if _is_placeholder_secret(val) or _shannon_entropy(val) < 3.6:
                continue
            findings.append(
                {
                    "source": source,
                    "line": lineno,
                    "rule": "generic_high_entropy_secret",
                    "match": mask_secret_value(val),
                }
            )
    return findings


def redact_secrets(text: str) -> str:
    """Redact known secret patterns before persisting text to ledgers."""
    if not text:
        return text
    out = text
    for _rule_name, rx in SECRET_VALUE_PATTERNS:
        out = rx.sub(lambda m: "[REDACTED]" if not _is_placeholder_secret(m.group(0)) else m.group(0), out)
    return out


def _run_gitleaks_scan(root: Path) -> tuple[bool, list[dict[str, Any]]]:
    """Run optional gitleaks on staged changes if installed in PATH."""
    gl = shutil.which("gitleaks")
    if not gl:
        return False, []
    try:
        proc = subprocess.run(
            [gl, "protect", "--staged", "--no-banner", "--redact", "--report-format", "json", "--report-path", "-"],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, []
    findings: list[dict[str, Any]] = []
    if proc.returncode == 1 and proc.stdout.strip():
        try:
            items = json.loads(proc.stdout)
            if isinstance(items, list):
                for item in items[:20]:
                    if isinstance(item, dict):
                        findings.append(
                            {
                                "source": str(item.get("File") or "<staged>"),
                                "line": int(item.get("StartLine") or 0),
                                "rule": f"gitleaks:{item.get('RuleID') or 'secret'}",
                                "match": mask_secret_value(str(item.get("Secret") or item.get("Match") or "****")),
                            }
                        )
        except json.JSONDecodeError:
            findings.append({"source": "<staged>", "line": 0, "rule": "gitleaks", "match": "****"})
    return True, findings


def scan_git_diff_secrets(root: Path) -> dict[str, Any]:
    """Scan added lines in git diff (working tree + staged) plus optional gitleaks."""
    findings: list[dict[str, Any]] = []
    for diff_args in (["git", "diff", "-U0", "--no-color"], ["git", "diff", "--cached", "-U0", "--no-color"]):
        try:
            proc = subprocess.run(
                diff_args,
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0 or not proc.stdout:
            continue
        cur_file = "<diff>"
        cur_line = 0
        for raw_ln in proc.stdout.splitlines():
            if raw_ln.startswith("+++ b/"):
                cur_file = raw_ln[6:].strip()
                continue
            if raw_ln.startswith("@@ "):
                m_hunk = re.search(r"\+(\d+)", raw_ln)
                cur_line = int(m_hunk.group(1)) if m_hunk else 0
                continue
            if raw_ln.startswith("+") and not raw_ln.startswith("+++"):
                if not cur_file.startswith(".harness/runtime/"):
                    for hit in scan_text_for_secrets(raw_ln[1:], source=cur_file):
                        hit["line"] = cur_line
                        findings.append(hit)
                cur_line += 1

    # Also scan untracked text files (small files only, skip secret/binary/runtime paths)
    for item in git_status_all(root):
        if item.get("code") != "??":
            continue
        rel = item["path"]
        if rel.startswith((".harness/runtime/", "graphify-out/")) or _is_secret_path(rel):
            continue
        fp = root / rel
        if not fp.is_file() or fp.stat().st_size > 256_000:
            continue
        try:
            raw_bytes = fp.read_bytes()
            if b"\x00" in raw_bytes[:1024]:
                continue
            txt = raw_bytes.decode("utf-8", errors="replace")
        except OSError:
            continue
        findings.extend(scan_text_for_secrets(txt, source=rel))

    used_gitleaks, gl_findings = _run_gitleaks_scan(root)
    findings.extend(gl_findings)

    # Deduplicate by (source, line, rule)
    seen: set[tuple[str, int, str]] = set()
    deduped: list[dict[str, Any]] = []
    for f in findings:
        key = (str(f["source"]), int(f["line"]), str(f["rule"]))
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return {"ok": not deduped, "gitleaks_used": used_gitleaks, "findings": deduped}
FLOW_RISK_SEGMENTS = ("migration", "migrations", "auth", "billing", "deploy", ".github/workflows")
FLOW_RISK_FILES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "uv.lock",
    "composer.json",
    "composer.lock",
    "cargo.toml",
    "go.mod",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "deploy.php",
    "deploy.yaml",
}


def _normalize_rel_path(root: Path, raw_path: str) -> str:
    """Normalize an absolute or relative path into a POSIX repo-relative path."""
    cleaned = raw_path.strip().strip('"').strip("'")
    if not cleaned:
        return ""
    p = Path(cleaned)
    try:
        if p.is_absolute():
            rel = p.resolve().relative_to(root.resolve()).as_posix()
        else:
            rel = cleaned.replace("\\", "/")
    except ValueError:
        rel = cleaned.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel.strip("/")


def is_secret_path(rel_path: str) -> bool:
    name = Path(rel_path).name
    lower = name.lower()
    if lower.startswith(".env") and lower not in SAFE_ENV_NAMES:
        return True
    if lower.endswith(SECRET_SUFFIXES) or lower.startswith(SECRET_PREFIXES):
        return True
    return False


_is_secret_path = is_secret_path


def _is_ro_harness_path(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/").strip("/")
    name = Path(norm).name
    if "/" not in norm and name in RO_FILES:
        return True
    if norm.startswith(".harness/"):
        if norm.startswith(".harness/baselines/") or norm.startswith(".harness/runtime/"):
            return False
        if norm.startswith(".harness/scripts/") or norm.endswith(".md"):
            return True
    return False


def _is_flow_risk_path(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/").strip("/").lower()
    parts = norm.split("/")
    name = parts[-1] if parts else ""
    if name in FLOW_RISK_FILES or name.startswith("dockerfile"):
        return True
    for seg in FLOW_RISK_SEGMENTS:
        if "/" in seg:
            if seg in norm:
                return True
        elif seg in parts:
            return True
    return False


def _has_opt_in_flow_pass(root: Path) -> bool:
    flow_file = root / ".harness" / "runtime" / "_FLOW.md"
    if not flow_file.is_file():
        return False
    txt = flow_file.read_text(encoding="utf-8", errors="replace")
    return "PASS" in txt


def _find_passing_snapshots(root: Path, task: str = "-") -> list[Path]:
    snap_candidates: list[Path] = []
    for sdir in (root / ".harness" / "runtime" / "snapshots", root / ".harness" / "snapshots"):
        if sdir.is_dir():
            snap_candidates.extend(sorted(sdir.glob("*.md")))
    snap_candidates.extend(sorted(root.glob("_SNAP_*.md")))
    tid = task.strip().split()[0] if task and task.strip() not in ("-", "?") else "-"
    matched = [p for p in snap_candidates if tid == "-" or tid.lower() in p.name.lower()]
    return [p for p in matched if "- Exit Code: 0" in p.read_text(encoding="utf-8", errors="replace")]


def _resolves_within_root(root: Path, raw_path: str) -> bool:
    """Return True iff raw_path resolves inside workspace root (blocks '..' and external absolute paths)."""
    cleaned = raw_path.strip().strip('"').strip("'")
    if not cleaned:
        return True
    p = Path(cleaned)
    try:
        resolved_root = root.resolve()
        resolved_target = (p if p.is_absolute() else (resolved_root / p)).resolve()
        resolved_target.relative_to(resolved_root)
        return True
    except (ValueError, OSError):
        return False


def check_pre_edit(root: Path, target_path: str) -> dict[str, Any]:
    """Evaluate PreToolUse / pre-edit policy for a single target file path."""
    rel = _normalize_rel_path(root, target_path)
    st = parse_active(root)
    state = st["State"].upper()

    if not rel:
        return {"decision": "allow", "ok": True, "path": "", "state": state, "reason": "No target path supplied"}

    if not _resolves_within_root(root, target_path):
        return {
            "decision": "deny",
            "ok": False,
            "path": rel,
            "state": state,
            "reason": f"Path Traversal (Art. I): {target_path} resolves outside workspace root",
        }

    if _is_secret_path(rel):
        return {
            "decision": "deny",
            "ok": False,
            "path": rel,
            "state": state,
            "reason": f"Secret Immunity (Art. I.7): cannot touch {rel}",
        }

    if _is_ro_harness_path(rel):
        return {
            "decision": "deny",
            "ok": False,
            "path": rel,
            "state": state,
            "reason": f"Immutability (Art. 0.1): {rel} is read-only",
        }

    # Always-writable governance state, baselines, runtime, and graphify cache
    if (
        rel in ALWAYS_WRITABLE_ROOT
        or rel.startswith(".harness/baselines/")
        or rel.startswith(".harness/runtime/")
        or rel.startswith("graphify-out/")
    ):
        return {"decision": "allow", "ok": True, "path": rel, "state": state, "reason": "ok"}

    if state == "BUILD":
        contract = extract_task_contract(root)
        if not is_path_within_contract(rel, contract["scope"], contract["targets"]):
            return {
                "decision": "deny",
                "ok": False,
                "path": rel,
                "state": state,
                "reason": (
                    f"Scope Guard (Art. II): {rel} is outside approved contract "
                    f"(scope={contract['scope']}, targets={contract['targets']})"
                ),
            }
        return {"decision": "allow", "ok": True, "path": rel, "state": state, "reason": "ok"}

    if state == "FLOW" or _has_opt_in_flow_pass(root):
        if _is_flow_risk_path(rel):
            return {
                "decision": "deny",
                "ok": False,
                "path": rel,
                "state": state,
                "reason": f"FLOW Risk Guard (Art. II.2): {rel} requires gated STAGE PLAN approval",
            }
        return {"decision": "allow", "ok": True, "path": rel, "state": state, "reason": "ok"}

    return {
        "decision": "deny",
        "ok": False,
        "path": rel,
        "state": state,
        "reason": f"Lock Gate (Art. II.1): source edit to {rel} denied while _ACTIVE.md is in {state} (requires BUILD or FLOW)",
    }


def check_stop_gate(root: Path) -> dict[str, Any]:
    """Evaluate Stop / PostInvocation DoD gate for active BUILD or FLOW tracks."""
    st = parse_active(root)
    state = st["State"].upper()
    opt_in_flow = _has_opt_in_flow_pass(root)
    active_build_or_flow = state in ("BUILD", "FLOW") or opt_in_flow

    if not active_build_or_flow:
        return {"decision": "allow", "ok": True, "state": state, "reason": "ok"}

    changed = [f["path"] for f in git_status_all(root)]
    source_edits = [
        f
        for f in changed
        if f not in ALWAYS_WRITABLE_ROOT
        and not f.startswith(".harness/runtime/")
        and not f.startswith("graphify-out/")
    ]
    if not source_edits:
        return {"decision": "allow", "ok": True, "state": state, "reason": "ok"}

    contract = extract_task_contract(root)
    task = contract["task"] if state == "BUILD" else "-"
    passing_snaps = _find_passing_snapshots(root, task=task)
    if not passing_snaps:
        return {
            "decision": "block",
            "ok": False,
            "state": state,
            "unverified_files": source_edits,
            "reason": (
                f"DoD Stop Gate (Art. IV): {len(source_edits)} unverified edit(s) in {state} "
                f"without a passing snapshot (Exit Code: 0) in .harness/runtime/snapshots/"
            ),
        }

    return {"decision": "allow", "ok": True, "state": state, "reason": "ok"}


def run_verify_guard(
    root: Path,
    task_id: str | None = None,
    require_snapshot: bool = False,
    require_cross_model: bool = False,
    scan_secrets: bool = True,
) -> dict[str, Any]:
    st = parse_active(root)
    contract = extract_task_contract(root, task_id=task_id)
    task = contract["task"]
    scope = contract["scope"]
    targets = contract["targets"]
    changed = [f["path"] for f in git_status_all(root)]

    out_of_scope: list[str] = []
    violations: list[str] = []

    for f in changed:
        if f.startswith("graphify-out/"):
            continue
        if _is_secret_path(f):
            violations.append(f"Secret file touched: {f}")
        if _is_ro_harness_path(f):
            violations.append(f"Read-Only file modified: {f}")
        if not is_path_within_contract(f, scope, targets):
            out_of_scope.append(f)
            violations.append(f"Out of Scope/Target (scope={scope}, targets={targets}): {f}")

    secret_findings: list[dict[str, Any]] = []
    if scan_secrets:
        sec_res = scan_git_diff_secrets(root)
        secret_findings = sec_res["findings"]
        for hit in secret_findings:
            violations.append(
                f"Secret leak detected ({hit['rule']}): {hit['source']}:{hit['line']} ({hit['match']})"
            )

    b, v = st["Builder"], st["Verifier"]
    cross_ok = b not in ("", "-") and v not in ("", "-") and b.lower() != v.lower()
    if require_cross_model and not cross_ok:
        violations.append(f"Cross-model required (Builder={b}, Verifier={v})")

    snap_candidates: list[Path] = []
    for sdir in (root / ".harness" / "runtime" / "snapshots", root / ".harness" / "snapshots"):
        if sdir.is_dir():
            snap_candidates.extend(sorted(sdir.glob("*.md")))
    snap_candidates.extend(sorted(root.glob("_SNAP_*.md")))
    snaps = [p for p in snap_candidates if task == "-" or task.lower() in p.name.lower()]
    if require_snapshot:
        if not snaps:
            violations.append(f"Missing snapshot in .harness/runtime/snapshots/ for {task}")
        elif any("- Exit Code: 0" not in p.read_text(encoding="utf-8", errors="replace") for p in snaps):
            violations.append("Snapshot has non-zero Exit Code")

    return {
        "ok": not violations,
        "state": st["State"],
        "task": task,
        "scope": scope,
        "cross_model": cross_ok,
        "targets": targets,
        "out_of_scope": out_of_scope,
        "secret_findings": secret_findings,
        "violations": violations,
    }


def extract_path_from_payload(payload: dict[str, Any]) -> str:
    """Extract a target file path from heterogeneous coding-agent hook JSON payloads."""
    candidate_keys = ("path", "file_path", "target_file", "TargetFile", "Path", "filename")
    for container in (payload, payload.get("tool_input"), payload.get("input"), payload.get("args")):
        if isinstance(container, dict):
            for key in candidate_keys:
                val = container.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    return ""


def format_hook_response(event: str, result: dict[str, Any], fmt: str) -> str:
    """Format normalized policy result into the requested host adapter contract."""
    decision = result.get("decision", "allow")
    reason = result.get("reason", "ok")

    if fmt == "claude":
        if event == "pre-edit":
            return json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow" if decision == "allow" else "deny",
                        "permissionDecisionReason": reason,
                    }
                },
                ensure_ascii=False,
            )
        if decision == "block":
            return json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False)
        return json.dumps({}, ensure_ascii=False)

    if fmt == "antigravity":
        if event == "pre-edit":
            return json.dumps({"decision": "allow" if decision == "allow" else "deny", "reason": reason}, ensure_ascii=False)
        if decision == "block":
            return json.dumps({"decision": "continue", "reason": reason}, ensure_ascii=False)
        return json.dumps({"decision": "allow", "reason": reason}, ensure_ascii=False)

    if fmt in ("json", "codex"):
        return json.dumps(result, ensure_ascii=False)

    tag = "ALLOW" if result.get("ok") else ("BLOCK" if decision == "block" else "DENY")
    return f"[GUARD:{event.upper()} {tag}] {reason}"


def _read_stdin_json() -> dict[str, Any]:
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic Policy Engine: VERIFY gate & Multi-Agent Hook guard")
    ap.add_argument("--event", choices=("verify", "pre-edit", "stop", "secrets"), default="verify")
    ap.add_argument("--path", default="", help="Target file path for --event pre-edit (else extracted from stdin JSON)")
    ap.add_argument(
        "--format",
        choices=("text", "json", "claude", "antigravity", "codex"),
        default="text",
        help="Output contract format for hook adapters",
    )
    ap.add_argument("--task", default=None)
    ap.add_argument("--require-snapshot", action="store_true")
    ap.add_argument("--require-cross-model", action="store_true")
    ap.add_argument("--no-secret-scan", action="store_true", help="Skip secret content scan during --event verify")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    out_fmt = "json" if (args.json and args.format == "text") else args.format

    if args.event == "pre-edit":
        target = args.path or extract_path_from_payload(_read_stdin_json())
        res = check_pre_edit(root, target)
        print(format_hook_response("pre-edit", res, out_fmt))
        return 0 if res["ok"] else 2

    if args.event == "stop":
        res = check_stop_gate(root)
        print(format_hook_response("stop", res, out_fmt))
        return 0 if res["ok"] else 2

    if args.event == "secrets":
        res = scan_git_diff_secrets(root)
        if out_fmt == "json":
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            gl_tag = " +gitleaks" if res["gitleaks_used"] else ""
            print(f"[GUARD:SECRETS {'PASS' if res['ok'] else 'FAIL'}{gl_tag}] Findings={len(res['findings'])}")
            for hit in res["findings"]:
                print(f"  - {hit['source']}:{hit['line']} [{hit['rule']}] {hit['match']}")
        return 0 if res["ok"] else 1

    res = run_verify_guard(
        root,
        args.task,
        args.require_snapshot,
        args.require_cross_model,
        scan_secrets=not args.no_secret_scan,
    )
    if out_fmt == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(
            f"[GUARD: {'PASS' if res['ok'] else 'FAIL'}] "
            f"Task={res['task']} Scope={res['scope']} Targets={res['targets']}"
        )
        for err in res["violations"]:
            print(f"  - {err}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
