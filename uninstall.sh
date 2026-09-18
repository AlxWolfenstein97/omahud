#!/usr/bin/env bash
#
# Menu, theme-set hook, cache/state. Restores MangoHud colour backup via
# `omahud clear` while colors.bak still exists. Optional floating terminal for
# shared package drop. Hardened contrast / goverlay sync behaviour is kept —
# uninstall does not touch layout or metrics beyond colour restore.
#
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_id="io.github.alxwolfenstein97.omahud"
hooks="$HOME/.config/omarchy/hooks/theme-set.d"
state="$HOME/.local/state/omarchy/omahud"
cache="$HOME/.cache/omarchy/omahud"
menu_lock="$HOME/.local/state/omarchy/style-extenders/menu.lock"

note() { printf 'omahud: %s\n' "$1"; }

offer_pkg_drop() {
  local -a have=()
  local pkg
  for pkg in "$@"; do
    pacman -Q "$pkg" &>/dev/null && have+=("$pkg")
  done
  ((${#have[@]})) || return 0
  local list="${have[*]}"
  local script="$state/uninstall-floater.sh"
  mkdir -p "$state"
  {
    printf '%s\n' '#!/usr/bin/env bash' 'set -uo pipefail'
    printf '%s\n' "printf '%s\n' 'OmaHud — uninstall'"
    printf '%s\n' "printf '%s\n' '────────────────────────────────'"
    printf '%s\n' "printf '%s\n' 'Optional — drop shared packages only if nothing else needs them:'"
    for pkg in "${have[@]}"; do
      case $pkg in
        python-pillow) printf '%s\n' "printf '  • %s — %s\n' 'python-pillow' 'Style carousel mockups'" ;;
        python-numpy) printf '%s\n' "printf '  • %s — %s\n' 'python-numpy' 'Adwaita cursor remaps'" ;;
        adw-gtk-theme) printf '%s\n' "printf '  • %s — %s\n' 'adw-gtk-theme' 'GTK theme Chroma paints'" ;;
        *) printf '%s\n' "printf '  • %s\n' $(printf %q "$pkg")" ;;
      esac
    done
    printf '%s\n' "printf '%s\n' '────────────────────────────────'"
    printf '%s\n' "printf '%s\n' ''"
    printf '%s\n' "read -r -p 'Drop ${list}? [y/N] ' a"
    printf '%s\n' 'case $a in'
    printf '%s\n' "  [yY]|[yY][eE][sS]) omarchy pkg drop ${list} ;;"
    printf '%s\n' "  *) printf 'skipped package drop\n' ;;"
    printf '%s\n' 'esac'
  } >"$script"
  chmod 755 "$script"
  if command -v omarchy-launch-floating-terminal-with-presentation >/dev/null 2>&1; then
    note "optional package drop — opening floating terminal"
    omarchy-launch-floating-terminal-with-presentation "bash $(printf %q "$script")" >/dev/null 2>&1 &
  else
    note "optional: omarchy pkg drop $list"
  fi
}


export OMAHUD_PLUGIN_DIR="$here"

# Tombstone + disable first so Service --quiet cannot resurrect the Style row.
mkdir -p "$state"
touch "$state/uninstalled"
if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin disable "$plugin_id" >/dev/null 2>&1 || true
fi

# Restore pre-OmaHud colours while the backup still exists (before state wipe).
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

rm -rf "$cache"
find "$state" -mindepth 1 ! -name uninstalled -delete 2>/dev/null || true
touch "$state/uninstalled"
note "cleared state/cache (tombstone left so quiet install cannot resurrect)"

omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true
omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true

offer_pkg_drop python-pillow

note "done — no omahud menu/hook left; colour backup restored when present"
note "plugin files remain at $here until you omit/remove the plugin"
note "if colours still look themed: no pre-OmaHud colors.bak existed (paint stays)"
exit 0
