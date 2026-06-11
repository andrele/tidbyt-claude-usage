REPO_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
STAR     := $(REPO_DIR)claude_usage.star
OUT_WEBP := /tmp/claude_usage.webp

# ── Local preview ─────────────────────────────────────────────────────────────

## Open the app in a browser with mock data (no config needed)
serve:
	pixlet serve $(STAR)

## Render to WebP using live data (requires Claude Code running)
render:
	python3 $(REPO_DIR)update_tidbyt.py --print-data | \
	  xargs -I{} pixlet render $(STAR) data='{}' -o $(OUT_WEBP) && \
	echo "Rendered to $(OUT_WEBP)"

## Render using the embedded mock data
render-mock:
	pixlet render $(STAR) -o $(OUT_WEBP)
	@echo "Rendered to $(OUT_WEBP)"

# ── Dry-run / debug ───────────────────────────────────────────────────────────

## Fetch and print live usage JSON without rendering or pushing
dry-run:
	python3 $(REPO_DIR)update_tidbyt.py --dry-run

## Print only the pre-processed data that would be passed to the .star file
print-data:
	python3 $(REPO_DIR)update_tidbyt.py --print-data

# ── Push ──────────────────────────────────────────────────────────────────────

## Fetch usage + render + push to the Tidbyt device (requires config.json)
push:
	python3 $(REPO_DIR)update_tidbyt.py

# ── Cron installer ────────────────────────────────────────────────────────────

## Show the cron line that would be installed (does not modify crontab)
show-cron:
	@echo "*/5 * * * * cd $(REPO_DIR) && /usr/bin/python3 update_tidbyt.py >> /tmp/tidbyt-claude.log 2>&1"

## Install the cron job (runs every 5 minutes; prompts before modifying crontab)
install-cron:
	@echo "The following line will be appended to your crontab:"
	@echo "  */5 * * * * cd $(REPO_DIR) && /usr/bin/python3 update_tidbyt.py >> /tmp/tidbyt-claude.log 2>&1"
	@read -p "Proceed? [y/N] " ans && [ "$$ans" = "y" ] || exit 0 && \
	  (crontab -l 2>/dev/null; echo "*/5 * * * * cd $(REPO_DIR) && /usr/bin/python3 update_tidbyt.py >> /tmp/tidbyt-claude.log 2>&1") | crontab -
	@echo "Cron job installed."

# ── macOS launchd agent ───────────────────────────────────────────────────────

## (macOS) Install a launchd agent that pushes every 5 min (recommended over cron)
install-launchd:
	@bash $(REPO_DIR)scripts/macos-launchd.sh install

## (macOS) Stop and remove the launchd agent
uninstall-launchd:
	@bash $(REPO_DIR)scripts/macos-launchd.sh uninstall

## (macOS) Show launchd agent status
status-launchd:
	@bash $(REPO_DIR)scripts/macos-launchd.sh status

.PHONY: serve render render-mock dry-run print-data push show-cron install-cron install-launchd uninstall-launchd status-launchd
