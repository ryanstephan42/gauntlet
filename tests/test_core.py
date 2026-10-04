import json
import socket
import threading

from gauntlet.economy import Shop
from gauntlet.games import load_games
from gauntlet.retroarch import RetroArchClient
from gauntlet.schema import validate_game
from gauntlet.settings import load_settings

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
    assert len(games) == 2


def test_settings_defaults_and_bad_types(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"player_count": "x", "starting_points": 5, "bogus": 1}))
    s = load_settings(str(p))
    assert s.player_count == 2 and s.starting_points == 5


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


def test_udp_timeout_returns_none():
    c = RetroArchClient("127.0.0.1", 9, timeout=0.1)
    assert c.read_memory("0x10") is None
