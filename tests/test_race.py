import json
import os
import random
import socket
import sys
import time

from gauntlet.detect import Install
from gauntlet.fakera import FakeRetroArch
from gauntlet.match import (KEYBOARD2_RA, NO_PAD, MatchRunner, Participant, Purchase, RacePlan, race_config,
                            race_setup, tile_rects)
from gauntlet.referee import RaceReferee
from gauntlet.retroarch import Launcher, read_cfg
from gauntlet.schema import normalize_game
from gauntlet.settings import Settings

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ch(win, **kw):
    return {"mode": "turns", "win": win, **kw}


def test_race_first_to_goal_ends_for_everyone():
    r = RaceReferee(ch({"type": "reach", "value": 10}), ["a", "b"])
    assert r.update({"a": 3, "b": 4}, 0.0) is None
    assert r.update({"a": 9, "b": 10}, 1.0) is None  # needs 2 confirming polls
    v = r.update({"a": 10, "b": 10}, 1.5)
    assert v.winners == ["b"] and v.losers == ["a"] and not v.draw
    assert v.reason == "first to the goal" and v.times["b"] == 1.5
    assert r.status("b") == "finished" and r.status("a") == "racing"
    assert r.update({"a": 99, "b": 0}, 2.0) is v  # decided: later values change nothing


def test_race_same_poll_finish_is_a_draw():
    r = RaceReferee(ch({"type": "reach", "value": 1}), ["a", "b"], confirm=1)
    v = r.update({"a": 1, "b": 1}, 0.0)
    assert v.draw and sorted(v.winners) == ["a", "b"]


def test_race_per_player_ready_gate_and_clock():
    r = RaceReferee(ch({"type": "reach", "value": 5}, time_limit=10), ["a", "b"], confirm=1)
    r.update({"a": 0, "b": 0}, 0.0, {"a": True, "b": False})
    assert r.status("a") == "racing" and r.status("b") == "waiting"
    r.update({"a": 0, "b": 0}, 2.0, {"a": True, "b": True})
    assert r.elapsed(3.0) == {"a": 3.0, "b": 1.0}
    assert r.remaining(3.0) == 9.0  # the slowest starter still has 9s
    v = r.update({"a": 0, "b": 5}, 4.0)
    assert v.winners == ["b"] and v.times["b"] == 2.0


def test_race_timeout_ranks_by_score():
    r = RaceReferee(ch({"type": "reach", "value": 50}, time_limit=5), ["a", "b"], confirm=1)
    r.update({"a": 0, "b": 0}, 0.0)
    assert r.update({"a": 20, "b": 30}, 5.0).winners == ["b"]
    assert r.verdict.reason == "nobody finished: best score"


def test_race_compare_waits_for_everyone():
    r = RaceReferee(ch({"type": "compare", "order": "high"}, time_limit=5), ["a", "b"], confirm=1)
    r.update({"a": 0, "b": 0}, 0.0, {"a": True, "b": False})
    r.update({"a": 0, "b": 0}, 1.0, {"a": True, "b": True})
    assert r.update({"a": 7, "b": 3}, 5.0) is None  # b still has a second left
    v = r.update({"a": 7, "b": 9}, 6.0)
    assert v.winners == ["b"] and v.reason == "highest score"


def test_race_survival_last_one_standing():
    r = RaceReferee(ch({"type": "eliminate", "value": 0}, time_limit=60), ["a", "b", "c"], confirm=1)
    r.update({"a": 3, "b": 3, "c": 3}, 0.0)
    assert r.update({"a": 0, "b": 2, "c": 3}, 5.0) is None
    assert r.status("a") == "out"
    v = r.update({"a": 0, "b": 0, "c": 1}, 8.0)
    assert v.winners == ["c"] and sorted(v.losers) == ["a", "b"] and v.reason == "last one standing"


def test_race_survivors_at_time_limit_tie():
    r = RaceReferee(ch({"type": "eliminate", "value": 0}, time_limit=5), ["a", "b"], confirm=1)
    r.update({"a": 3, "b": 3}, 0.0)
    v = r.update({"a": 1, "b": 2}, 5.0)
    assert v.draw and sorted(v.winners) == ["a", "b"]


def test_race_player_quits():
    r = RaceReferee(ch({"type": "reach", "value": 9}), ["a", "b"], confirm=1)
    r.update({"a": 1, "b": 1}, 0.0)
    assert r.drop("a", 2.0) is None  # b can still finish
    assert r.status("a") == "out"
    assert r.update({"a": None, "b": 9}, 3.0).winners == ["b"]
    r2 = RaceReferee(ch({"type": "eliminate", "value": 0}), ["a", "b"], confirm=1)
    r2.update({"a": 1, "b": 1}, 0.0)
    assert r2.drop("a", 1.0).winners == ["b"]
    r3 = RaceReferee(ch({"type": "reach", "value": 9}), ["a", "b"], confirm=1)
    r3.update({"a": 4, "b": 1}, 0.0)
    r3.drop("a", 1.0)
    assert r3.drop("b", 2.0).winners == ["a"]  # nobody finished: best score


# ----------------------------------------------------------------------------- race setup
def pad(key, idx):
    return Participant(key, key.upper(), pad_index=idx)


def test_race_setup_rules():
    st = Settings()
    assert race_setup([pad("a", 0), pad("b", 1)], st).race
    assert race_setup([pad("a", 0), pad("b", 1)], st).input_driver is None
    assert not race_setup([pad("a", 0)], st).race
    shared = race_setup([pad("a", 0), pad("b", 0)], st)
    assert not shared.race and "share" in shared.note
    assert not race_setup([pad("a", 0), Participant("b", "B")], st).race  # no device = can't isolate
    kb, kb2 = Participant("a", "A", keyboard="keyboard"), Participant("b", "B", keyboard="keyboard2")
    assert race_setup([kb, kb2], st, udev=True) == RacePlan(True, "udev")
    no_udev = race_setup([kb, kb2], st, udev=False)
    assert not no_udev.race and "input" in no_udev.note
    one_kb = race_setup([kb, pad("b", 0)], st, udev=False)
    assert one_kb.race and one_kb.input_driver is None and "focused" in one_kb.note
    st.race_input_driver = "sdl2"
    assert race_setup([kb, kb2], st, udev=False) == RacePlan(True, "sdl2")
    st.simultaneous_play = False
    assert not race_setup([pad("a", 0), pad("b", 1)], st).race


def test_tile_rects():
    assert tile_rects(1, 1920, 1080) == [(0, 0, 1920, 1080)]
    assert tile_rects(2, 1920, 1080) == [(0, 0, 960, 1080), (960, 0, 960, 1080)]
    assert tile_rects(3, 1920, 1080) == [(0, 0, 960, 540), (960, 0, 960, 540), (0, 540, 960, 540)]
    assert len(tile_rects(4, 1920, 1080)) == 4
    assert tile_rects(2, 2560, 1414, 1720, -1414) == [(1720, -1414, 1280, 1414), (3000, -1414, 1280, 1414)]


def test_race_config_isolates_input():
    st = Settings()
    parts = [Participant("a", "A", keyboard="keyboard"), Participant("b", "B", keyboard="keyboard2"),
             pad("c", 3)]
    a = race_config(parts, [], st, 0, (0, 0, 960, 540), "udev")
    b = race_config(parts, [], st, 1)
    c = race_config(parts, [], st, 2)
    assert a["input_max_users"] == 1 and a["input_driver"] == "udev"
    assert "input_player1_up" not in a and a["input_player1_joypad_index"] == NO_PAD
    assert a["video_fullscreen"] is False and a["video_windowed_position_width"] == 960
    assert "audio_mute_enable" not in a and b["audio_mute_enable"] is True
    assert b["input_player1_up"] == KEYBOARD2_RA["up"] and b["input_player1_x"] == "nul"
    assert b["input_player1_joypad_index"] == NO_PAD
    assert c["input_player1_up"] == "nul" and c["input_player1_joypad_index"] == 3
    assert a["input_pause_toggle"] == "nul"  # 'p' is player 2's start button


# ----------------------------------------------------------------------------- end to end
def free_ports(n):
    """n consecutive free UDP ports, below Linux's ephemeral range so client sockets can't take them."""
    for _ in range(50):
        base = random.randrange(20000, 32000)
        socks = []
        try:
            for i in range(n):
                t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                socks.append(t)
                t.bind(("127.0.0.1", base + i))
            return base
        except OSError:
            pass
        finally:
            for t in socks:
                t.close()
    raise RuntimeError("no free ports")


def setup(tmp_path, monkeypatch, script, n=2):
    cores = tmp_path / "cores"
    cores.mkdir()
    (cores / "fake_libretro.so").write_text("")
    rom = tmp_path / "game.sfc"
    rom.write_text("")
    base = free_ports(n)
    script.setdefault("ram_size", 0x1000)
    script.setdefault("boot_delay", 0.1)
    script["by_port"] = {str(base + i): v for i, v in enumerate(script.pop("players", []))}
    (tmp_path / "script.json").write_text(json.dumps(script))
    monkeypatch.setenv("GAUNTLET_FAKE_SCRIPT", str(tmp_path / "script.json"))
    monkeypatch.setenv("GAUNTLET_FAKE_LOG", str(tmp_path / "fake{port}.log"))
    monkeypatch.setenv("PYTHONPATH", REPO)
    st = Settings(state_dir=str(tmp_path / "state"), core_dir=str(cores), retroarch_port=base,
                  poll_interval=0.05, close_delay=0.1, boot_timeout=10, start_states_dir=str(tmp_path / "ss"))
    launcher = Launcher(st, installs=[Install("Fake", [sys.executable, "-m", "gauntlet.fakera"])])
    game = normalize_game({"schema_version": 2,
                           "meta": {"name": "Fake", "system": "snes", "core": "fake", "rom": str(rom)},
                           "challenges": [], "shop": []})
    logs = [tmp_path / f"fake{base + i}.log" for i in range(n)]
    return st, launcher, game, logs


def run(runner, timeout=20):
    runner.start()
    runner.join(timeout)
    assert runner.finished, runner.snapshot()
    return runner.snapshot()


REACH = {"id": "coins", "name": "Coins", "mode": "turns", "min_time": 0, "time_limit": 30,
         "metric": {"address": "0x10"}, "win": {"type": "reach", "value": 5}}


def test_race_first_to_goal_closes_every_window(tmp_path, monkeypatch):
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {"players": [
        {"events": [{"at": 2.0, "address": 0x10, "bytes": [5]}]},
        {"events": [{"at": 0.8, "address": 0x10, "bytes": [5]}]}]})
    item = {"name": "Slow", "actions": [{"type": "memory_write", "address": "0x20", "value": 7}]}
    runner = MatchRunner(launcher, game, REACH, [pad("a", 0), pad("b", 1)], [Purchase(item, "a", ["b"])], st)
    assert runner.race.race
    snap = run(runner)
    assert snap["phase"] == "finished", snap
    assert runner.verdict.winners == ["b"] and runner.verdict.reason == "first to the goal"
    assert snap["players"]["b"]["status"] == "finished" and snap["players"]["a"]["status"] == "racing"
    a, b = (log.read_text() for log in logs)
    assert "WRITE_CORE_MEMORY 20 07" in b and "WRITE_CORE_MEMORY 20" not in a  # effect only in B's window
    assert "B wins!" in a and "B wins!" in b
    assert "QUIT" in a and "QUIT" in b
    assert all(i.process.poll() is not None for i in runner.instances)
    assert [r.player for r in runner.turn_results] == ["b"]
    cfg_b = read_cfg(os.path.join(st.sub_state("retroarch"), "race_p2.cfg"))
    assert cfg_b["network_cmd_port"] == str(st.retroarch_port + 1)
    assert cfg_b["savestate_directory"].endswith(os.path.join("states", "p2"))
    assert cfg_b["input_player1_joypad_index"] == "1"


class FakePlacer:
    """A compositor showing Gauntlet's own window and one per launched RetroArch (fakera opens none)."""
    name = "Fake"

    def __init__(self):
        self.runner = None
        self.placed = {}
        self.calls = []

    def area(self):
        return (1000, 20, 2000, 1000)

    def windows(self):
        procs = [i.process for i in self.runner.instances] + [self.runner.process]
        return [("gauntlet", os.getpid())] + [(f"w{p.pid}", p.pid) for p in procs if p]

    def place(self, wid, rect):
        self.placed[wid] = rect
        self.calls.append((wid, rect))
        return True

    def focus(self, wid):
        self.calls.append((wid, "focus"))
        return True

    def geometry(self, wid):
        return {"floating": False, "rect": (0, 0, 800, 600)}

    def restore(self, wid, geometry):
        self.calls.append((wid, "restore", geometry["floating"]))
        return True


def test_race_windows_are_placed_on_their_tiles(tmp_path, monkeypatch):
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {"players": [
        {"events": [{"at": 1.5, "address": 0x10, "bytes": [5]}]}, {}]})
    st.stage_layout = False
    backend = FakePlacer()
    runner = MatchRunner(launcher, game, REACH, [pad("a", 0), pad("b", 1)], [], st, placer=backend)
    backend.runner = runner
    assert not runner.stage
    snap = run(runner)
    assert snap["phase"] == "finished", snap
    pids = [i.process.pid for i in runner.instances]
    assert backend.placed == {f"w{pids[0]}": (1000, 20, 1000, 1000), f"w{pids[1]}": (2000, 20, 1000, 1000)}
    # once RetroArch is up every window is focused in turn (so it adopts its new size), ending on P1
    assert backend.calls[-2:] == [(f"w{pids[1]}", "focus"), (f"w{pids[0]}", "focus")]
    cfg_b = read_cfg(os.path.join(st.sub_state("retroarch"), "race_p2.cfg"))
    assert cfg_b["video_windowed_position_x"] == "2000"  # RetroArch's own keys agree with the tile
    assert not runner._placer._thread.is_alive()


def test_race_stage_layout_games_on_top_scoreboard_below(tmp_path, monkeypatch):
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {"players": [
        {"events": [{"at": 1.5, "address": 0x10, "bytes": [5]}]}, {}]})
    backend = FakePlacer()
    runner = MatchRunner(launcher, game, REACH, [pad("a", 0), pad("b", 1)], [], st, placer=backend)
    backend.runner = runner
    assert runner.stage
    snap = run(runner)
    assert snap["phase"] == "finished", snap
    pids = [i.process.pid for i in runner.instances]
    assert backend.placed == {f"w{pids[0]}": (1000, 20, 1000, 750), f"w{pids[1]}": (2000, 20, 1000, 750),
                              "gauntlet": (1000, 770, 2000, 250)}
    assert snap["hud"] == (1000, 770, 2000, 250)
    assert ("gauntlet", "focus") not in backend.calls  # only game windows are focused
    assert backend.calls[-1] == ("gauntlet", "restore", False)  # put back before the result shows


def test_versus_stage_layout_places_the_shared_window(tmp_path, monkeypatch):
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {
        "events": [{"at": 0.0, "address": 0x10, "bytes": [3]}, {"at": 0.0, "address": 0x11, "bytes": [3]},
                   {"at": 1.2, "address": 0x11, "bytes": [0]}]}, n=1)
    st.stage_hud_percent = 30
    ch = {"id": "ko", "name": "KO", "mode": "versus", "min_time": 0, "time_limit": 30,
          "metric": {"address": {"1": "0x10", "2": "0x11"}}, "win": {"type": "eliminate", "value": 0}}
    backend = FakePlacer()
    players = [Participant("a", "A", 1, 0), Participant("b", "B", 2, 1)]
    runner = MatchRunner(launcher, game, ch, players, [], st, placer=backend)
    backend.runner = runner
    snap = run(runner)
    assert snap["phase"] == "finished" and runner.verdict.winners == ["a"], snap
    pid = runner.process.pid
    assert backend.placed == {f"w{pid}": (1000, 20, 2000, 700), "gauntlet": (1000, 720, 2000, 300)}
    cfg = read_cfg(os.path.join(st.sub_state("retroarch"), "match.cfg"))
    assert cfg["video_fullscreen"] == "false" and cfg["video_windowed_position_y"] == "20"
    assert backend.calls[-1] == ("gauntlet", "restore", False)


def test_race_window_closed_counts_as_quit(tmp_path, monkeypatch):
    ch = dict(REACH, win={"type": "eliminate", "value": 0})
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {
        "events": [{"at": 0.0, "address": 0x10, "bytes": [3]}],
        "players": [{"exit_at": 1.5}, {}]})
    runner = MatchRunner(launcher, game, ch, [pad("a", 0), pad("b", 1)], [], st)
    snap = run(runner)
    assert snap["phase"] == "finished", snap
    assert runner.verdict.winners == ["b"] and runner.verdict.reason == "last one standing"


def test_race_start_state_in_every_window(tmp_path, monkeypatch):
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {"players": [{}, {}]})
    os.makedirs(st.start_states_dir)
    with open(os.path.join(st.start_states_dir, "s.state"), "w") as f:
        json.dump([{"address": 0x10, "bytes": [5]}], f)
    runner = MatchRunner(launcher, game, dict(REACH, start_state="s.state"), [pad("a", 0), pad("b", 1)], [], st)
    snap = run(runner)
    assert snap["phase"] == "finished" and runner.verdict.draw  # both start at the goal
    for log in logs:
        assert "ENTRY_STATE game.state1 ok" in log.read_text()
    for folder in ("p1", "p2"):
        assert os.path.isfile(os.path.join(st.sub_state("states", folder), "game.state1"))


def start_playing(runner):
    runner.start()
    deadline = time.time() + 10
    while runner.snapshot()["phase"] != "playing" and time.time() < deadline:
        time.sleep(0.05)


def test_race_end_early_needs_manual_result(tmp_path, monkeypatch):
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {"players": [{}, {}]})
    runner = MatchRunner(launcher, game, REACH, [pad("a", 0), pad("b", 1)], [], st)
    start_playing(runner)
    runner.end()
    assert run(runner)["phase"] == "no_verdict"
    assert all(i.process.poll() is not None for i in runner.instances)


def test_race_forfeit(tmp_path, monkeypatch):
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {"players": [{}, {}]})
    runner = MatchRunner(launcher, game, REACH, [pad("a", 0), pad("b", 1)], [], st)
    start_playing(runner)
    runner.forfeit("b")
    snap = run(runner)
    assert snap["phase"] == "finished" and runner.verdict.winners == ["a"]
    assert all(i.process.poll() is not None for i in runner.instances)


def test_race_second_port_in_use(tmp_path, monkeypatch):
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {})
    fake = FakeRetroArch(port=st.retroarch_port + 1, ram_size=16)
    fake.start_thread()
    try:
        runner = MatchRunner(launcher, game, REACH, [pad("a", 0), pad("b", 1)], [], st)
        snap = run(runner)
        assert snap["phase"] == "error" and str(st.retroarch_port + 1) in snap["message"]
        assert not runner.instances[0].process
    finally:
        fake.running = False


def test_race_off_takes_turns(tmp_path, monkeypatch):
    st, launcher, game, logs = setup(tmp_path, monkeypatch, {
        "events": [{"at": 0.3, "address": 0x10, "bytes": [5]}]})
    st.simultaneous_play = False
    runner = MatchRunner(launcher, game, REACH, [pad("a", 0), pad("b", 1)], [], st)
    snap = run(runner, 30)
    assert snap["phase"] == "finished" and len(runner.turn_results) == 2 and not runner.instances
