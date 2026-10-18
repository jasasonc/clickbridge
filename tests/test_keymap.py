import pytest

from clickbridge.keymap import (
    DEFAULT_MAP,
    KeymapError,
    build_keymap,
    load_config,
    parse_map_item,
)
from clickbridge.keys import evdev_name, pick_backend_name


def test_default_is_mywhoosh_map():
    assert DEFAULT_MAP == {
        "SHIFT_UP_R": "k", "SHIFT_UP_L": "i", "NAV_LEFT": "Left", "NAV_RIGHT": "Right",
        "NAV_UP": "u", "Y": "1", "B": "2", "Z": "3", "A": "7",
    }  # fmt: skip
    assert "NAV_DOWN" not in DEFAULT_MAP


def test_parse_item():
    assert parse_map_item("nav_up=w") == ("NAV_UP", "w")
    assert parse_map_item("NAV_UP=") == ("NAV_UP", None)
    assert parse_map_item("NAV_UP") == ("NAV_UP", None)


def test_unknown_button_rejected():
    with pytest.raises(KeymapError):
        parse_map_item("FOO=x")


def test_flags_override_and_unmap():
    km = build_keymap(map_flags=["NAV_UP=w", "Y="])
    assert km["NAV_UP"] == "w"
    assert "Y" not in km
    assert km["A"] == "7"


def test_right_only_makes_b_shift_down():
    assert build_keymap(right_only=True)["B"] == "i"


def test_config_file_then_flags(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('preset = "none"\n[keys]\nNAV_UP = "w"\nA = "x"\n')
    km = build_keymap(load_config(cfg), map_flags=["A=y"])
    assert km == {"NAV_UP": "w", "A": "y"}


def test_config_on_top_of_default_preset(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[keys]\nNAV_DOWN = "d"\nNAV_UP = ""\n')
    km = build_keymap(load_config(cfg))
    assert km["NAV_DOWN"] == "d"
    assert "NAV_UP" not in km
    assert km["SHIFT_UP_R"] == "k"


def test_missing_config_is_empty(tmp_path):
    assert load_config(tmp_path / "none.toml") == {}


def test_unknown_preset():
    with pytest.raises(KeymapError):
        build_keymap(preset="zwift")


def test_evdev_names():
    assert evdev_name("k") == "KEY_K"
    assert evdev_name("Left") == "KEY_LEFT"
    assert evdev_name("7") == "KEY_7"


def test_explicit_backend_name():
    assert pick_backend_name("xdotool") == "xdotool"
    with pytest.raises(ValueError):
        pick_backend_name("nope")
