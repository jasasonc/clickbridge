"""Zwift Click v2 wire protocol: constants and frame decoding.

Ported from the protocol descriptions in BikeControl (jonasbark/swiftcontrol)
and ajchellew/zwiftplay. See the README for credits.
"""
from __future__ import annotations

ZWIFT_MFR_ID = 0x094A  # 2378, "Zwift, Inc"
MFR_TYPE_V2_RIGHT = 0x0A  # first byte of the manufacturer data
MFR_TYPE_V2_LEFT = 0x0B
SVC_RIDE = "0000fc82-0000-1000-8000-00805f9b34fb"  # newer firmware
SVC_CUSTOM = "00000001-19ca-4651-86e5-fa29dcdd09d1"  # older firmware
CH_ASYNC = "00000002-19ca-4651-86e5-fa29dcdd09d1"  # notify: button frames
CH_SYNC_RX = "00000003-19ca-4651-86e5-fa29dcdd09d1"  # write: commands to device
CH_SYNC_TX = "00000004-19ca-4651-86e5-fa29dcdd09d1"  # indicate: replies

RIDE_ON = b"RideOn"
HANDSHAKE_V2 = RIDE_ON + bytes([0x02, 0x03])
FF04_START = bytes([0xFF, 0x04, 0x00])
OP_RESET = 0x18
OP_CONTROLLER = 0x23
OP_EMPTY = 0x15
# The device says "I stopped talking" (needs a new unlock window).
STOPPED_PREFIXES = (
    bytes([0xFF, 0x05, 0x00, 0xEA, 0x05]),
    bytes([0xFF, 0x05, 0x00, 0xFA, 0x05]),
)

# A bit that is 0 means pressed. The idle frame is 23 08 FF FF FF FF 0F.
BUTTON_BITS = {
    "NAV_LEFT": 0x00001,
    "NAV_UP": 0x00002,
    "NAV_RIGHT": 0x00004,
    "NAV_DOWN": 0x00008,
    "A": 0x00010,
    "B": 0x00020,
    "Y": 0x00040,
    "Z": 0x00080,
    "SHIFT_UP_L": 0x00100,  # left unit "-"
    "SHIFT_DN_L": 0x00200,  # Zwift Ride only
    "SHIFT_UP_R": 0x01000,  # right unit "+"
    "SHIFT_DN_R": 0x02000,  # Zwift Ride only
}
KNOWN_MASK = 0
for _bit in BUTTON_BITS.values():
    KNOWN_MASK |= _bit

# The buttons each Click v2 unit really has. Other bits are ignored.
UNIT_BUTTONS = {
    "left": frozenset({"NAV_LEFT", "NAV_UP", "NAV_RIGHT", "NAV_DOWN", "SHIFT_UP_L"}),
    "right": frozenset({"A", "B", "Y", "Z", "SHIFT_UP_R"}),
}


def pb_fields(data: bytes) -> dict[int, list]:
    """Read a protobuf message: field number -> list of varints or byte strings."""
    out: dict[int, list] = {}
    i = 0
    n = len(data)

    def varint() -> int:
        nonlocal i
        value = shift = 0
        while True:
            if i >= n:
                raise ValueError("truncated varint")
            b = data[i]
            i += 1
            value |= (b & 0x7F) << shift
            if not b & 0x80:
                return value
            shift += 7

    while i < n:
        key = varint()
        field, wire = key >> 3, key & 7
        if wire == 0:
            val = varint()
        elif wire == 2:
            ln = varint()
            val = data[i : i + ln]
            i += ln
        elif wire == 1:
            val = data[i : i + 8]
            i += 8
        elif wire == 5:
            val = data[i : i + 4]
            i += 4
        else:
            raise ValueError(f"wire type {wire}")
        out.setdefault(field, []).append(val)
    return out


def button_map_from_frame(frame: bytes) -> int:
    """Return the button bitmask of a controller frame (opcode 0x23)."""
    if not frame or frame[0] != OP_CONTROLLER:
        raise ValueError("not a controller frame")
    return pb_fields(frame[1:]).get(1, [0xFFFFFFFF])[0]


def pressed_buttons(button_map: int) -> tuple[set[str], int]:
    """Return the pressed button names and any unknown bits that are 0."""
    cleared = ~button_map & 0xFFFFFFFF
    names = {name for name, bit in BUTTON_BITS.items() if cleared & bit}
    return names, cleared & ~KNOWN_MASK


def decode_frame(frame: bytes, side: str) -> set[str]:
    """Return the buttons held down in a controller frame, for one unit."""
    names, _ = pressed_buttons(button_map_from_frame(frame))
    return names & UNIT_BUTTONS[side]


def hexs(b: bytes) -> str:
    return b.hex(" ")
