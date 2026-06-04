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
COLOR_GREEN   = "#00C853"   # < 70 % — all good
COLOR_AMBER   = "#FFB300"   # 70–89 % — getting full
COLOR_RED     = "#FF3D00"   # ≥ 90 % — almost out
COLOR_DIM     = "#555555"   # labels / secondary
COLOR_WHITE   = "#FFFFFF"   # Pure white
COLOR_TRACK   = "#222222"   # progress bar track background
COLOR_MASCOT  = "#D97757"   # Anthropic / Claude brand orange

# ── Claude Code mascot (18 × 5, '#' = on, '.' = transparent) ────────────────
# Derived from the block-char mascot shown in the Claude Code CLI:
#   ▐▛███▜▌
#  ▝▜█████▛▘
#    ▘▘ ▝▝
# Each block char encodes a 2-wide × 2-tall pixel cell; the 5 rows below
# are the top/bottom halves of the 3 terminal lines (bottom of line 3 = all off).
MASCOT_PIXELS = [
    "...############...",   # top    of terminal line 1
    "...##.######.##...",   # bottom of terminal line 1  (eye-socket gaps at col 5 & 12)
    ".################.",   # top    of terminal line 2  (widest — shoulders)
    "...############...",   # bottom of terminal line 2
    "....#.#....#.#....",   # top    of terminal line 3  (feet)
]

# ── Fallback mock data for `pixlet serve` without --config ───────────────────
DEFAULT_DATA = """{"five_hour_pct":45,"five_hour_resets_at":"2026-01-01T03:00:00Z","seven_day_pct":32,"seven_day_resets_at":"2026-01-07T00:00:00Z","extra_enabled":false,"extra_used":0,"extra_limit":0,"extra_pct":0}"""

BAR_WIDTH  = 60
BAR_HEIGHT = 3

# ── Helpers ──────────────────────────────────────────────────────────────────

def mascot():
    """Render MASCOT_PIXELS as an 18×5 pixel-art widget."""
    rows = []
    for row_str in MASCOT_PIXELS:
        cells = []
        for i in range(len(row_str)):
            c = COLOR_MASCOT if row_str[i] == "#" else "#000000"
            cells.append(render.Box(width = 1, height = 2, color = c))
        rows.append(render.Row(children = cells))
    return render.Column(children = rows)

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
        return "%dh%dm left" % (hours, mins)
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

    # ── Row 1: Claude mascot (left)  ·  reset countdown (right) ──
    header = render.Row(
        expanded    = True,
        main_align  = "space_between",
        cross_align = "center",
        children = [
            mascot(),
            render.Text(content = countdown, font = "CG-pixel-3x5-mono", color = COLOR_WHITE),
        ],
    )

    # ── Row 3: 5-hour progress bar ──
    # Layout: "5h " + full bar (44px) + " XX%"
    primary = render.Row(
        expanded    = True,
        main_align  = "space_between",
        cross_align = "center",
        children = [
            render.Text(content = "5H",               font = "CG-pixel-3x5-mono", color = COLOR_WHITE),
            progress_bar(five_pct, hero_color, width = 38, height = 3),
            render.Text(content = "%d%%" % five_pct, font = "CG-pixel-3x5-mono", color = COLOR_WHITE),
        ],
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
                children    = [header, primary, secondary],
            ),
        ),
    )
