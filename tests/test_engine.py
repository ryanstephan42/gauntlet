import json
import os
import socket
import sys
import time

import pytest

from gauntlet.actions import Effect, EffectContext, EffectScheduler, collect_config
from gauntlet.detect import Install, find_core, find_rom, list_cores
from gauntlet.fakera import FakeRetroArch
from gauntlet.match import MatchRunner, Participant, Purchase, build_config, plan_effects
from gauntlet.memory import Memory, Var, compare, host_address, parse_int, var_for
from gauntlet.referee import Referee, TurnReferee, TurnResult, forfeit_verdict, rank_turns
from gauntlet.retroarch import Launcher, RetroArchClient, parse_status
from gauntlet.schema import normalize_game, validate_game
from gauntlet.settings import Settings
from gauntlet.systems import guess_system

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def fake():
    ra = FakeRetroArch(port=0, ram_size=0x10000)
    ra.start_thread()
    yield ra
    ra.running = False


@pytest.fixture
def client(fake):
    c = RetroArchClient("127.0.0.1", fake.port, timeout=0.3)
    yield c
    c.close()


# ----------------------------------------------------------------------------- memory
def test_parse_int_formats():
    assert parse_int("0x1F") == 31
    assert parse_int("$1F") == 31
    assert parse_int(12) == 12
    with pytest.raises(ValueError):
        parse_int(True)


def test_host_address_layouts():
    assert host_address(0x33B21D, "swap32") == 0x33B21E
    assert host_address(0x10, "swap16") == 0x11
    assert host_address(0x10, "linear") == 0x10


def test_var_encode_decode_signed_and_clamp():
    v = Var(0, size=2, endian="big", signed=True)
    assert v.decode(v.encode(-5)) == -5
    assert v.decode(v.encode(99999)) == 32767
    u = Var(0, size=1)
    assert u.decode(u.encode(-3)) == 0


def test_var_bit_and_mask_merge():
    v = Var(0, size=1, bit=3)
    assert v.decode(bytes([0b1000])) == 1
    assert v.merge(bytes([0b0001]), 1) == bytes([0b1001])
    m = Var(0, size=1, mask=0x0F)
    assert m.merge(bytes([0xA5]), 0x3) == bytes([0xA3])


def test_var_for_per_player_and_stride():
    spec = {"address": {"1": "0x10", "2": "0x20"}}
    assert var_for(spec, 2).address == 0x20
    with pytest.raises(KeyError):
        var_for(spec, 3)
    assert var_for({"address": "0x100", "stride": "0x40"}, 3).address == 0x180
    assert compare("ge", 5, 5) and not compare("lt", 5, 5)


def test_memory_roundtrip_swap32(client, fake):
    mem = Memory(client, "swap32")
    var = Var(0x100, size=2, endian="big")
    assert mem.write(var, 0x1234)
    # logical bytes 12 34 at 0x100/0x101 land at host 0x103/0x102
    assert fake.ram[0x103] == 0x12 and fake.ram[0x102] == 0x34
    assert mem.read(var) == 0x1234


# ----------------------------------------------------------------------------- client
def test_client_status_and_chunked_read(client, fake):
    st = client.status()
    assert st.state == "PLAYING" and st.running
    fake.poke(0x2000, range(256))
    client.chunk = 100
    data = client.read_bytes(0x2000, 256)
    assert list(data) == list(range(256))
    assert client.read_bytes(0x20000, 4) is None


def test_client_no_server_returns_none():
    c = RetroArchClient("127.0.0.1", free_port(), timeout=0.1)
    assert c.status() is None
    assert not c.is_ready()


def test_parse_status_variants():
    assert parse_status("GET_STATUS CONTENTLESS").state == "CONTENTLESS"
    st = parse_status("GET_STATUS PAUSED nintendo_64,Super Mario 64 (USA),crc32=3ce60709")
    assert st.state == "PAUSED" and st.content == "Super Mario 64 (USA)"


def test_client_messages(client, fake):
    client.show_msg("hello")
    time.sleep(0.2)
    assert "hello" in fake.messages


# ----------------------------------------------------------------------------- detect
def test_list_and_find_core(tmp_path):
    (tmp_path / "snes9x_libretro.so").write_text("")
    (tmp_path / "snes9x_libretro.info").write_text("")
    assert set(list_cores([str(tmp_path)])) == {"snes9x"}
    assert find_core("snes9x", [str(tmp_path)]).endswith("snes9x_libretro.so")
    assert find_core("snes9x_libretro", [str(tmp_path)])
    assert find_core("missing", [str(tmp_path)]) is None


def test_find_rom_in_system_folder(tmp_path):
    (tmp_path / "snes").mkdir()
    rom = tmp_path / "snes" / "Game (USA).sfc"
    rom.write_text("")
    assert find_rom("Game (USA).sfc", "snes", [str(tmp_path)]) == str(rom)
    assert guess_system(str(rom)) == "snes"


def test_install_core_arg_translation():
    inst = Install("x", ["ra"], host_core_dir="/host/cores", sandbox_core_dir="/app/cores", sandboxed=True)
    assert inst.core_arg("/host/cores/a_libretro.so") == "/app/cores/a_libretro.so"


# ----------------------------------------------------------------------------- schema
def test_v1_migration_to_v2():
    v1 = {"meta": {"name": "G", "core": "mupen64plus_next_libretro.so", "rom": "g.z64"},
          "referee": {"address": "0x10", "bytes": 1, "win_value": 3},
          "shop": [{"id": "a", "name": "A", "cost": 1, "action_type": "memory_write",
                    "address": "0x10", "value": 1}]}
    g = normalize_game(v1)
    assert g["schema_version"] == 2
    assert g["meta"]["system"] == "n64"
    assert g["memory"]["layout"] == "swap32"
    assert g["challenges"][0]["win"] == {"type": "reach", "value": 3}
    assert g["shop"][0]["actions"][0]["type"] == "memory_write"
    assert validate_game(g) == []


def test_validate_reports_bad_challenge():
    g = normalize_game({"schema_version": 2, "meta": {"name": "G", "system": "snes", "core": "snes9x",
                                                      "rom": "x.sfc"},
                        "challenges": [{"id": "c", "name": "C", "mode": "versus",
                                        "metric": {"address": "0x1"}, "win": {"type": "compare"}}],
                        "shop": []})
    errors = validate_game(g)
    assert any("time_limit" in e for e in errors)


def test_repo_games_are_v2_valid():
    from gauntlet.games import load_games
    games, problems = load_games(os.path.join(REPO, "gauntlet_data"))
    assert games and problems == {}
    for g in games:
        assert validate_game(g) == [], g["meta"]["name"]


# ----------------------------------------------------------------------------- actions
def test_effect_timed_restore_and_freeze(client, fake):
    mem = Memory(client)
    ctx = EffectContext(client, mem)
    fake.poke(0x10, [5])
    timed = Effect({"type": "memory_write", "address": "0x10", "value": 1, "op": "add",
                    "duration": 1.0, "restore": True})
    freeze = Effect({"type": "memory_write", "address": "0x20", "value": 9, "repeat": 0.1, "duration": 0.5})
    sched = EffectScheduler(ctx, [timed, freeze])
    sched.tick(0.0)
    assert fake.ram[0x10] == 6 and fake.ram[0x20] == 9
    fake.poke(0x20, [0])
    sched.tick(0.3)
    assert fake.ram[0x20] == 9
    sched.tick(1.2)
    assert fake.ram[0x10] == 5
    assert not sched.failures


def test_effect_when_condition_and_delay(client, fake):
    ctx = EffectContext(client, Memory(client))
    e = Effect({"type": "memory_write", "address": "0x30", "value": 7, "delay": 0.5,
                "when": {"address": "0x31", "op": "eq", "value": 1}})
    sched = EffectScheduler(ctx, [e])
    sched.tick(0.6)
    assert fake.ram[0x30] == 0
    fake.poke(0x31, [1])
    sched.tick(0.7)
    assert fake.ram[0x30] == 7


def test_message_placeholders(client, fake):
    ctx = EffectContext(client, Memory(client), names={1: "Ann", 2: "Bob"})
    EffectScheduler(ctx, [Effect({"type": "message", "text": "{buyer} hits {target}"}, 1, "", 1, 2)]).tick(0)
    time.sleep(0.2)
    assert "Ann hits Bob" in fake.messages


def test_collect_config(tmp_path):
    (tmp_path / "x.cfg").write_text('video_shader_enable = "true"\n')
    merged = collect_config([{"type": "retroarch_config", "config_file": "x.cfg"},
                             {"type": "retroarch_config", "settings": {"fastforward_ratio": "2.0"}},
                             {"type": "message", "text": "hi"}], str(tmp_path))
    assert merged == {"video_shader_enable": "true", "fastforward_ratio": "2.0"}


# ----------------------------------------------------------------------------- referee
def _ch(**kw):
    base = {"mode": "versus", "win": {"type": "reach", "value": 3}, "min_time": 0, "on_timeout": "compare"}
    base.update(kw)
    return base


def test_referee_reach_needs_confirmation():
    r = Referee(_ch(), ["a", "b"])
    assert r.update({"a": 3, "b": 0}, 0) is None
    v = r.update({"a": 3, "b": 1}, 0.2)
    assert v.winners == ["a"] and v.losers == ["b"]


def test_referee_ready_gating_and_timeout_compare():
    r = Referee(_ch(win={"type": "compare", "order": "low"}, time_limit=10), ["a", "b"])
    assert r.update({"a": 5, "b": 2}, 1, ready=False) is None
    assert r.started_at is None
    r.update({"a": 5, "b": 2}, 2)
    v = r.update({"a": 5, "b": 2}, 12.5)
    assert v.winners == ["b"]


def test_referee_eliminate_last_standing():
    r = Referee(_ch(win={"type": "eliminate", "value": 0}), ["a", "b", "c"])
    for t in range(2):
        r.update({"a": 0, "b": 2, "c": 0}, t)
    v = r.update({"a": 0, "b": 2, "c": 0}, 3)
    assert v.winners == ["b"]


def test_referee_coop_team_goal_and_timeout():
    r = Referee(_ch(mode="coop"), ["a", "b"])
    r.update({"a": 3, "b": 3}, 0)
    assert r.update({"a": 3, "b": 3}, 1).winners == ["a", "b"]
    r = Referee(_ch(mode="coop", time_limit=5, on_timeout="draw"), ["a", "b"])
    r.update({"a": 0, "b": 0}, 0)
    v = r.update({"a": 0, "b": 0}, 6)
    assert v.draw and v.winners == ["a", "b"]


def test_turns_ranking():
    ch = _ch(mode="turns", time_limit=60)
    t = TurnReferee(ch, "a")
    t.update(0, 0)
    t.update(3, 10)
    res_a = t.update(3, 10.5)
    assert res_a.success and res_a.time == 10.5
    res_b = TurnResult("b", True, 8.0, 3)
    v = rank_turns(ch, [res_a, res_b])
    assert v.winners == ["b"] and v.reason == "fastest to the goal"
    assert TurnReferee(ch, "c").stop(3).success is False


def test_forfeit_verdict():
    v = forfeit_verdict(["a", "b"], "a")
    assert v.winners == ["b"] and v.forfeit == "a" and not v.draw


# ----------------------------------------------------------------------------- match planning
def test_plan_effects_targets_ports():
    game = {"meta": {"name": "G"}}
    ch = {"mode": "versus"}
    parts = [Participant("a", "Ann", 1), Participant("b", "Bob", 2)]
    item = {"name": "Poison", "actions": [{"type": "memory_write", "address": {"1": "0x1", "2": "0x2"},
                                           "value": 0}]}
    effects = plan_effects(game, ch, parts, [Purchase(item, "a", ["b"])])
    writes = [e for e in effects if e.action["type"] == "memory_write"]
    assert [e.port for e in writes] == [2]
    assert any(e.action["type"] == "message" for e in effects)


def test_plan_effects_turns_only_current_player():
    game = {"meta": {"name": "G"}}
    ch = {"mode": "turns"}
    parts = [Participant("a", "Ann"), Participant("b", "Bob")]
    item = {"name": "Slow", "actions": [{"type": "memory_write", "address": "0x1", "value": 0}]}
    pu = [Purchase(item, "a", ["b"])]
    assert not [e for e in plan_effects(game, ch, parts, pu, "a") if e.action["type"] == "memory_write"]
    eff = [e for e in plan_effects(game, ch, parts, pu, "b") if e.action["type"] == "memory_write"]
    assert len(eff) == 1 and eff[0].port == 1


def test_build_config_ports(tmp_path):
    st = Settings(config_dir=str(tmp_path))
    parts = [Participant("a", "A", 1, pad_index=1), Participant("b", "B", 2, keyboard="keyboard2")]
    cfg = build_config(parts, [], st)
    assert cfg["input_player1_joypad_index"] == 1
    assert cfg["input_player2_a"] == "u"
    assert cfg["input_max_users"] == 2
    cfg = build_config(parts, [], st, turn_player="a")
    assert cfg["input_max_users"] == 1 and "input_player2_a" not in cfg


# ----------------------------------------------------------------------------- end to end
def _e2e_setup(tmp_path, monkeypatch, script):
    cores = tmp_path / "cores"
    cores.mkdir()
    (cores / "fake_libretro.so").write_text("")
    rom = tmp_path / "game.sfc"
    rom.write_text("")
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(script))
    monkeypatch.setenv("GAUNTLET_FAKE_SCRIPT", str(script_path))
    monkeypatch.setenv("GAUNTLET_FAKE_LOG", str(tmp_path / "fake.log"))
    monkeypatch.setenv("PYTHONPATH", REPO)
    st = Settings(state_dir=str(tmp_path / "state"), core_dir=str(cores), retroarch_port=free_port(),
                  poll_interval=0.05, close_delay=0.1, boot_timeout=10)
    launcher = Launcher(st, installs=[Install("Fake", [sys.executable, "-m", "gauntlet.fakera"])])
    game = normalize_game({"schema_version": 2,
                           "meta": {"name": "Fake", "system": "snes", "core": "fake", "rom": str(rom)},
                           "challenges": [], "shop": []})
    return st, launcher, game


def _wait(runner, timeout=20):
    runner.join(timeout)
    assert runner.finished, runner.snapshot()
    return runner.snapshot()


def test_match_runner_versus_e2e(tmp_path, monkeypatch):
    script = {"ram_size": 0x1000, "boot_delay": 0.2,
              "events": [{"at": 1.5, "address": 0x11, "bytes": [3]}]}
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, script)
    ch = {"id": "c", "name": "C", "mode": "versus", "min_time": 0, "on_timeout": "compare",
          "metric": {"address": {"1": "0x10", "2": "0x11"}}, "win": {"type": "reach", "value": 3}}
    item = {"name": "Boost", "actions": [{"type": "memory_write", "address": {"1": "0x20", "2": "0x21"},
                                          "value": 42}]}
    runner = MatchRunner(launcher, game, ch, [Participant("a", "Ann", 1), Participant("b", "Bob", 2)],
                         [Purchase(item, "a", ["a"])], st)
    runner.start()
    snap = _wait(runner)
    assert snap["phase"] == "finished"
    assert runner.verdict.winners == ["b"]
    log = (tmp_path / "fake.log").read_text()
    assert "WRITE_CORE_MEMORY 20 2A" in log
    assert "Bob wins!" in log
    assert "QUIT" in log
    assert runner.process.poll() is not None


def test_match_runner_manual_no_verdict(tmp_path, monkeypatch):
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, {"boot_delay": 0.1, "exit_at": 1.0})
    runner = MatchRunner(launcher, game, {"id": "m", "name": "M", "mode": "manual"},
                         [Participant("a", "A", 1), Participant("b", "B", 2)], [], st)
    runner.start()
    snap = _wait(runner)
    assert snap["phase"] == "no_verdict" and runner.verdict is None


def test_match_runner_forfeit(tmp_path, monkeypatch):
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, {"boot_delay": 0.1})
    runner = MatchRunner(launcher, game, {"id": "m", "name": "M", "mode": "manual"},
                         [Participant("a", "A", 1), Participant("b", "B", 2)], [], st)
    runner.start()
    deadline = time.time() + 10
    while runner.snapshot()["phase"] != "playing" and time.time() < deadline:
        time.sleep(0.05)
    runner.forfeit("a")
    snap = _wait(runner)
    assert snap["phase"] == "finished" and runner.verdict.winners == ["b"]


def test_match_runner_turns_e2e(tmp_path, monkeypatch):
    script = {"ram_size": 0x1000, "boot_delay": 0.1,
              "events": [{"at": 0.8, "address": 0x10, "bytes": [5]}]}
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, script)
    ch = {"id": "t", "name": "T", "mode": "turns", "min_time": 0, "on_timeout": "compare", "time_limit": 30,
          "metric": {"address": "0x10"}, "win": {"type": "reach", "value": 5}}
    runner = MatchRunner(launcher, game, ch, [Participant("a", "A"), Participant("b", "B")], [], st)
    runner.start()
    snap = _wait(runner, 30)
    assert snap["phase"] == "finished"
    assert len(runner.turn_results) == 2 and all(r.success for r in runner.turn_results)
    assert runner.verdict.reason == "fastest to the goal"


def test_match_runner_missing_rom_errors(tmp_path, monkeypatch):
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, {})
    game["meta"]["rom"] = str(tmp_path / "nope.sfc")
    runner = MatchRunner(launcher, game, {"id": "m", "name": "M", "mode": "manual"},
                         [Participant("a", "A")], [], st)
    runner.start()
    snap = _wait(runner)
    assert snap["phase"] == "error" and "ROM not found" in snap["message"]


def test_match_runner_port_in_use(tmp_path, monkeypatch, fake):
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, {})
    st.retroarch_port = fake.port
    runner = MatchRunner(launcher, game, {"id": "m", "name": "M", "mode": "manual"},
                         [Participant("a", "A")], [], st)
    runner.start()
    snap = _wait(runner)
    assert snap["phase"] == "error" and "already" in snap["message"]
