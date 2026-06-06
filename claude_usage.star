"""
Applet: Claude Usage
Summary: Claude Code session & weekly usage
Description: Shows Claude Code subscription usage — 5-hour session window and
             7-day weekly allocation, with a reset countdown. Either window can
             be the highlighted "hero" row via the `hero` config key ("5h" or "7d").
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

# Fonts: the size contrast between the hero and secondary rows is the main cue
# for which window matters most. Hero is the larger font, secondary the small one.
HERO_FONT = "tb-8"
SEC_FONT  = "CG-pixel-3x5-mono"

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
DEFAULT_DATA = """{"five_hour_pct":45,"five_hour_resets_at":"2026-01-01T03:00:00Z","seven_day_pct":32,"seven_day_resets_at":"2026-01-07T00:00:00Z","extra_enabled":false,"extra_used":0,"extra_limit":0,"extra_pct":0,"hero":"5h"}"""

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
    """Return a short countdown string: '5d17h', '2h14m', '45m', or a status."""
    if not resets_at_str:
        return "Not started"
    reset_time  = time.parse_time(resets_at_str)
    diff        = reset_time - time.now()
    total_secs  = int(diff.seconds)
    if total_secs <= 60:
        return "Usage reset"
    days  = total_secs // 86400
    hours = (total_secs % 86400) // 3600
    mins  = (total_secs % 3600) // 60
    if days > 0:
        return "%dd%dh left" % (days, hours)
    if hours > 0:
        return "%dh%dm left" % (hours, mins)
    return "%dm left" % mins

def usage_row(label, pct, is_hero):
    """
    One usage line: label + progress bar + percentage.

    The hero row uses the larger font in white with a taller/wider bar; the
    secondary row is dimmed and uses the small font with a thinner bar.
    """
    color = usage_color(pct)
    if is_hero:
        return render.Row(
            expanded    = True,
            main_align  = "space_between",
            cross_align = "center",
            children = [
                render.Text(content = label,             font = HERO_FONT, color = COLOR_WHITE),
                render.Padding(pad = (0, 0, 2, 0), child = progress_bar(pct, color, width = 30, height = 4)),
                render.Text(content = "%d%%" % pct,       font = HERO_FONT, color = COLOR_WHITE),
            ],
        )
    return render.Row(
        expanded    = True,
        main_align  = "space_between",
        cross_align = "center",
        children = [
            render.Text(content = label,             font = SEC_FONT, color = COLOR_DIM),
            progress_bar(pct, color, width = 38, height = 2),
            render.Text(content = "%d%%" % pct,       font = SEC_FONT, color = COLOR_DIM),
        ],
    )

# ── Main ─────────────────────────────────────────────────────────────────────

def main(config):
    data_str = config.get("data") or DEFAULT_DATA
    data = json.decode(data_str)

    five_pct     = int(data.get("five_hour_pct")    or 0)
    five_resets  = data.get("five_hour_resets_at")  or ""
    seven_pct    = int(data.get("seven_day_pct")    or 0)
    seven_resets = data.get("seven_day_resets_at")  or ""
    hero         = data.get("hero")                 or "5h"

    # The countdown tracks whichever window is the hero.
    if hero == "7d":
        countdown = format_countdown(seven_resets)
        hero_row  = usage_row("7D", seven_pct, True)
        sec_row   = usage_row("5h", five_pct,  False)
    else:
        countdown = format_countdown(five_resets)
        hero_row  = usage_row("5H", five_pct,  True)
        sec_row   = usage_row("7d", seven_pct, False)

    # ── Row 1: Claude mascot (left)  ·  reset countdown (right) ──
    header = render.Row(
        expanded    = True,
        main_align  = "space_between",
        cross_align = "center",
        children = [
            mascot(),
            render.Text(content = countdown, font = SEC_FONT, color = COLOR_WHITE),
        ],
    )

    return render.Root(
        child = render.Padding(
            pad = (2, 2, 2, 2),
            child = render.Column(
                expanded    = True,
                main_align  = "space_evenly",
                cross_align = "center",
                children    = [header, hero_row, sec_row],
            ),
        ),
    )
