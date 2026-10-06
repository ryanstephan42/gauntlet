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
from gauntlet.memory import Memory, Var, compare, host_address, parse_int, read_metric, var_for
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


def test_read_metric_adds_scaled_terms(client, fake):
    mem = Memory(client)
    fake.poke(0x10, [3, 4, 5, 1, 9])
    team = {"address": "0x10", "add": [{"address": "0x11"}, {"address": "0x12"}]}
    assert read_metric(mem, team) == 12
    score = {"address": {"1": "0x10", "2": "0x11"}, "add": [{"address": {"1": "0x13", "2": "0x14"}, "scale": -1}]}
    assert read_metric(mem, score, 1) == 2 and read_metric(mem, score, 2) == -5
    assert read_metric(mem, {"address": "0x10"}) == 3
    assert read_metric(mem, {"address": "0x10", "add": [{"address": "0x90000"}]}) is None


def test_metric_add_validation():
    def game(metric):
        return {"schema_version": 2, "meta": {"name": "T", "core": "c", "rom": "r", "players": 2},
                "challenges": [{"id": "a", "name": "A", "mode": "versus", "metric": metric,
                                "win": {"type": "reach", "value": 1}}]}
    assert validate_game(game({"address": "0x10", "add": [{"address": "0x11", "scale": -1}]})) == []
    assert any("add must be" in e for e in validate_game(game({"address": "0x10", "add": []})))
    assert any("scale" in e for e in validate_game(game({"address": "0x10", "add": [{"address": "0x11",
                                                                                     "scale": "x"}]})))
    assert any("address" in e for e in validate_game(game({"address": "0x10", "add": [{"size": 1}]})))
    assert validate_game(game({"address": "0x10", "count": 3, "step": "0x2", "add": [{"address": "0x20",
                                                                                     "count": 2}]})) == []
    assert any("count" in e for e in validate_game(game({"address": "0x10", "count": 0})))
    assert any("step needs count" in e for e in validate_game(game({"address": "0x10", "step": "0x2"})))


def test_read_metric_count_step_sums_counters(client, fake):
    mem = Memory(client, "swap32")
    for i, v in enumerate([1, 2, 3, 4]):
        Memory(client, "swap32").write(Var(0x40 + 0x10 * i + 2, 2, "big"), v)
    assert read_metric(mem, {"address": "0x42", "size": 2, "endian": "big", "count": 4, "step": "0x10"}) == 10
    spec = {"address": "0x42", "size": 2, "endian": "big", "count": 2, "step": "0x10",
            "add": [{"address": "0x62", "size": 2, "endian": "big", "count": 2, "step": "0x10", "scale": 10}]}
    assert read_metric(mem, spec) == 3 + 70


def test_read_metric_count_step_reads_distant_counters_individually():
    class ReadClient:
        def __init__(self):
            self.reads = []

        def read_bytes(self, address, size):
            self.reads.append((address, size))
            return bytes([address & 0xFF]) * size

    client = ReadClient()
    mem = Memory(client)
    spec = {"address": "0x10", "size": 1, "count": 2, "step": "0x10000000"}

    assert read_metric(mem, spec) == 0x20
    assert client.reads == [(0x10, 1), (0x10000010, 1)]


def test_read_metric_contiguous_and_overlapping_counters_use_one_block():
    class ReadClient:
        def __init__(self):
            self.reads = []

        def read_bytes(self, address, size):
            self.reads.append((address, size))
            return bytes([1]) * size

    client = ReadClient()
    mem = Memory(client)

    assert read_metric(mem, {"address": "0x10", "size": 2, "count": 2}) == 514
    assert read_metric(mem, {"address": "0x20", "size": 2, "count": 2, "step": 1}) == 514
    assert client.reads == [(0x10, 4), (0x20, 3)]


def test_read_metric_follows_pointer(client, fake):
    mem = Memory(client, "swap32")
    ptr = {"address": "0x100", "mask": "0xFFFFFF"}
    spec = {"address": "0x47", "size": 1, "pointer": ptr, "add": [{"address": "0x70", "pointer": ptr, "scale": -16}]}
    defaults = {"endian": "big"}
    assert read_metric(mem, spec, 1, defaults) is None  # null pointer: object not loaded yet
    mem.write(Var(0x100, 4, "big"), 0x80000200)
    mem.write(Var(0x247, 1), 3)
    mem.write(Var(0x270, 1), 1)
    assert read_metric(mem, spec, 1, defaults) == 3 - 16
    mem.write(Var(0x100, 4, "big"), 0x80000400)
    mem.write(Var(0x447, 1), 5)
    assert read_metric(mem, spec, 1, defaults) == 5
    chained = {"address": "0x47", "pointer": {"address": "0x0", "mask": "0xFFFFFF",
                                              "pointer": {"address": "0x500", "mask": "0xFFFFFF"}}}
    assert read_metric(mem, chained, 1, defaults) is None
    mem.write(Var(0x500, 4, "big"), 0x80000100)
    assert read_metric(mem, chained, 1, defaults) == 5

def test_metric_pointer_validation():
    def game(metric):
        return {"schema_version": 2, "meta": {"name": "T", "core": "c", "rom": "r", "players": 1},
                "challenges": [{"id": "a", "name": "A", "mode": "turns", "metric": metric,
                                "win": {"type": "reach", "value": 1}}]}
    assert validate_game(game({"address": "0x47", "pointer": {"address": "0x100", "mask": "0xFFFFFF"}})) == []
    assert any("pointer must be" in e for e in validate_game(game({"address": "0x47", "pointer": "0x100"})))
    assert any("pointer" in e for e in validate_game(game({"address": "0x47", "pointer": {"size": 4}})))
    assert any("pointer.pointer" in e for e in validate_game(game({"address": "0x47", "pointer": {
        "address": "0x0", "pointer": {"address": "zz"}}})))

# ----------------------------------------------------------------------------- client
def test_client_status_and_chunked_read(client, fake):
    st = client.status()
    assert st.state == "PLAYING" and st.running
    fake.poke(0x2000, range(256))
    client.chunk = 100
    data = client.read_bytes(0x2000, 256)
    assert list(data) == list(range(256))
    assert client.read_bytes(0x20000, 4) is None


def test_client_falls_back_to_core_ram_without_memory_map():
    ra = FakeRetroArch(port=0, ram_size=0x20000, memory_map=False)
    ra.start_thread()
    c = RetroArchClient("127.0.0.1", ra.port, timeout=0.3)
    try:
        ra.poke(0x0E00, [7, 8])
        assert c.read_bytes(0x0E00, 2) == bytes([7, 8]) and c.ram_api
        assert c.write_bytes(0x0E00, bytes([9])) == 1
        assert ra.ram[0x0E00] == 9
        assert any(cmd.startswith("WRITE_CORE_RAM e00 09") for cmd in ra.commands)
        mem = Memory(c)
        assert mem.write(Var(0x10, size=2), 0x1234) and mem.read(Var(0x10, size=2)) == 0x1234
        # a write before any read also detects the fallback
        c2 = RetroArchClient("127.0.0.1", ra.port, timeout=0.3)
        assert c2.write_bytes(0x20, bytes([5])) == 1 and c2.ram_api and ra.ram[0x20] == 5
        c2.close()
    finally:
        c.close()
        ra.running = False


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


def test_retroarch_overrides_written_but_network_kept(tmp_path):
    st = Settings(state_dir=str(tmp_path), retroarch_port=55999,
                  retroarch_overrides={"input_joypad_driver": "null", "network_cmd_port": 1, "video_vsync": False})
    launcher = Launcher(st, installs=[Install("Fake", ["true"])])
    text = open(launcher.write_config("t", {"input_max_users": 2})).read()
    assert 'input_joypad_driver = "null"' in text and 'video_vsync = "false"' in text
    assert 'network_cmd_port = "55999"' in text and 'input_max_users = "2"' in text
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"retroarch_overrides": {"a": [1]}}))
    from gauntlet.settings import load_settings
    assert load_settings(str(p)).retroarch_overrides == {}


def test_start_state_lookup_and_staging(tmp_path, monkeypatch):
    from gauntlet import startstate
    user, bundled = tmp_path / "user", tmp_path / "app" / "start_states"
    user.mkdir()
    bundled.mkdir(parents=True)
    monkeypatch.setattr(startstate, "app_root", lambda: str(tmp_path / "app"))
    st = Settings(state_dir=str(tmp_path / "state"), start_states_dir=str(user))
    (bundled / "a.state").write_bytes(b"bundled")
    assert startstate.find_start_state(st, {"start_state": "a.state"}) == (str(bundled / "a.state"), "a.state")
    (user / "a.state").write_bytes(b"user")      # a capture overrides the bundled file
    assert startstate.find_start_state(st, {"start_state": "a.state"})[0] == str(user / "a.state")
    assert startstate.find_start_state(st, {"start_state": "nope.state"}) == (None, "nope.state")
    assert startstate.find_start_state(st, {}) == (None, None)
    assert startstate.find_start_state(st, {"start_state": "../a.state"}) == (None, None)
    dest = startstate.stage(str(user / "a.state"), str(tmp_path / "ra"), "/roms/Game (USA).sfc")
    assert os.path.basename(dest) == "Game (USA).state1" and open(dest, "rb").read() == b"user"
    game = {"meta": {"name": "Mortal Kombat II"}}
    assert startstate.state_filename(game, {"id": "ko"}) == "mortal_kombat_ii_ko.state"
    folder = tmp_path / "cap"
    folder.mkdir()
    (folder / "x.state").write_bytes(b"1")
    (folder / "x.state1.png").write_bytes(b"png")
    os.utime(folder / "x.state", (1, 1))
    (folder / "x.state2").write_bytes(b"2")
    assert startstate.newest_state(str(folder)).endswith("x.state2")
    startstate.clear_folder(str(folder))
    assert startstate.newest_state(str(folder)) is None
    for bad in ("a/b.state", "..", "", [], ["ok.state", "../x.state"], ["ok.state", 3]):
        g = normalize_game({"schema_version": 2, "meta": {"name": "T", "core": "c", "rom": "r"},
                            "challenges": [{"id": "m", "name": "M", "mode": "manual", "start_state": bad}]})
        assert any("start_state" in e for e in validate_game(g)), bad


def test_several_start_states_one_picked_per_match(tmp_path):
    import random
    from gauntlet import startstate
    user = tmp_path / "user"
    user.mkdir()
    for n in ("l1.state", "l2.state", "l3.state"):
        (user / n).write_bytes(n.encode())
    st = Settings(state_dir=str(tmp_path / "state"), start_states_dir=str(user))
    ch = {"start_state": ["l1.state", "l2.state", "gone.state", "l3.state"]}
    assert startstate.state_names(ch) == ["l1.state", "l2.state", "gone.state", "l3.state"]
    picks = {startstate.find_start_state(st, ch, random.Random(i))[1] for i in range(60)}
    assert picks == {"l1.state", "l2.state", "l3.state"}           # missing files are never picked
    assert startstate.find_start_state(st, {"start_state": ["gone.state", "l2.state"]}) == (
        str(user / "l2.state"), "l2.state")
    assert startstate.find_start_state(st, {"start_state": ["gone.state"]}) == (None, "gone.state")
    # stored as a plain string for one state (older format), a list for more, removed when empty
    c = {}
    startstate.set_state_names(c, ["a.state"])
    assert c == {"start_state": "a.state"}
    startstate.set_state_names(c, ["a.state", "b.state", "a.state", "../x"])
    assert c == {"start_state": ["a.state", "b.state"]}
    startstate.set_state_names(c, [])
    assert c == {}
    game = {"meta": {"name": "Super Mario 64"}}
    assert startstate.next_state_name(game, {"id": "star"}) == "super_mario_64_star.state"
    assert startstate.next_state_name(game, {"id": "star"}, ["super_mario_64_star.state"]) == (
        "super_mario_64_star_2.state")
    g = normalize_game({"schema_version": 2, "meta": {"name": "T", "core": "c", "rom": "r"},
                        "challenges": [{"id": "m", "name": "M", "mode": "manual",
                                        "start_state": ["a.state", "b.state"]}]})
    assert validate_game(g) == []


def test_launcher_entry_slot_and_flat_states(tmp_path):
    st = Settings(state_dir=str(tmp_path))
    launcher = Launcher(st, installs=[Install("Fake", ["ra"])])
    assert launcher.command("c.so", "g.sfc", "x.cfg", 1)[-2:] == ["--entryslot", "1"]
    assert "--entryslot" not in launcher.command("c.so", "g.sfc", "x.cfg")
    text = open(launcher.write_config("t")).read()
    assert 'sort_savestates_by_content_enable = "false"' in text and 'savestate_auto_load = "false"' in text


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
                  poll_interval=0.05, close_delay=0.1, boot_timeout=10, start_countdown=0)
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


def test_countdown_holds_the_first_frame_then_starts_the_clock(tmp_path, monkeypatch):
    script = {"ram_size": 0x1000, "boot_delay": 0.2, "events": [{"at": 2.0, "address": 0x11, "bytes": [3]}]}
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, script)
    st.start_countdown = 2
    ch = {"id": "c", "name": "C", "mode": "versus", "min_time": 0, "on_timeout": "compare",
          "metric": {"address": {"1": "0x10", "2": "0x11"}}, "win": {"type": "reach", "value": 3}}
    runner = MatchRunner(launcher, game, ch, [Participant("a", "Ann", 1), Participant("b", "Bob", 2)], [], st)
    runner.start()
    phases = set()
    deadline = time.monotonic() + 20
    while not runner.finished and time.monotonic() < deadline:
        snap = runner.snapshot()
        if snap["phase"] == "countdown":
            phases.add(snap["countdown"])
        time.sleep(0.05)
    snap = _wait(runner)
    assert snap["phase"] == "finished" and runner.verdict.winners == ["b"]
    assert phases == {1, 2}
    assert snap["go_at"] is not None
    # The fake's game clock was frozen during the 2 s countdown, so the score landed well after GO
    assert snap["elapsed"] >= 1.0, snap["elapsed"]
    cmds = [line for line in (tmp_path / "fake.log").read_text().splitlines()
            if line.startswith(("PAUSE_TOGGLE", "SHOW_MSG", "FRAMEADVANCE"))]
    assert cmds[:7] == ["PAUSE_TOGGLE", "SHOW_MSG 2", "FRAMEADVANCE", "SHOW_MSG 1", "FRAMEADVANCE",
                        "PAUSE_TOGGLE", "SHOW_MSG GO!"], cmds


def test_cancel_during_countdown(tmp_path, monkeypatch):
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, {"ram_size": 0x1000, "boot_delay": 0.1})
    st.start_countdown = 10
    ch = {"id": "c", "name": "C", "mode": "versus", "min_time": 0, "on_timeout": "compare",
          "metric": {"address": {"1": "0x10", "2": "0x11"}}, "win": {"type": "reach", "value": 3}}
    runner = MatchRunner(launcher, game, ch, [Participant("a", "Ann", 1), Participant("b", "Bob", 2)], [], st)
    runner.start()
    deadline = time.monotonic() + 15
    while runner.snapshot()["phase"] != "countdown" and time.monotonic() < deadline:
        time.sleep(0.05)
    t0 = time.monotonic()
    runner.cancel()
    snap = _wait(runner)
    assert time.monotonic() - t0 < 5
    assert snap["phase"] == "cancelled" and runner.verdict is None
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


def test_mk2_preset_versus_on_core_ram(tmp_path, monkeypatch):
    """The live-verified MK2 preset, against a fake core without a memory map (like snes9x)."""
    from gauntlet.presets import game_from_preset, load_presets
    script = {"ram_size": 0x4000, "boot_delay": 0.1, "memory_map": False,
              "events": [{"at": 0.4, "address": 0x2EFC, "bytes": [0xA1]},
                         {"at": 0.4, "address": 0x30AA, "bytes": [0xA1]},
                         {"at": 6.0, "address": 0x2EFC, "bytes": [0]}]}
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, script)
    preset = next(p for p in load_presets() if p["id"] == "mk2_snes_usa")
    game = normalize_game(game_from_preset(preset, core="fake", rom=game["meta"]["rom"]))
    ch = game["challenges"][0]
    jaw = next(i for i in game["shop"] if i["id"] == "glass_jaw")
    runner = MatchRunner(launcher, game, ch, [Participant("a", "Ann", 1), Participant("b", "Bob", 2)],
                         [Purchase(jaw, "a", ["b"])], st)
    runner.start()
    snap = _wait(runner, 30)
    assert snap["phase"] == "finished"
    assert runner.verdict.winners == ["b"] and runner.verdict.reason == "last one standing"
    log = (tmp_path / "fake.log").read_text().upper()
    assert "WRITE_CORE_RAM 30AA 50" in log
    assert "READ_CORE_RAM 2EFC 1" in log


def test_match_runner_loads_start_state_each_turn(tmp_path, monkeypatch):
    """The state is staged as <rom>.state1 and RetroArch gets --entryslot 1, fresh for every turn."""
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, {"ram_size": 0x1000, "boot_delay": 0.1})
    states = tmp_path / "start_states"
    states.mkdir()
    (states / "fake_t.state").write_text(json.dumps([{"address": 0x10, "bytes": [5]}]))
    st.start_states_dir = str(states)
    ch = {"id": "t", "name": "T", "mode": "turns", "min_time": 0, "time_limit": None, "on_timeout": "compare",
          "metric": {"address": "0x10"}, "win": {"type": "reach", "value": 5}, "start_state": "fake_t.state"}
    runner = MatchRunner(launcher, game, ch, [Participant("a", "A"), Participant("b", "B")], [], st)
    runner.start()
    snap = _wait(runner)
    assert snap["phase"] == "finished", snap
    assert len(runner.turn_results) == 2       # both turns reached 5 straight from the state
    log = (tmp_path / "fake.log").read_text()
    assert log.count("ENTRY_STATE game.state1 ok") == 2
    assert os.path.isfile(os.path.join(st.sub_state("states"), "game.state1"))


def test_match_runner_missing_start_state_warns(tmp_path, monkeypatch):
    st, launcher, game = _e2e_setup(tmp_path, monkeypatch, {"boot_delay": 0.1, "exit_at": 1.0})
    st.start_states_dir = str(tmp_path / "none")
    runner = MatchRunner(launcher, game, {"id": "m", "name": "M", "mode": "manual", "start_state": "gone.state"},
                         [Participant("a", "A", 1)], [], st)
    runner.start()
    snap = _wait(runner)
    assert any("gone.state" in w and "not found" in w for w in snap["warnings"])
    assert "ENTRY_STATE" not in (tmp_path / "fake.log").read_text()
