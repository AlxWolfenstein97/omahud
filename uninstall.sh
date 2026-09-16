#!/usr/bin/env bash
# Remove OmaHud menu + theme-set hook. Leaves MangoHud.conf (and colour backup) alone.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export OMAHUD_PLUGIN_DIR="$here"

"$here/bin/omahud" uninstall-menu 2>/dev/null || true
rm -f "$HOME/.config/omarchy/hooks/theme-set.d/omahud"

if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin disable io.github.alxwolfenstein97.omahud >/dev/null 2>&1 || true
fi

printf 'omahud: uninstalled menu + hook (MangoHud.conf untouched)\n'
printf 'omahud: optional: omahud clear  # restore pre-OmaHud colours from backup\n'
printf 'omahud: optional: omarchy plugin remove io.github.alxwolfenstein97.omahud\n'
