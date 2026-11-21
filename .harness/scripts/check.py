"""Fast single-file Post-Edit Instant Diagnostics (zero-dependency core + auto-detected linters)."""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

SKIP_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".jsonl",
    ".log",
    ".lock",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".csv",
}

SUPPORTED_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".json": "json",
    ".toml": "toml",
    ".go": "go",
    ".php": "php",
    ".sh": "shell",
    ".bash": "shell",
    ".ps1": "powershell",
}


def _run_checker(cmd: list[str], cwd: Path, timeout: int = 6) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0, ""
    combined = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return proc.returncode, combined


def _find_nearest_parent(start: Path, root: Path, filename: str) -> Path | None:
    cur = start.parent.resolve()
    root_res = root.resolve()
    while True:
        if (cur / filename).is_file():
            return cur
        if cur == root_res or cur.parent == cur:
            return None
        cur = cur.parent


def _find_local_bin(project_dir: Path, name: str) -> str | None:
    suffixes = (".cmd", ".exe", "") if os.name == "nt" else ("",)
    bin_dir = project_dir / "node_modules" / ".bin"
    if not bin_dir.is_dir():
        return None
    for suf in suffixes:
        cand = bin_dir / f"{name}{suf}"
        if cand.is_file():
            return str(cand)
    return None


def _check_python(root: Path, fp: Path, timeout: int) -> tuple[list[str], list[str]]:
    checkers: list[str] = ["python:ast"]
    errors: list[str] = []
    try:
        src = fp.read_text(encoding="utf-8", errors="replace")
        ast.parse(src, filename=str(fp))
    except SyntaxError as ex:
        line = ex.lineno or 0
        col = ex.offset or 0
        errors.append(f"SyntaxError:{line}:{col}: {ex.msg}")
        return checkers, errors

    ruff = shutil.which("ruff")
    if ruff:
        checkers.append("ruff")
        rc, out = _run_checker([ruff, "check", "--output-format", "concise", "--no-fix", str(fp)], root, timeout)
        if rc != 0 and out:
            for ln in out.splitlines():
                s = ln.strip()
                if s and not s.startswith(("Found ", "[*]")):
                    errors.append(s)

    ty_bin = shutil.which("ty")
    if ty_bin:
        checkers.append("ty")
        rc, out = _run_checker([ty_bin, "check", "--output-format", "concise", str(fp)], root, timeout)
        if rc != 0 and out:
            for ln in out.splitlines():
                s = ln.strip()
                if s and not s.startswith(("Found ", "INFO ")):
                    errors.append(s)

    return checkers, errors


def _check_js_ts(root: Path, fp: Path, ext: str, timeout: int) -> tuple[list[str], list[str]]:
    checkers: list[str] = []
    errors: list[str] = []

    biome = shutil.which("biome")
    if not biome:
        pkg_dir = _find_nearest_parent(fp, root, "package.json")
        if pkg_dir:
            biome = _find_local_bin(pkg_dir, "biome")
    if biome:
        checkers.append("biome")
        rc, out = _run_checker([biome, "check", "--colors=off", str(fp)], root, timeout)
        if rc != 0 and out:
            for ln in out.splitlines():
                s = ln.strip()
                if s and ("error" in s.lower() or ":" in s):
                    errors.append(s)

    if ext in (".js", ".mjs", ".cjs"):
        node = shutil.which("node")
        if node:
            checkers.append("node")
            rc, out = _run_checker([node, "--check", str(fp)], root, timeout)
            if rc != 0 and out:
                errors.extend(ln.strip() for ln in out.splitlines() if ln.strip())

    if ext in (".ts", ".tsx", ".mts", ".cts") and not errors:
        ts_dir = _find_nearest_parent(fp, root, "tsconfig.json")
        if ts_dir:
            tsc = _find_local_bin(ts_dir, "tsc")
            if tsc:
                checkers.append("tsc")
                rc, out = _run_checker([tsc, "--noEmit", "--pretty", "false"], ts_dir, timeout=max(timeout, 8))
                if rc != 0 and out:
                    target_name = fp.name.lower()
                    rel_posix = fp.resolve().relative_to(ts_dir.resolve()).as_posix().lower()
                    for ln in out.splitlines():
                        s = ln.strip()
                        low = s.lower().replace("\\", "/")
                        if s and (rel_posix in low or target_name in low):
                            errors.append(s)

    return checkers, errors


def _check_json(fp: Path) -> tuple[list[str], list[str]]:
    try:
        json.loads(fp.read_text(encoding="utf-8", errors="replace"))
        return ["json"], []
    except json.JSONDecodeError as ex:
        return ["json"], [f"JSONDecodeError:{ex.lineno}:{ex.colno}: {ex.msg}"]


def _check_toml(fp: Path) -> tuple[list[str], list[str]]:
    try:
        tomllib.loads(fp.read_text(encoding="utf-8", errors="replace"))
        return ["tomllib"], []
    except tomllib.TOMLDecodeError as ex:
        return ["tomllib"], [f"TOMLDecodeError: {ex}"]


def _check_go(root: Path, fp: Path, timeout: int) -> tuple[list[str], list[str]]:
    gofmt = shutil.which("gofmt")
    if not gofmt:
        return [], []
    rc, out = _run_checker([gofmt, "-e", str(fp)], root, timeout)
    if rc == 0:
        return ["gofmt"], []
    errs = [ln.strip() for ln in out.splitlines() if ln.strip() and fp.name in ln]
    return ["gofmt"], errs or [ln.strip() for ln in out.splitlines()[:5] if ln.strip()]


def _check_php(root: Path, fp: Path, timeout: int) -> tuple[list[str], list[str]]:
    php = shutil.which("php")
    if not php:
        return [], []
    rc, out = _run_checker([php, "-l", str(fp)], root, timeout)
    if rc == 0:
        return ["php"], []
    return ["php"], [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.startswith("Errors parsing")]


def _check_shell(root: Path, fp: Path, timeout: int) -> tuple[list[str], list[str]]:
    sc = shutil.which("shellcheck")
    if sc:
        rc, out = _run_checker([sc, "-f", "gcc", str(fp)], root, timeout)
        return ["shellcheck"], ([ln.strip() for ln in out.splitlines() if ln.strip()] if rc != 0 else [])
    bash = shutil.which("bash")
    if bash:
        rc, out = _run_checker([bash, "-n", str(fp)], root, timeout)
        return ["bash"], ([ln.strip() for ln in out.splitlines() if ln.strip()] if rc != 0 else [])
    return [], []


def _check_powershell(root: Path, fp: Path, timeout: int) -> tuple[list[str], list[str]]:
    ps = shutil.which("pwsh") or (shutil.which("powershell") if os.name == "nt" else None)
    if not ps:
        return [], []
    script = (
        "$t=$null;$e=$null;"
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{str(fp).replace(chr(39), chr(39)*2)}',[ref]$t,[ref]$e);"
        "if($e -and $e.Count -gt 0){foreach($x in $e){Write-Output \"$($x.Extent.StartLineNumber):$($x.Extent.StartColumnNumber): $($x.Message)\"};exit 1}"
    )
    rc, out = _run_checker([ps, "-NoProfile", "-Command", script], root, timeout)
    return ["powershell"], ([ln.strip() for ln in out.splitlines() if ln.strip()] if rc != 0 else [])


def check_file(root: Path, rel_path: str, timeout: int = 6, max_lines: int = 15) -> dict[str, Any]:
    """Run fast single-file diagnostics on a workspace file."""
    fp = (root / rel_path).resolve()
    if not fp.is_file():
        return {"ok": True, "skipped": True, "path": rel_path, "language": "", "checkers": [], "diagnostics": []}

    ext = fp.suffix.lower()
    if ext in SKIP_EXTENSIONS or ext not in SUPPORTED_LANGUAGES:
        return {"ok": True, "skipped": True, "path": rel_path, "language": "", "checkers": [], "diagnostics": []}

    lang = SUPPORTED_LANGUAGES[ext]
    if lang == "python":
        checkers, errors = _check_python(root, fp, timeout)
    elif lang in ("typescript", "javascript"):
        checkers, errors = _check_js_ts(root, fp, ext, timeout)
    elif lang == "json":
        checkers, errors = _check_json(fp)
    elif lang == "toml":
        checkers, errors = _check_toml(fp)
    elif lang == "go":
        checkers, errors = _check_go(root, fp, timeout)
    elif lang == "php":
        checkers, errors = _check_php(root, fp, timeout)
    elif lang == "shell":
        checkers, errors = _check_shell(root, fp, timeout)
    elif lang == "powershell":
        checkers, errors = _check_powershell(root, fp, timeout)
    else:
        checkers, errors = [], []

    capped = errors[: max(1, max_lines)]
    truncated = max(0, len(errors) - len(capped))
    return {
        "ok": not errors,
        "skipped": not checkers,
        "path": rel_path,
        "language": lang,
        "checkers": checkers,
        "diagnostics": capped,
        "truncated": truncated,
    }


def format_post_edit_diagnostics(root: Path, rel_path: str, timeout: int = 6, max_lines: int = 15) -> str:
    """Return a concise [Diagnostics] block if issues were found, else empty string."""
    res = check_file(root, rel_path, timeout=timeout, max_lines=max_lines)
    if res["ok"] or not res["diagnostics"]:
        return ""
    header = f"[Diagnostics ({', '.join(res['checkers'])})]"
    lines = [header, *res["diagnostics"]]
    if res.get("truncated", 0) > 0:
        lines.append(f"...(+{res['truncated']} more)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fast single-file Post-Edit Instant Diagnostics")
    ap.add_argument("path", help="Relative or absolute path to file")
    ap.add_argument("--root", default=".", help="Workspace root directory")
    ap.add_argument("--timeout", type=int, default=6)
    ap.add_argument("--max-lines", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    target = Path(args.path)
    try:
        rel = target.resolve().relative_to(root).as_posix() if target.is_absolute() else args.path.replace("\\", "/")
    except ValueError:
        rel = args.path.replace("\\", "/")

    res = check_file(root, rel, timeout=args.timeout, max_lines=args.max_lines)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        status = "SKIP" if res["skipped"] else ("PASS" if res["ok"] else "FAIL")
        print(f"[CHECK:{status}] {rel} ({res['language'] or 'unsupported'}; checkers={','.join(res['checkers']) or 'none'})")
        for ln in res["diagnostics"]:
            print(f"  {ln}")
        if res.get("truncated", 0) > 0:
            print(f"  ...(+{res['truncated']} more)")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
