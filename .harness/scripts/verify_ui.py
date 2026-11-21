"""Browser / Visual Verification for Gate 2 (VERIFY): optional Playwright with zero-dep Chrome/Edge headless fallback."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _find_browser_binary() -> str | None:
    """Locate Chrome, Edge, or Chromium binary on PATH or standard Windows/macOS/Linux locations."""
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
        for cand in candidates:
            if cand.is_file():
                return str(cand)
    return None


def _has_playwright() -> bool:
    try:
        importlib.import_module("playwright.sync_api")
        return True
    except Exception:
        return False


def detect_ui_backend() -> str:
    """Return 'playwright', 'browser-cli', or '' if no headless browser backend is available."""
    if _has_playwright():
        return "playwright"
    if _find_browser_binary():
        return "browser-cli"
    return ""


def _next_snapshot_stem(snap_dir: Path, tag: str = "") -> str:
    snap_dir.mkdir(parents=True, exist_ok=True)
    clean_tag = re.sub(r"[^a-zA-Z0-9_-]+", "_", tag.strip()).strip("_")
    if clean_tag:
        return f"UI_{clean_tag}"
    existing = sorted(snap_dir.glob("UI_*.png"))
    max_seq = 0
    for p in existing:
        m = re.match(r"UI_(\d+)$", p.stem)
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    return f"UI_{max_seq + 1:03d}"


def _validate_url(raw_url: str) -> tuple[bool, str]:
    try:
        parsed = urllib.parse.urlparse(raw_url.strip())
    except ValueError:
        return False, "Invalid URL"
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False, "Only http:// and https:// URLs are supported"
    return True, ""


def _resolve_workspace_path(root: Path, raw_path: str) -> tuple[Path | None, str]:
    cleaned = raw_path.strip()
    if not cleaned:
        return None, "Empty path"
    root_res = root.resolve()
    cand = (root_res / cleaned).resolve()
    try:
        cand.relative_to(root_res)
    except ValueError:
        return None, f"Path escapes workspace root: {raw_path}"
    return cand, ""


def parse_viewport(viewport: str) -> tuple[tuple[int, int] | None, str]:
    raw = viewport.strip().lower()
    if not raw:
        return (1280, 800), ""
    m = re.fullmatch(r"(\d{3,4})\s*[x,]\s*(\d{3,4})", raw)
    if not m:
        return None, f"Invalid viewport '{viewport}'. Expected WIDTHxHEIGHT (e.g. '390x844')."
    w = max(240, min(3840, int(m.group(1))))
    h = max(240, min(2160, int(m.group(2))))
    return (w, h), ""


def _origin_of(raw_url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(raw_url.strip())
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    except ValueError:
        pass
    return ""


def _classify_failure(req_url: str, target_origins: set[str], ignore_third_party: bool) -> str:
    try:
        path = urllib.parse.urlparse(req_url).path.lower()
    except ValueError:
        path = ""
    if path.endswith("/favicon.ico") or path == "favicon.ico":
        return "ignored"
    if ignore_third_party and target_origins:
        origin = _origin_of(req_url)
        if origin and origin not in target_origins:
            return "third_party"
    return "failed"


def _goto_with_retry(page: Any, url: str, timeout_ms: int) -> Any:
    delays = (0.8, 1.2)
    last_exc: Exception | None = None
    for attempt in range(len(delays) + 1):
        try:
            return page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as ex:
            msg = str(ex)
            is_conn_err = any(
                tok in msg
                for tok in ("ERR_CONNECTION_REFUSED", "ECONNREFUSED", "ERR_CONNECTION_RESET", "ConnectionRefused")
            )
            if not is_conn_err or attempt >= len(delays):
                raise
            last_exc = ex
            time.sleep(delays[attempt])
    if last_exc is not None:
        raise last_exc
    return None


def _run_steps(page: Any, steps: list[dict[str, Any]], step_timeout_ms: int) -> list[str]:
    errors: list[str] = []
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"Step {idx}: expected object, got {type(step).__name__}")
            break
        action = str(step.get("action") or "").strip().lower()
        selector = str(step.get("selector") or "").strip()
        value = "" if step.get("value") is None else str(step.get("value"))
        try:
            if action == "click":
                if not selector:
                    raise ValueError("selector is required for 'click'")
                page.locator(selector).first.click(timeout=step_timeout_ms)
            elif action == "fill":
                if not selector:
                    raise ValueError("selector is required for 'fill'")
                page.locator(selector).first.fill(value, timeout=step_timeout_ms)
            elif action == "select":
                if not selector:
                    raise ValueError("selector is required for 'select'")
                page.locator(selector).first.select_option(value, timeout=step_timeout_ms)
            elif action == "press":
                if not value:
                    raise ValueError("value (key name) is required for 'press'")
                if selector:
                    page.locator(selector).first.press(value, timeout=step_timeout_ms)
                else:
                    page.keyboard.press(value)
            elif action == "wait_for":
                if selector:
                    page.locator(selector).first.wait_for(state="visible", timeout=step_timeout_ms)
                elif value:
                    page.get_by_text(value).first.wait_for(state="visible", timeout=step_timeout_ms)
                else:
                    raise ValueError("selector or value is required for 'wait_for'")
            elif action == "goto":
                ok_url, url_err = _validate_url(value)
                if not ok_url:
                    raise ValueError(url_err)
                page.goto(value, wait_until="domcontentloaded", timeout=step_timeout_ms)
            elif action == "assert_text":
                if not value:
                    raise ValueError("value is required for 'assert_text'")
                target_loc = page.locator(selector).first if selector else page.locator("body")
                txt = target_loc.inner_text(timeout=step_timeout_ms)
                if value not in txt:
                    raise AssertionError(f"Expected text {value!r} not found")
            else:
                raise ValueError(f"Unsupported action {action!r}")
        except Exception as ex:
            errors.append(f"Step {idx} ({action or '?'}): {str(ex)[:240]}")
            break
    return errors


def _extract_dom_summary(page: Any) -> dict[str, Any]:
    try:
        raw = page.evaluate(
            """() => {
                const body = document.body;
                const rawText = body ? (body.innerText || "") : "";
                const normalized = rawText.replace(/\\s+/g, " ").trim();
                const headings = Array.from(document.querySelectorAll("h1, h2, h3"))
                    .map(el => (el.innerText || "").replace(/\\s+/g, " ").trim())
                    .filter(Boolean)
                    .slice(0, 8);
                const interactive = document.querySelectorAll(
                    "a[href], button, input:not([type='hidden']), select, textarea"
                ).length;
                return {
                    text_len: normalized.length,
                    text_preview: normalized.slice(0, 1200),
                    headings,
                    interactive_count: interactive,
                };
            }"""
        )
        if not isinstance(raw, dict):
            return {}
        text_len = int(raw.get("text_len") or 0)
        interactive = int(raw.get("interactive_count") or 0)
        return {
            "text_len": text_len,
            "text_preview": str(raw.get("text_preview") or ""),
            "headings": [str(h) for h in (raw.get("headings") or [])[:8]],
            "interactive_count": interactive,
            "blank_page": text_len == 0 and interactive == 0,
        }
    except Exception:
        return {}


def _verify_with_playwright(
    url: str,
    shot_path: Path,
    width: int,
    height: int,
    full_page: bool,
    timeout_ms: int,
    *,
    wait_for: str = "",
    steps: list[dict[str, Any]] | None = None,
    assert_text: str = "",
    storage_state_path: Path | None = None,
    save_storage_state_path: Path | None = None,
    ignore_third_party: bool = True,
) -> dict[str, Any]:
    pw_mod = importlib.import_module("playwright.sync_api")
    console_errors: list[str] = []
    page_errors: list[str] = []
    raw_failures: list[tuple[str, str]] = []
    step_errors: list[str] = []
    assertion_errors: list[str] = []
    dom_summary: dict[str, Any] = {}
    http_status = 0
    title = ""
    final_url = url

    ctx_kwargs: dict[str, Any] = {"viewport": {"width": width, "height": height}}
    if storage_state_path is not None:
        if not storage_state_path.is_file():
            return {
                "ok": False,
                "backend": "playwright",
                "url": url,
                "error": f"storage_state file not found: {storage_state_path}",
            }
        ctx_kwargs["storage_state"] = str(storage_state_path)

    with pw_mod.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(**ctx_kwargs)
            page = ctx.new_page()
            page.on(
                "console",
                lambda msg: console_errors.append(str(msg.text)[:300]) if msg.type == "error" else None,
            )
            page.on("pageerror", lambda err: page_errors.append(str(err)[:300]))
            page.on(
                "response",
                lambda resp: (
                    raw_failures.append((str(resp.url), f"{resp.status} {resp.url}")) if resp.status >= 400 else None
                ),
            )
            page.on(
                "requestfailed",
                lambda req: raw_failures.append((str(req.url), f"FAILED {req.url} ({req.failure})")),
            )

            resp = _goto_with_retry(page, url, timeout_ms)
            if resp is not None:
                http_status = int(resp.status)

            if wait_for:
                try:
                    page.locator(wait_for).first.wait_for(state="visible", timeout=timeout_ms)
                except Exception as ex:
                    assertion_errors.append(f"wait_for '{wait_for}' timed out: {str(ex)[:200]}")
            else:
                try:
                    page.wait_for_load_state("networkidle", timeout=min(3000, timeout_ms))
                except Exception:
                    pass

            if steps:
                step_errors = _run_steps(page, steps, min(10_000, timeout_ms))
                if not step_errors:
                    try:
                        page.wait_for_load_state("networkidle", timeout=min(2500, timeout_ms))
                    except Exception:
                        pass

            title = page.title() or ""
            final_url = page.url or url
            dom_summary = _extract_dom_summary(page)

            if assert_text:
                visible_text = dom_summary.get("text_preview") or ""
                if assert_text not in visible_text:
                    try:
                        full_txt = page.locator("body").inner_text(timeout=min(3000, timeout_ms))
                    except Exception:
                        full_txt = visible_text
                    if assert_text not in full_txt:
                        assertion_errors.append(f"Expected text {assert_text!r} not found on page")

            if dom_summary.get("blank_page"):
                assertion_errors.append("Blank page rendered (no visible text or interactive elements)")

            page.screenshot(path=str(shot_path), full_page=full_page)

            if save_storage_state_path is not None and not step_errors:
                save_storage_state_path.parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=str(save_storage_state_path))
        finally:
            browser.close()

    target_origins = {o for o in (_origin_of(url), _origin_of(final_url)) if o}
    failed_requests: list[str] = []
    third_party_failures: list[str] = []
    for req_url, desc in raw_failures:
        kind = _classify_failure(req_url, target_origins, ignore_third_party)
        if kind == "failed":
            failed_requests.append(desc)
        elif kind == "third_party":
            third_party_failures.append(desc)

    ok = (
        (200 <= http_status < 400 or http_status == 0)
        and not console_errors
        and not page_errors
        and not failed_requests
        and not step_errors
        and not assertion_errors
    )
    return {
        "ok": ok,
        "backend": "playwright",
        "url": url,
        "final_url": final_url,
        "title": title,
        "http_status": http_status,
        "console_errors": console_errors[:20],
        "page_errors": page_errors[:20],
        "failed_requests": failed_requests[:20],
        "third_party_failures": third_party_failures[:10],
        "step_errors": step_errors[:10],
        "assertion_errors": assertion_errors[:10],
        "dom_summary": dom_summary,
        "screenshot": str(shot_path),
    }


def _verify_with_browser_cli(
    url: str,
    shot_path: Path,
    width: int,
    height: int,
    timeout_sec: int,
) -> dict[str, Any]:
    browser_bin = _find_browser_binary()
    if not browser_bin:
        return {
            "ok": False,
            "backend": "none",
            "url": url,
            "error": "No headless browser found. Install optional 'playwright' (uv sync --extra browser) or Chrome/Edge.",
        }

    # Quick HTTP reachability probe via stdlib urllib
    http_status = 0
    failed_requests: list[str] = []
    title = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Harness-VerifyUI/1.0"})
        with urllib.request.urlopen(req, timeout=min(10, timeout_sec)) as resp:
            http_status = int(resp.status)
            head = resp.read(32_768).decode("utf-8", errors="replace")
            m = re.search(r"<title[^>]*>(.*?)</title>", head, re.IGNORECASE | re.DOTALL)
            if m:
                title = " ".join(m.group(1).split())[:120]
    except urllib.error.HTTPError as ex:
        http_status = int(ex.code)
        failed_requests.append(f"{ex.code} {url}")
    except Exception as ex:
        return {
            "ok": False,
            "backend": "browser-cli",
            "url": url,
            "http_status": 0,
            "error": f"Failed to reach {url}: {ex}",
        }

    cmd = [
        browser_bin,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--window-size={width},{height}",
        f"--screenshot={shot_path}",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "backend": "browser-cli",
            "url": url,
            "http_status": http_status,
            "error": f"Browser headless capture timed out after {timeout_sec}s",
        }
    except OSError as ex:
        return {"ok": False, "backend": "browser-cli", "url": url, "error": f"Browser launch failed: {ex}"}

    shot_ok = shot_path.is_file() and shot_path.stat().st_size > 0
    ok = 200 <= http_status < 400 and shot_ok and proc.returncode == 0
    return {
        "ok": ok,
        "backend": "browser-cli",
        "url": url,
        "final_url": url,
        "title": title,
        "http_status": http_status,
        "console_errors": [],
        "page_errors": [],
        "failed_requests": failed_requests,
        "screenshot": str(shot_path) if shot_ok else "",
        "note": "Captured via headless browser CLI. Install playwright (uv sync --extra browser) for JS console & network inspection.",
    }


def verify_ui(
    root: Path,
    url: str,
    *,
    tag: str = "",
    width: int = 1280,
    height: int = 800,
    viewport: str = "",
    full_page: bool = False,
    wait_for: str = "",
    steps: list[dict[str, Any]] | None = None,
    assert_text: str = "",
    storage_state: str = "",
    save_storage_state: str = "",
    ignore_third_party: bool = True,
    timeout_sec: int = 20,
    write_snapshot: bool = True,
) -> dict[str, Any]:
    """Run headless browser verification and capture screenshot into .harness/runtime/snapshots/."""
    valid, err = _validate_url(url)
    if not valid:
        return {"ok": False, "url": url, "error": err}

    if viewport.strip():
        parsed_vp, vp_err = parse_viewport(viewport)
        if vp_err or parsed_vp is None:
            return {"ok": False, "url": url, "error": vp_err or "Invalid viewport"}
        width, height = parsed_vp

    storage_state_path: Path | None = None
    if storage_state.strip():
        storage_state_path, st_err = _resolve_workspace_path(root, storage_state)
        if st_err or storage_state_path is None:
            return {"ok": False, "url": url, "error": st_err or "Invalid storage_state path"}

    save_storage_state_path: Path | None = None
    if save_storage_state.strip():
        save_storage_state_path, sv_err = _resolve_workspace_path(root, save_storage_state)
        if sv_err or save_storage_state_path is None:
            return {"ok": False, "url": url, "error": sv_err or "Invalid save_storage_state path"}

    snap_dir = root / ".harness" / "runtime" / "snapshots"
    stem = _next_snapshot_stem(snap_dir, tag=tag)
    shot_path = snap_dir / f"{stem}.png"

    backend = detect_ui_backend()
    if backend == "playwright":
        try:
            has_extended = bool(
                wait_for.strip()
                or steps
                or assert_text.strip()
                or storage_state_path is not None
                or save_storage_state_path is not None
                or not ignore_third_party
            )
            if has_extended:
                res = _verify_with_playwright(
                    url,
                    shot_path,
                    width,
                    height,
                    full_page,
                    timeout_sec * 1000,
                    wait_for=wait_for.strip(),
                    steps=steps,
                    assert_text=assert_text.strip(),
                    storage_state_path=storage_state_path,
                    save_storage_state_path=save_storage_state_path,
                    ignore_third_party=ignore_third_party,
                )
            else:
                res = _verify_with_playwright(url, shot_path, width, height, full_page, timeout_sec * 1000)
        except Exception as ex:
            res = {"ok": False, "backend": "playwright", "url": url, "error": f"Playwright failed: {ex}"}
    elif backend == "browser-cli":
        pw_only = [
            name
            for name, active in (
                ("steps", bool(steps)),
                ("wait_for", bool(wait_for.strip())),
                ("assert_text", bool(assert_text.strip())),
                ("storage_state", storage_state_path is not None),
                ("save_storage_state", save_storage_state_path is not None),
            )
            if active
        ]
        if pw_only:
            res = {
                "ok": False,
                "backend": "browser-cli",
                "url": url,
                "error": (
                    f"Playwright is required for {', '.join(pw_only)} "
                    "(browser-cli fallback only supports HTTP reachability + screenshot). "
                    "Install with: uv sync --extra browser"
                ),
            }
        else:
            res = _verify_with_browser_cli(url, shot_path, width, height, timeout_sec)
    else:
        res = {
            "ok": False,
            "backend": "none",
            "url": url,
            "error": "No headless browser backend available. Install playwright (uv sync --extra browser) or Chrome/Edge.",
        }

    # Normalize screenshot path to repo-relative POSIX when inside root
    shot_val = res.get("screenshot")
    if isinstance(shot_val, str) and shot_val:
        try:
            res["screenshot_rel"] = Path(shot_val).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            res["screenshot_rel"] = shot_val

    if write_snapshot and not res.get("error"):
        md_path = snap_dir / f"{stem}.md"
        lines = [
            f"# UI Verification Snapshot: {stem}",
            f"- URL: {res.get('final_url') or url}",
            f"- Backend: {res.get('backend')}",
            f"- Viewport: {width}x{height}",
            f"- Title: {res.get('title') or '-'}",
            f"- HTTP Status: {res.get('http_status', 0)}",
            f"- Exit Code: {0 if res.get('ok') else 1}",
            f"- Screenshot: {res.get('screenshot_rel') or res.get('screenshot') or '-'}",
        ]
        for label, key in (
            ("Step Errors", "step_errors"),
            ("Assertion Errors", "assertion_errors"),
            ("Console Errors", "console_errors"),
            ("Page Errors", "page_errors"),
            ("Failed Requests", "failed_requests"),
            ("Third-Party Failures (Ignored)", "third_party_failures"),
        ):
            items = res.get(key)
            if isinstance(items, list) and items:
                lines.append(f"\n## {label} ({len(items)})")
                for item in items:
                    lines.append(f"- {item}")
        dom = res.get("dom_summary")
        if isinstance(dom, dict) and dom:
            lines.append("\n## DOM Summary")
            lines.append(f"- Text Length: {dom.get('text_len', 0)}")
            lines.append(f"- Interactive Elements: {dom.get('interactive_count', 0)}")
            lines.append(f"- Blank Page: {bool(dom.get('blank_page'))}")
            headings = dom.get("headings") or []
            if headings:
                lines.append(f"- Headings: {' | '.join(str(h) for h in headings[:6])}")
            preview = str(dom.get("text_preview") or "").strip()
            if preview:
                lines.append(f"\n```\n{preview[:800]}\n```")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            res["snapshot_md"] = md_path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            res["snapshot_md"] = str(md_path)

    return res


def format_verify_ui_report(res: dict[str, Any]) -> str:
    if res.get("error"):
        return f"[VERIFY_UI:FAIL] {res['error']}"
    status = "PASS" if res.get("ok") else "FAIL"
    final_url = res.get("final_url") or res.get("url")
    url_part = str(res.get("url"))
    if final_url and final_url != url_part:
        url_part = f"{url_part} -> {final_url}"
    lines = [
        f"[VERIFY_UI:{status}] {url_part} (HTTP {res.get('http_status', 0)}, backend={res.get('backend')})",
        f"Title: {res.get('title') or '-'} | Screenshot: {res.get('screenshot_rel') or res.get('screenshot') or '-'}",
    ]
    for label, key in (
        ("Step errors", "step_errors"),
        ("Assertion errors", "assertion_errors"),
        ("Console errors", "console_errors"),
        ("Page errors", "page_errors"),
        ("Failed requests", "failed_requests"),
    ):
        items = res.get(key) or []
        if items:
            lines.append(f"{label} ({len(items)}):")
            for item in items[:8]:
                lines.append(f"  - {item}")
    tp = res.get("third_party_failures") or []
    if tp:
        lines.append(f"Third-party failures ignored: {len(tp)}")
    dom = res.get("dom_summary")
    if isinstance(dom, dict) and dom:
        headings = dom.get("headings") or []
        head_str = f" | Headings: {' / '.join(str(h) for h in headings[:4])}" if headings else ""
        lines.append(
            f"DOM: {dom.get('text_len', 0)} chars, {dom.get('interactive_count', 0)} interactive{head_str}"
        )
        preview = str(dom.get("text_preview") or "").strip()
        if preview:
            lines.append(f"Visible text: {preview[:500]}")
    if res.get("note"):
        lines.append(f"Note: {res['note']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Browser / Visual Verification for Harness Gate 2 (VERIFY)")
    ap.add_argument("url", help="Target http(s) URL (e.g. http://127.0.0.1:5173)")
    ap.add_argument("--root", default=".", help="Workspace root directory")
    ap.add_argument("--tag", default="", help="Optional snapshot tag (default auto-numbered UI_001)")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=800)
    ap.add_argument("--viewport", default="", help="Viewport WIDTHxHEIGHT (overrides --width/--height)")
    ap.add_argument("--full-page", action="store_true")
    ap.add_argument("--wait-for", default="", help="CSS selector to wait for before capture")
    ap.add_argument("--assert-text", default="", help="Text that must appear on the page")
    ap.add_argument("--storage-state", default="", help="Relative path to Playwright storage_state JSON")
    ap.add_argument("--save-storage-state", default="", help="Relative path to save Playwright storage_state JSON")
    ap.add_argument("--strict-third-party", action="store_true", help="Fail on third-party 4xx/5xx requests too")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    res = verify_ui(
        Path(args.root).resolve(),
        args.url,
        tag=args.tag,
        width=args.width,
        height=args.height,
        viewport=args.viewport,
        full_page=args.full_page,
        wait_for=args.wait_for,
        assert_text=args.assert_text,
        storage_state=args.storage_state,
        save_storage_state=args.save_storage_state,
        ignore_third_party=not args.strict_third_party,
        timeout_sec=args.timeout,
        write_snapshot=not args.no_snapshot,
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(format_verify_ui_report(res))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
