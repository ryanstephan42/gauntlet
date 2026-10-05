import json
import os
import socket
import sys
import threading

from gauntlet.economy import Shop
from gauntlet.games import load_games
from gauntlet.retroarch import RetroArchClient
from gauntlet.schema import validate_game
from gauntlet.settings import Settings, load_settings

GOOD = {
    "meta": {"name": "G", "core": "c.so", "rom": "r.sfc"},
    "referee": {"address": "0x00FF30", "bytes": 1, "win_value": 2},
    "shop": [{"id": "a", "name": "A", "cost": 3, "action_type": "memory_write",
              "address": "0x10", "value": 5}],
}


def test_valid_game():
    assert validate_game(GOOD) == []


def test_invalid_game():
    bad = json.loads(json.dumps(GOOD))
    bad["shop"][0]["address"] = "zz"
    bad["shop"].append({"id": "a", "name": "B", "cost": -1, "action_type": "nope"})
    del bad["meta"]["rom"]
    errs = validate_game(bad)
    assert len(errs) >= 4


def test_unhashable_action_types_are_skipped(tmp_path):
    for index, action in enumerate(([], {})):
        bad = json.loads(json.dumps(GOOD))
        bad["shop"][0]["action_type"] = action
        assert any("unknown action_type" in error for error in validate_game(bad))
        (tmp_path / f"bad{index}.json").write_text(json.dumps(bad))
    games, problems = load_games(str(tmp_path))
    assert games == []
    assert set(problems) == {"bad0.json", "bad1.json"}


def test_shop():
    s = Shop([{"cost": 3}, {"cost": 9}], 10)
    assert s.buy(0) and s.points == 7
    assert not s.buy(0)
    assert not s.buy(1)
    assert not s.buy(5)
    assert s.refund(0) and s.points == 10


def test_load_games_skips_bad(tmp_path):
    (tmp_path / "ok.json").write_text(json.dumps(GOOD))
    (tmp_path / "bad.json").write_text("{not json")
    (tmp_path / "inv.json").write_text("{}")
    games, problems = load_games(str(tmp_path))
    assert len(games) == 1
    assert set(problems) == {"bad.json", "inv.json"}


def test_repo_games_valid():
    games, problems = load_games("gauntlet_data")
    assert problems == {}
    assert len(games) == 21


def test_presets_valid():
    from gauntlet.presets import load_presets
    from gauntlet.schema import validate_game
    presets = load_presets()
    assert len(presets) >= 21
    for p in presets:
        game = json.loads(json.dumps(p["game"]))
        game["meta"]["rom"] = "game.rom"  # the add-game wizard fills this in
        assert validate_game(game) == [], p["id"]


def test_settings_defaults_and_bad_types(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"player_count": "x", "starting_points": 5, "bogus": 1}))
    s = load_settings(str(p))
    assert s.player_count == 2 and s.starting_points == 5


def test_settings_invalid_ranges_fall_back_individually(tmp_path):
    p = tmp_path / "ranges.json"
    p.write_text(json.dumps({
        "retroarch_host": "localhost",
        "retroarch_port": 70000,
        "player_count": 5,
        "starting_points": -1,
        "width": 100,
        "height": 600,
        "boot_timeout": float("inf"),
    }))
    s = load_settings(str(p))
    assert s.retroarch_host == "localhost"
    assert s.retroarch_port == 55355
    assert s.player_count == 2
    assert s.starting_points == 10
    assert s.width == 1024
    assert s.height == 600
    assert s.boot_timeout == 30.0


def test_boot_timeout_must_be_positive_and_finite(tmp_path):
    for index, timeout in enumerate((0, -1, float("nan"), float("inf"))):
        p = tmp_path / f"timeout{index}.json"
        p.write_text(json.dumps({"boot_timeout": timeout}))
        assert load_settings(str(p)).boot_timeout == 30.0


def test_udp_client():
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]

    def serve():
        for _ in range(2):
            data, addr = srv.recvfrom(1024)
            if data.startswith(b"READ_CORE_MEMORY"):
                srv.sendto(b"READ_CORE_MEMORY ff30 02", addr)
            else:
                srv.sendto(b"GET_STATUS PLAYING", addr)

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    c = RetroArchClient("127.0.0.1", port, timeout=2)
    assert c.read_memory("0xFF30") == [2]
    assert c.is_ready()
    t.join(3)
    srv.close()


def test_is_ready_requires_loaded_content():
    client = RetroArchClient()
    client.send = lambda command: "GET_STATUS MENU"
    assert not client.is_ready()
    client.send = lambda command: "GET_STATUS PLAYING"
    assert client.is_ready()
    client.send = lambda command: "GET_STATUS PAUSED"
    assert client.is_ready()


def test_udp_timeout_returns_none():
    c = RetroArchClient("127.0.0.1", 9, timeout=0.1)
    assert c.read_memory("0x10") is None


def test_frozen_build_uses_writable_data_root_and_seeds_games(tmp_path, monkeypatch):
    from gauntlet import paths
    bundle = tmp_path / "bundle"
    (bundle / "gauntlet_data").mkdir(parents=True)
    (bundle / "gauntlet_data" / "a.json").write_text("{}")
    (bundle / "gauntlet_data" / "notes.txt").write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.data_path == str(tmp_path / "xdg" / "gauntlet" / "gauntlet_data")
    assert paths.seed_data_dir(s.data_path) == ["a.json"]
    os.remove(os.path.join(s.data_path, "a.json"))
    assert paths.seed_data_dir(s.data_path) == []  # only on first run
