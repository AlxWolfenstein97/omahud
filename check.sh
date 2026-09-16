#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export OMAHUD_PLUGIN_DIR="$here"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

export OMAHUD_HOME="$tmp"
export OMAHUD_STATE_DIR="$tmp/state"
export OMAHUD_CACHE_DIR="$tmp/cache"
export OMAHUD_MANGOHUD_CONF="$tmp/MangoHud/MangoHud.conf"
export OMAHUD_GOVERLAY_GAMECONFIG="$tmp/.local/share/goverlay/gameconfig"
mkdir -p "$tmp/MangoHud" "$tmp/.config/omarchy/themes/fixture" "$tmp/state" "$tmp/cache"
mkdir -p "$tmp/.config/omarchy/extensions"

# minimal theme
cat >"$tmp/.config/omarchy/themes/fixture/colors.toml" <<'EOF'
background = "#111111"
foreground = "#eeeeee"
bright_foreground = "#ffffff"
accent = "#4488ff"
red = "#ff0000"
yellow = "#ffff00"
green = "#00ff00"
cyan = "#00ffff"
magenta = "#ff00ff"
EOF

# layout-heavy conf — colours should change, metrics stay
mkdir -p "$tmp/MangoHud" "$tmp/.local/share/goverlay/gameconfig/global"
cat >"$tmp/MangoHud/MangoHud.conf" <<'EOF'
legacy_layout=0
background_alpha=0.6
background_color=000000
text_color=AAAAAA
position=top-left
toggle_hud=Shift_R+F12
no_display
gpu_stats
gpu_color=FFFFFF
cpu_stats
cpu_color=FFFFFF
fps
fps_color=FF0000,FFFF00,00FF00
frame_timing
frametime_color=FFFFFF
EOF
cp "$tmp/MangoHud/MangoHud.conf" "$tmp/.local/share/goverlay/gameconfig/global/MangoHud.conf"

pass() { printf 'ok  %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; exit 1; }

"$here/bin/omahud" list | grep -q fixture && pass "list fixture" || bad "list fixture"

"$here/bin/omahud" set fixture --quiet
grep -q 'background_color=111111' "$tmp/MangoHud/MangoHud.conf" && pass "bg retint" || bad "bg retint"
grep -q 'gpu_stats' "$tmp/MangoHud/MangoHud.conf" && pass "metrics kept" || bad "metrics kept"
grep -q 'toggle_hud=Shift_R+F12' "$tmp/MangoHud/MangoHud.conf" && pass "keybind kept" || bad "keybind kept"
grep -q 'position=top-left' "$tmp/MangoHud/MangoHud.conf" && pass "position kept" || bad "position kept"
grep -q 'gpu_color=00FF00' "$tmp/MangoHud/MangoHud.conf" && pass "gpu colour" || bad "gpu colour"
grep -q 'gpu_color=00FF00' "$tmp/.local/share/goverlay/gameconfig/global/MangoHud.conf" \
  && pass "goverlay copy retint" || bad "goverlay copy retint"
grep -q 'gpu_stats' "$tmp/.local/share/goverlay/gameconfig/global/MangoHud.conf" \
  && pass "goverlay metrics kept" || bad "goverlay metrics kept"

"$here/bin/omahud" preview fixture >/dev/null
[[ -f $tmp/cache/previews/fixture.png ]] && pass "preview png" || bad "preview png"

"$here/bin/omahud" install-menu
grep -q 'style.hud' "$tmp/.config/omarchy/extensions/omarchy-menu.jsonc" && pass "menu" || bad "menu"

"$here/bin/omahud" clear --quiet
grep -q 'background_color=000000' "$tmp/MangoHud/MangoHud.conf" && pass "clear restore" || bad "clear restore"
grep -q 'gpu_stats' "$tmp/MangoHud/MangoHud.conf" && pass "metrics after clear" || bad "metrics after clear"

omarchy plugin validate "$here" && pass "omarchy plugin validate" || bad "validate"

printf 'omahud check: all good\n'
