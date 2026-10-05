import json
import os
import zipfile

import pytest

from gauntlet.economy import PlayerCart
from gauntlet.fakera import FakeRetroArch
from gauntlet.memlab import RamSearch, Watch, decode_all, logical_bytes
from gauntlet.packs import export_pack, import_pack
from gauntlet.playlist import Playlist
from gauntlet.presets import (TEMPLATES, game_from_preset, generic_items, load_presets, match_presets,
                              normalize_title, template)
from gauntlet.referee import Verdict
from gauntlet.retroarch import RetroArchClient
from gauntlet.schema import normalize_game, validate_game
from gauntlet.session import Player, Session
from gauntlet.settings import Settings
from gauntlet.stats import Stats


@pytest.fixture
def fake():
    ra = FakeRetroArch(port=0, ram_size=0x1000)
    ra.start_thread()
    yield ra
    ra.running = False


@pytest.fixture
def client(fake):
    c = RetroArchClient("127.0.0.1", fake.port, timeout=0.3)
    yield c
    c.close()


# --------------------------------------------------------------------------- memlab
def test_logical_bytes_swap32():
    raw = bytes([3, 2, 1, 0, 7, 6, 5, 4])
    assert logical_bytes(raw, 0, "swap32") == bytes(range(8))
    assert logical_bytes(raw, 0, "linear") == raw
    assert decode_all(bytes([1, 0, 2, 0]), 2, "little", False) == [1, 2]


def test_ram_search_filters(client, fake):
    fake.ram[0x10] = 5
    fake.ram[0x20] = 5
    s = RamSearch(client, start=0, length=0x100)
    assert s.reset()
    assert s.filter("eq", 5) == 2
    fake.ram[0x10] = 6
    assert s.filter("increased") == 1
    assert s.results() == [(0x10, 6)]
    assert s.filter("unchanged") == 1
    assert s.history == [0x100, 2, 1, 1]
    with pytest.raises(ValueError):
        s.filter("bogus")


def test_ram_search_swap32_16bit(client, fake):
    # logical big-endian 0x0102 at logical address 0x40 -> stored byte-swapped per word
    fake.ram[0x40 ^ 3] = 0x01
    fake.ram[0x41 ^ 3] = 0x02
    s = RamSearch(client, layout="swap32", start=0, length=0x80, size=2, endian="big")
    s.reset()
    assert s.filter("eq", 0x0102) == 1
    assert s.results()[0][0] == 0x40


def test_ram_search_unreachable():
    c = RetroArchClient("127.0.0.1", 1, timeout=0.05)
    assert RamSearch(c, length=16).reset() is False


def test_watch_spec():
    w = Watch(0x7E0010, size=2, signed=True)
    assert w.to_spec() == {"address": "0x7E0010", "size": 2, "signed": True}
    assert w.label == "0x7E0010"


# --------------------------------------------------------------------------- presets
def test_presets_match_and_validate():
    assert normalize_title("Super Mario 64 (USA).z64") == "super mario 64"
    hits = match_presets("n64", "Super Mario 64 (USA).z64")
    assert hits and hits[0]["id"] == "sm64_usa"
    assert match_presets("snes", "Super Mario 64 (USA).z64") == []
    for p in load_presets():
        g = game_from_preset(p, core="core", rom="rom.bin", name="X")
        assert validate_game(g) == [], p["id"]
        assert g["meta"]["name"] == "X"


def test_generic_items_and_templates_validate():
    items = generic_items()
    assert {"turbo", "slowmo"} <= {i["id"] for i in items}
    for tid, _label, _data in TEMPLATES:
        ch = dict(template(tid), id=tid, name=tid)
        if ch["mode"] != "manual":
            ch["metric"] = {"address": "0x10"}
        game = {"schema_version": 2, "meta": {"name": "T", "core": "c", "rom": "r", "players": 2},
                "challenges": [ch], "shop": items}
        assert validate_game(game) == [], tid
    with pytest.raises(KeyError):
        template("nope")


# --------------------------------------------------------------------------- packs
def _game(name):
    return normalize_game({"schema_version": 2, "meta": {"name": name, "core": "c", "rom": "r.bin",
                                                           "image": "cover.png"},
                           "challenges": [{"id": "m", "name": "M", "mode": "manual"}],
                           "shop": [{"id": "ff", "name": "FF", "cost": 1, "actions": [
                               {"type": "retroarch_config", "config_file": "ff.cfg"}]}]})


def test_pack_roundtrip(tmp_path):
    src_assets, src_cfg = tmp_path / "a", tmp_path / "c"
    src_assets.mkdir()
    src_cfg.mkdir()
    (src_assets / "cover.png").write_bytes(b"png")
    (src_cfg / "ff.cfg").write_text('fastforward_ratio = "4"\n')
    g = _game("Pack Game")
    g["_file"] = "pack_game.json"
    zp = export_pack([g], str(tmp_path / "p.zip"), str(src_assets), str(src_cfg))
    names = zipfile.ZipFile(zp).namelist()
    assert set(names) == {"games/pack_game.json", "assets/cover.png", "config/ff.cfg"}

    data, assets, cfg = tmp_path / "d2", tmp_path / "a2", tmp_path / "c2"
    imported, errors = import_pack(zp, str(data), str(assets), str(cfg))
    assert imported == ["Pack Game"] and errors == []
    assert (assets / "cover.png").read_bytes() == b"png"
    assert (cfg / "ff.cfg").exists()
    # second import never overwrites: game gets a new filename
    imported, _ = import_pack(zp, str(data), str(assets), str(cfg))
    assert sorted(os.listdir(data)) == ["pack_game.json", "pack_game_2.json"]


def test_pack_carries_start_states(tmp_path):
    states = tmp_path / "s"
    states.mkdir()
    (states / "pg_m.state").write_bytes(b"STATE")
    g = _game("Pack Game")
    g["challenges"][0]["start_state"] = "pg_m.state"
    zp = export_pack([g], str(tmp_path / "p.zip"), str(tmp_path / "a"), str(tmp_path / "c"),
                     [str(tmp_path / "missing"), str(states)])
    assert "start_states/pg_m.state" in zipfile.ZipFile(zp).namelist()
    out = tmp_path / "s2"
    imported, errors = import_pack(zp, str(tmp_path / "d2"), str(tmp_path / "a2"), str(tmp_path / "c2"), str(out))
    assert imported == ["Pack Game"] and errors == []
    assert (out / "pg_m.state").read_bytes() == b"STATE"
    # without a destination folder the states are skipped (reported), games still import
    imported, errors = import_pack(zp, str(tmp_path / "d3"), str(tmp_path / "a3"), str(tmp_path / "c3"))
    assert imported == ["Pack Game"] and errors == ["skipped start_states/pg_m.state"]


def test_pack_rejects_traversal_and_invalid(tmp_path):
    zp = tmp_path / "evil.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("../evil.json", "{}")
        z.writestr("games/../../evil.json", "{}")
        z.writestr("assets/sub/x.png", "x")
        z.writestr("games/bad.json", json.dumps({"meta": {}}))
        z.writestr("games/broken.json", "{not json")
    imported, errors = import_pack(str(zp), str(tmp_path / "d"), str(tmp_path / "a"), str(tmp_path / "c"))
    assert imported == []
    assert len(errors) == 5
    assert not (tmp_path / "evil.json").exists()
    assert not (tmp_path / "a").exists()


# --------------------------------------------------------------------------- stats
def _session():
    players = [Player(0, "Ann"), Player(1, "Bob")]
    pl = Playlist("gauntlet", [{"game": "g.json", "challenge": "m"}], rounds=3)
    return Session(players, pl, starting_points=10, seed=1)


def _play(session, settings, winner, carts=None):
    rnd = session.next_round()
    session.begin_match(carts or {})
    loser = 1 - winner
    session.record_match(Verdict([winner], [loser], reason="test"), settings)
    return rnd, rnd.matches[-1]


def test_stats_achievements_and_leaderboard(tmp_path):
    settings = Settings()
    session = _session()
    stats = Stats(str(tmp_path / "stats.json"))
    debuff = {"id": "d", "name": "Debuff", "cost": 1, "category": "debuff", "target": "opponent"}
    cart = PlayerCart(session.player(0), 10, 3)
    cart.buy(debuff, [1])
    rnd, m = _play(session, settings, 0, {0: cart, 1: PlayerCart(session.player(1), 10, 3)})
    new = stats.record_match(session, rnd, m, "Game", {"d": debuff})
    assert ("Ann", "first_win") in new and ("Ann", "saboteur") in new
    for _ in range(2):
        rnd, m = _play(session, settings, 0)
        new = stats.record_match(session, rnd, m, "Game")
    assert ("Ann", "on_fire") in new
    assert session.next_round() is None and session.finished
    new = stats.record_session(session)
    assert ("Ann", "champion") in new and ("Ann", "flawless") in new
    stats.save()

    again = Stats(str(tmp_path / "stats.json"))
    board = again.leaderboard()
    assert [r["name"] for r in board] == ["Ann", "Bob"]
    assert board[0]["wins"] == 3 and board[1]["losses"] == 3
    assert again.data["games"]["Game"]["plays"] == 3
    assert "champion" in again.unlocked("Ann")


def test_stats_underdog(tmp_path):
    settings = Settings()
    session = _session()
    session.player(1).points = 2
    stats = Stats(str(tmp_path / "s.json"))
    rnd, m = _play(session, settings, 1)
    assert ("Bob", "underdog") in stats.record_match(session, rnd, m, "G")


def test_stats_tolerates_corrupt_file(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("[not valid")
    assert Stats(str(p)).leaderboard() == []
