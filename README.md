# OmaHud

**Omarchy themes your desktop. OmaHud retints MangoHud — colours only —
so Goverlay (or your hand-tuned conf) keeps owning metrics, layout, and
keybinds. Change theme mid-match and the overlay follows; no game restart.**

![OmaHud — MangoHud colour mockup](preview.png)

Stock Omarchy paints Hyprland, the terminal, and (with Chroma) your GTK apps.
MangoHud stayed on whatever palette you last saved in Goverlay — or got
**smashed** when a theme dropped a full `mangohud.conf.tpl` over the whole file
(Asphalt-era experiments, Catppuccin Mango packs). Your desktop wore Hackerman
neon; the HUD either ignored it or wiped your metrics layout on every switch.

OmaHud closes that gap the same way Style → OBS Themes works: a labelled image
picker, one mockup per installed theme, and an apply step that only rewrites
existing `*_color` keys. Pick once, or let `omarchy theme set` keep the HUD in
lockstep forever after — **live, in-game**, with no restart. That is the thing
the old full-file `.tpl` never gave you.

## Goals (and honest limits)

These Style plugins extend Omarchy’s theme system **without requiring theme
authors — or you — to ship anything extra**. Official themes, your forks, and
third-party installs all work as long as they have a `colors.toml`. That
“every theme” contract is intentional: once the desktop can follow farther,
making *another* theme is more worth it. Longer origin story, stop-line, and
marketplace notes live in [Chroma](https://github.com/AlxWolfenstein97/chroma).

| Goal | What that means here |
|------|----------------------|
| Zero extra assets | No per-theme HUD screenshots. Colours come from `colors.toml` alone. |
| Extreme compatibility | Stock + user + foreign themes all appear in the picker automatically. |
| Colours only | Rewrite existing `*_color` keys. Never invent `gpu_stats`, positions, or hotkeys. |
| Goverlay / traps | Not a how-to-HUD guide — skip colour pickers, know what we paint. See below. |
| Live reload | Patch the conf; MangoHud picks it up mid-session. No game restart to judge a tint. |
| Carousel-safe | Mockups are 1536×864 with ~8% side inset so the Style tile crop does not chop labels. |
| Snappy pickers | Mockups warm in parallel across CPU cores and **skip tiles whose `colors.toml` (and layout version) haven’t changed** — reopen is near-instant. On par with Omarchy’s stock Style carousels. |

The applied conf *is* your real MangoHud file — only the paint moves. Picker art
traces a PasCube / middle-left metrics silhouette (True Theme Vibe), same idea as
[OmaOBS](https://github.com/AlxWolfenstein97/omaobs) / [OmaBoot](https://github.com/AlxWolfenstein97/omaboot).

### Why a picker if `theme-set` already syncs?

Chroma can stay silent — it rewrites toolkit CSS for the whole desktop. MangoHud
is one surface with a conf people already tuned. The Style carousel is still
worth it: skim how the HUD would look across **every** installed theme faster
than applying and eyeballing each one in a game. Pick once (or never — the hook
keeps pace after that). Same idea as OmaOBS / OmaCursor / OmaBoot.

## What you get

- **Style → HUD Themes** in the Omarchy menu — same carousel picker as Unlock /
  Theme / OBS / Cursors / Boot.
- **Live theme discovery** — every Omarchy theme with a `colors.toml` under
  `~/.config/omarchy/themes` or `$OMARCHY_PATH/themes`.
- **Mockups** — middle-left 3-col metrics panel + frametime graph on a PasCube-ish
  field, coloured from that theme’s palette (carousel-safe inset).
- **Colours-only patch** — existing `*_color` keys in the global conf (and
  Goverlay’s copies by default). Layout stays yours — traps below.
- **Live in-game retint** — MangoHud re-reads the conf; no game restart.
- **theme-set hook** — `omarchy theme set …` keeps HUD colours in step.
- **Escape hatches** — `omahud clear`, or a Goverlay colour preset (see traps).
- **Stable Style order** — install normalises extender blocks under a shared
  flock (`Cursors` → `OBS` → `Boot` → `VT` → `TTY` → `HUD`) so quiet / itemised
  enables don’t race or shuffle the menu.

## Goverlay / MangoHud: traps (not a how-to)

You are here because you already run the overlay and want it **looking** like
Omarchy — not because you need a “how do I HUD” tutorial. MangoHud is one of
those tools you should already know a bit: 32-bit bits when you need them,
loading it (often chained with gamemode / gamescope / other Steam launch
options), Lutris wiring outside Steam, and so on. That is why we **do not pull**
`mangohud` or `goverlay` (same idea as OmaOBS not pulling OBS). The old theme
`.tpl` was optional if you already ran Mango; this plugin is the same deal.
OmaHud only pulls **Pillow** for the Style carousel.

[Goverlay](https://github.com/benjamimgois/goverlay) is still the sane place to
shape metrics/layout so you are not hand-editing the conf. This section is so
you do **not** waste time or walk into OmaHud-specific traps:

| Trap | Reality |
|------|---------|
| Fiddling Goverlay **colour** pickers every theme change | Pointless — OmaHud owns paint from `colors.toml`. Use Goverlay for metrics, graphs, position, keybinds. |
| Expecting OmaHud to install or teach MangoHud | No. Bring your own overlay; we only retint an existing conf. |
| Assuming every per-game conf gets painted | We touch `~/.config/MangoHud/MangoHud.conf` and, by default, Goverlay’s `gameconfig/*/MangoHud.conf` (so its GUI pickers match). Hand-rolled paths / launch-option confs **outside** that tree are on you. |
| Saving a Goverlay colour preset then wondering why theme paint vanished | Intentional escape: Stock / Simple White / Afterburner / GOverlay puts non-theme colours back (layout kept). Next sync / Style pick restores Omarchy paint. Prefer `omahud clear` for the pre-OmaHud snapshot. |
| Expecting Goverlay’s *app* chrome to theme | Out of scope (same stop-line as Chroma leftovers). Only MangoHud `*_color` keys move. |

Opt out of the Goverlay `gameconfig` retint with
`touch ~/.local/state/omarchy/omahud/no-goverlay-sync` (or `OMAHUD_SYNC_GOVERLAY=0`)
if you only want the global conf touched.

## Mockups: True Theme Vibe (PasCube silhouette)

MangoHud has no theme format to draw from — only a conf. We do not ask theme
authors for HUD screenshots. One live PasCube capture locks the metrics
silhouette; Pillow recolours that panel from every `colors.toml`.

**How it was done**

1. Capture live `mangohud pascube` with the user’s middle-left Goverlay layout
   (**Hackerman** colours).
2. Trace that chrome in `lib/omahud.py` (SAFE_X / SAFE_Y inset), then recolour
   from each theme’s MangoHud colour map.
3. Light themes get a near-opaque panel + contrast boost on the **tile only** so
   Latte pastels stay readable in the carousel; dark themes keep the raw palette.
   Apply always uses the raw `colors.toml` map.

**Compare — live PasCube vs generated mockup (same silhouette):**

| Real HUD (PasCube) | OmaHud mockup |
| --- | --- |
| ![Real MangoHud on PasCube — middle-left layout](reference-mangohud-pascube.png) | ![OmaHud mockup — middle-left 3-col panel from colors.toml map](preview.png) |

Hero above is the live-shaped mockup on Hackerman. Picker tiles are the drawn
mockups. (`MANGOHUD_CONFIGFILE` + conf with `no_display` stripped for shots —
bare `MANGOHUD_CONFIG=…` alone falls back to stock top-left chrome.)

## Install

```sh
omarchy plugin add https://github.com/AlxWolfenstein97/omahud.git --enable
```

That clones into `~/.config/omarchy/plugins/io.github.alxwolfenstein97.omahud`.
Or from a checkout:

```sh
~/.config/omarchy/plugins/io.github.alxwolfenstein97.omahud/install.sh
omarchy plugin enable io.github.alxwolfenstein97.omahud
```

**Needs (installer pulls these if missing):**

| Package | Why |
|---------|-----|
| `python-pillow` | Draws the Style → HUD Themes mockup PNGs. Without it the carousel is empty on first open. |

**Bring your own (not pulled):** `mangohud` / `goverlay` if you use them — we
assume you already know how to load the overlay. Also uses Omarchy’s image
picker (`omarchy-menu-images`). `install.sh` pulls Pillow **before** warming
mockups. Same quiet-install story as the other Style siblings: interactive
install asks in-TTY; shell-service `--quiet` (itemised / marketplace enable)
opens one floating terminal once when Pillow is missing, then continues. Menu
write is flock’d with the other extenders.

No `MangoHud.conf` yet? Create one however you already do (Goverlay save, copy,
etc.), then Style → HUD Themes / `omahud sync`. Install removes any legacy
full-file `theme-set.d/mangohud` hook so templates stop overwriting you.

## How it works

1. `bin/omahud-switcher` renders PNG mockups into
   `~/.cache/omarchy/omahud/previews/`, then opens `omarchy-menu-images`.
2. On selection, `bin/omahud-set` maps `colors.toml` → MangoHud colour keys and
   patches them in place (live conf **and** Goverlay’s GUI copies by default).
3. `~/.config/omarchy/hooks/theme-set.d/omahud` runs `omahud-sync` after every
   desktop theme change.

Shape stays with your conf / Goverlay; paint stays with OmaHud — traps above.
Catppuccin’s MangoHud pack is still a full-file replace (layout + pastel
colours), same smash as the old themed `.tpl`. OmaHud keeps the split.

CLI:

```sh
omahud list
omahud show tokyo-night
omahud set tokyo-night      # pin HUD to that palette
omahud sync                 # follow current Omarchy theme
omahud clear                # restore pre-OmaHud colours
omahud preview              # warm all mockups
omahud switcher             # picker → prints slug
omahud current
```

## Disable vs remove

| Action | What happens |
|--------|----------------|
| `omarchy plugin disable …` | Shell service stops. **Theme-set hook still runs** — HUD colours keep syncing on every desktop theme flip. |
| `./uninstall.sh` then disable / remove | Menu, hook, and OmaHud cache/state gone. `MangoHud.conf` (and Goverlay copies) stay as last painted. Shared packages stay. |
| `omahud clear` | Restores the colour snapshot from first apply. Run **before** uninstall if you still want that backup (uninstall clears state). |
| `omarchy pkg drop python-pillow` | Optional. Only if nothing else on the machine needs Pillow. |

**Full wipe** — copy-paste to remove plugin wiring *and* the shared package this
installer may have pulled (skip the `pkg drop` line if something else still
needs Pillow). Run `omahud clear` first if you want stock/pre-OmaHud colours back.
MangoHud / Goverlay stay installed — we never pulled them:

```sh
omahud clear                # optional — restore pre-OmaHud colours while backup exists
~/.config/omarchy/plugins/io.github.alxwolfenstein97.omahud/uninstall.sh
omarchy plugin disable io.github.alxwolfenstein97.omahud
omarchy plugin remove io.github.alxwolfenstein97.omahud
omarchy pkg drop python-pillow
```

## Limits, honestly

- **No conf yet** — we never pull MangoHud; sync is a no-op until
  `~/.config/MangoHud/MangoHud.conf` exists.
- **Not a MangoHud howto** — 32-bit libs, Steam / Lutris / gamescope / gamemode
  launch chains, etc. are assumed knowledge. See **Goverlay / MangoHud: traps**.
- **Colour pickers in Goverlay** — don’t use them for theme matching; saving a
  preset is only an escape hatch until the next sync.
- **Game-specific confs** — global + Goverlay `gameconfig/*` by default; custom
  paths outside that are on you.
- **Goverlay’s own chrome** — not themed. Only MangoHud `*_color` keys move.
- **Mockups ≠ live layout** — tiles trace a PasCube middle-left silhouette for
  *tint*; your real metrics layout is whatever you already configured.
- **Light-theme tiles** — carousel art may darken weak pastels for readability;
  the live overlay still uses the raw `colors.toml` map.

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
- [Omarchy](https://omarchy.org/) — theme pipeline, Style menu image picker, and
  `theme-set` hooks this plugin hooks into.

## License

MIT — see [LICENSE](LICENSE).
