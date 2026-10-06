"""Smoke test for the Phase 7.4 in-window prototype; skipped unless snes9x, the SMW ROM and its state exist."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "prototypes", "inwindow"))
demo = pytest.importorskip("demo")
lr = pytest.importorskip("libretro")


def _available():
    try:
        return all(os.path.exists(p) for p in (demo.core_path(), demo.ROM, demo.STATE))
    except (OSError, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(not _available(), reason="snes9x core, SMW ROM or start state not present")


def test_two_instances_stay_identical_and_expose_ram():
    a, b = demo.start(2)
    try:
        assert a.ram()[demo.LEVEL] == 0x29  # Yoshi's Island 1
        for f in range(240):
            a.buttons = b.buttons = demo.auto_buttons(0, f)
            a.run()
            b.run()
        assert bytes(a.ram()) == bytes(b.ram())
        assert a.ram()[0x71] != 9  # the scripted run doesn't die
        assert (a.ram()[demo.X_POS] | a.ram()[demo.X_POS + 1] << 8) > 200
        assert a.frame[1:3] == (256, 224)
    finally:
        a.close()
        b.close()
