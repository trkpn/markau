"""Compact polyglot Repo Map (optional Tree-sitter AST with zero-dependency Python AST & regex fallback)."""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._core import SKIP_DIRS

EXT_TO_TS_LANG: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
}

_TS_DEF_NODE_TYPES = {
    "class_definition",
    "function_definition",
    "async_function_definition",
    "class_declaration",
    "function_declaration",
    "method_definition",
    "interface_declaration",
    "type_alias_declaration",
    "struct_item",
    "enum_item",
    "impl_item",
    "trait_item",
    "function_item",
    "type_spec",
    "method_declaration",
}

_REGEX_PATTERNS: dict[str, re.Pattern[str]] = {
    "js_ts": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
        r"(?:(class|interface|type|function)\s+([A-Za-z_$][\w$]*)|(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>)"
    ),
    "go": re.compile(r"^\s*(?:(func)\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)|(type)\s+([A-Za-z_]\w*)\s+(?:struct|interface))"),
    "rust": re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(fn|struct|enum|trait|impl)\s+([A-Za-z_]\w*)"),
    "php": re.compile(r"^\s*(?:(?:public|protected|private|static|abstract|final)\s+)*(class|interface|trait|function)\s+([A-Za-z_]\w*)"),
    "c_java": re.compile(r"^\s*(?:public|private|protected|static|final|abstract\s+)*(class|interface|enum|struct)\s+([A-Za-z_]\w*)"),
}


def _extract_python_ast(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    syms: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("__")]
            suffix = f" ({', '.join(methods[:6])}{'...' if len(methods) > 6 else ''})" if methods else ""
            syms.append(f"class {node.name} L{node.lineno}{suffix}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            syms.append(f"def {node.name} L{node.lineno}")
    return syms


def _extract_tree_sitter(raw_bytes: bytes, lang: str) -> list[str] | None:
    try:
        tlp = importlib.import_module("tree_sitter_language_pack")
        parser = tlp.get_parser(lang)
    except Exception:
        return None
    try:
        tree = parser.parse(raw_bytes)
    except Exception:
        return None
    syms: list[str] = []

    def _walk(node: Any, depth: int = 0) -> None:
        if depth > 4 or len(syms) >= 30:
            return
        if node.type in _TS_DEF_NODE_TYPES:
            name_node = node.child_by_field_name("name")
            if name_node is None and node.type == "impl_item":
                name_node = node.child_by_field_name("type")
            if name_node is not None:
                name = raw_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="replace").strip()
                if name:
                    kind = node.type.split("_")[0]
                    syms.append(f"{kind} {name} L{node.start_point[0] + 1}")
        for child in node.children:
            _walk(child, depth + 1)

    _walk(tree.root_node)
    return syms


def _extract_regex(text: str, ext: str) -> list[str]:
    if ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        rx = _REGEX_PATTERNS["js_ts"]
    elif ext == ".go":
        rx = _REGEX_PATTERNS["go"]
    elif ext == ".rs":
        rx = _REGEX_PATTERNS["rust"]
    elif ext == ".php":
        rx = _REGEX_PATTERNS["php"]
    else:
        rx = _REGEX_PATTERNS["c_java"]
    syms: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = rx.match(line)
        if not m:
            continue
        groups = [g for g in m.groups() if g]
        if len(groups) >= 2:
            syms.append(f"{groups[0]} {groups[1]} L{lineno}")
        elif len(groups) == 1:
            syms.append(f"fn {groups[0]} L{lineno}")
        if len(syms) >= 30:
            break
    return syms


def extract_file_symbols(fp: Path) -> list[str]:
    ext = fp.suffix.lower()
    if ext not in EXT_TO_TS_LANG:
        return []
    try:
        if fp.stat().st_size > 400_000:
            return []
        raw = fp.read_bytes()
    except OSError:
        return []
    if ext == ".py":
        return _extract_python_ast(raw.decode("utf-8", errors="replace"))
    ts_syms = _extract_tree_sitter(raw, EXT_TO_TS_LANG[ext])
    if ts_syms is not None:
        return ts_syms
    return _extract_regex(raw.decode("utf-8", errors="replace"), ext)


def build_repo_map(
    root: Path,
    subpath: str = ".",
    max_files: int = 40,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Build a compact symbol outline across source files under root/subpath."""
    target = (root / subpath).resolve() if subpath and subpath != "." else root.resolve()
    if not target.exists():
        return {"ok": False, "error": f"Path not found: {subpath}", "entries": [], "text": ""}

    files: list[Path] = []
    if target.is_file():
        files = [target]
    else:
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                if p.suffix.lower() in EXT_TO_TS_LANG:
                    files.append(p)
                    if len(files) >= max_files * 3:
                        break
            if len(files) >= max_files * 3:
                break

    entries: list[dict[str, Any]] = []
    lines: list[str] = []
    total_chars = 0
    for fp in files:
        if len(entries) >= max_files:
            break
        syms = extract_file_symbols(fp)
        if not syms:
            continue
        try:
            rel = fp.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = fp.name
        row = f"{rel}: " + ", ".join(syms[:12]) + (f" (+{len(syms) - 12})" if len(syms) > 12 else "")
        if total_chars + len(row) + 1 > max_chars:
            lines.append("...(repo map truncated; pass a narrower path)")
            break
        entries.append({"path": rel, "symbols": syms})
        lines.append(row)
        total_chars += len(row) + 1

    text = "\n".join(lines) if lines else "(no source symbols found)"
    return {"ok": True, "file_count": len(entries), "entries": entries, "text": text}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compact polyglot Repo Map (Tree-sitter + stdlib fallback)")
    ap.add_argument("path", nargs="?", default=".", help="Relative directory or file to map")
    ap.add_argument("--root", default=".", help="Workspace root directory")
    ap.add_argument("--max-files", type=int, default=40)
    ap.add_argument("--max-chars", type=int, default=4000)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    res = build_repo_map(Path(args.root).resolve(), args.path, max_files=args.max_files, max_chars=args.max_chars)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if not res["ok"]:
            print(f"ERROR: {res['error']}")
            return 1
        print(res["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
