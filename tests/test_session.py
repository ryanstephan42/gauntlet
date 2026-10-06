import pytest

from gauntlet.economy import PlayerCart, catchup_bonus, compute_payouts, needs_target_pick, resolve_targets
from gauntlet.playlist import Playlist
from gauntlet.referee import Verdict
from gauntlet.session import Player, Session
from gauntlet.settings import Settings

ITEM = {"id": "boost", "name": "Boost", "cost": 3, "limit": 2, "target": "self"}
HEX = {"id": "hex", "name": "Hex", "cost": 2, "limit": 1, "target": "opponent"}


def players(n):
    return [Player(i, f"P{i + 1}", i) for i in range(n)]


def test_targets():
    assert resolve_targets(ITEM, 0, [0, 1, 2]) == [0]
    assert resolve_targets(HEX, 0, [0, 1, 2], 2) == [2]
    assert resolve_targets(HEX, 0, [0, 1]) == [1]
    assert resolve_targets(dict(HEX, target="others"), 0, [0, 1, 2]) == [1, 2]
    assert resolve_targets(dict(HEX, target="all"), 0, [0, 1]) == [0, 1]
    assert needs_target_pick(HEX, 3) and not needs_target_pick(HEX, 2)


def test_cart_limits_cap_and_wager():
    c = PlayerCart(0, budget=10, max_items=2)
    assert c.buy(ITEM, [0]) and c.buy(ITEM, [0])
    assert c.why_not(ITEM) == "max 2 items"
    c.max_items = 5
    assert c.why_not(ITEM) == "limit reached"
    assert c.remaining == 4
    assert not c.set_wager(5) and c.set_wager(4)
    assert c.why_not(HEX) == "not enough points"
    assert c.refund() and c.remaining == 3
    c.ready = True
    assert not c.refund()


def test_payouts_win_streak_catchup_wager():
    st = Settings(win_points=5, loss_points=1, draw_points=2, catchup_step=5, catchup_max=3,
                  streak_bonus=1, streak_max=3)
    v = Verdict([0], [1])
    out = compute_payouts(st, v, {0: {"points": 20, "streak": 2}, 1: {"points": 8, "streak": 0}},
                          {0: 2, 1: 3})
    assert out[0]["base"] == 5 and out[0]["streak"] == 2 and out[0]["wager"] == 5
    assert out[1]["base"] == 1 and out[1]["catchup"] == 2 and out[1]["wager"] == 0
    draw = compute_payouts(st, Verdict([0, 1], [], draw=True), {0: {"points": 1}, 1: {"points": 1}}, {0: 2})
    assert draw[0]["total"] == 4 and draw[1]["total"] == 2
    assert catchup_bonus(0, 100, 5, 3) == 3


def test_session_single_flow_and_refund():
    st = Settings()
    s = Session(players(2), Playlist("single", [{"game": "g.json", "challenge": "c"}]), 10, seed=1)
    rnd = s.next_round()
    assert rnd.players == [0, 1] and rnd.label == "Match"
    cart = PlayerCart(0, 10)
    cart.buy(ITEM, [0])
    s.begin_match({0: cart, 1: PlayerCart(1, 10)})
    assert s.player(0).points == 7
    s.abort_match()
    assert s.player(0).points == 10 and s.player(0).items_bought == 0
    s.begin_match({0: cart, 1: PlayerCart(1, 10)})
    s.record_match(Verdict([1], [0]), st)
    assert s.player(1).points == 15 and s.player(1).wins == 1
    assert s.player(0).points == 8
    assert s.next_round() is None and s.finished
    assert s.champion().id == 1


def test_best_of_three_series():
    st = Settings()
    s = Session(players(2), Playlist("single", [{"game": "g", "challenge": "c", "best_of": 3}]), 0, seed=1)
    rnd = s.next_round()
    s.record_match(Verdict([0], [1]), st)
    assert not rnd.decided
    s.record_match(Verdict([0, 1], [], draw=True), st)
    assert not rnd.decided
    s.record_match(Verdict([0], [1]), st)
    assert rnd.decided and rnd.winners() == [0]


def test_gauntlet_rounds_fixed_and_shuffle():
    entries = [{"game": "a"}, {"game": "b"}]
    s = Session(players(3), Playlist("gauntlet", entries, rounds=3), 0, seed=4)
    games = []
    while (r := s.next_round()):
        games.append(r.game)
        s.record_match(Verdict([0], [1, 2]), Settings())
    assert games == ["a", "b", "a"]
    s2 = Session(players(2), Playlist("gauntlet", entries, rounds=5, shuffle=True), 0, seed=4)
    s3 = Session(players(2), Playlist("gauntlet", entries, rounds=5, shuffle=True), 0, seed=4)
    g2, g3 = [], []
    for sess, out in ((s2, g2), (s3, g3)):
        while (r := sess.next_round()):
            out.append(r.game)
            sess.record_match(Verdict([0], [1]), Settings())
    assert g2 == g3


@pytest.mark.parametrize("seed", range(20))
def test_shuffle_plays_every_game_before_repeating(seed):
    entries = [{"game": g} for g in "abcde"]
    s = Session(players(2), Playlist("gauntlet", entries, rounds=12, shuffle=True), 0, seed=seed)
    games = []
    while (r := s.next_round()):
        games.append(r.game)
        s.record_match(Verdict([0], [1]), Settings())
    assert sorted(games[:5]) == list("abcde")
    assert sorted(games[5:10]) == list("abcde")
    assert len(set(games[10:])) == 2
    assert all(a != b for a, b in zip(games, games[1:]))


@pytest.mark.parametrize("n,expected_rounds", [(2, 1), (3, 2), (4, 3)])
def test_bracket(n, expected_rounds):
    s = Session(players(n), Playlist("bracket", [{"game": "a"}]), 0, seed=7)
    played = []
    while (r := s.next_round()):
        assert len(r.players) == 2
        played.append(r.label)
        s.record_match(Verdict([r.players[1]], [r.players[0]]), Settings())  # lower seed wins
    assert len(played) == expected_rounds
    assert played[-1] == "Final"
    standings = s.standings()
    final = s.rounds[-1]
    assert standings[0].id == final.players[1]
    assert standings[1].id == final.players[0]


def test_bracket_pairings():
    byes, pairs = Playlist.pairings([1, 2, 3])
    assert byes == [1] and pairs == [(2, 3)]
    byes, pairs = Playlist.pairings([1, 2, 3, 4])
    assert byes == [] and pairs == [(1, 4), (2, 3)]


def test_session_save_resume(tmp_path):
    st = Settings()
    s = Session(players(4), Playlist("bracket", [{"game": "a"}, {"game": "b"}]), 10, seed=3)
    r = s.next_round()
    c = PlayerCart(r.players[0], 10)
    c.set_wager(2)
    s.begin_match({r.players[0]: c})
    s.record_match(Verdict([r.players[0]], [r.players[1]]), st)
    s.next_round()
    s.begin_match({})
    path = tmp_path / "s.json"
    s.save(str(path))
    t = Session.load(str(path))
    assert [p.points for p in t.players] == [p.points for p in s.players]
    assert t.rounds[0].matches[0]["payouts"][r.players[0]]["result"] == "win"
    assert t.pending is not None
    assert t.current_round.players == s.current_round.players
    t.abort_match()
    t.record_match(Verdict([t.current_round.players[0]], [t.current_round.players[1]]), st)
    assert t.next_round().label == "Final"
