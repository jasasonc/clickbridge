"""BLE side: one Unit per Click v2 controller, and the Bridge that owns both."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from . import __version__
from .debounce import Debouncer
from .keys import KeySender
from .protocol import (
    CH_ASYNC,
    CH_SYNC_RX,
    CH_SYNC_TX,
    FF04_START,
    HANDSHAKE_V2,
    MFR_TYPE_V2_LEFT,
    MFR_TYPE_V2_RIGHT,
    OP_CONTROLLER,
    OP_EMPTY,
    OP_RESET,
    RIDE_ON,
    STOPPED_PREFIXES,
    SVC_CUSTOM,
    SVC_RIDE,
    UNIT_BUTTONS,
    ZWIFT_MFR_ID,
    button_map_from_frame,
    hexs,
    pressed_buttons,
)

log = logging.getLogger("clickbridge")


@dataclass
class Options:
    test: bool = False
    verbose: bool = False
    ff04: bool = True
    reset: bool = True
    reset_after: float = 0.0
    left: bool = True
    right: bool = True


class Unit:
    def __init__(self, side: str, bridge: Bridge):
        self.side = side
        self.b = bridge
        self.dev: BLEDevice | None = None
        self.seen = 0.0
        self.advert = asyncio.Event()
        self.debounce = Debouncer()
        self.stopped = asyncio.Event()
        self.tag = f"[{side}]"

    def note_advert(self, dev: BLEDevice, ad: AdvertisementData) -> None:
        first = self.dev is None or time.monotonic() - self.seen > 30
        self.dev, self.seen = dev, time.monotonic()
        self.advert.set()
        if first:
            log.info(
                "%s advertising: %s %s rssi=%s mfr=%s",
                self.tag, dev.address, ad.local_name, ad.rssi,
                {k: v.hex() for k, v in ad.manufacturer_data.items()},
            )  # fmt: skip

    async def run(self) -> None:
        backoff = 2.0
        while True:
            self.advert.clear()
            # Wait for a fresh advert. The Click sleeps and advertises after a press.
            while not (self.dev and time.monotonic() - self.seen < 15):
                try:
                    await asyncio.wait_for(self.advert.wait(), 5)
                except asyncio.TimeoutError:
                    pass
                self.advert.clear()
            try:
                outcome = await self.session()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - keep the loop alive
                log.warning("%s session error: %r", self.tag, e)
                outcome = "error"
            self.seen = 0.0  # force a new advert before the next attempt
            self.debounce.reset()
            if outcome == "locked":
                log.warning(
                    "%s Zwift service hidden: unit is LOCKED. Unlock it once with the "
                    "Zwift app (see README). Retrying in 30 s.", self.tag,
                )  # fmt: skip
                await asyncio.sleep(30)
            else:
                await asyncio.sleep(backoff)

    async def session(self) -> str:
        assert self.dev
        log.info("%s connecting to %s", self.tag, self.dev.address)
        disconnected = asyncio.Event()
        client = BleakClient(self.dev, disconnected_callback=lambda _c: disconnected.set(), timeout=15)
        await client.connect()
        try:
            log.info("%s connected, mtu=%s", self.tag, getattr(client, "mtu_size", "?"))
            svc = client.services.get_service(SVC_RIDE) or client.services.get_service(SVC_CUSTOM)
            if svc is None:
                log.info("%s services: %s", self.tag, [s.uuid for s in client.services])
                return "locked"
            ch = {c.uuid.lower(): c for c in svc.characteristics}
            if not all(u in ch for u in (CH_ASYNC, CH_SYNC_RX, CH_SYNC_TX)):
                log.warning("%s characteristics missing: %s", self.tag, list(ch))
                return "error"
            opts = self.b.opts
            self.stopped.clear()
            await client.start_notify(ch[CH_ASYNC], lambda _c, d: self.on_data("async", bytes(d)))
            await client.start_notify(ch[CH_SYNC_TX], lambda _c, d: self.on_data("sync", bytes(d)))
            rx = ch[CH_SYNC_RX]
            await client.write_gatt_char(rx, HANDSHAKE_V2, response=False)
            log.info("%s sent RideOn handshake", self.tag)
            if opts.ff04:
                await asyncio.sleep(0.3)
                await client.write_gatt_char(rx, FF04_START, response=False)
            t0 = time.monotonic()
            while not disconnected.is_set():
                try:
                    await asyncio.wait_for(self.stopped.wait(), 1.0)
                except asyncio.TimeoutError:
                    pass
                if self.stopped.is_set() and opts.reset:
                    log.warning("%s device went quiet (needs unlock); sending RESET for another window", self.tag)
                    await client.write_gatt_char(rx, bytes([OP_RESET]), response=False)
                    await asyncio.sleep(1.0)
                    break
                if opts.reset_after and opts.reset and time.monotonic() - t0 > opts.reset_after:
                    log.info("%s periodic RESET after %ss", self.tag, opts.reset_after)
                    await client.write_gatt_char(rx, bytes([OP_RESET]), response=False)
                    await asyncio.sleep(1.0)
                    break
            return "ok"
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            log.info("%s disconnected", self.tag)

    def on_data(self, via: str, d: bytes) -> None:
        if not d:
            return
        if d.startswith(RIDE_ON):
            log.info("%s %s RideOn reply: %s", self.tag, via, hexs(d))
            return
        if any(d.startswith(p) for p in STOPPED_PREFIXES):
            log.warning("%s %s device-stopped message: %s", self.tag, via, hexs(d))
            self.stopped.set()
            return
        op = d[0]
        if op == OP_EMPTY:
            return
        if op == OP_CONTROLLER:
            try:
                bm = button_map_from_frame(d)
            except ValueError as e:
                log.warning("%s bad controller frame %s (%s)", self.tag, hexs(d), e)
                return
            self.on_buttons(bm, d)
            return
        log.debug("%s %s op=0x%02x %s", self.tag, via, op, hexs(d))

    def on_buttons(self, button_map: int, raw: bytes) -> None:
        names, unknown = pressed_buttons(button_map)
        names &= UNIT_BUTTONS[self.side]
        if self.b.opts.test or self.b.opts.verbose:
            log.info(
                "%s frame map=0x%08x pressed=%s unknown_bits=0x%x raw=%s",
                self.tag, button_map, sorted(names) or "-", unknown, hexs(raw),
            )  # fmt: skip
        for name in self.debounce.update(names, time.monotonic()):
            key = self.b.keymap.get(name)
            if not key:
                log.info("%s %s pressed (no key mapped)", self.tag, name)
                continue
            asyncio.get_running_loop().create_task(self.b.keys.press(key, f"{self.side} {name}"))


class Bridge:
    def __init__(self, opts: Options, keymap: dict[str, str], keys: KeySender, backend_name: str = ""):
        self.opts = opts
        self.keymap = keymap
        self.keys = keys
        self.backend_name = backend_name
        sides = [s for s, on in (("left", opts.left), ("right", opts.right)) if on]
        self.units = {s: Unit(s, self) for s in sides}

    def on_advert(self, dev: BLEDevice, ad: AdvertisementData) -> None:
        mfr = ad.manufacturer_data.get(ZWIFT_MFR_ID)
        if not mfr:
            return
        side = {MFR_TYPE_V2_RIGHT: "right", MFR_TYPE_V2_LEFT: "left"}.get(mfr[0])
        if side is None:
            log.debug("ignoring Zwift device %s type 0x%02x (not a Click v2)", dev.address, mfr[0])
        elif side in self.units:
            self.units[side].note_advert(dev, ad)

    async def run(self) -> None:
        log.info(
            "clickbridge %s  mode=%s  backend=%s  map=%s", __version__,
            "TEST (no keys sent)" if self.opts.test else "live", self.backend_name, self.keymap,
        )  # fmt: skip
        tasks = [asyncio.create_task(u.run()) for u in self.units.values()]
        async with BleakScanner(self.on_advert):
            log.info("scanning for Click v2 units; press a button on each to wake it")
            await asyncio.gather(*tasks)
