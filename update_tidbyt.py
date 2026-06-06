#!/usr/bin/env python3
"""
update_tidbyt.py — Fetch live Claude usage and push to a Tidbyt device.

Usage:
    python3 update_tidbyt.py                  # normal run
    python3 update_tidbyt.py --dry-run        # print fetched JSON, skip render/push
    python3 update_tidbyt.py --print-data     # print pre-processed data JSON to stdout

The script reads:
  - ~/.claude/.credentials.json   OAuth token kept fresh by the Claude Code daemon
  - config.json                   Tidbyt device_id, api_token, etc.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# Windows consoles default to cp1252 and choke on the box-drawing chars used
# in --dry-run output. Force UTF-8 so the script runs cleanly everywhere.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ── Constants ────────────────────────────────────────────────────────────────

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
USAGE_ENDPOINT   = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA       = "oauth-2025-04-20"

# ── Helpers ──────────────────────────────────────────────────────────────────

def log(tag: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [{tag:6}] {msg}", file=sys.stderr, flush=True)


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return json.load(f)


def load_credentials() -> dict:
    """Read the OAuth token written by the Claude Code daemon."""
    with open(CREDENTIALS_PATH) as f:
        creds = json.load(f)
    oauth = creds.get("claudeAiOauth", creds)
    return {
        "access_token": oauth["accessToken"],
        "refresh_token": oauth.get("refreshToken"),
        "expires_at_ms": oauth.get("expiresAt"),   # epoch milliseconds
    }


def claude_version() -> str:
    """Return the installed Claude Code version string (e.g. '2.1.161')."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        # "2.1.161 (Claude Code)" → "2.1.161"
        return result.stdout.strip().split()[0]
    except Exception:
        return "2.0.0"


def normalize_ts(ts: str) -> str:
    """
    Simplify an ISO timestamp to RFC3339 with Z suffix so Starlark
    time.parse_time() can handle it reliably.

    "2026-06-03T18:50:00.800294+00:00"  →  "2026-06-03T18:50:00Z"
    "2026-06-03T18:50:00Z"              →  "2026-06-03T18:50:00Z"
    """
    if not ts:
        return ""
    return ts[:19] + "Z"


def fetch_usage(token: str, version: str) -> dict:
    """GET /api/oauth/usage with the required headers."""
    req = urllib.request.Request(
        USAGE_ENDPOINT,
        headers={
            "Authorization":   f"Bearer {token}",
            "User-Agent":      f"claude-code/{version}",
            "anthropic-beta":  OAUTH_BETA,
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def build_display_data(usage: dict) -> dict:
    """
    Distil the raw API response into a flat dict that claude_usage.star
    consumes.  All values are simple scalars — no None, no sub-dicts.
    """
    five_hour = usage.get("five_hour") or {}
    seven_day = usage.get("seven_day") or {}
    extra     = usage.get("extra_usage") or {}

    return {
        "five_hour_pct":      int(five_hour.get("utilization") or 0),
        "five_hour_resets_at": normalize_ts(five_hour.get("resets_at", "")),
        "seven_day_pct":      int(seven_day.get("utilization") or 0),
        "seven_day_resets_at": normalize_ts(seven_day.get("resets_at", "")),
        "extra_enabled":      bool(extra.get("is_enabled", False)),
        "extra_used":         int(extra.get("used_credits") or 0),
        "extra_limit":        int(extra.get("monthly_limit") or 0),
        "extra_pct":          int(extra.get("utilization") or 0),
    }


_USAGE_DDL = """
CREATE TABLE IF NOT EXISTS usage (
    ts                  TEXT PRIMARY KEY,
    five_hour_pct       REAL,
    five_hour_resets_at TEXT,
    seven_day_pct       REAL,
    seven_day_resets_at TEXT,
    extra_used          REAL,
    extra_limit         REAL
)
"""

def log_usage(usage: dict, data: dict, db_path: Path) -> None:
    """Append one row to the SQLite time-series DB.  Never raises — caller wraps in try/except."""
    five_hour = usage.get("five_hour") or {}
    seven_day = usage.get("seven_day") or {}
    extra     = usage.get("extra_usage") or {}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = (
        ts,
        five_hour.get("utilization"),   # raw float, better resolution than display int
        data.get("five_hour_resets_at"),
        seven_day.get("utilization"),
        data.get("seven_day_resets_at"),
        extra.get("used_credits"),
        extra.get("monthly_limit"),
    )
    con = sqlite3.connect(db_path)
    try:
        con.execute(_USAGE_DDL)
        con.execute(
            "INSERT OR IGNORE INTO usage "
            "(ts, five_hour_pct, five_hour_resets_at, seven_day_pct, seven_day_resets_at, extra_used, extra_limit) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        con.commit()
    finally:
        con.close()


def render_and_push(data: dict, cfg: dict) -> None:
    """Run `pixlet render` then `pixlet push`."""
    repo_dir  = Path(__file__).parent
    star_file = repo_dir / "claude_usage.star"
    out_webp  = Path(tempfile.gettempdir()) / "claude_usage.webp"
    data_json = json.dumps(data)

    # Allow overriding the pixlet binary (e.g. an absolute path on Windows where
    # it may not be on PATH for a scheduled task). Falls back to "pixlet".
    pixlet = cfg.get("pixlet_bin", "pixlet")

    # ── Render ────────────────────────────────────────────────────────────────
    render_cmd = [
        pixlet, "render",
        str(star_file),
        f"data={data_json}",
        "-o", str(out_webp),
    ]
    log("render", f"claude_usage.star  5h={data['five_hour_pct']}%  7d={data['seven_day_pct']}%")
    result = subprocess.run(render_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log("ERROR", f"pixlet render failed:\n{result.stderr}")
        sys.exit(1)

    # ── Push ──────────────────────────────────────────────────────────────────
    device_id       = cfg["device_id"]
    api_token       = cfg["api_token"]
    installation_id = cfg.get("installation_id", "claude-usage")

    push_cmd = [
        pixlet, "push",
        device_id, str(out_webp),
        "-t", api_token,
        "-i", installation_id,
        "-b",   # stay in rotation, don't force-display immediately
    ]
    log("push", f"device={device_id}  installation={installation_id}")
    result = subprocess.run(push_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log("ERROR", f"pixlet push failed:\n{result.stderr}")
        sys.exit(1)

    log("done", "pushed successfully")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    dry_run    = "--dry-run"    in sys.argv
    print_data = "--print-data" in sys.argv

    repo_dir    = Path(__file__).parent
    config_path = repo_dir / "config.json"

    # Load config (only needed when actually pushing)
    cfg: dict = {}
    if not (dry_run or print_data):
        if not config_path.exists():
            log("ERROR",
                "config.json not found. "
                "Copy config.example.json → config.json and fill in device_id / api_token.")
            sys.exit(1)
        cfg = load_config(config_path)

    # Load OAuth credentials (written and refreshed by the Claude Code daemon)
    try:
        creds = load_credentials()
    except FileNotFoundError:
        log("ERROR",
            f"{CREDENTIALS_PATH} not found. "
            "Open Claude Code at least once to authenticate.")
        sys.exit(1)

    token   = creds["access_token"]
    version = claude_version()
    log("info", f"claude version: {version}")

    # Fetch live usage from Anthropic
    try:
        usage = fetch_usage(token, version)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            expires_ms = creds.get("expires_at_ms") or 0
            now_ms     = datetime.now(timezone.utc).timestamp() * 1000
            if expires_ms and expires_ms < now_ms:
                log("ERROR", "Token expired — open Claude Code to refresh.")
            else:
                log("ERROR", "401 Unauthorized — token may have been invalidated.")
        else:
            log("ERROR", f"HTTP {exc.code}: {exc}")
        sys.exit(1)
    except Exception as exc:
        log("ERROR", f"Failed to fetch usage: {exc}")
        sys.exit(1)

    data = build_display_data(usage)
    # Which window the .star file highlights as the large "hero" row.
    data["hero"] = cfg.get("hero", "5h")

    # ── Optional time-series logging ─────────────────────────────────────────
    log_db_val = cfg.get("log_db")
    if log_db_val:
        db_path = Path(log_db_val)
        if not db_path.is_absolute():
            db_path = Path(__file__).parent / db_path
        try:
            log_usage(usage, data, db_path)
            log("db", f"logged to {db_path}")
        except Exception as exc:
            log("WARN", f"usage logging failed (continuing): {exc}")
    log("usage",
        f"5h={data['five_hour_pct']}%  resets@{data['five_hour_resets_at']}  "
        f"7d={data['seven_day_pct']}%  "
        + (f"extra={data['extra_pct']}% (${data['extra_used']}/${data['extra_limit']})"
           if data["extra_enabled"] else "extra=off"))

    if dry_run:
        print("\n── raw API response ─────────────────────────────────────")
        print(json.dumps(usage, indent=2))
        print("\n── display data for Starlark ────────────────────────────")
        print(json.dumps(data, indent=2))
        log("dry-run", "skipping render and push")
        return

    if print_data:
        # Machine-readable one-liner for Makefile / shell pipes
        print(json.dumps(data))
        return

    render_and_push(data, cfg)


if __name__ == "__main__":
    main()
