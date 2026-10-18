"""Command line entry point."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from . import __version__
from .bridge import Bridge, Options
from .keymap import CONFIG_PATH, PRESETS, KeymapError, build_keymap, load_config
from .keys import BACKENDS, make_sender

DEFAULT_WINDOW = "mywhoosh"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clickbridge", description="Zwift Click v2 BLE controller to keyboard keys.")
    p.add_argument("--test", action="store_true", help="log decoded presses, send no keys")
    p.add_argument("-v", "--verbose", action="store_true", help="log every button frame")
    p.add_argument("--backend", choices=("auto", *BACKENDS), help="key backend (default: auto)")
    p.add_argument("--window", help="window regex for hyprland and xdotool (default: mywhoosh; empty = focused window)")
    p.add_argument("--hold-ms", type=int, help="key hold time in ms (default: 40)")
    p.add_argument("--config", type=Path, help=f"TOML config file (default: {CONFIG_PATH})")
    p.add_argument("--preset", choices=sorted(PRESETS), help="key map preset (default: mywhoosh)")
    p.add_argument("--map", action="append", default=[], metavar="BUTTON=key",
                   help="override one key, for example NAV_UP=u; BUTTON= (empty) unmaps")  # fmt: skip
    p.add_argument("--right-only", action="store_true", help="B on the right unit becomes shift down")
    p.add_argument("--no-ff04", dest="ff04", action="store_false", help="skip the FF 04 00 start frame")
    p.add_argument("--no-reset", dest="reset", action="store_false", help="do not RESET a unit that goes quiet")
    p.add_argument("--reset-after", type=float, metavar="SEC", help="also RESET every SEC seconds (default: off)")
    p.add_argument("--list-map", action="store_true", help="print the resulting key map and exit")
    p.add_argument("--version", action="version", version=f"clickbridge {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        keymap = build_keymap(config, args.map, args.right_only, args.preset)
    except (KeymapError, OSError, ValueError) as e:
        print(f"clickbridge: {e}", file=sys.stderr)
        return 2
    if args.list_map:
        for name, key in keymap.items():
            print(f"{name}={key}")
        return 0
    opts_cfg = config.get("options", {})
    logging.basicConfig(
        level=logging.DEBUG if (args.verbose or args.test) else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
    )  # fmt: skip
    logging.getLogger("bleak").setLevel(logging.WARNING)
    window = args.window if args.window is not None else opts_cfg.get("window", DEFAULT_WINDOW)
    try:
        keys, backend_name = make_sender(
            args.backend or opts_cfg.get("backend", "auto"),
            window,
            args.hold_ms or opts_cfg.get("hold_ms", 40),
            args.test,
        )
    except (RuntimeError, ValueError) as e:
        print(f"clickbridge: {e}", file=sys.stderr)
        return 2
    opts = Options(
        test=args.test,
        verbose=args.verbose,
        ff04=args.ff04,
        reset=args.reset,
        reset_after=args.reset_after or opts_cfg.get("reset_after", 0.0),
    )
    bridge = Bridge(opts, keymap, keys, backend_name)
    loop = asyncio.new_event_loop()
    main_task = loop.create_task(bridge.run())
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, main_task.cancel)
    try:
        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        logging.getLogger("clickbridge").info("stopped")
    finally:
        loop.close()
    return 0
