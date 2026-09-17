#!/usr/bin/env bash
#
# OmaHud installer. Safe to re-run: rewrites menu + theme-set hook.
# Does NOT replace MangoHud.conf — only colour keys on sync/set.
#
# Flags:
#   --quiet   less chatter (used by the shell service on startup)
#
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
quiet=0
for arg in "$@"; do
  case $arg in
    --quiet) quiet=1 ;;
  esac
done

note() { (( quiet )) || printf 'omahud: %s\n' "$1"; }
warn() { printf 'omahud: %s\n' "$1" >&2; }

plugin_id="io.github.alxwolfenstein97.omahud"
hooks="$HOME/.config/omarchy/hooks/theme-set.d"
state="$HOME/.local/state/omarchy/omahud"

mkdir -p "$hooks" "$state" "$HOME/.config/MangoHud"

chmod 755 "$here"/bin/* "$here/omarchy/theme-set-hook" "$here/check.sh" \
  "$here/install.sh" "$here/uninstall.sh" 2>/dev/null || true

export OMAHUD_PLUGIN_DIR="$here"

# Packages need sudo. Interactive install can ask in this TTY; Service --quiet
# cannot — open one floating terminal (once) so the password prompt is reachable.
pull_pkgs() {
  local -a missing=()
  local pkg
  for pkg in "$@"; do
    pacman -Q "$pkg" &>/dev/null || missing+=("$pkg")
  done
  if ((${#missing[@]} == 0)); then
    rm -f "$state/pkgs-prompted"
    return 0
  fi

  if ! command -v omarchy >/dev/null 2>&1; then
    warn "install manually: pacman -S ${missing[*]}"
    return 1
  fi

  note "installing ${missing[*]}"
  if (( ! quiet )) && [[ -t 0 || -t 1 ]]; then
    if omarchy pkg add "${missing[@]}"; then
      rm -f "$state/pkgs-prompted"
      return 0
    fi
    warn "could not install: ${missing[*]}"
    return 1
  fi

  if [[ -f $state/pkgs-prompted ]]; then
    warn "still missing ${missing[*]} — run: omarchy pkg add ${missing[*]}"
    return 1
  fi
  mkdir -p "$state"
  touch "$state/pkgs-prompted"
  local cmd="omarchy pkg add ${missing[*]}"
  if command -v omarchy-launch-floating-terminal-with-presentation >/dev/null 2>&1; then
    warn "sudo needed for ${missing[*]} — opening a floating terminal"
    omarchy-launch-floating-terminal-with-presentation "$cmd" >/dev/null 2>&1 &
  else
    warn "run: $cmd"
  fi
  return 1
}

# Pillow draws Style carousel mockups — install before warming previews.
# Do NOT pull mangohud / goverlay (same idea as OmaOBS not pulling OBS): this
# plugin is optional paint for people who already run the overlay.
pull_pkgs python-pillow || true
if ! pacman -Q mangohud &>/dev/null; then
  warn "mangohud not installed — install it (and optionally goverlay) yourself; OmaHud only retints an existing conf"
elif [[ ! -f $HOME/.config/MangoHud/MangoHud.conf ]]; then
  warn "no ~/.config/MangoHud/MangoHud.conf yet — set metrics in Goverlay (or copy a conf), then omahud sync"
fi

# ------------------------------------------------------------------- theme hook
# Prefer OmaHud over any legacy full-file mangohud theme hook.
rm -f "$hooks/mangohud"
install -m 755 "$here/omarchy/theme-set-hook" "$hooks/omahud"
note "hook: $hooks/omahud"

# ------------------------------------------------------------------------ menu
menu_lock="$HOME/.local/state/omarchy/style-extenders/menu.lock"
menu_sha="$HOME/.local/state/omarchy/style-extenders/menu.sha"
menu_file="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
mkdir -p "$(dirname "$menu_lock")"
(
  flock 9
  "$here/bin/omahud" install-menu
  if command -v omarchy-shell >/dev/null 2>&1 && [[ -f $menu_file ]]; then
    new_sha=$(sha256sum "$menu_file" 2>/dev/null | awk '{print $1}')
    old_sha=$(cat "$menu_sha" 2>/dev/null || true)
    if [[ -n $new_sha && $new_sha != "$old_sha" ]]; then
      omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true
      omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
      printf '%s\n' "$new_sha" >"$menu_sha"
    fi
  fi
) 9>"$menu_lock"
if (( ! quiet )); then
  note "Style → HUD Themes is live; if the row is missing, run: omarchy-shell shell rescanPlugins"
fi

# ----------------------------------------------------------- initial apply/sync
if command -v omarchy >/dev/null 2>&1; then
  if (( ! quiet )) || [[ ! -f $state/synced ]]; then
    if [[ -f $HOME/.config/MangoHud/MangoHud.conf ]] \
      && "$here/bin/omahud-sync" --quiet >/dev/null 2>&1; then
      touch "$state/synced"
      note "synced MangoHud colours to current Omarchy palette"
    else
      warn "initial sync skipped (no MangoHud.conf yet? set metrics in Goverlay first)"
    fi
  fi
fi

if (( ! quiet )); then
  (
    "$here/bin/omahud" preview >/dev/null 2>&1 || true
  ) &
fi

if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin enable "$plugin_id" >/dev/null 2>&1 || true
fi

note "done — Style > HUD Themes, or '$here/bin/omahud switcher'"
note "colours only — Goverlay keeps owning metrics / layout / keybinds"
exit 0
