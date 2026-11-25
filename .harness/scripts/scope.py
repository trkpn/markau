"""Workspace topology & scope automation (Single Repo, Monorepo, Polyglot Monorepo, Polyrepo).

Provides zero-token scope discovery, _ACTIVE.md Env synchronization, and 1-command
scoped verification (run verify -> log _LOG.jsonl -> capture .harness/runtime/snapshots/ -> check guard).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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


def _detect_package_manager(root: Path) -> str:
    if (root / "pnpm-workspace.yaml").is_file() or (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "bun.lock").is_file() or (root / "bun.lockb").is_file():
        return "bun"
    if (root / "yarn.lock").is_file():
        return "yarn"
    if (root / "package-lock.json").is_file() or (root / "package.json").is_file():
        return "npm"
    return ""


def _pm_exec_prefix(pm: str) -> str:
    if pm == "pnpm":
        return "pnpm"
    if pm == "bun":
        return "bunx"
    if pm == "yarn":
        return "yarn"
    return "npx"


def _detect_workspace_runners(root: Path) -> list[str]:
    runners: list[str] = []
    if (root / "turbo.json").is_file():
        runners.append("turbo")
    if (root / "nx.json").is_file():
        runners.append("nx")
    if _find_justfile(root) is not None:
        runners.append("just")
    if (root / "mise.toml").is_file() or (root / ".mise.toml").is_file():
        runners.append("mise")
    return runners


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk, returning {} on missing or invalid files."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


_SAFE_ARG_RE = re.compile(r"^[A-Za-z0-9@._/:+-]+$")
_UNSAFE_SHELL_CHARS = set("\n\r'\"`$;|&<>")


def _quote_shell_arg(val: str) -> str:
    """Return a shell-safe token (unquoted if strictly safe, single-quoted if spaced, empty if unsafe)."""
    s = val.strip()
    if not s or any(ch in _UNSAFE_SHELL_CHARS for ch in s):
        return ""
    return s if _SAFE_ARG_RE.match(s) else f"'{s}'"


def _glob_to_regex(pat: str, *, prefix_match: bool = False) -> re.Pattern[str]:
    parts = re.split(r"(\*\*/|\*\*|\*|\?)", pat.strip("/"))
    out = "".join(
        "(?:.+/)?" if p == "**/" else ".*" if p == "**" else "[^/]*" if p == "*" else "[^/]" if p == "?" else re.escape(p)
        for p in parts
    )
    tail = "(?:/.*)?$" if prefix_match else "$"
    return re.compile(f"^{out}{tail}")


def _read_turbo_tasks(root: Path) -> set[str]:
    data = _read_json(root / "turbo.json")
    tasks = data.get("tasks") or data.get("pipeline")
    return {str(k) for k in tasks} if isinstance(tasks, dict) else set()


def _pick_turbo_task(turbo_tasks: set[str] | None) -> str:
    if not turbo_tasks:
        return "test"
    return next((t for t in ("test", "check", "lint", "typecheck", "build") if t in turbo_tasks), "test")


def _read_workspace_globs(root: Path) -> tuple[list[str], list[str]]:
    includes: list[str] = []
    excludes: list[str] = []

    def _add_pat(raw_pat: str) -> None:
        pat = re.sub(r"\s+#.*$", "", raw_pat).strip().strip("'\"")
        is_neg = pat.startswith("!")
        if is_neg:
            pat = pat[1:].strip().strip("'\"")
        while pat.startswith("./"):
            pat = pat[2:]
        pat = pat.rstrip("/")
        if not pat or pat.startswith("/") or ".." in Path(pat).parts:
            return
        bucket = excludes if is_neg else includes
        if pat not in bucket:
            bucket.append(pat)

    pnpm_ws = root / "pnpm-workspace.yaml"
    if pnpm_ws.is_file():
        try:
            in_pkgs = False
            for raw in pnpm_ws.read_text(encoding="utf-8", errors="replace").splitlines():
                s = raw.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("packages:"):
                    rest = re.sub(r"\s+#.*$", "", s[len("packages:") :]).strip()
                    if rest.startswith("[") and rest.endswith("]"):
                        for item in rest[1:-1].split(","):
                            _add_pat(item)
                        in_pkgs = False
                    else:
                        in_pkgs = True
                    continue
                if in_pkgs:
                    if s.startswith("- "):
                        _add_pat(s[2:])
                    elif not raw[0].isspace():
                        in_pkgs = False
        except OSError:
            pass

    ws = _read_json(root / "package.json").get("workspaces")
    items = ws if isinstance(ws, list) else (ws.get("packages") if isinstance(ws, dict) else [])
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                _add_pat(item)
    return includes, excludes


def _expand_workspace_globs(root: Path, includes: list[str], excludes: list[str]) -> list[Path]:
    """Expand workspace include globs while pruning SKIP_DIRS (never walking node_modules) and applying ! exclusions."""
    if not includes:
        return []
    excl_res = [_glob_to_regex(pat, prefix_match=True) for pat in excludes]
    seen: set[Path] = set()
    results: list[Path] = []

    def _collect(candidate: Path) -> None:
        if not candidate.is_dir() or not (_has_manifest(candidate) or (candidate / ".git").exists()):
            return
        try:
            res = candidate.resolve()
            rel_parts = res.relative_to(root).parts
        except (ValueError, OSError):
            return
        if not rel_parts or any(part.startswith(".") or part in SKIP_DIRS for part in rel_parts):
            return
        rel = "/".join(rel_parts)
        if any(rx.match(rel) for rx in excl_res):
            return
        if res not in seen:
            seen.add(res)
            results.append(res)

    star_star_res = [_glob_to_regex(pat) for pat in includes if "**" in pat]
    for pat in includes:
        if "**" in pat:
            continue
        try:
            for match in sorted(root.glob(pat), key=lambda p: p.as_posix().lower()):
                _collect(match)
        except (OSError, ValueError, NotImplementedError):
            continue

    if star_star_res:
        for dirpath, dirnames, _ in os.walk(root):
            cur = Path(dirpath)
            rel_base = "" if cur == root else cur.relative_to(root).as_posix()
            dirnames[:] = sorted(
                (
                    d
                    for d in dirnames
                    if not d.startswith(".")
                    and d not in SKIP_DIRS
                    and not any(rx.match(f"{rel_base}/{d}" if rel_base else d) for rx in excl_res)
                ),
                key=str.lower,
            )
            if cur == root:
                continue
            if any(rx.match(rel_base) for rx in star_star_res):
                _collect(cur)

    return sorted(results, key=lambda p: p.relative_to(root).as_posix().lower())


def _read_just_recipes(just_path: Path) -> set[str]:
    recipes: set[str] = set()
    try:
        for line in just_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line[0].isspace() or line.lstrip().startswith("#"):
                continue
            if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:=", line):
                continue
            m = re.match(r"^@?([A-Za-z_][A-Za-z0-9_-]*)(?:\s+[^:#]*?)?\s*:(?!=)", line)
            if m:
                recipes.add(m.group(1))
    except OSError:
        pass
    return recipes


def _pick_js_script(pkg_path: Path) -> tuple[str, str]:
    pkg = _read_json(pkg_path)
    pkg_name = str(pkg.get("name") or "").strip()
    scripts = pkg.get("scripts")
    if isinstance(scripts, dict):
        for candidate in ("test", "check", "lint", "typecheck", "build"):
            if candidate in scripts and "no test specified" not in str(scripts[candidate]):
                return pkg_name, candidate
    return pkg_name, ""


def _resolve_js_verify_cmd(
    *,
    pm: str,
    runners: tuple[str, ...],
    is_root: bool,
    pkg_name: str,
    rel_path: str,
    dir_name: str,
    script_name: str,
    nx_name: str = "",
    has_pnpm_ws: bool = False,
    in_workspace: bool = True,
    turbo_tasks: set[str] | None = None,
) -> str:
    exec_pfx = _pm_exec_prefix(pm)
    filter_target = _quote_shell_arg(pkg_name) or _quote_shell_arg(f"./{rel_path}")
    if "turbo" in runners and (is_root or in_workspace) and (not turbo_tasks or script_name in turbo_tasks):
        if is_root:
            return f"{exec_pfx} turbo run {script_name}"
        if filter_target:
            return f"{exec_pfx} turbo run {script_name} --filter={filter_target}"
    if "nx" in runners and not is_root:
        nx_target = _quote_shell_arg(nx_name) or _quote_shell_arg(pkg_name) or _quote_shell_arg(dir_name)
        if nx_target:
            return f"{exec_pfx} nx {script_name} {nx_target}"
    if pm == "pnpm" and has_pnpm_ws and not is_root and in_workspace and filter_target:
        return f"pnpm --filter {filter_target} {script_name}"
    active_pm = pm if pm in ("pnpm", "bun", "yarn") else "npm"
    return f"{active_pm} test" if (script_name == "test" and active_pm != "bun") else f"{active_pm} run {script_name}"


def _find_justfile(d: Path) -> Path | None:
    return next((d / n for n in ("justfile", "Justfile") if (d / n).is_file()), None)


def _has_manifest(d: Path) -> bool:
    return (
        any((d / fname).exists() for fname, _, _ in MANIFEST_DETECTORS)
        or (d / "project.json").is_file()
        or _find_justfile(d) is not None
        or any(d.glob("*.rockspec"))
    )


def _detect_dir_stack(
    d: Path,
    *,
    is_root: bool = False,
    rel_path: str = ".",
    pm: str = "",
    runners: tuple[str, ...] = (),
    root_just_recipes: set[str] | None = None,
    has_pnpm_ws: bool = False,
    in_workspace: bool = True,
    turbo_tasks: set[str] | None = None,
) -> tuple[list[str], str]:
    stacks: list[str] = []
    verify_cmd = ""
    manifest_default_cmd = ""
    exec_pfx = _pm_exec_prefix(pm)

    for fname, stack_name, default_cmd in MANIFEST_DETECTORS:
        p = d / fname
        if not p.exists():
            continue
        if stack_name not in stacks:
            stacks.append(stack_name)
        if fname == "package.json":
            if not verify_cmd:
                pkg_name, script_name = _pick_js_script(p)
                if script_name:
                    nx_name = str(_read_json(d / "project.json").get("name") or "").strip() if "nx" in runners else ""
                    verify_cmd = _resolve_js_verify_cmd(
                        pm=pm,
                        runners=runners,
                        is_root=is_root,
                        pkg_name=pkg_name,
                        rel_path=rel_path,
                        dir_name=d.name,
                        script_name=script_name,
                        nx_name=nx_name,
                        has_pnpm_ws=has_pnpm_ws,
                        in_workspace=in_workspace,
                        turbo_tasks=turbo_tasks,
                    )
        elif not manifest_default_cmd:
            manifest_default_cmd = default_cmd

    if (d / "project.json").is_file() and "nx" in runners:
        if not stacks:
            stacks.append("node")
        if not verify_cmd:
            pj = _read_json(d / "project.json")
            pname = _quote_shell_arg(str(pj.get("name") or d.name))
            targets = pj.get("targets")
            if pname and isinstance(targets, dict):
                for cand in ("test", "check", "lint", "build"):
                    if cand in targets:
                        verify_cmd = f"{exec_pfx} nx {cand} {pname}"
                        break

    if not verify_cmd:
        local_jf = _find_justfile(d)
        if local_jf is not None:
            recipes = _read_just_recipes(local_jf)
            for cand in ("test", "check", "lint"):
                if cand in recipes:
                    verify_cmd = f"just {cand}"
                    break

    if not verify_cmd and not is_root and root_just_recipes:
        for cand in (f"test-{d.name}", f"check-{d.name}"):
            if cand in root_just_recipes:
                verify_cmd = f"just {cand}"
                break

    if not verify_cmd and is_root:
        if "turbo" in runners:
            verify_cmd = f"{exec_pfx} turbo run {_pick_turbo_task(turbo_tasks)}"
        elif "nx" in runners:
            verify_cmd = f"{exec_pfx} nx affected -t test"

    if not verify_cmd and manifest_default_cmd:
        verify_cmd = manifest_default_cmd

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
    """Scan workspace root (up to depth 2 + workspace globs) to classify repo topology and list scopes."""
    resolved = root.resolve()
    has_root_git = (resolved / ".git").exists()
    git_roots = discover_git_roots(resolved)
    pm = _detect_package_manager(resolved)
    runners = _detect_workspace_runners(resolved)
    runners_t = tuple(runners)
    has_pnpm_ws = (resolved / "pnpm-workspace.yaml").is_file()
    turbo_tasks = _read_turbo_tasks(resolved) if "turbo" in runners_t else set()
    root_just = _find_justfile(resolved)
    root_just_recipes = _read_just_recipes(root_just) if root_just else set()

    ws_includes, ws_excludes = _read_workspace_globs(resolved)
    ws_dirs = _expand_workspace_globs(resolved, ws_includes, ws_excludes)
    ws_set = set(ws_dirs)
    has_ws_globs = bool(ws_includes)

    scopes: list[dict[str, Any]] = []
    seen_scopes: set[str] = set()
    seen_resolved: set[Path] = {resolved}
    root_stacks, root_cmd = _detect_dir_stack(
        resolved,
        is_root=True,
        rel_path=".",
        pm=pm,
        runners=runners_t,
        root_just_recipes=root_just_recipes,
        has_pnpm_ws=has_pnpm_ws,
        turbo_tasks=turbo_tasks,
    )
    if root_stacks or has_root_git or runners:
        seen_scopes.add(".")
        scopes.append(
            {
                "scope": ".",
                "stacks": root_stacks or ["general"],
                "verify_cmd": root_cmd,
                "has_git": has_root_git,
            }
        )

    def _add_child_scope(child: Path) -> list[str]:
        child_res = child.resolve()
        rel = child.relative_to(resolved).as_posix()
        child_git = (child / ".git").exists()
        in_ws = (child_res in ws_set) if has_ws_globs else True
        stacks, vcmd = _detect_dir_stack(
            child,
            is_root=False,
            rel_path=rel,
            pm=pm,
            runners=runners_t,
            root_just_recipes=root_just_recipes,
            has_pnpm_ws=has_pnpm_ws,
            in_workspace=in_ws,
            turbo_tasks=turbo_tasks,
        )
        if rel not in seen_scopes and child_res not in seen_resolved and (child_git or stacks or vcmd):
            seen_scopes.add(rel)
            seen_resolved.add(child_res)
            scopes.append(
                {
                    "scope": rel,
                    "stacks": stacks or (["git-repo"] if child_git else ["general"]),
                    "verify_cmd": vcmd,
                    "has_git": child_git,
                }
            )
        return stacks

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
            child_git = (child / ".git").exists()
            has_manifest = _has_manifest(child)
            if not child_git and not has_manifest and parent_has_stack:
                if depth < 2:
                    _scan_children(child, depth + 1, parent_has_stack)
                continue
            stacks = _add_child_scope(child)
            if depth < 2 and not child_git:
                _scan_children(child, depth + 1, bool(stacks) or parent_has_stack)

    _scan_children(resolved, 1, bool(root_stacks))
    for match in ws_dirs:
        _add_child_scope(match)

    non_root_scopes = [s for s in scopes if s["scope"] != "."]
    all_stacks = sorted({st for s in scopes for st in s["stacks"] if st not in ("general", "git-repo")})

    if not has_root_git and len(git_roots) >= 1 and any(gr != resolved for gr in git_roots):
        topology = "polyrepo"
    elif len(non_root_scopes) >= 1:
        topology = "polyglot-monorepo" if len(all_stacks) > 1 else "monorepo"
    else:
        topology = "single-repo"

    affected_cmd = ""
    exec_pfx = _pm_exec_prefix(pm)
    if "turbo" in runners:
        affected_cmd = f"{exec_pfx} turbo run {_pick_turbo_task(turbo_tasks)} --filter='...[HEAD]'"
    elif "nx" in runners:
        affected_cmd = f"{exec_pfx} nx affected -t test"

    return {
        "root": str(resolved),
        "topology": topology,
        "runners": runners,
        "package_manager": pm,
        "affected_cmd": affected_cmd,
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


_ROOT_RUNNER_PREFIXES = (
    "turbo ",
    "pnpm turbo ",
    "pnpm exec turbo ",
    "pnpm dlx turbo ",
    "npx turbo ",
    "npm exec turbo ",
    "bunx turbo ",
    "bun run turbo ",
    "yarn turbo ",
    "nx ",
    "npx nx ",
    "pnpm nx ",
    "bunx nx ",
    "yarn nx ",
    "just ",
    "mise run ",
    "mise x ",
    "mise exec ",
    "pnpm --filter",
    "pnpm -r ",
    "npm --workspace",
    "yarn workspace",
    "cargo test -p",
    "cargo check -p",
)

_JUST_VALUE_FLAGS = {
    "-f",
    "--justfile",
    "-d",
    "--working-directory",
    "--color",
    "--dotenv-filename",
    "--dotenv-path",
    "--dump-format",
    "--shell",
}


def _is_root_runner_cmd(cmd: str) -> bool:
    stripped = cmd.strip()
    low = stripped.lower()
    if any(low.startswith(pfx) for pfx in _ROOT_RUNNER_PREFIXES):
        return True
    if low.startswith("pnpm ") and (
        " --filter" in low or " -r " in low or bool(re.search(r"(?:^|\s)-F(?:\s|=|$)", stripped))
    ):
        return True
    return low.startswith(("npm ", "yarn ")) and (" --workspace" in low or " -w " in low)


def _uses_local_just(cmd: str, scope_dir: Path, is_root_scope: bool, root: Path | None = None) -> bool:
    if is_root_scope:
        return False
    parts = cmd.strip().split()
    if len(parts) < 2 or parts[0].lower() != "just":
        return False
    local_jf = _find_justfile(scope_dir)
    if local_jf is None:
        return False
    if root is not None and _find_justfile(root) is None:
        return True
    skip = 0
    recipe = ""
    for tok in parts[1:]:
        if skip > 0:
            skip -= 1
            continue
        if tok == "--set":
            skip = 2
            continue
        if tok in _JUST_VALUE_FLAGS:
            skip = 1
            continue
        if tok.startswith("-"):
            continue
        recipe = tok
        break
    return bool(recipe) and recipe in _read_just_recipes(local_jf)


def _has_local_only_runner_config(cmd: str, root: Path, scope_dir: Path) -> bool:
    """Return True if a runner command targets a sub-scope that owns the runner config while root does not."""
    if scope_dir == root or not scope_dir.is_dir():
        return False
    low = cmd.strip().lower()
    if "turbo " in f" {low}" and (scope_dir / "turbo.json").is_file() and not (root / "turbo.json").is_file():
        return True
    if "nx " in f" {low}" and (scope_dir / "nx.json").is_file() and not (root / "nx.json").is_file():
        return True
    if low.startswith("cargo ") and (scope_dir / "Cargo.toml").is_file() and not (root / "Cargo.toml").is_file():
        return True
    if (
        low.startswith("mise ")
        and ((scope_dir / "mise.toml").is_file() or (scope_dir / ".mise.toml").is_file())
        and not ((root / "mise.toml").is_file() or (root / ".mise.toml").is_file())
    ):
        return True
    if (
        low.startswith(("pnpm ", "npm ", "yarn "))
        and ((scope_dir / "pnpm-workspace.yaml").is_file() or (scope_dir / "package.json").is_file())
        and not ((root / "pnpm-workspace.yaml").is_file() or (root / "package.json").is_file())
    ):
        return True
    return False


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

    scope_dir = (resolved / scope).resolve()
    try:
        scope_dir.relative_to(resolved)
    except ValueError:
        return {"ok": False, "error": f"Scope escapes workspace root: {scope}"}

    if (
        _is_root_runner_cmd(cmd)
        and not _uses_local_just(cmd, scope_dir, scope == ".", root=resolved)
        and not _has_local_only_runner_config(cmd, resolved, scope_dir)
    ):
        workdir = resolved
    else:
        workdir = scope_dir if scope_dir.is_dir() else resolved

    exit_code = 0
    output = ""
    if cmd:
        if os.name == "nt":
            pwsh = shutil.which("pwsh")
            if pwsh:
                shell_cmd = [pwsh, "-NoProfile", "-Command", cmd]
            elif "&&" in cmd or "||" in cmd:
                shell_cmd = ["cmd", "/c", cmd]
            else:
                shell_cmd = ["powershell", "-NoProfile", "-Command", cmd]
        else:
            shell_cmd = ["bash", "-lc", cmd]
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
            runners_str = f" | Runners: {', '.join(res['runners'])}" if res.get("runners") else ""
            print(f"Topology: {res['topology']}{runners_str} | Stacks: {', '.join(res['stacks']) or '-'}")
            if res.get("affected_cmd"):
                print(f"Affected: `{res['affected_cmd']}`")
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
