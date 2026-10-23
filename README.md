# clickbridge

clickbridge turns the buttons of a Zwift Click v2 into keyboard keys on Linux.
It talks to the controller over Bluetooth Low Energy (BLE). It needs no phone
and no Zwift app while you ride.

Each Click v2 unit is a separate BLE device. clickbridge connects to the left
and the right unit at the same time. One button press sends one key press.
Holding a button does not repeat the key.

## Supported hardware

- Zwift Click v2, left and right unit: tested on full rides with MyWhoosh
  (Wine/Proton through Lutris, Hyprland). Both units shift gears.
- Zwift Click v1, Zwift Play, Zwift Ride: not tested. clickbridge ignores them.

## Install

Python 3.10 or newer and BlueZ are required.

    uv tool install git+https://github.com/jasasonc/clickbridge
    # or: pipx install git+https://github.com/jasasonc/clickbridge

From a clone of this repository:

    uv tool install -e .

For the `uinput` backend, add the extra:

    uv tool install "clickbridge[uinput] @ git+https://github.com/jasasonc/clickbridge"

## Key backends

clickbridge picks the first backend that works, in this order. Use `--backend`
to choose one.

| Backend    | Use                                                              |
|------------|------------------------------------------------------------------|
| `hyprland` | Hyprland. Needs `hyprctl`. Sends keys to a window found by regex. |
| `wtype`    | Other Wayland compositors. Types into the focused window.         |
| `xdotool`  | X11. Needs `xdotool`.                                             |
| `uinput`   | Any display server. Needs the `uinput` extra and `/dev/uinput`.   |

`wtype` does not reach Wine windows. Use `hyprland`, `xdotool` or `uinput` for
games under Wine.

For `uinput`, your user must have write access to `/dev/uinput`. Add this udev
rule in `/etc/udev/rules.d/99-uinput.rules`:

    KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"

Then add your user to the `input` group, reload the rules, and log in again.

## Quick test

Run this command. It prints each decoded button and sends no keys.

    clickbridge --test

Press a button on each unit. A sleeping unit wakes on the first press. The
log shows `pressed=['Y']` for the right unit Y button, for example.

To send keys, run `clickbridge` with no flags.

## Use with MyWhoosh under Lutris

1. Install clickbridge.
2. Copy `examples/mywhoosh-hook.sh` to a fixed path and make it executable.
3. In Lutris, open the game and select Configure, then System options.
4. Set Pre-launch script to `<path>/mywhoosh-hook.sh start`.
5. Set Post-exit script to `<path>/mywhoosh-hook.sh stop`.

The hook starts clickbridge before the game and stops it by PID after the game.
The log is in `~/.local/state/clickbridge/clickbridge.log`.

MyWhoosh under Wine must not find a running Bonjour service in the prefix. If
Bonjour runs, the game crashes at startup.

## Key map

The default map is for MyWhoosh.

| Unit  | Button         | Key         | MyWhoosh action    |
|-------|----------------|-------------|--------------------|
| right | + (`SHIFT_UP_R`) | `k`       | gear number up     |
| left  | - (`SHIFT_UP_L`) | `i`       | gear number down   |
| left  | `NAV_LEFT`     | `Left`      | arrow key (not verified) |
| left  | `NAV_RIGHT`    | `Right`     | arrow key (not verified) |
| left  | `NAV_UP`       | `u`         | minimal UI         |
| left  | `NAV_DOWN`     | none        |                    |
| right | `Y` `B` `Z` `A` | `1` `2` `3` `7` | emotes        |

Change a key with a flag. An empty key removes the mapping.

    clickbridge --map NAV_DOWN=d --map NAV_UP=

Or use a config file at `~/.config/clickbridge/config.toml`. See
`examples/config.toml`. Flags override the file. The file overrides the preset.
Use `preset = "none"` to start with an empty map. Run `clickbridge --list-map`
to see the result.

Key names are X keysym names: `k`, `Left`, `F5`, `space`.

Other options: `--window REGEX`, `--hold-ms N`, `--right-only` (B becomes
shift down), `--no-reset`, `--reset-after SEC`, `-v`.

## Daily unlock for Click v2

Other tools report that the Click v2 firmware needs an unlock from the Zwift
app about once a day. clickbridge was tested on several days with no Zwift app
installed, and both units worked for full rides.

If a unit still stops after about 1 minute:

- clickbridge sends RESET. The unit restarts and works for another short time.
- If the unit hides its Zwift service, clickbridge logs `LOCKED` and tries
  again every 30 s.

To fix the problem, connect each unit once in the Zwift app on a phone or on
Windows. Please open an issue if this happens to you.

## Credits

The protocol comes from these projects:

- [BikeControl](https://github.com/jonasbark/swiftcontrol) by Jonas Bark
  (Click v2 handshake, button bits, RESET handling).
- [zwiftplay](https://github.com/ajchellew/zwiftplay) by ajchellew.
- The Zwift Play protocol write-up by Makinolo.

clickbridge contains no code from these projects. BikeControl versions up to
the `gpl3` tag are under GPL-3.0. Newer versions use a non-commercial licence.
This package uses only the protocol facts and stays under GPL-3.0-or-later.

clickbridge is not affiliated with Zwift or MyWhoosh.

## Licence

GPL-3.0-or-later. See `LICENSE`.
