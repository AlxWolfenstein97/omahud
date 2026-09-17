# OmaHud

**Omarchy themes your desktop. OmaHud retints MangoHud — colours only —
so Goverlay (or your hand-tuned conf) keeps owning metrics, layout, and
keybinds. Change theme mid-match and the overlay follows; no game restart.**

![OmaHud — MangoHud colour mockup](preview.png)

## Why this exists

Early theme experiments (including [Asphalt Legends](https://github.com/AlxWolfenstein97/omarchy-asphalt-legends-theme))
dropped a full `mangohud.conf.tpl` into Omarchy’s themed templates. That path
worked like Catppuccin Mango packs: every `omarchy theme set` replaced the
**whole** HUD file and smashed people’s Goverlay layouts, FPS graphs, and
hotkeys. Fine as a one-theme pack experiment; wrong once Style plugins got
good at “your surface, our paint.”

OmaHud is the other side of that idea. It only rewrites existing `*_color`
keys in `~/.config/MangoHud/MangoHud.conf` (and, by default, Goverlay’s own
`gameconfig/*/MangoHud.conf` copies so the GUI colour pickers match). Metrics
stay yours. MangoHud re-reads the conf on the fly — Style → HUD Themes or a
desktop theme switch retints **live, in-game**, with no restart. That is the
thing the old `.tpl` never gave you.

Broader “theme every surface that accepts colour data” origin, stop-line, and
marketplace notes live in [Chroma](https://github.com/AlxWolfenstein97/chroma).

## Goals (and honest limits)

These Style plugins extend Omarchy’s theme system **without requiring theme
authors — or you — to ship anything extra**. Official themes, your forks, and
third-party installs all work as long as they have a `colors.toml`. Same
contract as OmaOBS / OmaCursor / OmaBoot / OmaVT.

| Goal | What that means here |
|------|----------------------|
| Colours only | Rewrite existing `*_color` keys. Never invent `gpu_stats`, positions, or hotkeys. |
| Goverlay stays useful | Build the metrics layout in Goverlay; OmaHud only repaints. GUI copies get the same tint by default. |
| Live reload | Patch the conf; MangoHud picks it up mid-session. No game restart, no vkcube hop just to judge a tint. |
| Carousel-safe | Mockups are 1536×864 with ~8% side inset (same SAFE_X as OmaOBS / OmaTTY) so the Style tile crop does not chop labels. |
| Snappy pickers | Mockups warm in parallel across CPU cores and **skip tiles whose `colors.toml` / layout haven’t changed** — reopen is near-instant. Same ProcessPool + fingerprint tricks as the other Style siblings. |
| Stable Style order | Install normalises extender blocks (`Cursors` → `OBS` → `Boot` → `VT` → `TTY` → `HUD`) under a shared flock so quiet shell-service installs don’t race or shuffle the menu. |
| Theme-set sync | Hook keeps HUD colours with the desktop (same idea as OmaOBS / OmaCursor). |
| Escape hatch | First apply snapshots prior colours; `omahud clear` puts them back. |

Live PasCube / Goverlay cube is still the ground truth for the *real* overlay;
Style mockups are for picking a tint quickly. Light themes get a near-opaque
panel + contrast boost on the **tile only** so Latte pastels stay readable in
the carousel; dark themes keep the raw palette. Apply always uses the raw
`colors.toml` map.

**Reference — live PasCube (middle-left metrics, Hackerman colours):**

| Real HUD (PasCube) | OmaHud mockup (same silhouette) |
| --- | --- |
| ![Real MangoHud on PasCube — middle-left layout](reference-mangohud-pascube.png) | ![OmaHud mockup — middle-left 3-col panel from colors.toml map](preview.png) |

Style carousel tiles use the same panel chrome, recoloured from each theme’s
`colors.toml`. (`MANGOHUD_CONFIGFILE` + conf with `no_display` stripped for
shots — bare `MANGOHUD_CONFIG=…` alone falls back to stock top-left chrome.)

### Why a picker if `theme-set` already syncs?

Chroma can stay silent — it rewrites toolkit CSS for the whole desktop. MangoHud
is one surface with a real conf people already tuned. The Style carousel is
still worth it: skim how the HUD would look across **every** installed theme
faster than applying and eyeballing each one in a game. Pick once (or never —
the hook keeps pace after that). Same idea as OmaOBS / OmaCursor / OmaBoot.

## Install

```sh
omarchy plugin add https://github.com/AlxWolfenstein97/omahud.git --enable
```

Or from a checkout:

```sh
~/.config/omarchy/plugins/io.github.alxwolfenstein97.omahud/install.sh
omarchy plugin enable io.github.alxwolfenstein97.omahud
```

**Needs (installer pulls when missing, before warming mockups):**

| Package | Why |
|---------|-----|
| `python-pillow` | Style → HUD Themes mockups |
| `mangohud` | The overlay being retinted |

Same quiet-install story as the other Style siblings: `omarchy pkg add` needs
sudo — interactive install asks in-TTY; shell-service `--quiet` (itemised /
marketplace enable) opens one floating terminal once when packages are missing,
then continues. Menu write is flock’d with the other extenders so a batch enable
doesn’t leave Style entries in a random order or stroke the shell with overlapping
refreshes.

If `MangoHud.conf` does not exist yet, set metrics once in **Goverlay** (or
copy a conf), then Style → HUD Themes / `omahud sync`. Install removes any
legacy full-file `theme-set.d/mangohud` hook so templates stop overwriting you.

## How it works

1. Style → **HUD Themes** warms PNG mockups, then `omahud-set <theme>` patches
   colour keys in place (live conf **and** Goverlay’s GUI copy by default).
2. `~/.config/omarchy/hooks/theme-set.d/omahud` runs `omahud-sync` after every
   desktop theme switch.
3. Goverlay keeps writing layout/metrics into the same files. If you pick a
   built-in colour preset (**MangoHud Stock**, **Simple White**, **Afterburner**,
   **GOverlay**) and save, those colours land until the next sync / Style pick —
   intentional: OmaHud is for matching Omarchy themes, not fighting hand-tuned
   Goverlay paint. Layout/metrics from any preset stay; only `*_color` keys move.

Catppuccin’s MangoHud pack is a full-file replace (layout + pastel colours) —
same smash as the old themed `.tpl`. OmaHud keeps the split: your metrics, our
tints.

Disable Goverlay GUI sync if you only want `~/.config/MangoHud/MangoHud.conf`:

```sh
touch ~/.local/state/omarchy/omahud/no-goverlay-sync
# or: OMAHUD_SYNC_GOVERLAY=0 omahud sync
```

CLI:

```sh
omahud list
omahud show tokyo-night
omahud set tokyo-night      # pin HUD to that palette
omahud sync                 # follow current Omarchy theme
omahud clear                # restore pre-OmaHud colours
omahud preview              # warm mockups
omahud switcher             # image picker → slug on stdout
```

## Uninstall

```sh
~/.config/omarchy/plugins/io.github.alxwolfenstein97.omahud/uninstall.sh
omarchy plugin remove io.github.alxwolfenstein97.omahud
# optional: omahud clear   # before remove, if you want old colours back
```

## Check

```sh
bash ~/.config/omarchy/plugins/io.github.alxwolfenstein97.omahud/check.sh
```

## Credits

- **Layout reference:** [`reference-mangohud-pascube.png`](reference-mangohud-pascube.png)
  — live `mangohud pascube` with the user’s middle-left metrics layout
  (**Hackerman** colours). Mockups trace that 3-col panel + frametime graph.
- Sibling Style plugins: [OmaOBS](https://github.com/AlxWolfenstein97/omaobs),
  [OmaCursor](https://github.com/AlxWolfenstein97/omacursor),
  [OmaBoot](https://github.com/AlxWolfenstein97/omaboot),
  [OmaVT](https://github.com/AlxWolfenstein97/omavt),
  [OmaTTY](https://github.com/AlxWolfenstein97/omatty),
  [Chroma](https://github.com/AlxWolfenstein97/chroma).
- Theme that first proved the full-file `.tpl` was the wrong shape:
  [Asphalt Legends](https://github.com/AlxWolfenstein97/omarchy-asphalt-legends-theme)
  (now points here for MangoHud).
- [MangoHud](https://github.com/flightlessmango/MangoHud) +
  [Goverlay](https://github.com/benjamimgois/goverlay) — metrics UI; we only
  touch the paint.
- [Omarchy](https://omarchy.org/) — Style menu + theme-set hooks.

## License

MIT — see [LICENSE](LICENSE).
