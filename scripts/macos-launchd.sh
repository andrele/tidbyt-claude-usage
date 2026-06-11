#!/usr/bin/env bash
#
# macos-launchd.sh — manage the macOS launchd LaunchAgent that runs
# update_tidbyt.py every 5 minutes.
#
#   ./scripts/macos-launchd.sh install     # generate plist, load, run now
#   ./scripts/macos-launchd.sh uninstall   # stop and remove
#   ./scripts/macos-launchd.sh status      # show whether it's loaded
#
# A LaunchAgent is used instead of cron because it runs in the GUI login
# session, where reading the Claude OAuth token from the Keychain works
# reliably (cron on macOS frequently cannot access the login Keychain).
#
set -euo pipefail

LABEL="com.claudeusage.tidbyt"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REPO_DIR/com.claudeusage.tidbyt.plist.example"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="${PYTHON:-/usr/bin/python3}"
DOMAIN="gui/$(id -u)"

cmd="${1:-install}"

case "$cmd" in
  install)
    if [ ! -f "$TEMPLATE" ]; then
      echo "error: template not found: $TEMPLATE" >&2
      exit 1
    fi
    mkdir -p "$HOME/Library/LaunchAgents"
    sed -e "s|__PYTHON__|$PYTHON|g" \
        -e "s|__REPO_DIR__|$REPO_DIR|g" \
        "$TEMPLATE" > "$DEST"
    # Reload cleanly if it was already installed.
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$DEST"
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "Installed $LABEL"
    echo "  plist:   $DEST"
    echo "  runs:    $PYTHON $REPO_DIR/update_tidbyt.py  (every 5 minutes)"
    echo "  logs:    tail -f /tmp/tidbyt-claude.log"
    echo
    echo "First run may prompt to allow python3 to read the 'Claude Code-credentials'"
    echo "Keychain item — click 'Always Allow' so unattended runs succeed."
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$DEST"
    echo "Removed $LABEL"
    ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      launchctl print "$DOMAIN/$LABEL" | grep -E "state =|program =|path =|last exit code" || true
    else
      echo "Not loaded. Run: make install-launchd"
    fi
    ;;
  *)
    echo "usage: $0 {install|uninstall|status}" >&2
    exit 2
    ;;
esac
