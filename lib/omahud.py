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
MOCKUP_LAYOUT_VERSION = "1"
MOCKUP_SIZE = (1536, 864)

# Keys we may retint. Multi-value keys use comma-separated RRGGBB lists.
# We only rewrite a key if it already exists in the user's conf — never inject
# metrics / layout / keybinds.
COLOR_KEYS_SINGLE = (
    "background_color",
    "text_color",
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
)
COLOR_KEYS_TRIPLE = (
    "gpu_load_color",
    "cpu_load_color",
    "fps_color",
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
    seen: set[str] = set()
    for line in original.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in COLOR_KEYS and key in colors:
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{key}={colors[key]}")
                replaced += 1
                seen.add(key)
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
    conf = mangohud_conf_path()
    n, changed = patch_mangohud_colors(conf, colors)
    state = paths()["state"]
    state.mkdir(parents=True, exist_ok=True)
    atomic_write(state / "current", slug + "\n")
    if not quiet:
        if changed:
            note(f"retinted {n} colour key(s) in {conf} ← {pretty_name(slug)}")
            note("layout / metrics / keybinds untouched — reopen Goverlay or the game HUD to see colours")
        else:
            note(f"already matching {pretty_name(slug)} ({n} colour key(s) present)")
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
    conf = mangohud_conf_path()
    n, changed = patch_mangohud_colors(conf, restored)
    current = paths()["state"] / "current"
    if current.is_file():
        current.unlink()
    if not quiet:
        note(f"restored {n} colour key(s) from backup" + (" (changed)" if changed else ""))
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


def render_mockup(palette: dict[str, str], dest: Path, size: tuple[int, int] = MOCKUP_SIZE) -> Path:
    """Fake in-game HUD strip — metrics chrome, not a live vkcube capture."""
    w, h = size
    bg = hex_to_rgb(palette["_bg"])
    # Dim “game” field behind the HUD
    field = tuple(max(0, c - 18) for c in bg)
    img = Image.new("RGB", (w, h), field)
    draw = ImageDraw.Draw(img)

    # Subtle vignette grid so it reads as a 3D viewport, not a blank tile
    grid = hex_to_rgb(palette.get("_accent", palette["_fg"]))
    for x in range(0, w, 64):
        draw.line((x, 0, x, h), fill=tuple(max(0, c // 5) for c in grid))
    for y in range(0, h, 64):
        draw.line((0, y, w, y), fill=tuple(max(0, c // 5) for c in grid))

    panel_x, panel_y = 80, 120
    panel_w, panel_h = 420, 520
    panel_bg = hex_to_rgb("#" + palette["background_color"])
    # alpha-ish by mixing with field
    panel_fill = tuple(int(panel_bg[i] * 0.75 + field[i] * 0.25) for i in range(3))
    draw.rounded_rectangle(
        (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h),
        radius=8,
        fill=panel_fill,
    )

    font = try_ui_font(28)
    font_sm = try_ui_font(20)
    text = hex_to_rgb("#" + palette["text_color"])
    gpu = hex_to_rgb("#" + palette["gpu_color"])
    cpu = hex_to_rgb("#" + palette["cpu_color"])
    ram = hex_to_rgb("#" + palette["ram_color"])
    fps_hi = hex_to_rgb(palette["_green"])
    fps_mid = hex_to_rgb(palette["_yellow"])
    fps_lo = hex_to_rgb(palette["_red"])

    x = panel_x + 24
    y = panel_y + 24
    rows = [
        ("GPU", "64%", "72°C", gpu),
        ("VRAM", "3.2 GiB", "", hex_to_rgb("#" + palette["vram_color"])),
        ("CPU", "41%", "58°C", cpu),
        ("RAM", "12.4 GiB", "", ram),
        ("FPS", "144", "6.9 ms", fps_hi),
    ]
    for label, a, b, color in rows:
        draw.text((x, y), label, font=font_sm, fill=color)
        draw.text((x + 110, y), a, font=font, fill=text)
        if b:
            draw.text((x + 260, y), b, font=font, fill=text)
        y += 56
        # load bar
        bar_y = y - 12
        draw.rectangle((x, bar_y, x + 360, bar_y + 6), fill=tuple(c // 4 for c in text))
        draw.rectangle((x, bar_y, x + 220, bar_y + 6), fill=color)
        y += 28

    # fps colour legend
    draw.text((x, y + 8), "fps", font=font_sm, fill=text)
    for i, col in enumerate((fps_lo, fps_mid, fps_hi)):
        bx = x + 80 + i * 70
        draw.rectangle((bx, y + 12, bx + 56, y + 28), fill=col)

    badge = f"{palette['_name']} · MangoHud colours · layout yours"
    draw.text((80, h - 48), badge, font=font_sm, fill=hex_to_rgb(palette["_fg"]))

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
