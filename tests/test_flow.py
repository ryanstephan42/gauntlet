"""Headless end-to-end tests of the pygame UI: drive screens with injected input, FakeRetroArch as emulator."""
import json
import os
import random
import socket
import sys
import time

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from gauntlet.inputmap import KEYBOARD, KEYBOARD2, Action, InputEvent  # noqa: E402
from gauntlet.detect import Install  # noqa: E402
from gauntlet.retroarch import Launcher  # noqa: E402
from gauntlet.session import Player, Session  # noqa: E402
from gauntlet.settings import Settings, load_settings  # noqa: E402
from gauntlet.ui import flow, tools  # noqa: E402
from gauntlet.ui.app import App  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GAME = {
    "schema_version": 2,
    "meta": {"name": "Fake Fighter", "system": "snes", "core": "fake", "rom": "", "players": 2},
    "memory": {"layout": "linear", "endian": "little"},
    "challenges": [
        {"id": "ko", "name": "First to 3", "mode": "versus", "min_time": 0, "on_timeout": "compare",
         "metric": {"address": {"1": "0x10", "2": "0x11"}}, "win": {"type": "reach", "value": 3}},
        {"id": "manual", "name": "Honour system", "mode": "manual"},
        {"id": "coins", "name": "Coin race", "mode": "turns", "min_time": 0, "time_limit": 30,
         "metric": {"address": "0x12"}, "win": {"type": "reach", "value": 5}},
    ],
    "shop": [
        {"id": "boost", "name": "Boost", "cost": 2, "category": "buff", "target": "self", "limit": 1,
         "actions": [{"type": "memory_write", "address": {"1": "0x20", "2": "0x21"}, "value": 42}]},
        {"id": "jinx", "name": "Jinx", "cost": 3, "category": "debuff", "target": "opponent", "limit": 1,
         "actions": [{"type": "memory_write", "address": {"1": "0x30", "2": "0x31"}, "value": 7}]},
    ],
}


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Driver:
    """Small helper around App: inject input, advance time, inspect the current screen."""

    def __init__(self, app, tmp_path):
        self.app = app
        self.tmp = tmp_path

    @property
    def screen(self):
        return self.app.manager.current

    @property
    def overlay(self):
        return self.app.overlays[-1] if self.app.overlays else None

    def settle(self, steps=6, dt=0.05):
        for _ in range(steps):
            self.app.step(dt)

    def press(self, action, device=KEYBOARD, key=None, times=1):
        for _ in range(times):
            self.app.inject(InputEvent(device, action, key))
            self.settle()

    def choose(self, option):
        ov = self.overlay
        assert ov is not None and hasattr(ov, "options"), f"no choice overlay (screen {self.screen})"
        assert option in ov.options, (option, ov.options)
        ov.index = ov.options.index(option)
        self.press(Action.CONFIRM)

    def type_text(self, text):
        ov = self.overlay
        assert ov is not None and ov.wants_text
        ov.osk.text = ""
        ov.type_text(text)
        self.press(Action.START)

    def menu(self, label):
        """Activate a MenuScreen row by label."""
        scr = self.screen
        labels = [r[0] for r in scr.list.items]
        assert label in labels, (label, labels)
        scr.list.index = labels.index(label)
        self.press(Action.CONFIRM)

    def field(self, key):
        scr = self.screen
        keys = [f.key for f in scr.fields]
        assert key in keys, (key, keys)
        scr.index = keys.index(key)
        return scr.fields[scr.index]

    def wait_for(self, predicate, timeout=25, what=""):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.step(0.05)
            if predicate():
                return
            time.sleep(0.02)
        raise AssertionError(f"timed out waiting for {what or predicate}; screen={self.screen}")

    def fake_log(self):
        path = self.tmp / "fake.log"
        return path.read_text() if path.exists() else ""


def make_app(tmp_path, monkeypatch, script=None, game=GAME, write_game=True):
    cores = tmp_path / "cores"
    cores.mkdir(exist_ok=True)
    (cores / "fake_libretro.so").write_text("")
    monkeypatch.setattr("gauntlet.detect.ROM_DIR_CANDIDATES", ())
    (tmp_path / "snes").mkdir()
    rom = tmp_path / "snes" / "fake.sfc"
    rom.write_text("")
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    if write_game:
        g = json.loads(json.dumps(game))
        g["meta"]["rom"] = str(rom)
        (data / "fake.json").write_text(json.dumps(g))
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(script or {"ram_size": 0x1000, "boot_delay": 0.2}))
    monkeypatch.setenv("GAUNTLET_FAKE_SCRIPT", str(script_path))
    monkeypatch.setenv("GAUNTLET_FAKE_LOG", str(tmp_path / "fake.log"))
    monkeypatch.setenv("PYTHONPATH", REPO)
    monkeypatch.setattr("gauntlet.match.udev_keyboard_available", lambda: False)
    st = Settings(data_dir=str(data), state_dir=str(tmp_path / "state"), start_states_dir=str(tmp_path / "ss"), core_dir=str(cores),
                  rom_dir=str(tmp_path), retroarch_port=free_port(), poll_interval=0.05, close_delay=0.1,
                  boot_timeout=15, sound=False, split_keyboard=True, starting_points=10)
    launcher = Launcher(st, installs=[Install("Fake", [sys.executable, "-m", "gauntlet.fakera"])])
    app = App(st, launcher=launcher, size=(1280, 720), audio=False, settings_path=str(tmp_path / "settings.json"))
    app.manager.push(flow.MainMenu(app))
    d = Driver(app, tmp_path)
    d.settle()
    return d


@pytest.fixture
def driver(tmp_path, monkeypatch):
    d = make_app(tmp_path, monkeypatch, {"ram_size": 0x1000, "boot_delay": 0.2,
                                          "events": [{"at": 1.2, "address": 0x11, "bytes": [3]}]})
    yield d
    d.app.shutdown()


def start_session(d, challenge_next=0, best_of=None):
    """Main menu -> two keyboard players -> select the fake game -> start a single-game session."""
    d.menu("New Session")
    assert isinstance(d.screen, flow.PlayerSetup)
    d.press(Action.CONFIRM, KEYBOARD)
    d.press(Action.CONFIRM, KEYBOARD2)
    assert [p.name for p in d.screen.players] == ["Player 1", "Player 2"]
    d.press(Action.START)
    assert isinstance(d.screen, flow.GameSelect)
    for _ in range(challenge_next):
        d.press(Action.NEXT)
    d.press(Action.CONFIRM)
    assert len(d.screen.selected) == 1
    d.press(Action.START)
    assert isinstance(d.screen, flow.PlaylistOptions)
    assert d.screen.field("kind").value == "single"
    if best_of:
        d.screen.field("best_of").value = best_of
    d.press(Action.START)
    assert isinstance(d.screen, flow.RoundIntro)
    assert os.path.exists(d.app.session_path)
    return d.screen.session


def shop_and_launch(d, buy_p1=True):
    d.press(Action.CONFIRM)                      # round intro -> shop
    assert isinstance(d.screen, flow.ShopScreen)
    shop = d.screen
    if buy_p1:
        d.press(Action.CONFIRM, KEYBOARD)        # P1 buys "Boost" (first row)
        assert shop.carts[0].spent == 2
    d.press(Action.START, KEYBOARD)
    d.press(Action.START, KEYBOARD2)
    d.settle(20)                                 # all ready for 0.6 s -> pre-match
    assert isinstance(d.screen, flow.PreMatch), d.screen
    assert not d.screen.errors, d.screen.errors
    d.press(Action.START)
    assert isinstance(d.screen, flow.MatchScreen)
    return d.screen


# ------------------------------------------------------------------------------------ tests
def test_main_menu_lists_everything(driver):
    labels = [r[0] for r in driver.screen.list.items]
    assert labels[0] == "New Session" and "Settings" in labels and labels[-1] == "Quit"
    resume = next(r for r in driver.screen.list.items if r[0] == "Resume Session")
    assert resume[2] is False
    assert len(driver.app.games) == 1 and not driver.app.problems
    assert driver.app.health(driver.app.games[0]) == []


def test_full_versus_session_with_fake_retroarch(driver):
    d = driver
    session = start_session(d)
    match = shop_and_launch(d)
    d.wait_for(lambda: isinstance(d.screen, flow.ResultsScreen), what="results")
    res = d.screen
    assert res.verdict.winners == [1]               # player 2 reached 3 first
    log = d.fake_log()
    assert "WRITE_CORE_MEMORY 20 2A" in log          # P1's Boost was applied to port 1
    assert match.runner.process.poll() is not None   # RetroArch was closed
    p1, p2 = session.player(0), session.player(1)
    assert p1.points == 10 - 2 + res.payouts[0]["total"]
    assert p2.points == 10 + res.payouts[1]["total"]
    assert p2.wins == 1 and p1.losses == 1
    d.settle(40)                                     # count-up animation
    d.press(Action.CONFIRM)
    assert isinstance(d.screen, flow.StandingsScreen)
    d.press(Action.CONFIRM)
    assert isinstance(d.screen, flow.FinalScreen)
    assert session.finished
    assert not os.path.exists(d.app.session_path)    # finished sessions are cleared
    stats = json.load(open(os.path.join(d.app.settings.state_path, "stats.json")))
    assert stats["players"]["Player 2"]["wins"] == 1
    assert stats["history"] and stats["history"][-1]["game"] == "Fake Fighter"
    d.press(Action.CONFIRM)
    assert isinstance(d.screen, flow.MainMenu)


def test_wide_match_window_draws_the_scoreboard_strip(driver, monkeypatch):
    import pygame
    d = driver
    start_session(d)
    match = shop_and_launch(d)
    d.wait_for(lambda: match.snap.get("values"), what="live values")
    assert match.power_ups(0) == [("Boost", True)] and match.power_ups(1) == []
    assert match.player_status(0)[0] == "bar"
    calls = []
    real = match.draw_strip
    monkeypatch.setattr(match, "draw_strip", lambda p, h: (calls.append(h), real(p, h)))
    painter = d.app.painter
    for size in ((2560, 354), (1280, 720)):
        surf = pygame.Surface(size)
        painter.set_surface(surf)
        try:
            match.draw(surf)
        finally:
            painter.set_surface(d.app.screen)
    assert len(calls) == 1 and abs(calls[0] - 1280 * 354 / 2560) < 1e-6
    d.wait_for(lambda: isinstance(d.screen, flow.ResultsScreen), what="results")


def test_manual_challenge_reports_result(driver):
    d = driver
    session = start_session(d, challenge_next=1)
    assert d.screen.challenge["mode"] == "manual"
    shop_and_launch(d, buy_p1=False)
    # the fake RetroArch keeps running: end the match from the match menu
    d.wait_for(lambda: d.screen.snap.get("phase") == "playing", what="playing")
    d.press(Action.BACK)
    d.choose("End now & report result")
    d.wait_for(lambda: isinstance(d.screen, flow.ManualResult), what="manual result screen")
    d.press(Action.CONFIRM)                          # "Player 1 wins"
    assert isinstance(d.screen, flow.ResultsScreen)
    assert d.screen.verdict.winners == [0] and d.screen.verdict.manual
    assert session.player(0).wins == 1


def test_cancel_match_refunds_points(driver):
    d = driver
    session = start_session(d)
    shop_and_launch(d)
    assert session.player(0).points == 8
    d.press(Action.BACK)
    d.choose("Cancel match (refund)")
    d.wait_for(lambda: isinstance(d.screen, flow.RoundIntro), what="round intro after cancel")
    assert session.player(0).points == 10 and session.pending is None
    assert not session.rounds[-1].matches


def test_forfeit_from_match_menu(driver):
    d = driver
    session = start_session(d, challenge_next=1)
    shop_and_launch(d, buy_p1=False)
    d.wait_for(lambda: d.screen.snap.get("phase") == "playing", what="playing")
    d.press(Action.BACK)
    d.choose("Forfeit...")
    d.choose("Player 2")
    d.wait_for(lambda: isinstance(d.screen, flow.ResultsScreen), what="results")
    assert d.screen.verdict.winners == [0]
    assert session.player(1).losses == 1


def test_save_exit_and_resume(driver):
    d = driver
    session = start_session(d, best_of=3)
    d.press(Action.BACK)                             # round intro -> pause menu
    d.choose("Save & exit to menu")
    assert isinstance(d.screen, flow.MainMenu)
    saved = Session.load(d.app.session_path)
    assert saved.id == session.id and not saved.finished
    d.menu("Resume Session")
    assert isinstance(d.screen, flow.PlayerSetup) and d.screen.session is not None
    d.press(Action.START)                            # nobody claimed yet -> refused
    assert isinstance(d.screen, flow.PlayerSetup)
    d.press(Action.CONFIRM, KEYBOARD)
    d.press(Action.CONFIRM, KEYBOARD2)
    d.press(Action.START)
    assert isinstance(d.screen, flow.RoundIntro)
    assert d.screen.session.id == session.id and d.screen.rnd.best_of == 3


def test_launch_error_offers_manual_result(tmp_path, monkeypatch):
    d = make_app(tmp_path, monkeypatch)
    try:
        start_session(d)
        os.remove(tmp_path / "snes" / "fake.sfc")             # ROM disappears before the match
        d.press(Action.CONFIRM)
        d.press(Action.START, KEYBOARD)
        d.press(Action.START, KEYBOARD2)
        d.settle(20)
        assert isinstance(d.screen, flow.PreMatch) and d.screen.errors
        d.press(Action.START)
        d.choose("Play elsewhere & report result")
        assert isinstance(d.screen, flow.ManualResult)
        d.press(Action.DOWN, times=2)                # draw
        d.press(Action.CONFIRM)
        assert isinstance(d.screen, flow.ResultsScreen) and d.screen.verdict.draw
    finally:
        d.app.shutdown()


def test_player_setup_hotseat_rename_and_colour(driver):
    d = driver
    d.menu("New Session")
    d.press(Action.CONFIRM, KEYBOARD)
    d.press(Action.CONFIRM, KEYBOARD)                # same device again = hotseat player
    scr = d.screen
    assert len(scr.players) == 2 and scr.players[0].device == scr.players[1].device
    colour = scr.players[1].color
    d.press(Action.RIGHT)
    assert scr.players[1].color != colour
    d.press(Action.ALT)
    d.type_text("Zed")
    assert scr.players[1].name == "Zed"
    d.press(Action.START)
    assert isinstance(d.screen, flow.GameSelect) and d.screen.shared
    d.press(Action.CONFIRM)                          # versus needs separate controllers
    assert not d.screen.selected
    assert any("share a controller" in m for m in d.app.toasts.messages)
    d.press(Action.NEXT)                             # manual challenge is fine for hotseat
    d.press(Action.CONFIRM)
    assert d.screen.selected == [("fake.json", "manual")]
    d.press(Action.BACK)
    d.press(Action.BACK)                             # player leaves
    d.press(Action.BACK)
    d.press(Action.BACK)
    assert isinstance(d.screen, flow.MainMenu)


def test_settings_saved_to_disk(driver):
    d = driver
    d.menu("Settings")
    assert isinstance(d.screen, tools.SettingsScreen)
    d.field("starting_points")
    d.press(Action.RIGHT, times=3)
    wagers = d.field("wagers").value
    d.press(Action.CONFIRM)
    d.press(Action.BACK)
    assert isinstance(d.screen, flow.MainMenu)
    st = load_settings(str(d.tmp / "settings.json"))
    assert st.starting_points == 13 and st.wagers is (not wagers)
    assert any("Settings saved" in m for m in d.app.toasts.messages)


def test_input_remap_captures_key(driver):
    import pygame
    d = driver
    d.menu("Settings")
    d.field("remap")
    d.press(Action.CONFIRM)
    assert isinstance(d.screen, tools.InputRemap)
    d.press(Action.CONFIRM)                          # rebind "Up"
    assert d.screen.capture_raw
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t, mod=0, unicode="t", scancode=0))
    d.settle(2)
    assert not d.screen.capture_raw
    assert d.app.settings.key_bindings.get("t") == "up"
    d.screen.reset()
    assert d.app.settings.key_bindings == {}


def test_stats_screen_tabs(driver):
    d = driver
    d.menu("Stats & Achievements")
    assert isinstance(d.screen, tools.StatsScreen)
    for _ in range(3):
        d.press(Action.RIGHT)
    assert d.screen.tab == 0
    d.press(Action.SELECT)
    d.choose("Yes")
    assert d.app.stats.data["history"] == []
    d.press(Action.BACK)
    assert isinstance(d.screen, flow.MainMenu)


def test_games_manager_duplicate_and_delete(driver):
    d = driver
    d.menu("Manage Games")
    assert isinstance(d.screen, tools.GamesManager)
    d.menu("Fake Fighter")
    d.choose("Duplicate")
    assert len(d.app.games) == 2
    copy_row = next(r[0] for r in d.screen.list.items if r[0].startswith("Fake Fighter") and r[0] != "Fake Fighter")
    d.menu(copy_row)
    d.choose("Delete")
    d.choose("Delete")
    assert len(d.app.games) == 1
    d.menu("Fake Fighter")
    d.choose("Export pack")
    assert "Exported" == d.overlay.title
    d.choose("OK")


def test_broken_game_file_is_reported(tmp_path, monkeypatch):
    d = make_app(tmp_path, monkeypatch)
    try:
        (tmp_path / "data" / "broken.json").write_text("{nope")
        d.app.reload_games()
        d.menu("Manage Games")
        row = next(r for r in d.screen.list.items if r[0] == "[broken] broken.json")
        assert "skipped" in row[3]
    finally:
        d.app.shutdown()


def test_wizard_creates_game(tmp_path, monkeypatch):
    d = make_app(tmp_path, monkeypatch, write_game=False)
    (tmp_path / "cores" / "snes9x_libretro.so").write_text("")
    try:
        assert d.app.games == []
        d.menu("Add Game")
        wiz = d.screen
        assert isinstance(wiz, tools.WizardScreen) and wiz.step == 0
        assert wiz.field("system").value == "snes"
        d.press(Action.START)                        # -> core
        assert wiz.step == 1 and wiz.field("core").value == "snes9x"
        d.press(Action.START)                        # -> ROM
        assert wiz.step == 2 and wiz.field("rom").value.endswith("fake.sfc")
        d.press(Action.START)                        # -> details
        assert wiz.step == 3
        assert wiz.meta["rom"] == "fake.sfc"           # portable: bare name found in the ROM folder
        d.field("name")
        d.press(Action.CONFIRM)
        d.type_text("Wizard Game")
        d.press(Action.START)                        # -> challenges
        assert wiz.step == 4
        d.press(Action.START)                        # needs a challenge first
        assert wiz.step == 4
        d.field("add")
        d.press(Action.CONFIRM)
        d.choose("First to N (versus)")
        ed = d.screen
        assert isinstance(ed, tools.ChallengeEditor)
        ed.field("address").value = "0x10-0x11"
        d.press(Action.START)                        # done
        assert d.screen is wiz and len(wiz.game["challenges"]) == 1
        assert wiz.game["challenges"][0]["metric"]["address"] == {"1": "0x10", "2": "0x11"}
        d.press(Action.START)                        # -> shop
        assert wiz.step == 5
        d.field("add_generic")
        d.press(Action.CONFIRM)
        d.choose("All of them")
        assert len(wiz.game["shop"]) >= 3
        d.field("add_custom")
        d.press(Action.CONFIRM)
        ie = d.screen
        assert isinstance(ie, tools.ItemEditor)
        ie.field("name").value = "Extra life"
        ie.field("address").value = "0x40"
        d.press(Action.START)
        assert d.screen is wiz and wiz.game["shop"][-1]["id"] == "extra_life"
        d.press(Action.START)                        # -> review
        assert wiz.step == 6 and wiz.field("save").enabled
        d.press(Action.START)                        # save
        assert isinstance(d.screen, flow.MainMenu)
        assert [g["meta"]["name"] for g in d.app.games] == ["Wizard Game"]
        assert d.app.health(d.app.games[0]) == []
        # edit it again: opens on the review step
        d.menu("Manage Games")
        d.menu("Wizard Game")
        d.choose("Edit")
        assert isinstance(d.screen, tools.WizardScreen) and d.screen.step == 6
        d.press(Action.START)
        assert isinstance(d.screen, tools.GamesManager) and len(d.app.games) == 1
    finally:
        d.app.shutdown()


def test_memory_lab_search_against_fake(tmp_path, monkeypatch):
    d = make_app(tmp_path, monkeypatch, {"ram_size": 0x20000, "boot_delay": 0.2})
    try:
        d.menu("Memory Lab")
        d.menu("Fake Fighter")
        lab = d.screen
        assert isinstance(lab, tools.MemoryLab)
        d.wait_for(lambda: lab.phase == "ready", what="memory lab ready")
        d.field("new")
        d.press(Action.CONFIRM)
        d.wait_for(lambda: lab.search is not None and not lab.busy, what="snapshot")
        assert len(lab.search.candidates) == lab.region_len
        poke = d.app.launcher.client()
        poke.write_bytes(0x1234, bytes([77]))
        poke.close()
        lab.field("value").value = 77
        d.field("apply")
        d.press(Action.CONFIRM)
        d.wait_for(lambda: lab.search.candidates is not None and len(lab.search.candidates) == 1,
                   what="filter")
        d.settle(4)
        row = d.field("r4660")
        d.press(Action.CONFIRM)
        d.choose("Watch")
        assert lab.watches and lab.watches[0].var.address == 0x1234
        d.wait_for(lambda: lab.watches[0].value == 77, what="watch refresh")
        d.press(Action.BACK)
        d.wait_for(lambda: isinstance(d.screen, tools.MemoryLabSetup), what="lab closed")
        assert lab.process.poll() is not None
        assert row.value == 0x1234
    finally:
        d.app.shutdown()


def test_capture_start_state_then_match_loads_it(driver):
    d = driver
    d.menu("Manage Games")
    d.menu("Fake Fighter")
    d.choose("Edit")
    wiz = d.screen
    assert isinstance(wiz, tools.WizardScreen)
    wiz.challenge_menu(0)
    d.choose("Edit")
    ed = d.screen
    assert isinstance(ed, tools.ChallengeEditor)
    assert ed.state_label() == "none - boot normally"
    d.field("start_state")
    d.press(Action.CONFIRM)
    d.choose("Capture from the game...")
    cap = d.screen
    assert isinstance(cap, tools.StateCapture) and cap.name == "fake_fighter_ko.state"
    d.press(Action.START)                          # nothing captured yet: stays
    assert d.screen is cap
    d.wait_for(lambda: cap.phase == "ready", what="capture ready")
    d.press(Action.CONFIRM)                        # Gauntlet sends SAVE_STATE
    d.wait_for(lambda: cap.captured is not None, what="state captured")
    d.press(Action.START)                          # keep
    assert d.screen is ed and ed.ch["start_state"] == "fake_fighter_ko.state"
    assert ed.state_label() == "fake_fighter_ko.state"
    saved = os.path.join(d.app.settings.start_states_path, "fake_fighter_ko.state")
    assert os.path.isfile(saved)
    d.wait_for(lambda: cap.process.poll() is not None, what="RetroArch closed")
    assert "SAVE_STATE" in d.fake_log()
    d.press(Action.START)                          # editor done
    assert d.screen is wiz
    d.press(Action.START)                          # save (review step)
    assert isinstance(d.screen, tools.GamesManager)
    assert d.app.games[0]["challenges"][0]["start_state"] == "fake_fighter_ko.state"
    d.press(Action.BACK)
    assert isinstance(d.screen, flow.MainMenu)
    start_session(d)
    shop_and_launch(d)
    d.wait_for(lambda: isinstance(d.screen, flow.ResultsScreen), what="results")
    assert "ENTRY_STATE fake.state1 ok" in d.fake_log()


def test_osk_typing_with_pad(driver):
    d = driver
    got = []
    d.app.text_input("Name", "", got.append, 8)
    d.press(Action.CONFIRM, "pad:0")                # first key on the on-screen keyboard
    d.press(Action.START, "pad:0")
    assert got and len(got[0]) == 1


def test_single_player_race_session(tmp_path, monkeypatch):
    """Split keyboard + udev: both players race in their own fake RetroArch; first to 5 coins wins."""
    d = make_app(tmp_path, monkeypatch)
    st = d.app.settings
    players = [(0, Player(0, "A", device=KEYBOARD)), (1, Player(1, "B", device=KEYBOARD2))]
    no_udev = flow.race_plan(d.app, players)
    assert not no_udev.race and "input" in no_udev.note   # two keyboards need udev: take turns
    st.race_input_driver = "udev"
    assert flow.race_plan(d.app, players).race
    st.retroarch_port = random.randrange(20000, 32000)    # the race uses port and port+1
    script = {"ram_size": 0x1000, "boot_delay": 0.2,
              "by_port": {str(st.retroarch_port + 1): {"events": [{"at": 1.0, "address": 0x12, "bytes": [5]}]}}}
    (tmp_path / "script.json").write_text(json.dumps(script))
    monkeypatch.setenv("GAUNTLET_FAKE_LOG", str(tmp_path / "fake{port}.log"))
    try:
        start_session(d, challenge_next=2)
        assert d.screen.race.race
        match = shop_and_launch(d)
        assert match.runner.race.race
        d.wait_for(lambda: match.snap.get("phase") == "playing", what="race playing")
        assert d.screen is match
        d.app.draw()
        d.wait_for(lambda: isinstance(d.screen, flow.ResultsScreen), what="results")
        assert d.screen.verdict.winners == [1] and d.screen.verdict.reason == "first to the goal"
        assert len(match.runner.instances) == 2
        assert all(i.process.poll() is not None for i in match.runner.instances)
        p1 = (tmp_path / f"fake{st.retroarch_port}.log").read_text()
        p2 = (tmp_path / f"fake{st.retroarch_port + 1}.log").read_text()
        assert "WRITE_CORE_MEMORY 20 2A" in p1 and "WRITE_CORE_MEMORY 20" not in p2  # Boost: P1's window only
        assert "Player 2 wins!" in p1 and "Player 2 wins!" in p2
        assert d.screen.session.player(1).wins == 1
        cfg = open(os.path.join(st.sub_state("retroarch"), "race_p2.cfg")).read()
        assert 'input_driver = "udev"' in cfg and 'input_player1_up = "i"' in cfg
        for a, b in (("racing", "finished"), ("waiting", "out"), ("done", "done")):  # every status renders
            row = {"time": 1.5, "reason": "goal reached", "value": 5}
            match.snap = dict(match.snap, phase="playing", values={0: 2},
                              players={0: dict(row, status=a), 1: dict(row, status=b, value=None)})
            match.draw_body(d.app.painter)
    finally:
        d.app.shutdown()
