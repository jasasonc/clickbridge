from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
IDLE = bytes.fromhex("2308ffffffff0f")


def load_frames():
    rows = []
    for line in (FIXTURES / "frames.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        side, name, *hexbytes = line.split()
        rows.append((side, name, bytes.fromhex("".join(hexbytes))))
    return rows


@pytest.fixture
def frames():
    return load_frames()
