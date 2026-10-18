"""Key map: defaults, presets, TOML config and --map flags."""
from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from .protocol import BUTTON_BITS

CONFIG_PATH = Path.home() / ".config" / "clickbridge" / "config.toml"

# MyWhoosh keys: K raises the gear number, I lowers it. U toggles the minimal UI.
# 1, 2, 3 and 7 are emotes. The arrows steer.
PRESETS: dict[str, dict[str, str]] = {
    "mywhoosh": {
        "SHIFT_UP_R": "k",
        "SHIFT_UP_L": "i",
        "NAV_LEFT": "Left",
        "NAV_RIGHT": "Right",
        "NAV_UP": "u",
        "Y": "1",
        "B": "2",
        "Z": "3",
        "A": "7",
    },
    "none": {},
}
DEFAULT_PRESET = "mywhoosh"
DEFAULT_MAP = PRESETS[DEFAULT_PRESET]

# `--right-only`: B on the right unit becomes shift down.
RIGHT_ONLY_KEY = "i"


class KeymapError(ValueError):
    pass


def parse_map_item(item: str) -> tuple[str, str | None]:
    """Parse "BUTTON=key". An empty key (or no "=") means unmap."""
    name, _, key = item.partition("=")
    name = name.strip().upper()
    if name not in BUTTON_BITS:
        raise KeymapError(f"unknown button {name!r}; use one of {', '.join(BUTTON_BITS)}")
    key = key.strip()
    return name, key or None


def apply_overrides(base: dict[str, str], items: list[str]) -> dict[str, str]:
    result = dict(base)
    for item in items:
        name, key = parse_map_item(item)
        if key is None:
            result.pop(name, None)
        else:
            result[name] = key
    return result


def load_config(path: Path | None = None) -> dict:
    """Read the TOML config. A missing file gives an empty config."""
    path = path or CONFIG_PATH
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def build_keymap(
    config: dict | None = None,
    map_flags: list[str] | None = None,
    right_only: bool = False,
    preset: str | None = None,
) -> dict[str, str]:
    """Merge preset, config [keys] and --map flags (later wins)."""
    config = config or {}
    preset = preset or config.get("preset", DEFAULT_PRESET)
    if preset not in PRESETS:
        raise KeymapError(f"unknown preset {preset!r}; use one of {', '.join(PRESETS)}")
    keymap = dict(PRESETS[preset])
    if right_only:
        keymap["B"] = RIGHT_ONLY_KEY
    items = [f"{k}={v}" for k, v in config.get("keys", {}).items()]
    keymap = apply_overrides(keymap, items)
    return apply_overrides(keymap, map_flags or [])
