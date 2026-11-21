"""Zero-dependency Remote Gate Notifications (Telegram, Discord, Generic Webhook)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.guard import redact_secrets


def _post_json(url: str, payload: dict[str, Any], timeout: int = 10) -> tuple[bool, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Harness-Notify/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(16_384).decode("utf-8", errors="replace")
            return 200 <= resp.status < 300, raw
    except urllib.error.HTTPError as ex:
        err = ex.read(2048).decode("utf-8", errors="replace") if hasattr(ex, "read") else ex.reason
        return False, f"HTTP {ex.code}: {err}"
    except Exception as ex:
        return False, str(ex)


def send_telegram(bot_token: str, chat_id: str, text: str, timeout: int = 10) -> tuple[bool, str]:
    token = bot_token.strip()
    cid = str(chat_id).strip()
    if not token or not cid:
        return False, "Missing Telegram bot token or chat_id"
    safe_text = redact_secrets(text)[:3800]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _post_json(url, {"chat_id": cid, "text": safe_text, "disable_web_page_preview": True}, timeout=timeout)


def poll_telegram_updates(
    bot_token: str, offset: int = 0, poll_timeout: int = 15
) -> tuple[bool, list[dict[str, Any]], str]:
    """Fetch pending Telegram Bot updates via long polling (no inbound port required)."""
    token = bot_token.strip()
    if not token:
        return False, [], "Missing Telegram bot token"
    qs = urllib.parse.urlencode({"offset": offset, "timeout": max(1, min(30, poll_timeout)), "limit": 20})
    url = f"https://api.telegram.org/bot{token}/getUpdates?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "Harness-Notify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=poll_timeout + 8) as resp:
            data = json.loads(resp.read(128_000).decode("utf-8", errors="replace"))
        if not isinstance(data, dict) or not data.get("ok"):
            return False, [], str(data)
        res = data.get("result")
        return True, res if isinstance(res, list) else [], ""
    except Exception as ex:
        return False, [], str(ex)


def send_discord(webhook_url: str, text: str, timeout: int = 10) -> tuple[bool, str]:
    url = webhook_url.strip()
    if not url:
        return False, "Missing Discord webhook URL"
    safe_text = redact_secrets(text)[:1900]
    return _post_json(url, {"content": safe_text}, timeout=timeout)


def send_generic_webhook(
    webhook_url: str, event: str, title: str, message: str, meta: dict[str, Any] | None = None, timeout: int = 10
) -> tuple[bool, str]:
    url = webhook_url.strip()
    if not url:
        return False, "Missing generic webhook URL"
    payload = {
        "source": "agent-harness",
        "event": event,
        "title": redact_secrets(title),
        "message": redact_secrets(message)[:3800],
        "meta": meta or {},
    }
    return _post_json(url, payload, timeout=timeout)


def parse_telegram_gate_command(text: str) -> tuple[str, str]:
    """Parse a Telegram remote-reply command into (action, value)."""
    cmd = text.strip()
    low = cmd.lower()
    if low in ("/status", "status"):
        return "status", ""
    if low in ("/abort", "abort", "/stop"):
        return "abort", ""
    if low in ("/ok", "ok"):
        return "prompt", "OK"
    if low.startswith("/no ") or low.startswith("no "):
        reason = cmd.split(" ", 1)[1].strip()
        return "prompt", f"NO {reason}" if reason else "NO"
    if low in ("/no", "no"):
        return "prompt", "NO"
    return "help", ""


def format_gate_message(
    event: str,
    workspace: str = "",
    state: str = "",
    task: str = "",
    strike: int = 0,
    summary: str = "",
    allow_remote_reply: bool = False,
) -> str:
    ev = event.strip().upper() or "ALERT"
    header = f"[HARNESS:{ev}]"
    if workspace:
        header += f" {workspace}"
    lines = [header]
    status_bits = [b for b in (f"State={state}" if state else "", f"Task={task}" if task else "", f"Strike={strike}" if strike else "") if b]
    if status_bits:
        lines.append(" | ".join(status_bits))
    if summary.strip():
        lines.append(redact_secrets(summary.strip())[:1200])
    if allow_remote_reply and ev in ("PLAN", "VERIFY", "GATE1", "GATE2"):
        lines.append("Reply: /ok | /no <reason> | /status")
    elif allow_remote_reply and ev == "LOCK":
        lines.append("Reply: /status | /abort (or open WebUI to inspect)")
    return "\n".join(lines)


def dispatch_notification(
    event: str,
    message: str,
    *,
    telegram_bot_token: str = "",
    telegram_chat_id: str = "",
    discord_webhook_url: str = "",
    generic_webhook_url: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a notification to all configured channels (best-effort, never raises)."""
    results: dict[str, dict[str, Any]] = {}
    if telegram_bot_token and telegram_chat_id:
        ok, info = send_telegram(telegram_bot_token, telegram_chat_id, message)
        results["telegram"] = {"ok": ok, "detail": info[:200]}
    if discord_webhook_url:
        ok, info = send_discord(discord_webhook_url, message)
        results["discord"] = {"ok": ok, "detail": info[:200]}
    if generic_webhook_url:
        ok, info = send_generic_webhook(generic_webhook_url, event, f"HARNESS:{event.upper()}", message, meta=meta)
        results["webhook"] = {"ok": ok, "detail": info[:200]}
    any_sent = bool(results)
    all_ok = any_sent and all(r["ok"] for r in results.values())
    return {"ok": all_ok, "configured": any_sent, "channels": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Send Agent Harness gate/alert notifications (Telegram, Discord, Webhook)")
    ap.add_argument("--event", default="alert", help="Event tag (e.g. plan, verify, lock, done, alert)")
    ap.add_argument("--workspace", default="")
    ap.add_argument("--state", default="")
    ap.add_argument("--task", default="")
    ap.add_argument("--strike", type=int, default=0)
    ap.add_argument("--message", "-m", required=True, help="Notification summary text")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    text = format_gate_message(
        args.event,
        workspace=args.workspace or Path.cwd().name,
        state=args.state,
        task=args.task,
        strike=args.strike,
        summary=args.message,
    )
    res = dispatch_notification(
        args.event,
        text,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL", ""),
        generic_webhook_url=os.environ.get("HARNESS_WEBHOOK_URL", ""),
        meta={"workspace": args.workspace, "state": args.state, "task": args.task, "strike": args.strike},
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if not res["configured"]:
            print("[NOTIFY:SKIP] No notification channel configured (set TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL, or HARNESS_WEBHOOK_URL).")
            return 0
        print(f"[NOTIFY:{'OK' if res['ok'] else 'PARTIAL'}] channels={list(res['channels'].keys())}")
    return 0 if (not res["configured"] or res["ok"]) else 1


if __name__ == "__main__":
    sys.exit(main())
