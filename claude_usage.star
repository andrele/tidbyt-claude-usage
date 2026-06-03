"""
Applet: Claude Usage
Summary: Claude Code session & weekly usage
Description: Shows Claude Code subscription usage — 5-hour session window (hero)
             and 7-day weekly allocation, with reset countdown.
Author: Andre Le
"""

load("encoding/json.star", "json")
load("render.star", "render")
load("time.star", "time")

# ── Colors ──────────────────────────────────────────────────────────────────
COLOR_GREEN = "#00C853"   # < 70 % — all good
COLOR_AMBER = "#FFB300"   # 70–89 % — getting full
COLOR_RED   = "#FF3D00"   # ≥ 90 % — almost out
COLOR_DIM   = "#555555"   # labels / secondary
COLOR_TRACK = "#222222"   # progress bar track background

# ── Fallback mock data for `pixlet serve` without --config ───────────────────
DEFAULT_DATA = """{"five_hour_pct":45,"five_hour_resets_at":"2026-01-01T03:00:00Z","seven_day_pct":32,"seven_day_resets_at":"2026-01-07T00:00:00Z","extra_enabled":false,"extra_used":0,"extra_limit":0,"extra_pct":0}"""

BAR_WIDTH  = 60
BAR_HEIGHT = 3

# ── Helpers ──────────────────────────────────────────────────────────────────

def usage_color(pct):
    """Pick a color based on utilisation percentage."""
    if pct >= 90:
        return COLOR_RED
    elif pct >= 70:
        return COLOR_AMBER
    return COLOR_GREEN

def progress_bar(pct, color, width = BAR_WIDTH, height = BAR_HEIGHT):
    """Render a two-segment (filled / track) horizontal bar."""
    fill_w  = int(width * pct / 100)
    if fill_w > width:
        fill_w = width
    empty_w = width - fill_w

    segs = []
    if fill_w > 0:
        segs.append(render.Box(width = fill_w,  height = height, color = color))
    if empty_w > 0:
        segs.append(render.Box(width = empty_w, height = height, color = COLOR_TRACK))
    return render.Row(children = segs)

def format_countdown(resets_at_str):
    """Return a short countdown string: '2h14m', '45m', or 'now'."""
    if not resets_at_str:
        return "?"
    reset_time  = time.parse_time(resets_at_str)
    diff        = reset_time - time.now()
    total_secs  = int(diff.seconds)
    if total_secs <= 60:
        return "now"
    hours = total_secs // 3600
    mins  = (total_secs % 3600) // 60
    if hours > 0:
        return "%dh%dm" % (hours, mins)
    return "%dm" % mins

# ── Main ─────────────────────────────────────────────────────────────────────

def main(config):
    data_str = config.get("data") or DEFAULT_DATA
    data = json.decode(data_str)

    five_pct    = int(data.get("five_hour_pct")    or 0)
    five_resets = data.get("five_hour_resets_at")  or ""
    seven_pct   = int(data.get("seven_day_pct")    or 0)

    hero_color  = usage_color(five_pct)
    seven_color = usage_color(seven_pct)
    countdown   = format_countdown(five_resets)

    # ── Row 1: "CLAUDE" label  ·  reset countdown (right) ──
    header = render.Row(
        expanded    = True,
        main_align  = "space_between",
        cross_align = "center",
        children = [
            render.Text(content = "CLAUDE",   font = "CG-pixel-3x5-mono", color = COLOR_DIM),
            render.Text(content = countdown,  font = "CG-pixel-3x5-mono", color = COLOR_DIM),
        ],
    )

    # ── Row 2: hero utilisation % (large, colour-coded) ──
    hero = render.Row(
        expanded    = True,
        main_align  = "center",
        cross_align = "center",
        children = [
            render.Text(
                content = "%d%%" % five_pct,
                font    = "5x8",
                color   = hero_color,
            ),
        ],
    )

    # ── Row 3: 5-hour progress bar ──
    bar_5h = render.Row(
        expanded    = True,
        main_align  = "center",
        cross_align = "center",
        children    = [progress_bar(five_pct, hero_color, width = BAR_WIDTH, height = BAR_HEIGHT)],
    )

    # ── Row 4: 7-day secondary line ──
    # Layout: "7d " + mini bar (44px) + " XX%"
    secondary = render.Row(
        expanded    = True,
        main_align  = "space_between",
        cross_align = "center",
        children = [
            render.Text(content = "7d",               font = "CG-pixel-3x5-mono", color = COLOR_DIM),
            progress_bar(seven_pct, seven_color, width = 38, height = 2),
            render.Text(content = "%d%%" % seven_pct, font = "CG-pixel-3x5-mono", color = COLOR_DIM),
        ],
    )

    return render.Root(
        child = render.Padding(
            pad = (2, 2, 2, 2),
            child = render.Column(
                expanded    = True,
                main_align  = "space_evenly",
                cross_align = "center",
                children    = [header, hero, bar_5h, secondary],
            ),
        ),
    )
