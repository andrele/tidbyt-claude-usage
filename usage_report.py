#!/usr/bin/env python3
"""
usage_report.py — Analyse Claude usage underutilisation from the SQLite time-series DB.

Usage:
    python3 usage_report.py                   # human-readable report (default)
    python3 usage_report.py --status          # machine-readable JSON + exit code
    python3 usage_report.py --status --window 7d   # key off the weekly window
    python3 usage_report.py --db path/to/usage.db  # explicit DB path

Exit codes (--status only):
    0  Currently utilising — rate of change is above the threshold
    1  Underutilised — flat usage with headroom remaining

The rate-of-change threshold (% / hr) is read from config.json
("underutil_rate_per_hr", default 1.0).  A window is considered "flat" when
the rolling rate falls below this threshold while utilisation < 100 % and the
window has not yet closed (minutes_to_reset > 0).

Underutilisation is measured as a lack of rate of change to the 5h or 7d
utilisation until window close — the waste crystallises when the window resets
at whatever utilisation it reached.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Config helpers ────────────────────────────────────────────────────────────

REPO_DIR    = Path(__file__).parent
CONFIG_PATH = REPO_DIR / "config.json"

_DEFAULT_RATE_THRESHOLD = 1.0   # %/hr below which a window is "flat"


def load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def resolve_db(cfg: dict, cli_db: str | None) -> Path:
    raw = cli_db or cfg.get("log_db", "usage.db")
    p   = Path(raw)
    return p if p.is_absolute() else REPO_DIR / p


# ── DB helpers ────────────────────────────────────────────────────────────────

def open_db(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        sys.exit(f"Database not found: {db_path}\n"
                 "Enable logging by setting \"log_db\" in config.json and running the updater.")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _parse_ts(ts: str) -> datetime:
    """Parse an RFC3339 Z-suffix timestamp."""
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _minutes_to_reset(resets_at: str) -> float:
    """Minutes from now until resets_at (negative if already past)."""
    if not resets_at:
        return 0.0
    try:
        delta = _parse_ts(resets_at) - datetime.now(timezone.utc)
        return delta.total_seconds() / 60
    except ValueError:
        return 0.0


# ── Core analysis queries ─────────────────────────────────────────────────────

# For each row, compute Δpct and Δminutes vs the previous row *within the same
# resets_at group* (i.e. within the same window instance).  When resets_at
# changes, the window rolled over — treat that as a fresh start (no prior row).
_ROC_SQL = """
WITH lagged AS (
    SELECT
        ts,
        {col}_pct            AS pct,
        {col}_resets_at      AS resets_at,
        LAG({col}_pct)       OVER w AS prev_pct,
        LAG(ts)              OVER w AS prev_ts,
        LAG({col}_resets_at) OVER w AS prev_resets_at
    FROM usage
    WINDOW w AS (PARTITION BY {col}_resets_at ORDER BY ts)
),
roc AS (
    SELECT
        ts,
        pct,
        resets_at,
        CASE
            WHEN prev_ts IS NULL OR prev_resets_at != resets_at THEN NULL
            ELSE (pct - prev_pct) /
                 MAX(
                     (julianday(ts) - julianday(prev_ts)) * 24.0,
                     0.0001   -- guard divide-by-zero
                 )
        END AS rate_per_hr
    FROM lagged
)
SELECT * FROM roc ORDER BY ts
"""

def query_roc(con: sqlite3.Connection, window: str) -> list[sqlite3.Row]:
    """All rows with rate-of-change for 'five_hour' or 'seven_day'."""
    col = "five_hour" if window == "5h" else "seven_day"
    return con.execute(_ROC_SQL.format(col=col)).fetchall()


def latest_window_status(con: sqlite3.Connection, window: str, threshold: float) -> dict:
    """
    Summarise the current (latest) window instance for the given window.
    Returns a dict with: pct, resets_at, rate_per_hr, headroom,
                         minutes_to_reset, flat (bool), underutilized (bool).

    When resets_at is blank the API hasn't started the next window yet (pct=0,
    session not kicked off).  We still flag flat if the last N readings have
    all been at 0% — the session is idle regardless of whether a reset time is
    known.
    """
    rows = query_roc(con, window)
    if not rows:
        return {}

    last = rows[-1]
    pct       = last["pct"]   if last["pct"]   is not None else 0.0
    rate      = last["rate_per_hr"] if last["rate_per_hr"] is not None else 0.0
    resets_at = last["resets_at"] or ""
    headroom  = max(0.0, 100.0 - pct)
    mins_left = _minutes_to_reset(resets_at)

    # When resets_at is blank the window hasn't started; count how many
    # consecutive trailing rows share the same blank resets_at at 0% pct.
    idle_mins_no_reset = 0.0
    if not resets_at:
        for r in reversed(rows):
            if r["resets_at"]:
                break
            idle_mins_no_reset += 5   # each row ≈ 5-min cron interval

    # Flat = rate below threshold AND headroom remains AND either:
    #   a) window is open with time left, OR
    #   b) resets_at is blank but we've been idle for > one cron tick
    window_open  = mins_left > 0
    idle_no_reset = (not resets_at) and (idle_mins_no_reset > 5) and (headroom > 0.0)
    flat          = (rate < threshold) and (headroom > 0.0) and (window_open or idle_no_reset)
    underutilized = flat

    return {
        "pct":                  round(pct, 1),
        "rate_per_hr":          round(rate, 2),
        "headroom":             round(headroom, 1),
        "resets_at":            resets_at,
        "minutes_to_reset":     round(mins_left, 0),
        "idle_mins_no_reset":   round(idle_mins_no_reset, 0),
        "flat":                 flat,
        "underutilized":        underutilized,
    }


# ── Closed-window waste analysis ──────────────────────────────────────────────

def closed_window_waste(con: sqlite3.Connection, window: str) -> list[dict]:
    """
    For every *completed* window instance (resets_at is in the past), return
    the final utilisation reached and the fraction wasted.
    A window instance is identified by its resets_at value; the last row before
    resets_at changes (or the last row with that resets_at, if it already passed)
    represents the final utilisation for that instance.
    """
    col = "five_hour" if window == "5h" else "seven_day"
    # Round resets_at to the nearest minute before grouping — the API jitters
    # ±1s on the same logical window boundary, which can straddle a minute
    # boundary (e.g. 06:39:59Z and 06:40:00Z are the same window).
    rows = con.execute(f"""
        SELECT round(julianday({col}_resets_at) * 1440) / 1440 AS resets_key,
               MIN({col}_resets_at) AS resets_at,
               MAX(ts) AS last_ts,
               MAX({col}_pct) AS final_pct
        FROM usage
        WHERE {col}_resets_at IS NOT NULL AND {col}_resets_at != ''
        GROUP BY round(julianday({col}_resets_at) * 1440)
        ORDER BY resets_key
    """).fetchall()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []
    for r in rows:
        resets_at = r["resets_at"] or ""
        if not resets_at or resets_at > now_str:
            continue   # current open window, skip
        final_pct = r["final_pct"] or 0.0
        results.append({
            "resets_at":  resets_at,
            "final_pct":  round(final_pct, 1),
            "unused_pct": round(max(0.0, 100.0 - final_pct), 1),
        })
    return results


# ── Daily breakdown ───────────────────────────────────────────────────────────

def daily_breakdown(con: sqlite3.Connection) -> list[dict]:
    """
    Per UTC calendar day: max 5h and 7d utilisation reached, and longest
    consecutive streak of 'flat' 5h readings (rows where five_hour_pct doesn't
    change) as a proxy for the deepest idle run.
    """
    rows = con.execute("""
        SELECT substr(ts, 1, 10) AS day,
               MAX(five_hour_pct)  AS max_5h,
               MAX(seven_day_pct)  AS max_7d,
               COUNT(*) AS readings
        FROM usage
        GROUP BY day
        ORDER BY day
    """).fetchall()

    # Fetch all rows for streak calculation
    all_rows = con.execute(
        "SELECT substr(ts,1,10) AS day, five_hour_pct FROM usage ORDER BY ts"
    ).fetchall()

    # Build per-day longest flat streak (consecutive identical five_hour_pct)
    streaks: dict[str, int] = {}
    cur_day    = None
    cur_pct    = None
    cur_streak = 0
    for r in all_rows:
        day = r["day"]
        pct = r["five_hour_pct"]
        if pct == cur_pct and day == cur_day:
            cur_streak += 1
        else:
            cur_pct    = pct
            cur_day    = day
            cur_streak = 1
        if day not in streaks or streaks[day] < cur_streak:
            streaks[day] = cur_streak

    result = []
    for r in rows:
        day = r["day"]
        result.append({
            "day":            day,
            "max_5h_pct":     round(r["max_5h"] or 0, 1),
            "max_7d_pct":     round(r["max_7d"] or 0, 1),
            "readings":       r["readings"],
            "longest_flat_5h_readings": streaks.get(day, 0),
            "longest_flat_5h_minutes":  streaks.get(day, 0) * 5,
        })
    return result


# ── Output formatters ─────────────────────────────────────────────────────────

def fmt_status_line(window: str, s: dict) -> str:
    label      = "5-hour session" if window == "5h" else "7-day weekly"
    flag       = "⚠ FLAT" if s.get("flat") else "✓ active"
    hrs_left   = s.get("minutes_to_reset", 0) / 60
    return (
        f"  {label}: {s.get('pct', 0):.1f}% used  "
        f"rate={s.get('rate_per_hr', 0):.2f}%/hr  "
        f"headroom={s.get('headroom', 0):.1f}%  "
        f"{hrs_left:.1f}h to reset  {flag}"
    )


def print_human_report(con: sqlite3.Connection, threshold: float) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n── Claude usage underutilisation report ── {now}\n")

    # Current status
    s5  = latest_window_status(con, "5h", threshold)
    s7d = latest_window_status(con, "7d", threshold)
    print("Current window status:")
    if s5:  print(fmt_status_line("5h", s5))
    if s7d: print(fmt_status_line("7d", s7d))

    # Closed-window waste (recent)
    print("\nClosed 5-hour windows (last 24 h):")
    waste5 = [w for w in closed_window_waste(con, "5h")
               if w["resets_at"] >= _hours_ago_str(24)]
    if waste5:
        for w in waste5[-12:]:   # cap at 12 lines
            bar_used = int(w["final_pct"] / 5)
            bar_str  = "█" * bar_used + "░" * (20 - bar_used)
            print(f"  {w['resets_at']}  [{bar_str}] {w['final_pct']:.0f}% used, "
                  f"{w['unused_pct']:.0f}% wasted")
    else:
        print("  (no closed windows in the last 24 h)")

    print("\nClosed 7-day windows (all time):")
    waste7 = closed_window_waste(con, "7d")
    if waste7:
        for w in waste7:
            bar_used = int(w["final_pct"] / 5)
            bar_str  = "█" * bar_used + "░" * (20 - bar_used)
            print(f"  {w['resets_at']}  [{bar_str}] {w['final_pct']:.0f}% used, "
                  f"{w['unused_pct']:.0f}% wasted")
    else:
        print("  (no closed 7-day windows yet)")

    # Daily breakdown
    days = daily_breakdown(con)
    if days:
        print(f"\nDaily breakdown (last {min(len(days), 7)} days):")
        print(f"  {'Day':10}  {'max5h%':>7}  {'max7d%':>7}  {'longest idle (5h)':>18}")
        for d in days[-7:]:
            idle_str = f"{d['longest_flat_5h_minutes']} min ({d['longest_flat_5h_readings']} readings)"
            print(f"  {d['day']:10}  {d['max_5h_pct']:>7.1f}  {d['max_7d_pct']:>7.1f}  {idle_str:>18}")
    print()


def _hours_ago_str(hours: int) -> str:
    from datetime import timedelta
    dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Claude usage underutilisation report")
    parser.add_argument("--status", action="store_true",
                        help="Machine-readable JSON verdict (exits 1 if underutilised)")
    parser.add_argument("--window", choices=["5h", "7d"], default="5h",
                        help="Window to key off for --status verdict (default: 5h)")
    parser.add_argument("--db", default=None,
                        help="Path to usage.db (overrides config.json log_db)")
    args = parser.parse_args()

    cfg       = load_config()
    db_path   = resolve_db(cfg, args.db)
    threshold = float(cfg.get("underutil_rate_per_hr", _DEFAULT_RATE_THRESHOLD))
    con       = open_db(db_path)

    if args.status:
        s5  = latest_window_status(con, "5h", threshold)
        s7d = latest_window_status(con, "7d", threshold)
        key = args.window
        verdict_src = s5 if key == "5h" else s7d
        underutilized = bool(verdict_src.get("underutilized"))
        result = {
            "underutilized": underutilized,
            "window_key":    key,
            "five_hour":     s5,
            "seven_day":     s7d,
        }
        print(json.dumps(result))
        sys.exit(1 if underutilized else 0)
    else:
        print_human_report(con, threshold)


if __name__ == "__main__":
    main()
