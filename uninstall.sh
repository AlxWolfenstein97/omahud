#!/usr/bin/env bash
#
# Clean-slate: menu, theme-set hook, cache/state. Leaves MangoHud.conf (and the
# colour backup under state — cleared with the rest of state) alone as paint on
# disk; run `omahud clear` first if you want pre-OmaHud colours restored.
#
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_id="io.github.alxwolfenstein97.omahud"
hooks="$HOME/.config/omarchy/hooks/theme-set.d"
state="$HOME/.local/state/omarchy/omahud"
cache="$HOME/.cache/omarchy/omahud"

note() { printf 'omahud: %s\n' "$1"; }

export OMAHUD_PLUGIN_DIR="$here"
"$here/bin/omahud" uninstall-menu 2>/dev/null || true
rm -f "$hooks/omahud"
note "removed theme-set hook"

rm -rf "$state" "$cache"
note "cleared state/cache"

omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true

if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin disable "$plugin_id" >/dev/null 2>&1 || true
fi

note "done — no omahud menu/hook left; MangoHud.conf untouched"
note "optional: omahud clear   # restore pre-OmaHud colours (run before uninstall if you still want the backup)"
note "plugin files remain at $here until you omit/remove the plugin"
note "optional: omarchy pkg drop python-pillow  # if nothing else needs Pillow"
note "optional: omarchy pkg drop mangohud       # if you no longer want the overlay"
exit 0
