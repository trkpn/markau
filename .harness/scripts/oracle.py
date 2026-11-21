"""Semantic, reversible AST/tree-sitter anonymizer & Oracle context engine.

Replaces manual LLM-driven BLIND.md drafting with deterministic, zero-token:
- Smart slicing (AST / tree-sitter function or class boundaries)
- Reversible symbol & file aliasing (preserving stdlib & third-party APIs)
- Secret / URL / IP / path sanitization & leak checking
- Auto-fulfillment of Cloud Oracle `Need:` requests
- Deterministic de-aliasing of Oracle responses back to real workspace names
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _core import SKIP_DIRS, append_jsonl, run_git, utc_now  # noqa: E402

ORACLE_THREAD_FILE = ".harness/runtime/oracle_thread.json"
ORACLE_DIR = ".harness/runtime/oracle"
ORACLE_INDEX_FILE = ".harness/runtime/oracle/index.jsonl"

EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".php": "php",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".sql": "sql",
}

COMMON_BUILTINS: set[str] = {
    # Python
    "True", "False", "None", "self", "cls", "super", "len", "str", "int", "float",
    "bool", "list", "dict", "set", "tuple", "range", "enumerate", "zip", "map",
    "filter", "sorted", "reversed", "any", "all", "min", "max", "sum", "abs",
    "round", "print", "open", "isinstance", "issubclass", "hasattr", "getattr",
    "setattr", "delattr", "type", "object", "Exception", "ValueError", "TypeError",
    "KeyError", "RuntimeError", "OSError", "IOError", "AttributeError", "IndexError",
    "ImportError", "StopIteration", "NotImplementedError", "Path", "Any", "Optional",
    # JS / TS
    "console", "window", "document", "globalThis", "process", "Buffer", "Promise",
    "Array", "Object", "String", "Number", "Boolean", "Map", "Set", "Date", "Error",
    "JSON", "Math", "RegExp", "fetch", "setTimeout", "clearTimeout", "setInterval",
    "require", "module", "exports", "default", "async", "await", "undefined", "null",
    "this", "props", "state", "useState", "useEffect", "useRef", "useMemo", "useCallback",
    # PHP / Laravel / Go / Rust / Java / Common
    "echo", "array", "count", "empty", "isset", "unset", "die", "exit", "var_dump",
    "__construct", "__destruct", "__invoke", "__toString", "__get", "__set", "__call",
    "handle", "casts", "fillable", "guarded", "hidden", "table", "rules", "authorize",
    "up", "down", "boot", "register", "event", "events", "payload", "timestamps",
    "fmt", "err", "nil", "error", "ctx", "context", "make", "append", "copy", "panic",
    "recover", "Ok", "Err", "Some", "Vec", "Option", "Result", "String", "println",
    "System", "Override", "main", "args", "req", "res", "next", "app", "db", "id",
    "key", "val", "value", "item", "items", "data", "result", "response", "request",
    "status", "code", "msg", "message", "name", "path", "file", "line", "lines",
    "index", "idx", "count", "total", "config", "cfg", "opts", "options", "params",
    "i", "j", "k", "x", "y", "n", "e", "ex", "v", "fn", "cb", "ok",
}

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:AKIA|ASIA|AROA|AIDA)[0-9A-Z]{16}\b"),
    re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s:@/'\"`<>()]+:([^\s@/'\"`<>()]+)@"),
    re.compile(r"-----BEGIN [A-Z0-9 ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]+ PRIVATE KEY-----"),
)

ABS_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![A-Za-z0-9_:])[A-Za-z]:(?:\\|/)[^\s'\"`<>()]+"),
    re.compile(r"(?<![A-Za-z0-9_:/])/(?:Users|home|var|etc|opt|srv|mnt|tmp)/[^\s'\"`<>()]+"),
    re.compile(r"(?:\.\.(?:/|\\))+[A-Za-z0-9_.-]+(?:(?:/|\\)[A-Za-z0-9_.-]+)*"),
)

URL_RE = re.compile(r"https?://[^\s'\"`<>()]+")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
SAFE_IPS = {"127.0.0.1", "0.0.0.0", "255.255.255.255"}

_TS_CACHE: dict[str, Any] = {}


def _get_ts_parser(lang: str) -> Any | None:
    """Return a cached tree-sitter Parser if available, else None (never raises)."""
    if lang in _TS_CACHE:
        return _TS_CACHE[lang]
    try:
        tlp = importlib.import_module("tree_sitter_language_pack")

        parser = tlp.get_parser(lang)
        _TS_CACHE[lang] = parser
        return parser
    except Exception:
        _TS_CACHE[lang] = None
        return None


def max_backtick_run(text: str) -> int:
    runs = re.findall(r"`+", text)
    return max((len(r) for r in runs), default=0)


def safe_fence(text: str, lang: str = "") -> str:
    ticks = "`" * max(4, max_backtick_run(text) + 1)
    body = text.rstrip("\n")
    return f"{ticks}{lang}\n{body}\n{ticks}"


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def extract_slice(
    file_path: Path,
    *,
    line: int | None = None,
    symbol: str | None = None,
    max_lines: int = 60,
) -> tuple[int, int, str]:
    """Extract a smart code slice (1-based start_line, end_line, text) using AST/tree-sitter or window."""
    lines = _read_lines(file_path)
    total = len(lines)
    if total == 0:
        return 1, 1, ""

    ext = file_path.suffix.lower()
    lang = EXT_TO_LANG.get(ext, "")

    # 1. Try Python AST for .py files
    if lang == "python":
        src = "\n".join(lines)
        try:
            tree = ast.parse(src)
            best: tuple[int, int] | None = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    s = getattr(node, "lineno", 1)
                    e = getattr(node, "end_lineno", s) or s
                    if symbol and node.name == symbol:
                        best = (s, min(e, s + max_lines - 1))
                        break
                    if line is not None and s <= line <= e:
                        span = e - s + 1
                        if span <= max_lines and (best is None or span < (best[1] - best[0] + 1)):
                            best = (s, e)
            if best:
                s, e = best
                return s, e, "\n".join(lines[s - 1 : e])
        except SyntaxError:
            pass

    # 2. Try tree-sitter for symbol or enclosing block
    if lang and (symbol or line is not None):
        parser = _get_ts_parser(lang)
        if parser is not None:
            raw = "\n".join(lines).encode("utf-8", errors="replace")
            tree = parser.parse(raw)
            best_ts: tuple[int, int] | None = None
            target_types = {
                "function_definition", "function_declaration", "function_item", "fn_item",
                "method_definition", "method_declaration",
                "class_definition", "class_declaration",
                "interface_declaration", "trait_item",
                "struct_item", "enum_item", "enum_declaration",
                "type_declaration", "type_spec", "impl_item",
            }
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                if node.type in target_types:
                    s = node.start_point[0] + 1
                    e = node.end_point[0] + 1
                    node_text = raw[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
                    if symbol and re.search(rf"\b{re.escape(symbol)}\b", node_text.splitlines()[0]):
                        best_ts = (s, min(e, s + max_lines - 1))
                        break
                    if line is not None and s <= line <= e:
                        span = e - s + 1
                        if span <= max_lines and (best_ts is None or span < (best_ts[1] - best_ts[0] + 1)):
                            best_ts = (s, e)
                stack.extend(node.children)
            if best_ts:
                s, e = best_ts
                return s, e, "\n".join(lines[s - 1 : e])

    # 3. Fallback: symbol regex search or centered line window
    if symbol:
        pat = re.compile(rf"\b{re.escape(symbol)}\b")
        for idx, text_line in enumerate(lines, start=1):
            if pat.search(text_line):
                line = idx
                break

    if line is not None:
        half = max_lines // 2
        s = max(1, line - half)
        e = min(total, s + max_lines - 1)
        s = max(1, e - max_lines + 1)
        return s, e, "\n".join(lines[s - 1 : e])

    e = min(total, max_lines)
    return 1, e, "\n".join(lines[:e])


def _collect_python_symbols(src: str) -> dict[str, str]:
    """Collect declared private symbols from Python source via ast (returns name -> kind)."""
    found: dict[str, str] = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return found

    imported_external: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_external.add((alias.asname or alias.name.split(".")[0]).strip())
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                for alias in node.names:
                    imported_external.add((alias.asname or alias.name).strip())

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            found[node.name] = "class"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (node.name.startswith("__") and node.name.endswith("__")):
                found[node.name] = "fn"
            for arg in list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs):
                if arg.arg not in ("self", "cls"):
                    found.setdefault(arg.arg, "var")
            if node.args.vararg:
                found.setdefault(node.args.vararg.arg, "var")
            if node.args.kwarg:
                found.setdefault(node.args.kwarg.arg, "var")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            found.setdefault(node.id, "var")
        elif isinstance(node, ast.ExceptHandler) and node.name:
            found.setdefault(node.name, "var")

    return {
        k: v
        for k, v in found.items()
        if k not in COMMON_BUILTINS and k not in imported_external and len(k) >= 2
    }


def _collect_ts_symbols(src: str, lang: str) -> dict[str, str]:
    """Collect declared symbols using tree-sitter when available."""
    parser = _get_ts_parser(lang)
    if parser is None:
        return {}
    raw = src.encode("utf-8", errors="replace")
    tree = parser.parse(raw)
    found: dict[str, str] = {}

    def _node_text(n: Any) -> str:
        return raw[n.start_byte : n.end_byte].decode("utf-8", errors="replace")

    class_nodes = {
        "class_declaration", "class_definition", "interface_declaration",
        "struct_item", "trait_item", "enum_item", "enum_declaration",
        "type_alias_declaration", "type_spec",
    }
    fn_nodes = {
        "function_declaration", "function_definition", "function_item", "fn_item",
        "method_definition", "method_declaration",
    }
    var_nodes = {
        "variable_declarator", "parameter", "parameter_declaration",
        "required_parameter", "optional_parameter", "formal_parameters",
        "var_spec", "short_var_declaration",
    }
    id_types = ("identifier", "type_identifier", "field_identifier", "property_identifier", "name", "variable_name")

    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        ntype = node.type
        if ntype in class_nodes or ntype in fn_nodes or ntype in var_nodes:
            kind = "class" if ntype in class_nodes else ("fn" if ntype in fn_nodes else "var")
            name_node = node.child_by_field_name("name")
            if name_node is not None and name_node.type in id_types:
                name = _node_text(name_node).lstrip("$")
                if name and name not in COMMON_BUILTINS and len(name) >= 2:
                    found.setdefault(name, kind)
            else:
                for child in node.children:
                    if child.type in id_types:
                        name = _node_text(child).lstrip("$")
                        if name and name not in COMMON_BUILTINS and len(name) >= 2:
                            found.setdefault(name, kind)
                            break
        stack.extend(node.children)
    return found


_DECL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:class|interface|struct|trait|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"), "class"),
    (re.compile(r"\b(?:async\s+)?(?:function|def|fn|func)\s+([A-Za-z_][A-Za-z0-9_]*)"), "fn"),
    (re.compile(r"\b(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*="), "var"),
    (re.compile(r"\$([A-Za-z_][A-Za-z0-9_]{2,})"), "var"),
)


def _collect_lexical_symbols(src: str) -> dict[str, str]:
    """Zero-dependency regex declaration collector for non-Python fallback."""
    found: dict[str, str] = {}
    for pat, kind in _DECL_PATTERNS:
        for m in pat.finditer(src):
            name = m.group(1)
            if name not in COMMON_BUILTINS and len(name) >= 2:
                found.setdefault(name, kind)
    return found


def strip_comments(src: str, ext: str = "") -> str:
    """Strip all code comments and docblocks while preserving string literals, shebangs, and PHP #[Attributes]."""
    if not src:
        return src
    lang = EXT_TO_LANG.get(ext.lower(), "")
    out: list[str] = []
    i, n = 0, len(src)
    c_style = lang in ("php", "javascript", "typescript", "tsx", "go", "rust", "java", "csharp", "c", "cpp", "kotlin", "swift")
    hash_style = lang in ("python", "ruby", "php")
    in_quote: str | None = None
    in_triple: str | None = None

    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""

        # Inside Python triple-quoted string (also strip standalone module/fn docstrings handled separately if needed)
        if in_triple is not None:
            if src[i : i + 3] == in_triple:
                out.append(in_triple)
                i += 3
                in_triple = None
                continue
            out.append(ch)
            i += 1
            continue

        # Inside single/double/backtick string literal
        if in_quote is not None:
            if ch == "\\" and i + 1 < n:
                out.append(src[i : i + 2])
                i += 2
                continue
            if ch == in_quote:
                in_quote = None
            out.append(ch)
            i += 1
            continue

        # Start of string literal
        if lang == "python" and src[i : i + 3] in ('"""', "'''"):
            in_triple = src[i : i + 3]
            out.append(in_triple)
            i += 3
            continue
        if ch in ("'", '"', "`"):
            in_quote = ch
            out.append(ch)
            i += 1
            continue

        # C-style block comment /* ... */ or /** ... */
        if c_style and ch == "/" and nxt == "*":
            end = src.find("*/", i + 2)
            i = (end + 2) if end != -1 else n
            continue

        # C-style line comment // ...
        if c_style and ch == "/" and nxt == "/":
            end = src.find("\n", i + 2)
            i = end if end != -1 else n
            continue

        # Hash line comment # ... (preserve #! shebang and PHP 8 #[Attribute])
        if hash_style and ch == "#":
            if (i == 0 and nxt == "!") or (lang == "php" and nxt == "["):
                out.append(ch)
                i += 1
                continue
            end = src.find("\n", i + 1)
            i = end if end != -1 else n
            continue

        out.append(ch)
        i += 1

    # Collapse consecutive blank lines left by stripped docblocks
    cleaned = "".join(out)
    cleaned_lines = [ln.rstrip() for ln in cleaned.splitlines()]
    compact: list[str] = []
    prev_blank = False
    for ln in cleaned_lines:
        is_blank = not ln.strip()
        if is_blank and prev_blank:
            continue
        compact.append(ln)
        prev_blank = is_blank
    return "\n".join(compact).strip()


def _discover_internal_namespaces(cwd: Path) -> set[str]:
    """Dynamically discover project-internal root namespaces from manifests (zero hardcoding)."""
    roots: set[str] = set()
    composer_p = cwd / "composer.json"
    if composer_p.is_file():
        try:
            data = json.loads(composer_p.read_text(encoding="utf-8", errors="replace"))
            for sec in ("autoload", "autoload-dev"):
                psr4 = (data.get(sec) or {}).get("psr-4") or {}
                if isinstance(psr4, dict):
                    for ns_prefix in psr4:
                        seg = str(ns_prefix).strip("\\").split("\\")[0]
                        if seg and len(seg) >= 2:
                            roots.add(seg)
        except Exception:
            pass
    go_mod = cwd / "go.mod"
    if go_mod.is_file():
        try:
            for line in go_mod.read_text(encoding="utf-8", errors="replace").splitlines()[:10]:
                m = re.match(r"^module\s+(\S+)", line.strip())
                if m:
                    for seg in m.group(1).split("/"):
                        if seg and "." not in seg and len(seg) >= 3:
                            roots.add(seg)
        except Exception:
            pass
    return roots


def _collect_workspace_class_names(cwd: Path) -> set[str]:
    """Scan workspace source filenames for PascalCase internal class stems (catches same-namespace refs without `use`)."""
    names: set[str] = set()
    root = cwd.resolve()
    try:
        for p in root.rglob("*"):
            rel_parts = p.relative_to(root).parts
            if any(part in SKIP_DIRS or part.startswith(".") for part in rel_parts):
                continue
            if p.is_file() and p.suffix.lower() in EXT_TO_LANG:
                stem = p.stem
                if re.match(r"^[A-Z][A-Za-z0-9_]{2,}$", stem) and stem not in COMMON_BUILTINS:
                    names.add(stem)
    except OSError:
        pass
    return names


def _collect_php_internal_refs(src: str, internal_roots: set[str]) -> tuple[dict[str, str], list[str]]:
    """Collect project-internal PHP namespaces and imported classes dynamically (keeping vendor libs untouched)."""
    classes: dict[str, str] = {}
    ns_segs: list[str] = []
    if not internal_roots:
        return classes, ns_segs

    # 1. `namespace Foo\Bar\Baz;` where Foo is an internal root
    for m in re.finditer(r"(?m)^\s*namespace\s+([A-Za-z_][A-Za-z0-9_\\]*)\s*;", src):
        segs = [s for s in m.group(1).split("\\") if s]
        if segs and segs[0] in internal_roots:
            for seg in segs:
                if seg not in ns_segs and seg not in COMMON_BUILTINS and len(seg) >= 2:
                    ns_segs.append(seg)

    # 2. `use Foo\Bar\MyClass [as Alias];` where Foo is an internal root
    for m in re.finditer(
        r"(?m)^\s*use\s+([A-Za-z_][A-Za-z0-9_\\]*)(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?\s*;",
        src,
    ):
        segs = [s for s in m.group(1).split("\\") if s]
        if len(segs) >= 2 and segs[0] in internal_roots:
            for seg in segs[:-1]:
                if seg not in ns_segs and seg not in COMMON_BUILTINS and len(seg) >= 2:
                    ns_segs.append(seg)
            cls_name = segs[-1]
            if cls_name not in COMMON_BUILTINS and len(cls_name) >= 2:
                classes.setdefault(cls_name, "class")
            alias_as = m.group(2)
            if alias_as and alias_as not in COMMON_BUILTINS and len(alias_as) >= 2:
                classes.setdefault(alias_as, "class")

    return classes, ns_segs


def collect_symbols(
    src: str,
    ext: str,
    *,
    internal_roots: set[str] | None = None,
    workspace_classes: set[str] | None = None,
) -> dict[str, str]:
    lang = EXT_TO_LANG.get(ext.lower(), "")
    if lang == "python":
        return _collect_python_symbols(src)
    found: dict[str, str] = {}
    if lang:
        found = _collect_ts_symbols(src, lang)
    if not found:
        found = _collect_lexical_symbols(src)
    if lang == "php" and internal_roots:
        php_cls, _ = _collect_php_internal_refs(src, internal_roots)
        for sym, kind in php_cls.items():
            found.setdefault(sym, kind)
    # Catch same-namespace workspace classes referenced in code without an explicit `use`
    if workspace_classes:
        for wcls in workspace_classes:
            if wcls not in found and re.search(rf"(?<![A-Za-z0-9_]){re.escape(wcls)}(?![A-Za-z0-9_])", src):
                found[wcls] = "class"
    return found


class OracleSession:
    """Stateful, bidirectional anonymizer & de-aliaser with per-task audit trail under .harness/runtime/oracle/."""

    def __init__(self, cwd: Path, data: dict[str, Any] | None = None) -> None:
        self.cwd = cwd.resolve()
        self.data: dict[str, Any] = data if data is not None else self._default_state()
        aliases = self.data.setdefault("aliases", {})
        aliases.setdefault("files", {})      # real_rel -> "001.py"
        aliases.setdefault("modules", {})    # real_stem -> "m001"
        aliases.setdefault("namespaces", {}) # real_ns -> "NsA"
        aliases.setdefault("symbols", {})    # real_sym -> "fn_a" / "ClassA" / "var_a"
        aliases.setdefault("literals", {})   # real_lit -> "https://example.invalid"
        aliases.setdefault("domain_nouns", [])
        self.data.setdefault("session_id", "")
        self.data.setdefault("task", "-")

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "version": 3,
            "session_id": "",
            "task": "-",
            "intent": "debug",
            "system_prompt": "",
            "messages": [],
            "aliases": {
                "files": {},
                "modules": {},
                "namespaces": {},
                "symbols": {},
                "literals": {},
                "domain_nouns": [],
            },
            "pending": None,
            "last_reply": None,
            "total_prompt_tokens": 0,
            "total_cached_tokens": 0,
            "last_prompt_tokens": 0,
            "last_cached_tokens": 0,
            "turn_count": 0,
        }

    @classmethod
    def load(cls, cwd: Path) -> OracleSession:
        p = cwd / ORACLE_THREAD_FILE
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return cls(cwd, raw)
            except Exception:
                pass
        return cls(cwd)

    def ensure_session_dir(self, task: str = "-") -> Path:
        """Ensure an isolated per-task folder under .harness/runtime/oracle/<YYYYMMDD-HHMMSS>_<Task>/."""
        clean_task = re.sub(r"[^A-Za-z0-9._-]+", "-", (task or "-").strip().split()[0]).strip("-") or "TASK"
        if not self.data.get("session_id"):
            ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            self.data["session_id"] = f"{ts}_{clean_task}"
            self.data["task"] = clean_task
        sdir = self.cwd / ORACLE_DIR / str(self.data["session_id"])
        sdir.mkdir(parents=True, exist_ok=True)
        return sdir

    def save(self) -> None:
        p = self.cwd / ORACLE_THREAD_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, indent=2, ensure_ascii=False)
        p.write_text(payload, encoding="utf-8")
        if self.data.get("session_id"):
            sdir = self.cwd / ORACLE_DIR / str(self.data["session_id"])
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "thread.json").write_text(payload, encoding="utf-8")

    def record_audit_event(
        self,
        *,
        direction: str,
        intent: str,
        payload: str,
        leaks: list[str] | None = None,
        note: str = "",
        task: str = "-",
    ) -> Path:
        """Append forensic JSONL record, human-readable transcript.md turn, and global index.jsonl entry."""
        sdir = self.ensure_session_dir(task=task)
        ts = utc_now()
        sha = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:16]
        leak_list = list(leaks or [])
        turn_no = int(self.data.get("turn_count") or 0) + (1 if direction == "outbound" else 0)
        if direction == "outbound":
            self.data["turn_count"] = turn_no

        rec = {
            "timestamp": ts,
            "session_id": self.data["session_id"],
            "task": self.data.get("task") or task,
            "turn": turn_no,
            "direction": direction,
            "intent": intent,
            "sha256": sha,
            "chars": len(payload),
            "leaks": leak_list,
            "note": note,
        }
        append_jsonl(sdir / "audit.jsonl", rec)

        # Append human-readable Markdown turn to transcript.md (strictly masked content only)
        tp = sdir / "transcript.md"
        if not tp.exists():
            tp.write_text(
                f"# Oracle Transcript: {self.data['session_id']}\n"
                f"- Task: `{self.data.get('task') or task}`\n"
                f"- Policy: Local-only (gitignored under `.harness/runtime/oracle/`)\n\n---\n\n",
                encoding="utf-8",
            )
        label = "OUTBOUND (Masked Payload Sent)" if direction == "outbound" else "INBOUND (Masked Cloud Reply)"
        leak_badge = "PASS (0 leaks)" if not leak_list else f"BLOCKED ({', '.join(leak_list)})"
        entry = (
            f"## Turn {turn_no} — {label}\n"
            f"- Timestamp: `{ts}` | Intent: `{intent.upper()}` | SHA256: `{sha}` | Privacy: `{leak_badge}`\n"
            + (f"- Note: {note}\n" if note else "")
            + "\n"
            + payload.strip()
            + "\n\n---\n\n"
        )
        with tp.open("a", encoding="utf-8") as f:
            f.write(entry)

        # Update global append-only index.jsonl on outbound turns
        if direction == "outbound":
            append_jsonl(
                self.cwd / ORACLE_INDEX_FILE,
                {
                    "timestamp": ts,
                    "session_id": self.data["session_id"],
                    "task": self.data.get("task") or task,
                    "intent": intent,
                    "turn": turn_no,
                    "leaks": len(leak_list),
                    "dir": f"{ORACLE_DIR}/{self.data['session_id']}",
                },
            )
        return sdir

    def alias_namespace(self, name: str) -> str:
        namespaces: dict[str, str] = self.data["aliases"]["namespaces"]
        if name in namespaces:
            return namespaces[name]
        used = set(namespaces.values())
        idx = 0
        while True:
            cand = f"Ns{self._idx_to_alpha(idx).upper()}"
            if cand not in used:
                namespaces[name] = cand
                return cand
            idx += 1

    def verify_bijection(self) -> list[str]:
        """Verify strict 1-to-1 bijection across all alias tables (no collisions)."""
        errors: list[str] = []
        seen_aliases: dict[str, str] = {}
        for table_name in ("files", "modules", "namespaces", "symbols"):
            tbl = self.data["aliases"].get(table_name) or {}
            for real, alias in tbl.items():
                if not alias:
                    errors.append(f"empty_alias:{table_name}:{real}")
                    continue
                if alias in seen_aliases and seen_aliases[alias] != real:
                    errors.append(f"collision:{alias}->{seen_aliases[alias]}|{real}")
                seen_aliases[alias] = real
        return errors

    def alias_file(self, rel_path: str) -> str:
        norm = rel_path.replace("\\", "/").lstrip("./")
        files: dict[str, str] = self.data["aliases"]["files"]
        if norm in files:
            return files[norm]
        idx = len(files) + 1
        ext = Path(norm).suffix or ".txt"
        alias = f"{idx:03d}{ext}"
        files[norm] = alias
        stem = Path(norm).stem
        if stem and stem not in ("__init__", "index", "main", "app"):
            self.data["aliases"]["modules"].setdefault(stem, f"m{idx:03d}")
        return alias

    @staticmethod
    def _idx_to_alpha(idx: int) -> str:
        # 0 -> a, 25 -> z, 26 -> aa
        out = ""
        n = idx
        while True:
            out = chr(ord("a") + (n % 26)) + out
            n = n // 26 - 1
            if n < 0:
                break
        return out

    def alias_symbol(self, name: str, kind: str = "var") -> str:
        symbols: dict[str, str] = self.data["aliases"]["symbols"]
        if name in symbols:
            return symbols[name]
        used = set(symbols.values())
        idx = 0
        while True:
            suffix = self._idx_to_alpha(idx)
            if kind == "class":
                cand = f"Class{suffix.upper()}"
            elif kind == "fn":
                cand = f"fn_{suffix}"
            else:
                cand = f"var_{suffix}"
            if cand not in used:
                symbols[name] = cand
                return cand
            idx += 1

    def mask_text(self, text: str, *, ext: str = "", collect_new_symbols: bool = True) -> str:
        if not text:
            return text
        out = text

        # 1. Collect & register new declared symbols if requested
        if collect_new_symbols and ext:
            for sym, kind in collect_symbols(out, ext).items():
                self.alias_symbol(sym, kind)

        # 2. Mask workspace root paths & external/traversal paths
        cwd_variants = {self.cwd.as_posix(), str(self.cwd), self.cwd.resolve().as_posix(), str(self.cwd.resolve())}
        for root_str in sorted(cwd_variants, key=len, reverse=True):
            if root_str:
                out = re.sub(re.escape(root_str), "/workspace", out, flags=re.IGNORECASE)

        # 3. Mask secrets, URLs, emails, IPs, and external/traversal paths
        lits: dict[str, str] = self.data["aliases"]["literals"]
        for pat in SECRET_PATTERNS:
            for m in pat.finditer(out):
                val = m.group(1) if pat.groups else m.group(0)
                if val:
                    lits.setdefault(val, "REDACTED_SECRET")
                    out = out.replace(val, "REDACTED_SECRET")

        for pat in ABS_PATH_PATTERNS:
            for m in pat.finditer(out):
                val = m.group(0)
                lits.setdefault(val, "[REDACTED_PATH]")
                out = out.replace(val, "[REDACTED_PATH]")

        for m in URL_RE.finditer(out):
            val = m.group(0)
            lits.setdefault(val, "https://example.invalid")
        for m in EMAIL_RE.finditer(out):
            val = m.group(0)
            lits.setdefault(val, "user@example.invalid")
        for m in IPV4_RE.finditer(out):
            val = m.group(0)
            if val not in SAFE_IPS:
                lits.setdefault(val, "192.0.2.1")

        for real_lit, fake_lit in sorted(lits.items(), key=lambda kv: -len(kv[0])):
            out = out.replace(real_lit, fake_lit)

        # 4. Mask known file paths (longest first)
        files: dict[str, str] = self.data["aliases"]["files"]
        for real_path, alias in sorted(files.items(), key=lambda kv: -len(kv[0])):
            out = out.replace(real_path, alias)
            win_path = real_path.replace("/", "\\")
            if win_path != real_path:
                out = out.replace(win_path, alias)

        # 5. Mask domain nouns & internal namespaces (word-boundary, longest first)
        for i, noun in enumerate(self.data["aliases"].get("domain_nouns") or []):
            if noun and len(noun) >= 3:
                out = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(noun)}(?![A-Za-z0-9_])", f"domain_{self._idx_to_alpha(i)}", out)

        namespaces: dict[str, str] = self.data["aliases"].get("namespaces") or {}
        for real_ns, alias in sorted(namespaces.items(), key=lambda kv: -len(kv[0])):
            out = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(real_ns)}(?![A-Za-z0-9_])", alias, out)

        # 6. Mask symbols (word-boundary, longest first)
        symbols: dict[str, str] = self.data["aliases"]["symbols"]
        for real_sym, alias in sorted(symbols.items(), key=lambda kv: -len(kv[0])):
            out = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(real_sym)}(?![A-Za-z0-9_])", alias, out)

        return out

    def dealias_text(self, text: str) -> str:
        """Deterministically restore aliased file paths, modules, namespaces, and symbols back to real names."""
        if not text:
            return text
        out = text
        reverse: list[tuple[str, str]] = []
        for real_path, alias in self.data["aliases"]["files"].items():
            reverse.append((alias, real_path))
        for real_mod, alias in self.data["aliases"]["modules"].items():
            reverse.append((alias, real_mod))
        for real_ns, alias in (self.data["aliases"].get("namespaces") or {}).items():
            reverse.append((alias, real_ns))
        for real_sym, alias in self.data["aliases"]["symbols"].items():
            reverse.append((alias, real_sym))

        # Longest alias first, word-boundary safe
        for alias, real in sorted(reverse, key=lambda kv: -len(kv[0])):
            if not alias:
                continue
            out = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])", real, out)
        return out

    def check_leaks(self, text: str) -> list[str]:
        """Return list of any real paths, internal namespaces, private symbols, or secrets found in outbound text."""
        leaks: list[str] = []
        cwd_posix = self.cwd.as_posix()
        cwd_win = str(self.cwd)
        if cwd_posix in text or cwd_win in text:
            leaks.append("workspace_root_path")

        for pat in SECRET_PATTERNS:
            matched = False
            for m in pat.finditer(text):
                val = m.group(1) if pat.groups else m.group(0)
                if val and val != "REDACTED_SECRET":
                    leaks.append("secret_token")
                    matched = True
                    break
            if matched:
                break

        for pat in ABS_PATH_PATTERNS:
            if pat.search(text):
                leaks.append("external_or_relative_path")
                break

        for real_path in self.data["aliases"]["files"]:
            if real_path in text or real_path.replace("/", "\\") in text:
                leaks.append(real_path)

        for real_ns in self.data["aliases"].get("namespaces") or {}:
            if len(real_ns) >= 3 and re.search(rf"(?<![A-Za-z0-9_]){re.escape(real_ns)}(?![A-Za-z0-9_])", text):
                leaks.append(real_ns)

        for real_sym in self.data["aliases"]["symbols"]:
            if len(real_sym) >= 3 and re.search(rf"(?<![A-Za-z0-9_]){re.escape(real_sym)}(?![A-Za-z0-9_])", text):
                leaks.append(real_sym)

        leaks.extend(self.verify_bijection())
        return sorted(set(leaks))


def _detect_deps(cwd: Path) -> str:
    """Read concise runtime/library versions from common manifests without leaking internal names."""
    deps: list[str] = []
    py = cwd / "pyproject.toml"
    if py.exists():
        txt = py.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'requires-python\s*=\s*"([^"]+)"', txt)
        if m:
            deps.append(f"python {m.group(1)}")
        for pkg in re.findall(r'"([A-Za-z0-9_.-]+[><=~!]+[^"]+)"', txt)[:10]:
            deps.append(pkg)
    pkg_json = cwd / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            for sec in ("dependencies", "devDependencies"):
                for k, v in list((data.get(sec) or {}).items())[:8]:
                    if not str(k).startswith("@internal"):
                        deps.append(f"{k} {v}")
        except Exception:
            pass
    composer_json = cwd / "composer.json"
    if composer_json.exists():
        try:
            data = json.loads(composer_json.read_text(encoding="utf-8"))
            for sec in ("require", "require-dev"):
                for k, v in list((data.get(sec) or {}).items())[:8]:
                    deps.append(f"{k} {v}")
        except Exception:
            pass
    go_mod = cwd / "go.mod"
    if go_mod.exists():
        for line in go_mod.read_text(encoding="utf-8", errors="replace").splitlines()[:12]:
            if line.startswith("go "):
                deps.append(line.strip())
    return ", ".join(deps) if deps else "not detected"


def _read_active_summary(cwd: Path) -> dict[str, str]:
    info: dict[str, str] = {"State": "-", "Task": "-", "Strike": "0", "Cursor": "-"}
    p = cwd / "_ACTIVE.md"
    if not p.exists():
        return info
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        for key in info:
            if line.startswith(f"{key}:"):
                info[key] = line.split(":", 1)[1].strip() or "-"
    return info


def _discover_target_files(cwd: Path, explicit_files: list[str] | None = None, limit: int = 4) -> list[Path]:
    if explicit_files:
        out: list[Path] = []
        for f in explicit_files:
            p = (cwd / f).resolve()
            if p.is_file() and cwd.resolve() in p.parents:
                out.append(p)
        return out[:limit]

    # 1. Check git modified files
    rc, st_out, _ = run_git(cwd, "status", "--porcelain")
    candidates: list[Path] = []
    if rc == 0 and st_out:
        for line in st_out.splitlines():
            if len(line) < 4:
                continue
            rel = line[3:].strip().strip('"').split(" -> ")[-1]
            if rel.startswith("_") or rel.startswith(".harness/") or rel == "ORACLE.md":
                continue
            p = (cwd / rel).resolve()
            if p.is_file() and p.suffix.lower() in EXT_TO_LANG:
                candidates.append(p)

    # 2. Fallback: parse file paths mentioned in _ACTIVE.md
    if not candidates and (cwd / "_ACTIVE.md").exists():
        active_txt = (cwd / "_ACTIVE.md").read_text(encoding="utf-8", errors="replace")
        for m in re.findall(r"([A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|php|go|rs|java|cs|rb))", active_txt):
            p = (cwd / m).resolve()
            if p.is_file() and p not in candidates:
                candidates.append(p)

    # 3. Fallback: top source files in workspace
    if not candidates:
        for p in sorted(cwd.rglob("*")):
            if any(part in SKIP_DIRS or part.startswith(".") for part in p.parts):
                continue
            if p.is_file() and p.suffix.lower() in EXT_TO_LANG:
                candidates.append(p)
                if len(candidates) >= limit:
                    break

    return candidates[:limit]


def _find_file_for_symbol(cwd: Path, sym: str) -> Path | None:
    """Locate a workspace source file defining `sym` (filename match first, then declaration regex)."""
    if not sym or len(sym) < 2:
        return None
    decl_rx = re.compile(rf"\b(?:class|interface|trait|enum|struct|function|def|fn|func)\s+{re.escape(sym)}\b")
    fallback: Path | None = None
    root = cwd.resolve()
    try:
        for p in sorted(root.rglob("*")):
            rel_parts = p.relative_to(root).parts
            if any(part in SKIP_DIRS or part.startswith(".") for part in rel_parts):
                continue
            if not p.is_file() or p.suffix.lower() not in EXT_TO_LANG:
                continue
            if p.stem == sym:
                return p
            if fallback is None:
                try:
                    if decl_rx.search(p.read_text(encoding="utf-8", errors="replace")):
                        fallback = p
                except OSError:
                    pass
    except OSError:
        pass
    return fallback


def prepare_consultation(
    cwd: Path,
    *,
    intent: str = "debug",
    question: str = "",
    files: list[str] | None = None,
    max_lines: int = 60,
) -> dict[str, Any]:
    """Build a comment-stripped, masked, leak-checked Oracle payload with per-task audit trail."""
    session = OracleSession.load(cwd)
    active = _read_active_summary(cwd)
    deps = _detect_deps(cwd)
    internal_roots = _discover_internal_namespaces(cwd)
    workspace_classes = _collect_workspace_class_names(cwd)
    target_paths = _discover_target_files(
        cwd,
        explicit_files=files,
        limit=max(6, len(files)) if files else (6 if intent == "plan" else 4),
    )

    # Register internal root namespaces & file aliases first
    for root_ns in sorted(internal_roots):
        session.alias_namespace(root_ns)

    rel_map: list[tuple[Path, str, str]] = []
    for p in target_paths:
        rel = p.relative_to(cwd.resolve()).as_posix()
        alias = session.alias_file(rel)
        rel_map.append((p, rel, alias))

    # Pass 1: Extract slices, strip ALL comments/docblocks, collect symbols & namespaces across ALL files
    raw_slices: list[tuple[Path, str, int, int, str]] = []
    for p, _rel, alias in rel_map:
        s, e, raw_slice = extract_slice(p, max_lines=max_lines)
        clean_slice = strip_comments(raw_slice, p.suffix)
        raw_slices.append((p, alias, s, e, clean_slice))
        if EXT_TO_LANG.get(p.suffix.lower()) == "php" and internal_roots:
            _, ns_segs = _collect_php_internal_refs(clean_slice, internal_roots)
            for seg in ns_segs:
                session.alias_namespace(seg)
        for sym, kind in collect_symbols(
            clean_slice,
            p.suffix,
            internal_roots=internal_roots,
            workspace_classes=workspace_classes,
        ).items():
            session.alias_symbol(sym, kind)

    # Pass 2: Mask every slice with the complete cross-file symbol & namespace table
    masked_slices: list[str] = []
    for p, alias, s, e, clean_slice in raw_slices:
        masked_code = session.mask_text(clean_slice, ext=p.suffix, collect_new_symbols=False)
        lang = EXT_TO_LANG.get(p.suffix.lower(), "")
        masked_slices.append(f"### {alias} L{s}-{e}\n{safe_fence(masked_code, lang)}")

    # Optional git diff for review intent
    diff_block = ""
    if intent == "review":
        rc, diff_out, _ = run_git(cwd, "diff", "--unified=3")
        if rc == 0 and diff_out:
            trimmed = "\n".join(diff_out.splitlines()[:120])
            masked_diff = session.mask_text(trimmed, collect_new_symbols=False)
            diff_block = f"\n## Masked Diff\n{safe_fence(masked_diff, 'diff')}\n"

    task_masked = session.mask_text(active["Task"], collect_new_symbols=False)
    cursor_masked = session.mask_text(active["Cursor"], collect_new_symbols=False)
    question_text = question.strip() or (
        "Break down a clean implementation plan and ordered task steps."
        if intent == "plan"
        else ("Review these changes for bugs, edge cases, and architectural risks." if intent == "review" else "Identify the root cause and provide an actionable fix.")
    )
    question_masked = session.mask_text(question_text, collect_new_symbols=False)

    sections = [
        f"## Intent: {intent.upper()}",
        f"- Deps: {deps}",
        f"- State: {active['State']} (Strike: {active['Strike']})",
        f"- Task: {task_masked}",
        f"- Cursor: {cursor_masked}",
        f"- Question: {question_masked}",
    ]
    if masked_slices:
        sections.append("\n## Files\n" + "\n\n".join(masked_slices))
    if diff_block:
        sections.append(diff_block)

    outbound = "\n".join(sections).strip() + "\n"
    leaks = session.check_leaks(outbound)

    session.data["intent"] = intent
    sdir = session.record_audit_event(
        direction="outbound",
        intent=intent,
        payload=outbound,
        leaks=leaks,
        note=f"prepare ({len(rel_map)} files)",
        task=active["Task"],
    )
    session.data["pending"] = {
        "created_at": utc_now(),
        "intent": intent,
        "question_raw": question_text,
        "question_masked": question_masked,
        "outbound": outbound,
        "leaks": leaks,
        "files": [{"real": rel, "alias": alias} for _, rel, alias in rel_map],
    }
    session.save()
    return {
        "ok": len(leaks) == 0,
        "intent": intent,
        "outbound": outbound,
        "leaks": leaks,
        "files": [{"real": rel, "alias": alias} for _, rel, alias in rel_map],
        "alias_count": len(session.data["aliases"]["symbols"]),
        "namespace_count": len(session.data["aliases"]["namespaces"]),
        "session_dir": str(sdir.relative_to(cwd.resolve()).as_posix()),
    }


NEED_LINE_RE = re.compile(r"^\s*-\s*Need:\s*(.+)$", re.MULTILINE)


def parse_need_requests(reply_text: str) -> list[str]:
    return [m.group(1).strip() for m in NEED_LINE_RE.finditer(reply_text) if m.group(1).strip()]


def fulfill_needs(cwd: Path, reply_text: str, *, max_lines: int = 60) -> dict[str, Any]:
    """Resolve Cloud Oracle `- Need:` requests (file or symbol) with 2-pass comment-stripped masking."""
    needs = parse_need_requests(reply_text)
    if not needs:
        return {"has_needs": False, "outbound": "", "leaks": [], "resolved": []}

    session = OracleSession.load(cwd)
    internal_roots = _discover_internal_namespaces(cwd)
    workspace_classes = _collect_workspace_class_names(cwd)

    # Record inbound reply that contained `- Need:` requests
    session.record_audit_event(
        direction="inbound",
        intent=str(session.data.get("intent") or "plan"),
        payload=reply_text,
        note=f"requested {len(needs)} slice(s)",
        task=str(session.data.get("task") or "-"),
    )

    # Pass 1: Resolve targets, extract slices, strip comments, collect ALL new symbols & namespaces
    resolved_items: list[tuple[Path, str, int, int, str]] = []
    for raw_need in needs[:4]:
        dealiased = session.dealias_text(raw_need)
        m_file = re.search(r"([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)", dealiased)
        target: Path | None = None
        sym: str | None = None
        line_num: int | None = None

        if m_file:
            rel = m_file.group(1).replace("\\", "/")
            cand = (cwd / rel).resolve()
            if cand.is_file() and cwd.resolve() in cand.parents:
                target = cand
            m_line = re.search(r"(?:\bL|:)(\d+)\b", dealiased)
            line_num = int(m_line.group(1)) if m_line else None
            rest = dealiased[m_file.end() :].strip()
            m_sym = re.search(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b", rest)
            if m_sym and not m_sym.group(1).startswith("L"):
                sym = m_sym.group(1)
        else:
            # Symbol-only Need request (e.g. `- Need: ClassL` -> dealiased `PricingService`)
            for tok in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b", dealiased):
                if tok in COMMON_BUILTINS:
                    continue
                found_p = _find_file_for_symbol(cwd, tok)
                if found_p is not None:
                    target = found_p
                    sym = tok
                    break

        if target is None:
            continue

        alias = session.alias_file(target.relative_to(cwd.resolve()).as_posix())
        s, e, raw_slice = extract_slice(target, line=line_num, symbol=sym, max_lines=max_lines)
        clean_slice = strip_comments(raw_slice, target.suffix)
        resolved_items.append((target, alias, s, e, clean_slice))

        if EXT_TO_LANG.get(target.suffix.lower()) == "php" and internal_roots:
            _, ns_segs = _collect_php_internal_refs(clean_slice, internal_roots)
            for seg in ns_segs:
                session.alias_namespace(seg)
        for s_name, kind in collect_symbols(
            clean_slice,
            target.suffix,
            internal_roots=internal_roots,
            workspace_classes=workspace_classes,
        ).items():
            session.alias_symbol(s_name, kind)

    if not resolved_items:
        session.save()
        return {"has_needs": False, "outbound": "", "leaks": [], "resolved": []}

    # Pass 2: Mask every slice with complete symbol & namespace tables
    blocks: list[str] = []
    resolved: list[str] = []
    for target, alias, s, e, clean_slice in resolved_items:
        masked = session.mask_text(clean_slice, ext=target.suffix, collect_new_symbols=False)
        lang = EXT_TO_LANG.get(target.suffix.lower(), "")
        blocks.append(f"### {alias} L{s}-{e}\n{safe_fence(masked, lang)}")
        resolved.append(f"{alias} L{s}-{e}")

    outbound = "## Requested Slices\n" + "\n\n".join(blocks) + "\n"
    leaks = session.check_leaks(outbound)
    session.record_audit_event(
        direction="outbound",
        intent=str(session.data.get("intent") or "plan"),
        payload=outbound,
        leaks=leaks,
        note=f"fulfilled {', '.join(resolved)}",
        task=str(session.data.get("task") or "-"),
    )
    session.save()
    return {
        "has_needs": True,
        "outbound": outbound,
        "leaks": leaks,
        "resolved": resolved,
    }


def dealias_reply(cwd: Path, reply_text: str, *, record_audit: bool = False) -> str:
    session = OracleSession.load(cwd)
    if record_audit and reply_text.strip():
        session.record_audit_event(
            direction="inbound",
            intent=str(session.data.get("intent") or "plan"),
            payload=reply_text,
            note="final oracle directive",
            task=str(session.data.get("task") or "-"),
        )
        session.save()
    return session.dealias_text(reply_text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Harness Oracle anonymizer & smart slicer")
    ap.add_argument("--cwd", type=Path, default=Path.cwd())
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare", help="Slice, mask, and leak-check context")
    p_prep.add_argument("--intent", choices=("plan", "debug", "review"), default="debug")
    p_prep.add_argument("--question", default="")
    p_prep.add_argument("--files", nargs="*", default=None)

    p_de = sub.add_parser("dealias", help="De-alias text using .harness/runtime/oracle_thread.json")
    p_de.add_argument("text")

    args = ap.parse_args(argv)
    if args.cmd == "prepare":
        res = prepare_consultation(args.cwd, intent=args.intent, question=args.question, files=args.files)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["ok"] else 2
    if args.cmd == "dealias":
        print(dealias_reply(args.cwd, args.text))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
