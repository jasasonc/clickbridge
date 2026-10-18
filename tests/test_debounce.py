from clickbridge.debounce import Debouncer
from clickbridge.protocol import decode_frame
from conftest import load_frames


def test_one_fire_per_press_while_held():
    d = Debouncer()
    assert d.update({"A"}, 0.0) == ["A"]
    assert d.update({"A"}, 0.1) == []
    assert d.update({"A"}, 5.0) == []


def test_release_then_press_fires_again():
    d = Debouncer()
    assert d.update({"A"}, 0.0) == ["A"]
    assert d.update(set(), 0.2) == []
    assert d.update({"A"}, 0.4) == ["A"]


def test_chatter_is_dropped():
    d = Debouncer()
    assert d.update({"A"}, 0.0) == ["A"]
    assert d.update(set(), 0.02) == []
    assert d.update({"A"}, 0.04) == []


def test_two_buttons_fire_in_stable_order():
    d = Debouncer()
    assert d.update({"Y", "A"}, 0.0) == ["A", "Y"]


def test_reset_clears_held_state():
    d = Debouncer()
    d.update({"A"}, 0.0)
    d.reset()
    assert d.update({"A"}, 1.0) == ["A"]


def test_real_frame_stream_fires_once_per_press():
    idle = bytes.fromhex("2308ffffffff0f")
    d = Debouncer()
    fired = []
    t = 0.0
    for side, _name, raw in load_frames():
        for frame in (idle, raw, raw, raw, idle):  # held for three frames
            t += 0.1
            fired += d.update(decode_frame(frame, side), t)
    assert sorted(fired) == sorted(n for _, n, _ in load_frames())
