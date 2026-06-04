# tidbyt-claude-usage

A [Tidbyt](https://tidbyt.com) Pixlet app that shows your **Claude Code subscription usage** on the 64×32 LED display.

**Row 1:** Claude Code pixel-art mascot (left) + countdown to 5-hour reset (right)  
**Row 2:** 5-hour session window — "5H" label + progress bar + utilisation %  
**Row 3:** 7-day weekly allocation — "7d" label + mini progress bar + utilisation %  
**Color coding:** green < 70 % → amber 70–89 % → red ≥ 90 %

```
[▐▛███▜▌]              2h14m
5H [████████████████  ] 88%
7d [████              ] 13%
```

---

## Requirements

| Tool | Notes |
|------|-------|
| `pixlet` | `/usr/local/bin/pixlet` — already installed |
| `python3` | stdlib only, no pip deps |
| Claude Code | Running (keeps the OAuth token fresh) |
| Tidbyt device | Physical device + API token |

---

## Setup

### 1. Get your Tidbyt credentials

In the **Tidbyt mobile app**:
1. Tap your device → **Settings** → **Get API key**
2. Copy the **Device ID** and **API Token**

### 2. Create `config.json`

```bash
cp config.example.json config.json
```

Edit `config.json`:
```json
{
  "device_id":       "abc123xyz",
  "api_token":       "tidbyt_...",
  "installation_id": "claude-usage"
}
```

> `config.json` is gitignored — never commit it.

### 3. Preview in browser (no device needed)

```bash
make serve
# or: pixlet serve claude_usage.star
```

Opens a live preview at `http://localhost:8080` using the built-in mock data.

### 4. Test with live data

```bash
make dry-run     # print fetched JSON — no render/push
make render      # render to /tmp/claude_usage.webp with live data
```

### 5. Push once to the device

```bash
make push
```

### 6. Install the cron job (every 5 minutes)

```bash
make install-cron   # shows the line and prompts before modifying crontab
```

Or add it manually:
```
*/5 * * * * cd /path/to/tidbyt-ai-usage && /usr/bin/python3 update_tidbyt.py >> /tmp/tidbyt-claude.log 2>&1
```

Check logs:
```bash
tail -f /tmp/tidbyt-claude.log
```

---

## Systemd timer alternative (Proxmox / Linux)

More robust than cron on systemd hosts:

**`/etc/systemd/system/tidbyt-claude.service`**
```ini
[Unit]
Description=Push Claude usage to Tidbyt

[Service]
Type=oneshot
User=andre
WorkingDirectory=/home/andre/repos/tidbyt-ai-usage
ExecStart=/usr/bin/python3 /home/andre/repos/tidbyt-ai-usage/update_tidbyt.py
StandardOutput=journal
StandardError=journal
```

**`/etc/systemd/system/tidbyt-claude.timer`**
```ini
[Unit]
Description=Run Tidbyt Claude usage update every 5 min

[Timer]
OnBootSec=60
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tidbyt-claude.timer
journalctl -fu tidbyt-claude.service
```

---

## How the data source works

The script reads your OAuth access token from `~/.claude/.credentials.json`
(maintained by the Claude Code daemon) and calls an undocumented Anthropic endpoint:

```
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <token>
User-Agent: claude-code/<version>
anthropic-beta: oauth-2025-04-20
```

Response fields used:

| Field | Meaning |
|-------|---------|
| `five_hour.utilization` | Session window usage (%) |
| `five_hour.resets_at` | When the 5-hour window resets |
| `seven_day.utilization` | Weekly usage (%) |
| `seven_day.resets_at` | When the weekly window resets |
| `extra_usage.*` | Pay-as-you-go credit usage (ignored by display) |

> **Note:** This endpoint is undocumented and may change.  The `claude-code` User-Agent
> is required; without it the endpoint aggressively rate-limits (429).
> The 5-minute update cadence avoids hammering the endpoint.

### Token refresh

The Claude Code daemon refreshes the token automatically.  **Do not** add an independent
refresh here — Anthropic rotates the `refreshToken` on every refresh, so two concurrent
refreshers will invalidate each other's tokens.  If you see 401 errors, open Claude Code
to trigger a fresh authentication.

---

## Files

```
claude_usage.star       Starlark/Pixlet app (pure presentation)
update_tidbyt.py        Python wrapper: fetch → render → push
config.example.json     Config template (copy to config.json)
config.json             Your real config (gitignored)
mock_usage.json         Raw API mock for offline testing
Makefile                Convenience targets
.gitignore
README.md
```
