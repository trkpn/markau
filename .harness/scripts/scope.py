"""Workspace topology & scope automation (Single Repo, Monorepo, Polyglot Monorepo, Polyrepo).

Provides zero-token scope discovery, _ACTIVE.md Env synchronization, and 1-command
scoped verification (run verify -> log _LOG.jsonl -> capture .harness/runtime/snapshots/ -> check guard).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._core import (
    SKIP_DIRS,
    discover_git_roots,
    extract_task_contract,
    is_path_within_contract,
)
from scripts.guard import run_verify_guard
from scripts.ledger import append_log
from scripts.snapshot import capture_snapshot

MANIFEST_DETECTORS: tuple[tuple[str, str, str], ...] = (
    ("pyproject.toml", "python", "pytest -q"),
    ("setup.py", "python", "pytest -q"),
    ("requirements.txt", "python", "pytest -q"),
    ("package.json", "node", "npm test"),
    ("Cargo.toml", "rust", "cargo test"),
    ("go.mod", "go", "go test ./..."),
    ("composer.json", "php", "vendor/bin/phpunit"),
    ("pom.xml", "java", "mvn test"),
    ("build.gradle", "java", "gradle test"),
    ("build.gradle.kts", "java", "gradle test"),
    ("mix.exs", "elixir", "mix test"),
    ("Gemfile", "ruby", "bundle exec rspec"),
    ("pubspec.yaml", "dart", "dart test"),
    ("CMakeLists.txt", "cpp", "ctest --output-on-failure"),
    ("build.zig", "zig", "zig build test"),
    ("build.zig.zon", "zig", "zig build test"),
    ("mojoproject.toml", "mojo", "mojo test"),
    (".busted", "lua", "busted"),
    (".luacheckrc", "lua", "luacheck ."),
)


def _has_manifest(d: Path) -> bool:
    return any((d / fname).exists() for fname, _, _ in MANIFEST_DETECTORS) or any(d.glob("*.rockspec"))


def _detect_dir_stack(d: Path) -> tuple[list[str], str]:
    stacks: list[str] = []
    verify_cmd = ""
    for fname, stack_name, default_cmd in MANIFEST_DETECTORS:
        p = d / fname
        if p.exists():
            if stack_name not in stacks:
                stacks.append(stack_name)
            if not verify_cmd:
                if fname == "package.json":
                    try:
                        pkg = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                        scripts = pkg.get("scripts") or {}
                        for candidate in ("test", "check", "lint", "typecheck", "build"):
                            if candidate in scripts and "no test specified" not in str(scripts[candidate]):
                                verify_cmd = "npm test" if candidate == "test" else f"npm run {candidate}"
                                break
                    except Exception:
                        pass
                else:
                    verify_cmd = default_cmd

    if any(d.glob("*.rockspec")):
        if "lua" not in stacks:
            stacks.append("lua")
        if not verify_cmd:
            verify_cmd = "luarocks test"

    if not stacks:
        try:
            py_files = [f for f in d.iterdir() if f.is_file() and f.suffix == ".py"]
            if not py_files and (d / "scripts").is_dir():
                py_files = [f for f in (d / "scripts").iterdir() if f.is_file() and f.suffix == ".py"]
            if py_files:
                stacks.append("python")
                for candidate_dir in (d / "tests", d, d / "scripts"):
                    if candidate_dir.is_dir():
                        if any(
                            f.name.startswith("test_") or f.name.endswith("_test.py")
                            for f in candidate_dir.iterdir()
                            if f.is_file() and f.suffix == ".py"
                        ):
                            verify_cmd = "pytest -q"
                            break
                        if (candidate_dir / "lint.py").is_file():
                            rel_lint = (candidate_dir / "lint.py").relative_to(d).as_posix()
                            verify_cmd = f"python {rel_lint}"
                            break
        except OSError:
            pass
    return stacks, verify_cmd


def discover_workspace(root: Path) -> dict[str, Any]:
    """Scan workspace root (up to depth 2) to classify repo topology and list scopes."""
    resolved = root.resolve()
    has_root_git = (resolved / ".git").exists()
    git_roots = discover_git_roots(resolved)

    scopes: list[dict[str, Any]] = []
    root_stacks, root_cmd = _detect_dir_stack(resolved)
    if root_stacks or has_root_git:
        scopes.append(
            {
                "scope": ".",
                "stacks": root_stacks or ["general"],
                "verify_cmd": root_cmd,
                "has_git": has_root_git,
            }
        )

    def _scan_children(base: Path, depth: int, parent_has_stack: bool) -> None:
        if depth > 2:
            return
        try:
            entries = sorted(base.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for child in entries:
            if not child.is_dir() or child.name.startswith(".") or child.name in SKIP_DIRS:
                continue
            rel = child.relative_to(resolved).as_posix()
            child_git = (child / ".git").exists()
            has_manifest = _has_manifest(child)
            if not child_git and not has_manifest and parent_has_stack:
                if depth < 2:
                    _scan_children(child, depth + 1, parent_has_stack)
                continue
            stacks, vcmd = _detect_dir_stack(child)
            if child_git or stacks:
                scopes.append(
                    {
                        "scope": rel,
                        "stacks": stacks or (["git-repo"] if child_git else []),
                        "verify_cmd": vcmd,
                        "has_git": child_git,
                    }
                )
            if depth < 2 and not child_git:
                _scan_children(child, depth + 1, bool(stacks) or parent_has_stack)

    _scan_children(resolved, 1, bool(root_stacks))

    non_root_scopes = [s for s in scopes if s["scope"] != "."]
    all_stacks = sorted({st for s in scopes for st in s["stacks"] if st not in ("general", "git-repo")})

    if not has_root_git and len(git_roots) >= 1 and any(gr != resolved for gr in git_roots):
        topology = "polyrepo"
    elif len(non_root_scopes) >= 1:
        topology = "polyglot-monorepo" if len(all_stacks) > 1 else "monorepo"
    else:
        topology = "single-repo"

    return {
        "root": str(resolved),
        "topology": topology,
        "git_roots": [gr.relative_to(resolved).as_posix() if gr != resolved else "." for gr in git_roots],
        "stacks": all_stacks,
        "scopes": scopes,
    }


def sync_active_env(root: Path) -> dict[str, Any]:
    """Probe workspace topology & scopes and write a concise Env summary into _ACTIVE.md."""
    info = discover_workspace(root)
    os_name = "Windows/PowerShell" if os.name == "nt" else f"{sys.platform}/bash"
    scope_parts = [
        f"{s['scope']} ({'/'.join(s['stacks'])}" + (f": `{s['verify_cmd']}`)" if s["verify_cmd"] else ")")
        for s in info["scopes"][:8]
    ]
    env_line = f"Env: {os_name} | Topology: {info['topology']} | Scopes: {', '.join(scope_parts) or '.'}"

    active = root / "_ACTIVE.md"
    if active.exists():
        txt = active.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^Env:\s*.*$", txt, flags=re.MULTILINE):
            updated = re.sub(r"^Env:\s*.*$", lambda _: env_line, txt, count=1, flags=re.MULTILINE)
        else:
            updated = f"{txt.rstrip()}\n{env_line}\n"
        active.write_text(updated, encoding="utf-8")
    return {"env_line": env_line, **info}


def run_scoped_verify(
    root: Path,
    task_id: str | None = None,
    scope_override: str | None = None,
    cmd_override: str | None = None,
    track: str = "FLOW",
    timeout: int = 120,
) -> dict[str, Any]:
    """Execute verification in the target Scope directory, log to _LOG.jsonl, capture snapshot, and check guard."""
    resolved = root.resolve()
    contract = extract_task_contract(resolved, task_id=task_id)
    task = contract["task"]
    scope = (scope_override or contract["scope"] or ".").replace("\\", "/").strip("/") or "."
    cmd = (cmd_override or contract["command"] or "").strip()

    if not cmd:
        disc = discover_workspace(resolved)
        for s in disc["scopes"]:
            if s["scope"] == scope and s["verify_cmd"]:
                cmd = s["verify_cmd"]
                break
        if not cmd and disc["scopes"]:
            cmd = disc["scopes"][0].get("verify_cmd") or ""

    workdir = (resolved / scope).resolve()
    try:
        workdir.relative_to(resolved)
    except ValueError:
        return {"ok": False, "error": f"Scope escapes workspace root: {scope}"}
    if not workdir.exists() or not workdir.is_dir():
        workdir = resolved

    exit_code = 0
    output = ""
    if cmd:
        shell_cmd = ["powershell", "-NoProfile", "-Command", cmd] if os.name == "nt" else ["bash", "-lc", cmd]
        try:
            proc = subprocess.run(
                shell_cmd,
                cwd=str(workdir),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            exit_code = proc.returncode
            output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        except subprocess.TimeoutExpired:
            exit_code = 124
            output = f"Verify command timed out after {timeout}s: {cmd}"
        except Exception as ex:
            exit_code = 1
            output = str(ex)

    tag = task if task and task != "-" else "verify"
    snap_path = capture_snapshot(
        resolved,
        tag=tag,
        track=track,
        verify_cmd=f"[{scope}] {cmd}" if cmd else f"[{scope}] (guard-only)",
        exit_code=exit_code,
    )
    guard_res = run_verify_guard(resolved, task_id=task if task != "-" else None)
    overall_ok = (exit_code == 0) and bool(guard_res["ok"])

    append_log(
        resolved,
        task=tag,
        exit_code=exit_code if overall_ok else (exit_code or 1),
        track=track,
        note=f"scope={scope} cmd={cmd or 'guard'} snap={snap_path.name}",
    )

    return {
        "ok": overall_ok,
        "task": tag,
        "scope": scope,
        "command": cmd,
        "exit_code": exit_code,
        "output": output[:2000],
        "snapshot": snap_path.name,
        "guard": guard_res,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Workspace topology, scope discovery & scoped verification tool")
    sub = ap.add_subparsers(dest="action", required=True)

    disc = sub.add_parser("discover", help="Detect topology (single-repo, monorepo, polyglot-monorepo, polyrepo) and scopes")
    disc.add_argument("--sync", action="store_true", help="Write detected Env line into _ACTIVE.md")
    disc.add_argument("--json", action="store_true")
    disc.add_argument("--root", default=".")

    chk = sub.add_parser("check", help="Check if a file path is permitted by active Task Scope/Target")
    chk.add_argument("path", help="Relative file path to check")
    chk.add_argument("--task", default=None)
    chk.add_argument("--root", default=".")

    ver = sub.add_parser("verify", help="Run scoped verify command + guard + log + snapshot in one step")
    ver.add_argument("--task", default=None)
    ver.add_argument("--scope", default=None)
    ver.add_argument("--cmd", default=None)
    ver.add_argument("--track", default="FLOW")
    ver.add_argument("--json", action="store_true")
    ver.add_argument("--root", default=".")

    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    if args.action == "discover":
        res = sync_active_env(root) if args.sync else discover_workspace(root)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"Topology: {res['topology']} | Stacks: {', '.join(res['stacks']) or '-'}")
            for s in res["scopes"]:
                v = f" -> `{s['verify_cmd']}`" if s["verify_cmd"] else ""
                g = " [git]" if s["has_git"] else ""
                print(f"  - {s['scope']} ({', '.join(s['stacks'])}){g}{v}")
        return 0

    if args.action == "check":
        c = extract_task_contract(root, task_id=args.task)
        allowed = is_path_within_contract(args.path, c["scope"], c["targets"])
        status = "ALLOW" if allowed else "BLOCK"
        print(f"[{status}] path={args.path} (Task={c['task']} Scope={c['scope']} Targets={c['targets']})")
        return 0 if allowed else 1

    if args.action == "verify":
        res = run_scoped_verify(root, task_id=args.task, scope_override=args.scope, cmd_override=args.cmd, track=args.track)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(
                f"[VERIFY: {'PASS' if res['ok'] else 'FAIL'}] "
                f"Task={res['task']} Scope={res['scope']} Exit={res['exit_code']} Snap={res['snapshot']}"
            )
            if res["output"]:
                print(res["output"])
            for v in res["guard"]["violations"]:
                print(f"  - Guard Violation: {v}")
        return 0 if res["ok"] else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
