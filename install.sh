#!/usr/bin/env bash
#
# OmaHud installer. Safe to re-run: theme-set hook always; menu written once
# (quiet skips rewrite when // omahud:start markers already exist).
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

# Tombstone from uninstall: Service --quiet must not resurrect wiring.
if [[ -f $state/uninstalled ]]; then
  if (( quiet )); then
    exit 0
  fi
  rm -f "$state/uninstalled"
fi

mkdir -p "$hooks" "$state" "$HOME/.config/MangoHud"

chmod 755 "$here"/bin/* "$here/omarchy/theme-set-hook" "$here/check.sh" \
  "$here/install.sh" "$here/uninstall.sh" 2>/dev/null || true

export OMAHUD_PLUGIN_DIR="$here"

# Packages need sudo. Interactive: header in this TTY. Service --quiet:
# one headed floating terminal once (pkgs-prompted). Headers name this plugin,
# what it does, and why each package is missing.
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
    warn "OmaHud needs ${missing[*]} for: Style → HUD Themes — MangoHud colour retints — install manually: pacman -S ${missing[*]}"
    return 1
  fi

  note "OmaHud needs ${missing[*]} — Style → HUD Themes — MangoHud colour retints"
  if (( ! quiet )) && [[ -t 0 || -t 1 ]]; then
    printf '%s\n' "OmaHud"
    printf '%s\n' "io.github.alxwolfenstein97.omahud"
    printf '%s\n' "Style → HUD Themes — MangoHud colour retints"
    printf '%s\n' "────────────────────────────────"
    printf '%s\n' "Needs to install (sudo / pacman):"
    for pkg in "${missing[@]}"; do
      case $pkg in
        python-pillow) printf '  • %s — %s\n' "$pkg" 'draw HUD Themes carousel mockups' ;;
        *) printf '  • %s\n' "$pkg" ;;
      esac
    done
    printf '%s\n' "────────────────────────────────"
    printf '%s\n' ""
    if omarchy pkg add "${missing[@]}"; then
      rm -f "$state/pkgs-prompted"
      return 0
    fi
    warn "OmaHud could not install: ${missing[*]}"
    return 1
  fi

  if [[ -f $state/pkgs-prompted ]]; then
    warn "OmaHud still missing ${missing[*]} (Style → HUD Themes — MangoHud colour retints) — run: omarchy pkg add ${missing[*]}"
    return 1
  fi
  mkdir -p "$state"
  touch "$state/pkgs-prompted"
  local script="$state/install-floater.sh"
  {
    printf '%s\n' '#!/usr/bin/env bash' 'set -uo pipefail'
    printf '%s\n' "printf '%s\\n' 'OmaHud'"
    printf '%s\n' "printf '%s\\n' 'io.github.alxwolfenstein97.omahud'"
    printf '%s\n' "printf '%s\\n' 'Style → HUD Themes — MangoHud colour retints'"
    printf '%s\n' "printf '%s\\n' '────────────────────────────────'"
    printf '%s\n' "printf '%s\\n' 'Needs to install (sudo / pacman):'"
    for pkg in "${missing[@]}"; do
      case $pkg in
        python-pillow) printf '%s\n' "printf '  • %s — %s\n' 'python-pillow' 'draw HUD Themes carousel mockups'" ;;
        *) printf '%s\n' "printf '  • %s\n' $(printf %q "$pkg")" ;;
      esac
    done
    printf '%s\n' "printf '%s\\n' '────────────────────────────────'"
    printf '%s\n' "printf '%s\\n' ''"
    printf '%s\n' "omarchy pkg add ${missing[*]}"
    if [[ -n ${PULL_PKGS_AFTER:-} ]]; then
      printf '%s\n' "$PULL_PKGS_AFTER"
    fi
  } >"$script"
  chmod 755 "$script"
  if command -v omarchy-launch-floating-terminal-with-presentation >/dev/null 2>&1; then
    warn "OmaHud missing ${missing[*]} (Style → HUD Themes — MangoHud colour retints) — opening floating terminal"
    omarchy-launch-floating-terminal-with-presentation "bash $(printf %q "$script")" >/dev/null 2>&1 &
  else
    warn "OmaHud: run omarchy pkg add ${missing[*]}"
  fi
  return 1
}



# Pillow draws Style carousel mockups — install before warming previews.
# Do NOT pull mangohud / goverlay (same idea as OmaOBS not pulling OBS): this
# plugin is optional paint for people who already run the overlay.
# Interactive: ask in this TTY. Quiet/Service: one floating terminal once
# (pkgs-prompted), never again on later boots if dismissed. Still never pulls mangohud.
pull_pkgs python-pillow || true
if ! pacman -Q mangohud &>/dev/null; then
  note "mangohud not on the box — OmaHud is paint-only; sync no-ops until you already run the overlay"
elif [[ ! -f $HOME/.config/MangoHud/MangoHud.conf ]]; then
  note "no MangoHud.conf yet — sync no-ops until one exists"
fi

# ------------------------------------------------------------------- theme hook
# Prefer OmaHud over any legacy full-file mangohud theme hook.
rm -f "$hooks/mangohud"
install -m 755 "$here/omarchy/theme-set-hook" "$hooks/omahud"
note "hook: $hooks/omahud"

# ------------------------------------------------------------------------ menu
# Interactive: always install-menu + normalize. Quiet: only if our markers are
# absent — do not rewrite/normalize omarchy-menu.jsonc on every shell start.
menu_lock="$HOME/.local/state/omarchy/style-extenders/menu.lock"
menu_sha="$HOME/.local/state/omarchy/style-extenders/menu.sha"
menu_file="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
mkdir -p "$(dirname "$menu_lock")"
(
  flock 9
  # Scrub Style rows for siblings removed via plugin remove (no uninstall.sh).
  scrubbed=0
  scrub_out=$(python3 - <<'ORPHANSCRUB' || true
from pathlib import Path
import re
menu = Path.home() / ".config/omarchy/extensions/omarchy-menu.jsonc"
if not menu.is_file():
    raise SystemExit(0)
plugins = Path.home() / ".config/omarchy/plugins"
pairs = [
    ("omacursor", "io.github.alxwolfenstein97.omacursor"),
    ("omaobs", "io.github.alxwolfenstein97.omaobs"),
    ("omaboot", "io.github.alxwolfenstein97.omaboot"),
    ("omavt", "io.github.alxwolfenstein97.omavt"),
    ("omatty", "io.github.alxwolfenstein97.omatty"),
    ("omahud", "io.github.alxwolfenstein97.omahud"),
]
text = menu.read_text(encoding="utf-8")
orig = text
for marker, pid in pairs:
    if (plugins / pid).is_dir():
        continue
    start, end = f"// {marker}:start", f"// {marker}:end"
    if start not in text:
        continue
    text = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\n?", "", text, flags=re.S)
if text != orig:
    menu.write_text(text, encoding="utf-8")
    print("scrubbed-orphan-style-menus")
ORPHANSCRUB
  )
  [[ $scrub_out == *scrubbed-orphan-style-menus* ]] && scrubbed=1
  write_menu=1
  if (( quiet )) && [[ -f $menu_file ]] && grep -qF '// omahud:start' "$menu_file"; then
    write_menu=0
  fi
  if (( write_menu )); then
    "$here/bin/omahud" install-menu
    if [[ -f $menu_file ]]; then
      new_sha=$(sha256sum "$menu_file" 2>/dev/null | awk '{print $1}')
      old_sha=$(cat "$menu_sha" 2>/dev/null || true)
      if [[ -n $new_sha && $new_sha != "$old_sha" ]]; then
        printf '%s\n' "$new_sha" >"$menu_sha"
        if command -v omarchy-shell >/dev/null 2>&1; then
          # Debounce refresh only when the menu was actually written.
          stamp="$HOME/.local/state/omarchy/style-extenders/menu.refresh"
          do_refresh=1
          if (( quiet )) && [[ -f $stamp ]]; then
            now=$(date +%s)
            then=$(stat -c %Y "$stamp" 2>/dev/null || echo 0)
            if (( now - then < 3 )); then
              do_refresh=0
            fi
          fi
          if (( do_refresh )); then
            touch "$stamp"
            omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true
            # Quiet Service installs need rescan too — otherwise Style rows
            # (esp. OBS Themes) stay invisible until a manual shell restart.
            omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
          fi
        fi
      fi
    fi
  fi
  if (( scrubbed && ! write_menu )); then
    if [[ -f $menu_file ]]; then
      new_sha=$(sha256sum "$menu_file" 2>/dev/null | awk '{print $1}')
      old_sha=$(cat "$menu_sha" 2>/dev/null || true)
      if [[ -n $new_sha && $new_sha != "$old_sha" ]]; then
        printf '%s\n' "$new_sha" >"$menu_sha"
      fi
    fi
    if command -v omarchy-shell >/dev/null 2>&1; then
      stamp="$HOME/.local/state/omarchy/style-extenders/menu.refresh"
      touch "$stamp"
      omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true
      omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
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
