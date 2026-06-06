# tidbyt-claude-usage

A [Tidbyt](https://tidbyt.com) Pixlet app that shows your **Claude Code subscription usage** on the 64×32 LED display.

**Row 1:** Claude Code pixel-art mascot (left) + countdown to 7-day reset (right)  
**Row 2:** 7-day weekly allocation (hero) — "7D" label + progress bar + utilisation %  
**Row 3:** 5-hour session window — "5h" label + mini progress bar + utilisation %  
**Color coding:** green < 70 % → amber 70–89 % → red ≥ 90 %

```
 ▐▛███▜▌
▝▜█████▛▘          5d17h left
  ▘▘ ▝▝
7D [██████            ] 31%
5h [████████          ] 41%
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
  "installation_id": "claudeusage"
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

## Windows setup

The Python wrapper is cross-platform. On Windows:

### 1. Install pixlet

Download the Windows build from the [pixlet releases](https://github.com/tidbyt/pixlet/releases)
and extract `pixlet.exe` somewhere stable (e.g. inside this repo, which is gitignored).

### 2. Create `config.json`

Same as above, but add `pixlet_bin` pointing at the binary so a scheduled task finds it
regardless of PATH:

```json
{
  "device_id":       "abc123xyz",
  "api_token":       "tidbyt_...",
  "installation_id": "claudeusage",
  "pixlet_bin":      "C:/Users/you/tidbyt-claude-usage/pixlet.exe"
}
```

### 3. Push once

```powershell
python update_tidbyt.py
```

### 4. Schedule every 5 minutes (Task Scheduler)

Copy `run.cmd.example` to `run.cmd` (gitignored) and adjust the Python path if needed, then:

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\path\to\tidbyt-claude-usage\run.cmd"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
              -ExecutionTimeLimit (New-TimeSpan -Minutes 4)
Register-ScheduledTask -TaskName "TidbytClaudeUsage" -Action $action -Trigger $trigger `
  -Settings $settings -Description "Push Claude usage to Tidbyt every 5 minutes"
```

Logs land in `%TEMP%\tidbyt-claude.log`.

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
run.cmd.example         Windows Task Scheduler wrapper (copy to run.cmd)
mock_usage.json         Raw API mock for offline testing
Makefile                Convenience targets
.gitignore
README.md
```
