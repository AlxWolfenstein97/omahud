#!/usr/bin/env bash
#
# Clean-slate: menu, theme-set hook, cache/state. Restores MangoHud colour
# backup via `omahud clear` while colors.bak still exists, then wipes state.
#
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_id="io.github.alxwolfenstein97.omahud"
hooks="$HOME/.config/omarchy/hooks/theme-set.d"
state="$HOME/.local/state/omarchy/omahud"
cache="$HOME/.cache/omarchy/omahud"
menu_lock="$HOME/.local/state/omarchy/style-extenders/menu.lock"

note() { printf 'omahud: %s\n' "$1"; }

export OMAHUD_PLUGIN_DIR="$here"

# Restore pre-OmaHud colours while the backup still exists.
if [[ -f $state/colors.bak ]]; then
  "$here/bin/omahud" clear --quiet 2>/dev/null || true
  note "restored MangoHud colours from backup"
fi

mkdir -p "$(dirname "$menu_lock")"
(
  flock 9
  "$here/bin/omahud" uninstall-menu 2>/dev/null || true
) 9>"$menu_lock"
rm -f "$hooks/omahud"
note "removed theme-set hook"

rm -rf "$state" "$cache"
mkdir -p "$state"
touch "$state/uninstalled"
note "cleared state/cache (tombstone left so quiet install cannot resurrect)"

omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true
omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true

if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin disable "$plugin_id" >/dev/null 2>&1 || true
fi

note "done — no omahud menu/hook left; colour backup restored when present"
note "plugin files remain at $here until you omit/remove the plugin"
note "optional: omarchy pkg drop python-pillow  # if nothing else needs Pillow"
note "if colours still look themed: no pre-OmaHud colors.bak existed (paint stays)"
exit 0
