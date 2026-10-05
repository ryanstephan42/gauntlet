import json
import subprocess
import sys
import time

from gauntlet import winplace


def test_descendants_finds_grandchildren():
    code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)"
    parent = subprocess.Popen([sys.executable, "-c", code])
    try:
        for _ in range(50):
            found = winplace.descendants(parent.pid)
            if len(found) >= 2:
                break
            time.sleep(0.1)
        assert parent.pid in found and len(found) == 2
    finally:
        for pid in found - {parent.pid}:
            subprocess.run(["kill", str(pid)])
        parent.kill()
        parent.wait()


class FakeBackend:
    name = "Fake"

    def __init__(self, windows=()):
        self.wins = list(windows)
        self.placed = []

    def area(self):
        return (100, 30, 2000, 1000)

    def windows(self):
        return list(self.wins)

    def place(self, wid, rect):
        self.placed.append((wid, rect))
        return True

    def focus(self, wid):
        self.placed.append((wid, "focus"))
        return True


def test_placer_matches_descendant_pids_and_replaces_new_windows():
    tree = {10: {10, 11, 12}, 20: {20, 21}}
    b = FakeBackend([("a", 12), ("other", 99)])
    p = winplace.Placer(b, descendants=lambda pid: tree[pid])
    p.add(10, (0, 0, 640, 480))
    p.add(20, (640, 0, 640, 480.0))
    assert p.poll() is False
    assert b.placed == [("a", (0, 0, 640, 480))]
    b.wins.append(("b", 21))
    assert p.poll() is True
    assert b.placed[-1] == ("b", (640, 0, 640, 480))
    n = len(b.placed)
    p.poll()
    assert len(b.placed) == n  # placed windows are left alone (the player may move them)
    b.wins = [("a2", 11), ("b", 21)]  # RetroArch recreated its window after loading the core
    p.poll()
    assert b.placed[n:] == [("a2", (0, 0, 640, 480))]


def test_refresh_focuses_placed_windows_ending_on_player_one():
    b = FakeBackend([("a", 1), ("b", 2)])
    p = winplace.Placer(b, descendants=lambda pid: {pid})
    p.add(1, (0, 0, 640, 480))
    p.add(2, (640, 0, 640, 480))
    p.add(3, (0, 480, 640, 480))  # never got a window: nothing to focus
    p.poll()
    del b.placed[:]
    p.refresh(pause=0)
    assert b.placed == [("b", "focus"), ("a", "focus")]


def test_placer_thread_stops():
    b = FakeBackend([("a", 1)])
    p = winplace.Placer(b, descendants=lambda pid: {pid})
    p.add(1, (0, 0, 10, 10))
    p.start(timeout=5, interval=0.01, settle=0.05)
    p._thread.join(2)
    assert not p._thread.is_alive() and b.placed == [("a", (0, 0, 10, 10))]
    p.stop()


def test_hyprland_backend():
    calls = []
    mons = [{"focused": False, "x": 0, "y": 0, "width": 3440, "height": 1440, "scale": 1, "reserved": [0, 0, 0, 0]},
            {"focused": True, "x": 1720, "y": -1440, "width": 5120, "height": 2880, "scale": 2,
             "reserved": [0, 26, 0, 0], "transform": 0}]
    clients = [{"address": "0xabc", "pid": 42, "mapped": True, "fullscreen": 0},
               {"address": "0xfff", "pid": 44, "mapped": True, "fullscreen": 2},
               {"address": "0xdef", "pid": 43, "mapped": False}]

    def run(cmd, timeout=2.0):
        calls.append(cmd)
        if cmd[:2] == ["hyprctl", "-j"]:
            return json.dumps({"monitors": mons, "clients": clients}[cmd[2]])
        return "ok"
    h = winplace.Hyprland(run)
    assert h.area() == (1720, -1414, 2560, 1414)
    assert h.windows() == [("0xabc", 42), ("0xfff", 44)]
    assert h.focus("0xabc") and calls[-1] == ["hyprctl", "dispatch", "focuswindow", "address:0xabc"]
    assert h.place("0xabc", (1720, -1414, 1280, 1414))
    batch = calls[-1]
    assert batch[:2] == ["hyprctl", "--batch"]
    assert batch[2].startswith("dispatch setfloating address:0xabc")
    assert "resizewindowpixel exact 1280 1414,address:0xabc" in batch[2]
    assert "movewindowpixel exact 1720 -1414,address:0xabc" in batch[2]
    h.place("0xfff", (0, 0, 10, 10))  # forced fullscreen by a window rule: focus it and leave fullscreen first
    assert calls[-1][2].startswith("dispatch focuswindow address:0xfff ; dispatch fullscreenstate 0 0 ; "
                                   "dispatch setfloating address:0xfff")
    assert winplace.Hyprland(lambda *a, **k: None).area() is None


def test_sway_backend():
    tree = {"type": "root", "nodes": [{"type": "output", "nodes": [{"type": "workspace", "nodes": [
        {"type": "con", "id": 7, "pid": 42, "nodes": []}], "floating_nodes": [
        {"type": "floating_con", "id": 8, "pid": 43, "nodes": []}]}]}]}
    outs = [{"focused": True, "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080}}]
    calls = []

    def run(cmd, timeout=2.0):
        calls.append(cmd)
        if cmd[:3] == ["swaymsg", "-r", "-t"]:
            return json.dumps({"get_tree": tree, "get_outputs": outs}[cmd[3]])
        return "[]"
    s = winplace.Sway(run)
    assert s.area() == (0, 0, 1920, 1080)
    assert sorted(s.windows()) == [(7, 42), (8, 43)]
    s.focus(8)
    assert calls[-1] == ["swaymsg", "[con_id=8] focus"]
    s.place(7, (0, 0, 960, 1080))
    assert calls[-1] == ["swaymsg", "[con_id=7] fullscreen disable, floating enable, resize set width 960 px height 1080 px, "
                                    "move absolute position 0 px 0 px"]


def test_detect():
    have = lambda name: f"/usr/bin/{name}"  # noqa: E731
    assert isinstance(winplace.detect({"HYPRLAND_INSTANCE_SIGNATURE": "x"}, which=have), winplace.Hyprland)
    assert isinstance(winplace.detect({"SWAYSOCK": "/run/sway"}, which=have), winplace.Sway)
    assert winplace.detect({"HYPRLAND_INSTANCE_SIGNATURE": "x"}, which=lambda n: None) is None
    assert winplace.detect({}, which=have) is None
    assert winplace.detect() is None  # conftest removes the real compositor from the environment
