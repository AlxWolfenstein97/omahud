#!/usr/bin/env python3
"""OmaHud — Omarchy palettes → MangoHud colours (layout stays yours).

Discovers every theme with a colors.toml. Patches only colour keys in
~/.config/MangoHud/MangoHud.conf so Goverlay / hand-tuned metrics survive.
Optional Style carousel mockups show the tint before you apply.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

PLUGIN_ID = "io.github.alxwolfenstein97.omahud"
HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")
MOCKUP_LAYOUT_VERSION = "5"
MOCKUP_SIZE = (1536, 864)
# omarchy-menu-images serves 1536×864 then crops ~8% sides into the Style tile —
# keep the HUD panel inside this inset or labels get chopped.
SAFE_X = 120
SAFE_Y = 56
# Match Goverlay's default background_alpha. Light themes keep more of the theme
# panel so dark ink stays readable (flat 0.55·bg+0.45·dark-field muddies Latte).
MOCKUP_BG_ALPHA = 0.6
MOCKUP_BG_ALPHA_LIGHT = 0.95
MOCKUP_LIGHT_LUMA = 160.0
# Pillow mockups lack MangoHud's AA + live outline; pull weak accents toward
# black/white until they clear ~AA contrast on the panel (apply colours untouched).
MOCKUP_MIN_CONTRAST = 4.5

# Keys we may retint. Multi-value keys use comma-separated RRGGBB lists.
# We only rewrite a key if it already exists in the user's conf — never inject
# metrics / layout / keybinds.
COLOR_KEYS_SINGLE = (
    "background_color",
    "text_color",
    "text_outline_color",
    "gpu_color",
    "vram_color",
    "cpu_color",
    "ram_color",
    "frametime_color",
    "engine_color",
    "wine_color",
    "media_player_color",
    "battery_color",
    "network_color",
    "io_color",
    "gpu_fan_color",
    "horizontal_separator_color",
)
COLOR_KEYS_TRIPLE = (
    "gpu_load_color",
    "cpu_load_color",
    "fps_color",
    # Catppuccin-style valued form (Goverlay usually keeps fps_color_change as a
    # bare flag + separate fps_color=… — we only rewrite when it has a value).
    "fps_color_change",
)
COLOR_KEYS = COLOR_KEYS_SINGLE + COLOR_KEYS_TRIPLE

MENU_START = "  // omahud:start"
MENU_END = "  // omahud:end"
STYLE_EXTENDER_BLOCKS = (
    "omacursor",
    "omaobs",
    "omaboot",
    "omavt",
    "omatty",
    "omahud",
)


def home() -> Path:
    return Path(os.environ.get("OMAHUD_HOME", Path.home())).expanduser()


def omarchy_path() -> Path:
    return Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))


def plugin_dir() -> Path:
    override = os.environ.get("OMAHUD_PLUGIN_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent.parent


def paths() -> dict[str, Path]:
    h = home()
    return {
        "user_themes": h / ".config/omarchy/themes",
        "stock_themes": omarchy_path() / "themes",
        "mangohud": Path(
            os.environ.get(
                "OMAHUD_MANGOHUD_CONF",
                h / ".config/MangoHud/MangoHud.conf",
            )
        ),
        "state": Path(os.environ.get("OMAHUD_STATE_DIR", h / ".local/state/omarchy/omahud")),
        "cache": Path(os.environ.get("OMAHUD_CACHE_DIR", h / ".cache/omarchy/omahud")),
        "menu": h / ".config/omarchy/extensions/omarchy-menu.jsonc",
        "hooks": h / ".config/omarchy/hooks/theme-set.d",
        "current_theme_name": h / ".local/state/omarchy/current/theme.name",
        "goverlay_gameconfig": Path(
            os.environ.get(
                "OMAHUD_GOVERLAY_GAMECONFIG",
                h / ".local/share/goverlay/gameconfig",
            )
        ),
    }


def note(msg: str) -> None:
    print(f"omahud: {msg}", file=sys.stderr)


def slugify(name: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", name or "")
    return cleaned.strip().lower().replace(" ", "-")


def pretty_name(slug: str) -> str:
    return re.sub(
        r"(^|-)([a-z])",
        lambda m: (" " if m.group(1) == "-" else "") + m.group(2).upper(),
        slugify(slug),
    )


def parse_hex(value: str, fallback: str) -> str:
    raw = (value or fallback).strip().strip('"').strip("'")
    if not HEX_RE.match(raw):
        raw = fallback
    if not raw.startswith("#"):
        raw = "#" + raw
    return raw.lower()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = parse_hex(value, "#000000").lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def strip_hex(value: str) -> str:
    """MangoHud wants RRGGBB without '#'."""
    return parse_hex(value, "#ffffff").lstrip("#").upper()


def atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_colors_toml(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def theme_dir(slug: str) -> Path | None:
    slug = slugify(slug)
    for root in (paths()["user_themes"], paths()["stock_themes"]):
        candidate = root / slug
        if (candidate / "colors.toml").is_file():
            return candidate
    return None


def list_theme_slugs() -> list[str]:
    found: set[str] = set()
    for root in (paths()["user_themes"], paths()["stock_themes"]):
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if entry.is_dir() and (entry / "colors.toml").is_file():
                found.add(entry.name)
    return sorted(found)


def current_omarchy_slug() -> str | None:
    name_path = paths()["current_theme_name"]
    if name_path.is_file():
        return slugify(name_path.read_text(encoding="utf-8").strip())
    return None


def current_omahud_slug() -> str | None:
    current = paths()["state"] / "current"
    if current.is_file():
        return slugify(current.read_text(encoding="utf-8").strip())
    return None


def palette_from_theme(slug: str) -> dict[str, str]:
    """Map colors.toml → MangoHud colour slots (RRGGBB, no '#')."""
    directory = theme_dir(slug)
    if directory is None:
        raise FileNotFoundError(f"theme not found or missing colors.toml: {slug}")
    raw = read_colors_toml(directory / "colors.toml")
    bg = parse_hex(raw.get("background", ""), "#1a1b26")
    fg = parse_hex(raw.get("bright_foreground", raw.get("foreground", "")), "#c0caf5")
    accent = parse_hex(raw.get("accent", raw.get("blue", "")), "#7aa2f7")
    green = parse_hex(raw.get("green", ""), "#9ece6a")
    yellow = parse_hex(raw.get("yellow", ""), "#e0af68")
    red = parse_hex(raw.get("red", ""), "#f7768e")
    cyan = parse_hex(raw.get("cyan", ""), "#7dcfff")
    magenta = parse_hex(raw.get("magenta", ""), "#bb9af7")
    return {
        "background_color": strip_hex(bg),
        "text_color": strip_hex(fg),
        "gpu_color": strip_hex(green),
        "vram_color": strip_hex(magenta),
        "cpu_color": strip_hex(cyan),
        "ram_color": strip_hex(accent),
        "frametime_color": strip_hex(green),
        "engine_color": strip_hex(fg),
        "wine_color": strip_hex(magenta),
        "media_player_color": strip_hex(accent),
        "battery_color": strip_hex(green),
        "network_color": strip_hex(cyan),
        "io_color": strip_hex(yellow),
        "gpu_fan_color": strip_hex(cyan),
        "gpu_load_color": ",".join(strip_hex(c) for c in (green, yellow, red)),
        "cpu_load_color": ",".join(strip_hex(c) for c in (green, yellow, red)),
        # fps_color is low→high (red, yellow, green) in typical Goverlay exports
        "fps_color": ",".join(strip_hex(c) for c in (red, yellow, green)),
        "fps_color_change": ",".join(strip_hex(c) for c in (red, yellow, green)),
        "text_outline_color": strip_hex(parse_hex(raw.get("darker_background", raw.get("dark_background", "")), "#11111b")),
        "horizontal_separator_color": strip_hex(magenta),
        # mockup helpers (with #)
        "_bg": bg,
        "_fg": fg,
        "_accent": accent,
        "_green": green,
        "_yellow": yellow,
        "_red": red,
        "_cyan": cyan,
        "_magenta": magenta,
        "_slug": slugify(slug),
        "_name": pretty_name(slug),
    }


def mangohud_conf_path() -> Path:
    return paths()["mangohud"]


def goverlay_sync_enabled() -> bool:
    """Retint Goverlay's own MangoHud copies so the GUI colour pickers match.

    Default on. Disable with OMAHUD_SYNC_GOVERLAY=0 or state file
    ~/.local/state/omarchy/omahud/no-goverlay-sync.
    """
    env = os.environ.get("OMAHUD_SYNC_GOVERLAY", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    return not (paths()["state"] / "no-goverlay-sync").is_file()


def mangohud_targets(*, include_goverlay: bool | None = None) -> list[Path]:
    """Live HUD conf + optional Goverlay gameconfig copies."""
    primary = mangohud_conf_path()
    out: list[Path] = [primary]
    if include_goverlay is None:
        include_goverlay = goverlay_sync_enabled()
    if not include_goverlay:
        return out
    root = paths()["goverlay_gameconfig"]
    if root.is_dir():
        for conf in sorted(root.glob("*/MangoHud.conf")):
            if conf.resolve() != primary.resolve():
                out.append(conf)
    return out


def backup_colors_once(text: str) -> None:
    state = paths()["state"]
    bak = state / "colors.bak"
    if bak.is_file():
        return
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in COLOR_KEYS:
            lines.append(stripped)
    if lines:
        state.mkdir(parents=True, exist_ok=True)
        atomic_write(bak, "\n".join(lines) + "\n")


def patch_mangohud_colors(conf: Path, colors: dict[str, str]) -> tuple[int, bool]:
    """Rewrite existing colour keys only. Returns (replacements, changed)."""
    if not conf.is_file():
        raise FileNotFoundError(
            f"no MangoHud.conf at {conf} — set up metrics in Goverlay (or write a "
            "config) first; OmaHud only retints colours"
        )
    original = conf.read_text(encoding="utf-8")
    backup_colors_once(original)
    out: list[str] = []
    replaced = 0
    for line in original.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in COLOR_KEYS and key in colors:
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{key}={colors[key]}")
                replaced += 1
                continue
        out.append(line)
    # Do not append missing colour keys — that would invent HUD chrome the user
    # never asked for. Metrics stay a Goverlay / hand-edit concern.
    new_text = "\n".join(out)
    if original.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    if new_text == original:
        return replaced, False
    atomic_write(conf, new_text)
    return replaced, True


def apply_theme(slug: str, *, quiet: bool = False) -> int:
    slug = slugify(slug)
    colors = palette_from_theme(slug)
    targets = mangohud_targets()
    primary = mangohud_conf_path()
    if not primary.is_file():
        raise FileNotFoundError(
            f"no MangoHud.conf at {primary} — set up metrics in Goverlay (or write a "
            "config) first; OmaHud only retints colours"
        )

    total = 0
    any_changed = False
    touched: list[str] = []
    for conf in targets:
        if not conf.is_file():
            continue
        n, changed = patch_mangohud_colors(conf, colors)
        total += n
        if changed:
            any_changed = True
            touched.append(str(conf))

    state = paths()["state"]
    state.mkdir(parents=True, exist_ok=True)
    atomic_write(state / "current", slug + "\n")
    if not quiet:
        label = pretty_name(slug)
        if any_changed:
            note(f"retinted {total} colour key(s) ← {label}")
            for path in touched:
                note(f"  {path}")
            if goverlay_sync_enabled() and any(
                "goverlay" in p for p in touched
            ):
                note("Goverlay GUI copy updated — reopen Goverlay to see the pickers match")
            note("layout / metrics / keybinds untouched")
        else:
            note(f"already matching {label} ({total} colour key(s) across {len(targets)} file(s))")
    return 0


def restore_backup(*, quiet: bool = False) -> int:
    bak = paths()["state"] / "colors.bak"
    if not bak.is_file():
        note("no colour backup yet (apply a theme once first)")
        return 1
    restored: dict[str, str] = {}
    for line in bak.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        restored[key.strip()] = value.strip()
    total = 0
    any_changed = False
    for conf in mangohud_targets():
        if not conf.is_file():
            continue
        n, changed = patch_mangohud_colors(conf, restored)
        total += n
        any_changed = any_changed or changed
    current = paths()["state"] / "current"
    if current.is_file():
        current.unlink()
    if not quiet:
        note(
            f"restored {total} colour key(s) from backup"
            + (" (changed)" if any_changed else "")
        )
    return 0


# --------------------------------------------------------------------------- mockups


def try_ui_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    ):
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _input_token(path: Path | None) -> str:
    if path is None:
        return "none"
    try:
        st = path.stat()
    except OSError:
        return "missing"
    return f"{st.st_mtime_ns}:{st.st_size}"


def preview_path(slug: str) -> Path:
    return paths()["cache"] / "previews" / f"{slugify(slug)}.png"


def _preview_meta_path(dest: Path) -> Path:
    return Path(str(dest) + ".meta")


def _preview_fresh(dest: Path, fingerprint: str) -> bool:
    if not dest.is_file():
        return False
    try:
        return _preview_meta_path(dest).read_text(encoding="utf-8").strip() == fingerprint
    except OSError:
        return False


def _write_preview_meta(dest: Path, fingerprint: str) -> None:
    try:
        _preview_meta_path(dest).write_text(fingerprint + "\n", encoding="utf-8")
    except OSError:
        pass


def _preview_fingerprint(slug: str) -> str:
    directory = theme_dir(slug)
    colors = (directory / "colors.toml") if directory else None
    return f"layout:{MOCKUP_LAYOUT_VERSION}|colors:{_input_token(colors)}|id:{slugify(slug)}"


def save_png_atomic(img: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".png", dir=dest.parent)
    try:
        os.close(fd)
        img.save(tmp, format="PNG", optimize=True)
        os.replace(tmp, dest)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def bust_image_picker_cache(preview_root: Path) -> None:
    try:
        os.utime(preview_root, None)
    except OSError:
        pass
    cache_home = home() / ".cache"
    for pattern in ("omarchy-menu-images*", "menu-images*"):
        for path in cache_home.glob(pattern):
            if path.is_file():
                path.unlink(missing_ok=True)


def _rgb_strip(value: str) -> tuple[int, int, int]:
    return hex_to_rgb("#" + value.lstrip("#"))


def _luma(rgb: tuple[int, int, int]) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _rel_chan(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def _rel_luma(rgb: tuple[int, int, int]) -> float:
    return 0.2126 * _rel_chan(rgb[0]) + 0.7152 * _rel_chan(rgb[1]) + 0.0722 * _rel_chan(rgb[2])


def _contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _rel_luma(a), _rel_luma(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _blend(fg: tuple[int, int, int], bg: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    a = max(0.0, min(1.0, alpha))
    return tuple(int(round(fg[i] * a + bg[i] * (1.0 - a))) for i in range(3))


def _mockup_ink(fill: tuple[int, int, int], panel: tuple[int, int, int]) -> tuple[int, int, int]:
    """Darken/lighten a HUD colour until it reads on the mock panel.

    Catppuccin Latte body text already clears AA; pastel GPU/VRAM/CPU labels do
    not on cream. Live MangoHud stays on the raw palette — this is tile-only.
    """
    if _contrast_ratio(fill, panel) >= MOCKUP_MIN_CONTRAST:
        return fill
    target = (12, 12, 14) if _rel_luma(panel) >= 0.5 else (245, 245, 248)
    best = fill
    for step in range(1, 21):
        # lerp fill → target (not the panel-alpha blend helper's fg-over-bg sense)
        t = step / 20.0
        cand = tuple(int(round(fill[i] * (1.0 - t) + target[i] * t)) for i in range(3))
        best = cand
        if _contrast_ratio(cand, panel) >= MOCKUP_MIN_CONTRAST:
            return cand
    return best


def _outline_ink(fill: tuple[int, int, int]) -> tuple[int, int, int]:
    """MangoHud-style edge: dark ink around light glyphs, light around dark."""
    return (16, 16, 18) if _luma(fill) >= 140 else (245, 245, 248)


def _draw_hud_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int] | None = None,
) -> None:
    """Glyph + 1px outline so metrics stay readable like the live HUD."""
    edge = outline if outline is not None else _outline_ink(fill)
    x, y = xy
    if edge != fill:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=edge)
    draw.text(xy, text, font=font, fill=fill)


def _triple_rgbs(value: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    while len(parts) < 3:
        parts.append(parts[-1] if parts else "FFFFFF")
    return _rgb_strip(parts[0]), _rgb_strip(parts[1]), _rgb_strip(parts[2])


def render_mockup(palette: dict[str, str], dest: Path, size: tuple[int, int] = MOCKUP_SIZE) -> Path:
    """True Theme Vibe HUD — middle-left 3-col panel matching the PasCube reference.

    Traces the user's Goverlay metrics silhouette (GPU/VRAM/CPU/RAM/engine/FPS +
    frametime graph), not a live capture. Colours come from colors.toml via the
    same MangoHud key map as apply_theme. Panel stays inside SAFE_X/SAFE_Y so the
    Style carousel crop does not chop labels. Light themes keep a near-opaque
    panel; weak accents are contrast-boosted for the tile only (Latte pastels).
    """
    w, h = size
    # Neutral “game” viewport (PasCube-ish grey), so palette reads on the HUD only
    field = (55, 55, 58)
    floor = (48, 48, 50)
    img = Image.new("RGB", (w, h), field)
    draw = ImageDraw.Draw(img)
    # floor plane + faint grid
    horizon = int(h * 0.58)
    draw.rectangle((0, horizon, w, h), fill=floor)
    for i in range(0, w, 48):
        draw.line((i, horizon, i + (i - w // 2) // 8, h), fill=(42, 42, 44))
    for j in range(horizon, h, 36):
        draw.line((0, j, w, j), fill=(42, 42, 44))
    # simple cube stand-in (center)
    cx, cy = w // 2, int(h * 0.48)
    cube = [(cx - 90, cy), (cx, cy - 55), (cx + 90, cy), (cx, cy + 55)]
    draw.polygon(cube, fill=(210, 210, 212), outline=(170, 170, 172))
    draw.polygon(
        [(cx - 90, cy), (cx, cy + 55), (cx, cy + 95), (cx - 90, cy + 40)],
        fill=(150, 150, 152),
    )
    draw.polygon(
        [(cx + 90, cy), (cx, cy + 55), (cx, cy + 95), (cx + 90, cy + 40)],
        fill=(120, 120, 122),
    )
    title_font = try_ui_font(22)
    draw.text((cx - 95, SAFE_Y), "PasCube Benchmark", font=title_font, fill=(220, 220, 220))

    panel_bg = _rgb_strip(palette["background_color"])
    light_panel = _luma(panel_bg) >= MOCKUP_LIGHT_LUMA
    alpha = MOCKUP_BG_ALPHA_LIGHT if light_panel else MOCKUP_BG_ALPHA
    panel_fill = _blend(panel_bg, field, alpha)

    text = _mockup_ink(_rgb_strip(palette["text_color"]), panel_fill)
    gpu = _mockup_ink(_rgb_strip(palette["gpu_color"]), panel_fill)
    cpu = _mockup_ink(_rgb_strip(palette["cpu_color"]), panel_fill)
    vram = _mockup_ink(_rgb_strip(palette["vram_color"]), panel_fill)
    ram = _mockup_ink(_rgb_strip(palette["ram_color"]), panel_fill)
    engine = _mockup_ink(_rgb_strip(palette["engine_color"]), panel_fill)
    ft = _mockup_ink(_rgb_strip(palette["frametime_color"]), panel_fill)
    fps_lo, fps_mid, fps_hi = (_mockup_ink(c, panel_fill) for c in _triple_rgbs(palette["fps_color"]))
    load_lo, load_mid, load_hi = (
        _mockup_ink(c, panel_fill) for c in _triple_rgbs(palette["gpu_load_color"])
    )

    # Middle-left panel inside carousel safe inset (not flush to the canvas edge)
    panel_w, panel_h = 340, 300
    panel_x = SAFE_X
    panel_y = max(SAFE_Y + 24, (h - panel_h) // 2)
    if panel_y + panel_h > h - SAFE_Y - 36:
        panel_y = h - SAFE_Y - 36 - panel_h
    draw.rectangle(
        (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h),
        fill=panel_fill,
    )

    font = try_ui_font(20)
    font_sm = try_ui_font(16)
    col_label = panel_x + 14
    col_a = panel_x + 100
    col_b = panel_x + 210
    y = panel_y + 14
    row_h = 36

    rows: list[tuple[str, tuple[int, int, int], str, tuple[int, int, int], str, tuple[int, int, int]]] = [
        ("GPU", gpu, "34%", load_mid, "42°C", text),
        ("VRAM", vram, "1.6 GiB", text, "", text),
        ("CPU", cpu, "5%", text, "43°C", text),
        ("RAM", ram, "5.9 GiB", text, "", text),
        ("VULKAN", engine, "60 FPS", fps_hi, "16.7 ms", text),
    ]
    for label, label_c, a, a_c, b, b_c in rows:
        _draw_hud_text(draw, (col_label, y), label, font=font, fill=label_c)
        _draw_hud_text(draw, (col_a, y), a, font=font, fill=a_c)
        if b:
            _draw_hud_text(draw, (col_b, y), b, font=font, fill=b_c)
        y += row_h

    # frametime graph (single bright line like a flat 16.7ms trace)
    graph_top = y + 4
    graph_bot = panel_y + panel_h - 36
    draw.rectangle(
        (panel_x + 12, graph_top, panel_x + panel_w - 12, graph_bot),
        fill=tuple(max(0, c - 10) for c in panel_fill),
    )
    gy = (graph_top + graph_bot) // 2
    draw.line((panel_x + 14, gy, panel_x + panel_w - 14, gy), fill=ft, width=2)

    _draw_hud_text(
        draw,
        (panel_x + 14, graph_bot + 6),
        "Frametime  min: 16.6ms, max: 16.8ms",
        font=font_sm,
        fill=text,
    )

    # Badge sits on the dark floor — always use light ink + dark outline.
    badge = f"{palette['_name']} · MangoHud colours · layout yours"
    _draw_hud_text(
        draw,
        (SAFE_X, h - SAFE_Y + 8),
        badge,
        font=font_sm,
        fill=(230, 230, 232),
        outline=(20, 20, 22),
    )

    save_png_atomic(img, dest)
    return dest


def generate_preview(slug: str, *, force: bool = False) -> Path:
    dest = preview_path(slug)
    fp = _preview_fingerprint(slug)
    if not force and _preview_fresh(dest, fp):
        return dest
    render_mockup(palette_from_theme(slug), dest)
    _write_preview_meta(dest, fp)
    return dest


def _warm_one(slug: str) -> Path:
    return generate_preview(slug, force=True)


def generate_all_previews() -> list[Path]:
    out: list[Path] = []
    root = paths()["cache"] / "previews"
    root.mkdir(parents=True, exist_ok=True)
    wanted = set(list_theme_slugs())
    for existing in root.glob("*.png"):
        if existing.stem not in wanted:
            existing.unlink(missing_ok=True)
            _preview_meta_path(existing).unlink(missing_ok=True)
    dirty = [s for s in wanted if not _preview_fresh(preview_path(s), _preview_fingerprint(s))]
    if not dirty:
        return out
    workers = max(1, min(len(dirty), os.cpu_count() or 2))
    try:
        ctx = mp.get_context("fork")
    except ValueError:
        ctx = mp.get_context()
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        futures = {pool.submit(_warm_one, s): s for s in dirty}
        for fut in as_completed(futures):
            try:
                out.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                note(f"preview failed for {futures[fut]}: {exc}")
    bust_image_picker_cache(root)
    return out


# --------------------------------------------------------------------------- menu


def remove_marked(content: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.S)
    return pattern.sub("", content)


def normalize_style_extender_menu_order(menu_path: Path) -> None:
    if not menu_path.is_file():
        return
    text = menu_path.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for name in STYLE_EXTENDER_BLOCKS:
        start, end = f"  // {name}:start", f"  // {name}:end"
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
        match = pattern.search(text)
        if not match:
            continue
        found[name] = match.group(0).strip("\n")
        text = pattern.sub("", text)
    if not found:
        return
    text = re.sub(r"\n{3,}", "\n\n", text)
    blocks = "\n\n".join(found[name] for name in STYLE_EXTENDER_BLOCKS if name in found)
    idx = text.rfind("}")
    if idx < 0:
        return
    head, tail = text[:idx].rstrip(), text[idx:]
    if head and not head.endswith("\n"):
        head += "\n"
    new = head + "\n" + blocks + "\n" + tail
    if not new.endswith("\n"):
        new += "\n"
    try:
        old = menu_path.read_text(encoding="utf-8")
    except OSError:
        old = ""
    if new != old:
        atomic_write(menu_path, new)


def menu_action() -> str:
    plug = str(plugin_dir())
    return (
        f'theme="$({plug}/bin/omahud-switcher)"; '
        f'[[ -n $theme ]] && {plug}/bin/omahud-set "$theme"'
    )


def install_menu_entry() -> None:
    path = paths()["menu"]
    content = path.read_text(encoding="utf-8") if path.is_file() else "{\n}\n"
    content = remove_marked(content, MENU_START, MENU_END)
    entries = [
        (
            "style.hud",
            {
                "icon": "󰡦",
                "label": "HUD Themes",
                "aliases": ["hud", "mangohud", "goverlay", "fps"],
                "description": "Retint MangoHud from any Omarchy palette without touching your layout or metrics",
                "action": menu_action(),
            },
        )
    ]
    brace = content.find("{")
    if brace < 0:
        raise RuntimeError(f"menu config has no root object: {path}")
    body = [MENU_START]
    for key, value in entries:
        body.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},")
    body.append(MENU_END)
    insertion = "\n".join(body) + "\n"
    atomic_write(path, content[: brace + 1] + "\n" + insertion + content[brace + 1 :])
    normalize_style_extender_menu_order(path)
    note(f"menu entry → {path}")


def uninstall_menu_entry() -> None:
    path = paths()["menu"]
    if not path.is_file():
        return
    content = path.read_text(encoding="utf-8")
    if MENU_START in content:
        atomic_write(path, remove_marked(content, MENU_START, MENU_END))


# --------------------------------------------------------------------------- commands


def cmd_list(_: argparse.Namespace) -> int:
    for slug in list_theme_slugs():
        print(slug)
    return 0


def cmd_current(_: argparse.Namespace) -> int:
    slug = current_omahud_slug()
    if slug:
        print(slug)
        return 0
    note("no HUD theme applied yet")
    return 1


def cmd_show(args: argparse.Namespace) -> int:
    colors = palette_from_theme(args.theme)
    for key in COLOR_KEYS:
        if key in colors:
            print(f"{key}={colors[key]}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    return apply_theme(args.theme, quiet=bool(args.quiet))


def cmd_sync(args: argparse.Namespace) -> int:
    slug = current_omarchy_slug()
    if not slug:
        note("no current Omarchy theme")
        return 1
    return apply_theme(slug, quiet=bool(args.quiet))


def cmd_clear(args: argparse.Namespace) -> int:
    return restore_backup(quiet=bool(args.quiet))


def cmd_preview(args: argparse.Namespace) -> int:
    if args.theme:
        path = generate_preview(args.theme, force=True)
        print(path)
        return 0
    paths_out = generate_all_previews()
    print(len(paths_out))
    return 0


def cmd_switcher(_: argparse.Namespace) -> int:
    generate_all_previews()
    preview_dir = paths()["cache"] / "previews"
    if not any(preview_dir.glob("*.png")):
        note("no previews — install python-pillow and ensure themes have colors.toml")
        return 1
    current = current_omahud_slug() or current_omarchy_slug()
    selected = None
    if current and (preview_dir / f"{current}.png").is_file():
        selected = str(preview_dir / f"{current}.png")
    cmd = [
        "omarchy-menu-images",
        "--show-labels",
        "--filterable",
        "--print-name",
    ]
    if selected:
        cmd.extend(["--selected", selected])
    cmd.append(str(preview_dir))
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        note("omarchy-menu-images not found")
        return 1
    choice = (result.stdout or "").strip()
    if not choice:
        return 0
    # menu-images may print a path or a stem
    stem = Path(choice).stem if choice.endswith(".png") else choice
    print(stem)
    return 0


def cmd_install_menu(_: argparse.Namespace) -> int:
    install_menu_entry()
    return 0


def cmd_uninstall_menu(_: argparse.Namespace) -> int:
    uninstall_menu_entry()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omahud", description="OmaHud — MangoHud colour sync")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List themes with colors.toml").set_defaults(func=cmd_list)
    sub.add_parser("current", help="Print last applied HUD theme slug").set_defaults(func=cmd_current)

    show = sub.add_parser("show", help="Print colour keys for a theme")
    show.add_argument("theme")
    show.set_defaults(func=cmd_show)

    setter = sub.add_parser("set", help="Retint MangoHud from a theme (layout untouched)")
    setter.add_argument("theme")
    setter.add_argument("--quiet", action="store_true")
    setter.set_defaults(func=cmd_set)

    sync = sub.add_parser("sync", help="Retint from the current Omarchy desktop theme")
    sync.add_argument("--quiet", action="store_true")
    sync.set_defaults(func=cmd_sync)

    clear = sub.add_parser("clear", help="Restore colours from the pre-OmaHud backup")
    clear.add_argument("--quiet", action="store_true")
    clear.set_defaults(func=cmd_clear)

    preview = sub.add_parser("preview", help="Warm Style mockups")
    preview.add_argument("theme", nargs="?")
    preview.set_defaults(func=cmd_preview)

    sub.add_parser("switcher", help="Open image picker; print chosen theme slug").set_defaults(
        func=cmd_switcher
    )
    sub.add_parser("install-menu", help="Add Style → HUD Themes").set_defaults(func=cmd_install_menu)
    sub.add_parser("uninstall-menu", help="Remove Style → HUD Themes").set_defaults(
        func=cmd_uninstall_menu
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except FileNotFoundError as exc:
        note(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001
        note(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
