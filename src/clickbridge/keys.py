"""Key-sending backends: hyprland, wtype, xdotool, uinput."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path

log = logging.getLogger("clickbridge")

BACKENDS = ("hyprland", "wtype", "xdotool", "uinput")


class Backend:
    name = ""

    def __init__(self, hold_ms: int = 40, window: str = ""):
        self.hold_ms = hold_ms
        self.window = window
        self._env = dict(os.environ)

    @classmethod
    def available(cls) -> bool:
        raise NotImplementedError

    async def send(self, key: str) -> bool:
        raise NotImplementedError

    async def _run(self, *argv: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            *argv, env=self._env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await proc.communicate()
        return proc.returncode or 0, out.decode(errors="replace").strip()


def _hypr_signature(rd: str) -> str | None:
    socks = sorted(Path(rd, "hypr").glob("*/.socket.sock"), key=lambda p: p.stat().st_mtime)
    return socks[-1].parent.name if socks else None


class HyprlandBackend(Backend):
    """hyprctl key events sent to one window found by regex. XWayland (Wine)
    only gets keys when the window has focus, so the window is focused first
    if it is not. With no window regex, keys go to the active window."""

    name = "hyprland"

    def __init__(self, hold_ms: int = 40, window: str = ""):
        super().__init__(hold_ms, window)
        self.window_re = re.compile(window, re.I) if window else None
        self._addr: str | None = None
        self._addr_t = 0.0
        # Started from a launcher, the Hyprland variables can be missing.
        rd = self._env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        self._env.setdefault("XDG_RUNTIME_DIR", rd)
        if not self._env.get("HYPRLAND_INSTANCE_SIGNATURE"):
            sig = _hypr_signature(rd)
            if sig:
                self._env["HYPRLAND_INSTANCE_SIGNATURE"] = sig

    @classmethod
    def available(cls) -> bool:
        if not shutil.which("hyprctl"):
            return False
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            return True
        rd = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        return _hypr_signature(rd) is not None

    async def find_window(self) -> str | None:
        if self._addr and time.monotonic() - self._addr_t < 5:
            return self._addr
        rc, out = await self._run("hyprctl", "clients", "-j")
        if rc != 0:
            return None
        try:
            clients = json.loads(out)
        except ValueError:
            return None
        for c in clients:
            blob = " ".join(str(c.get(k, "")) for k in ("class", "initialClass", "title", "initialTitle"))
            if self.window_re and self.window_re.search(blob):
                self._addr, self._addr_t = c["address"], time.monotonic()
                return self._addr
        self._addr = None
        return None

    async def _dispatch(self, lua: str) -> bool:
        # Hyprland 0.55 and later read `hyprctl dispatch` arguments as Lua.
        rc, out = await self._run("hyprctl", "dispatch", lua)
        if rc != 0 or out.strip().lower() != "ok":
            log.warning("hyprctl %s -> %s", lua, out)
            return False
        return True

    async def send(self, key: str) -> bool:
        target = ""
        if self.window_re:
            addr = await self.find_window()
            if not addr:
                log.warning("no window matching %r", self.window_re.pattern)
                return False
            rc, out = await self._run("hyprctl", "activewindow", "-j")
            try:
                active = json.loads(out).get("address")
            except ValueError:
                active = None
            target = f"address:{addr}"
            if active != addr:
                if not await self._dispatch(f"hl.dsp.focus({{ window = '{target}' }})"):
                    return False
                await asyncio.sleep(0.25)  # Wine drops the first key after a focus change
        win = f", window = '{target}'" if target else ""
        down = f"hl.dsp.send_key_state({{ mods = '', key = '{key}', state = 'down'{win} }})"
        up = f"hl.dsp.send_key_state({{ mods = '', key = '{key}', state = 'up'{win} }})"
        if not await self._dispatch(down):
            return False
        await asyncio.sleep(self.hold_ms / 1000)
        return await self._dispatch(up)


class WtypeBackend(Backend):
    """Types into the focused window. Does not reach Wine (XWayland) windows."""

    name = "wtype"

    @classmethod
    def available(cls) -> bool:
        return bool(shutil.which("wtype") and os.environ.get("WAYLAND_DISPLAY"))

    async def send(self, key: str) -> bool:
        rc, out = await self._run("wtype", "-P", key, "-s", str(max(self.hold_ms, 1)), "-p", key)
        if rc != 0:
            log.warning("wtype failed: %s", out)
        return rc == 0


class XdotoolBackend(Backend):
    """X11. Sends to the focused window, or to a window found by name regex."""

    name = "xdotool"

    @classmethod
    def available(cls) -> bool:
        return bool(shutil.which("xdotool") and os.environ.get("DISPLAY"))

    async def send(self, key: str) -> bool:
        argv = ["xdotool", "keydown"]
        if self.window:
            rc, out = await self._run("xdotool", "search", "--name", self.window)
            ids = out.split()
            if rc != 0 or not ids:
                log.warning("no window matching %r", self.window)
                return False
            argv += ["--window", ids[0]]
        rc, out = await self._run(*argv, key)
        if rc != 0:
            log.warning("xdotool failed: %s", out)
            return False
        await asyncio.sleep(self.hold_ms / 1000)
        argv[1] = "keyup"
        rc, _ = await self._run(*argv, key)
        return rc == 0


_EVDEV_NAMES = {
    "left": "KEY_LEFT", "right": "KEY_RIGHT", "up": "KEY_UP", "down": "KEY_DOWN",
    "return": "KEY_ENTER", "enter": "KEY_ENTER", "space": "KEY_SPACE", "escape": "KEY_ESC",
    "tab": "KEY_TAB", "backspace": "KEY_BACKSPACE", "plus": "KEY_KPPLUS", "minus": "KEY_MINUS",
    "page_up": "KEY_PAGEUP", "page_down": "KEY_PAGEDOWN", "home": "KEY_HOME", "end": "KEY_END",
}  # fmt: skip


def evdev_name(key: str) -> str:
    """Map a key name such as "k", "Left" or "F5" to an evdev KEY_ name."""
    low = key.lower()
    if low in _EVDEV_NAMES:
        return _EVDEV_NAMES[low]
    if low.startswith("key_"):
        return key.upper()
    return "KEY_" + key.upper()


class UinputBackend(Backend):
    """Virtual keyboard through /dev/uinput (python-evdev). Works on any
    display server. Keys go to the focused window."""

    name = "uinput"

    def __init__(self, hold_ms: int = 40, window: str = ""):
        super().__init__(hold_ms, window)
        self._ui = None

    @classmethod
    def available(cls) -> bool:
        try:
            import evdev  # noqa: F401
        except ImportError:
            return False
        return os.access("/dev/uinput", os.W_OK)

    def _device(self):
        if self._ui is None:
            from evdev import UInput
            from evdev import ecodes as e

            codes = [v for k, v in vars(e).items() if k.startswith("KEY_") and isinstance(v, int)]
            self._ui = UInput({e.EV_KEY: codes}, name="clickbridge")
        return self._ui

    async def send(self, key: str) -> bool:
        from evdev import ecodes as e

        code = getattr(e, evdev_name(key), None)
        if code is None:
            log.warning("uinput: unknown key %r", key)
            return False
        try:
            ui = self._device()
            ui.write(e.EV_KEY, code, 1)
            ui.syn()
            await asyncio.sleep(self.hold_ms / 1000)
            ui.write(e.EV_KEY, code, 0)
            ui.syn()
        except OSError as exc:
            log.warning("uinput failed: %s", exc)
            return False
        return True


_CLASSES = {c.name: c for c in (HyprlandBackend, WtypeBackend, XdotoolBackend, UinputBackend)}


def pick_backend_name(requested: str = "auto") -> str:
    """auto: the first usable one of hyprland, wtype, xdotool, uinput."""
    if requested != "auto":
        if requested not in _CLASSES:
            raise ValueError(f"unknown backend {requested!r}; use auto or one of {', '.join(BACKENDS)}")
        return requested
    for name in BACKENDS:
        if _CLASSES[name].available():
            return name
    raise RuntimeError("no key backend available; install wtype or xdotool, or the uinput extra")


class KeySender:
    """Serialises key presses through one backend. In test mode it only logs."""

    def __init__(self, backend: Backend | None, test: bool = False):
        self.backend = backend
        self.test = test
        self._lock = asyncio.Lock()

    async def press(self, key: str, why: str) -> None:
        if self.test or self.backend is None:
            log.info("TEST  would press %-5s (%s)", key, why)
            return
        async with self._lock:
            ok = await self.backend.send(key)
        log.info("KEY   %-5s (%s) %s", key, why, "sent" if ok else "NOT SENT")


def make_sender(requested: str, window: str, hold_ms: int, test: bool) -> tuple[KeySender, str]:
    if test:
        return KeySender(None, test=True), "none (test mode)"
    name = pick_backend_name(requested)
    return KeySender(_CLASSES[name](hold_ms=hold_ms, window=window), test=test), name
