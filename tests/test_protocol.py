import pytest

from clickbridge.protocol import (
    UNIT_BUTTONS,
    button_map_from_frame,
    decode_frame,
    pb_fields,
    pressed_buttons,
)
from conftest import IDLE, load_frames


@pytest.mark.parametrize("side,name,raw", load_frames())
def test_real_frames_decode_to_one_button(side, name, raw):
    assert decode_frame(raw, side) == {name}


def test_all_ten_buttons_covered(frames):
    assert len(frames) == 10
    assert {n for _, n, _ in frames} == UNIT_BUTTONS["left"] | UNIT_BUTTONS["right"]


def test_idle_frame_has_nothing_pressed():
    assert decode_frame(IDLE, "left") == set()
    assert decode_frame(IDLE, "right") == set()
    assert button_map_from_frame(IDLE) == 0xFFFFFFFF


def test_button_of_other_unit_is_ignored():
    # Y frame seen by the left unit: Y is not a left button.
    raw = bytes.fromhex("2308bfffffff0f")
    assert decode_frame(raw, "left") == set()


def test_no_unknown_bits_in_real_frames(frames):
    for _, _, raw in frames:
        assert pressed_buttons(button_map_from_frame(raw))[1] == 0


def test_two_buttons_at_once():
    names, _ = pressed_buttons(0xFFFFFFFF & ~0x1 & ~0x1000)
    assert names == {"NAV_LEFT", "SHIFT_UP_R"}


def test_wrong_opcode_rejected():
    with pytest.raises(ValueError):
        button_map_from_frame(bytes([0x19, 0x08, 0x00]))


def test_truncated_varint_rejected():
    with pytest.raises(ValueError):
        pb_fields(bytes([0x08, 0xFF]))


def test_pb_fields_basic():
    assert pb_fields(bytes([0x08, 0x96, 0x01]))[1] == [150]
