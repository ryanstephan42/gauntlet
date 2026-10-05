"""Gameplay flow screens: menu, player setup, game select, shop, match, results, standings."""
import logging
import os

from ..economy import PlayerCart, needs_target_pick, resolve_targets
from ..games import get_challenge
from ..inputmap import KEYBOARD, KEYBOARD2, Action, is_pad
from ..layout import DESIGN_H, DESIGN_W
from ..match import MatchRunner, Participant, Purchase, RacePlan, race_setup
from ..playlist import Playlist
from ..referee import Verdict
from ..session import PLAYER_COLORS, Player, Session
from ..stats import ACHIEVEMENTS
from .base import BaseScreen, Field, FormScreen, MenuScreen
from .fx import Confetti, CountUp, pulse

log = logging.getLogger("gauntlet.ui.flow")

CATEGORY_COLORS = {"buff": (60, 200, 110), "debuff": (232, 72, 85), "chaos": (200, 120, 255)}
MODE_LABELS = {"versus": "Versus", "turns": "Single-player", "coop": "Co-op", "manual": "Manual"}
FORFEIT_HOLD = 1.5
STRIP_ASPECT = 2.4  # a match window at least this wide (w/h) is drawn as the scoreboard strip


# ------------------------------------------------------------------------------------ helpers
def save_session(app, session):
    try:
        session.save(app.session_path)
    except OSError as e:
        app.toasts.show(f"Could not save session: {e}")


def clear_saved_session(app):
    try:
        os.remove(app.session_path)
    except OSError:
        pass


def saved_session(app):
    try:
        s = Session.load(app.session_path)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None if s.finished else s


def device_label(app, device):
    return app.input.pad_name(device)


def make_participants(app, players):
    """[(pid, Player)] -> [Participant] (port = position, joystick index, keyboard role)."""
    out = []
    for i, (pid, pl) in enumerate(players):
        idx = app.input.device_index(pl.device)
        out.append(Participant(pid, pl.name, i + 1, idx if idx is not None else pl.pad_index,
                               pl.device if pl.device in (KEYBOARD, KEYBOARD2) else None, pl.rgb))
    return out


def race_plan(app, players):
    """How single-player challenges run for these [(pid, Player)]: a race or taking turns."""
    return race_setup(make_participants(app, players), app.settings)


def mode_label(challenge, plan=None):
    if challenge.get("mode") == "turns" and plan is not None:
        return "Race" if plan.race else "Take turns"
    return MODE_LABELS.get(challenge.get("mode"), "?")


def compat(app, game, challenge, n_players, shared_device=False):
    """-> (problem or None, bracket_only)."""
    errors = app.health(game)
    if errors:
        return errors[0], False
    mode = challenge.get("mode", "manual")
    max_p = game["meta"].get("players", 2)
    if mode in ("versus", "coop"):
        if mode == "versus" and n_players < 2:
            return "needs 2+ players", False
        if shared_device:
            return "players share a controller (turns/manual only)", False
        if n_players > max_p:
            return (None, True) if mode == "versus" and max_p >= 2 else (f"max {max_p} players", False)
    return None, False


def finish_match(app, session, rnd, game, challenge, verdict, extra=None):
    """Record a verdict, update stats and show the results screen."""
    data = {"game": game["_file"] if game else rnd.game, "challenge": challenge.get("id") if challenge else ""}
    data.update(extra or {})
    payouts = session.record_match(verdict, app.settings, data)
    match = rnd.matches[-1]
    items = {i.get("id"): i for i in (game or {}).get("shop", [])}
    name = game["meta"]["name"] if game else rnd.game
    new = app.stats.record_match(session, rnd, match, name, items)
    try:
        app.stats.save()
    except OSError:
        pass
    save_session(app, session)
    app.manager.reset(ResultsScreen(app, session, rnd, game, verdict, payouts, new))


def draw_player_chip(p, player, x, y, w, size=24, extra=""):
    p.rect(x, y, 10, size + 12, player.rgb, radius=4)
    p.text(player.name + extra, x + 20, y + 4, size, width=w - 24, bold=True)


# ------------------------------------------------------------------------------------ main menu
class MainMenu(MenuScreen):
    title = "GAUNTLET"

    def on_enter(self):
        super().on_enter()
        if self.app.problems:
            self.toast(f"{len(self.app.problems)} game file(s) have errors: see Manage Games")

    def rows(self):
        from . import tools
        a = self.app
        resume = saved_session(a)
        return [
            ("New Session", lambda: self.push(PlayerSetup(a)), True,
             "Players join with their controllers, pick games, shop for power-ups and compete."),
            ("Resume Session", (lambda: self.resume(resume)) if resume else None, bool(resume),
             "Continue the last unfinished session." if resume else "No unfinished session."),
            ("Add Game", lambda: self.push(tools.WizardScreen(a)), True,
             "Step-by-step wizard: pick a system, core and ROM, choose a challenge template and shop items."),
            ("Manage Games", lambda: self.push(tools.GamesManager(a)), True,
             f"{len(a.games)} game(s). Edit, duplicate, delete, import/export packs, health check."),
            ("Memory Lab", lambda: self.push(tools.MemoryLabSetup(a)), True,
             "Launch a game and search its RAM for scores, lives and health to build challenges."),
            ("Stats & Achievements", lambda: self.push(tools.StatsScreen(a)), True,
             "Leaderboard, achievements and recent match history."),
            ("Settings", lambda: self.push(tools.SettingsScreen(a)), True,
             "Points and payouts, display, audio, input remapping, RetroArch."),
            ("Quit", a.quit, True, "Exit Gauntlet."),
        ]

    def resume(self, session):
        self.push(PlayerSetup(self.app, session=session))

    def on_action(self, event):
        if event.action is Action.BACK:
            self.app.confirm("Quit Gauntlet?", self.app.quit)
            return
        super().on_action(event)

    def draw_body(self, p):
        super().draw_body(p)
        a = self.app
        x = p.margin + 20 + self.width + 40
        y = 430
        inst = a.launcher.install
        p.text("RetroArch: " + (inst.label if inst else "not found"), x, y, 20,
               a.theme.good if inst else a.theme.bad)
        p.text(f"Games: {len(a.games)}" + (f"   ({len(a.problems)} with errors)" if a.problems else ""),
               x, y + 30, 20, a.theme.text_dim)
        pads = len(a.input.pads)
        p.text(f"Controllers: {pads}", x, y + 60, 20, a.theme.text_dim)


# ------------------------------------------------------------------------------------ player setup
class PlayerSetup(BaseScreen):
    """Press A to join. Same device again adds a hotseat player. With `session`: reassign controllers."""
    title = "Players"

    def __init__(self, app, session=None):
        super().__init__(app)
        self.session = session
        if session:
            self.players = session.players
            self.assigned = [False] * len(self.players)
            self.subtitle = "Resume: each player press A in order"
        else:
            self.players = []
            self.subtitle = "Press A / Enter to join"

    def _owned(self, device):
        idx = [i for i, p in enumerate(self.players) if p.device == device and
               (not self.session or self.assigned[i])]
        return idx

    def hints(self):
        if self.session:
            return [(Action.CONFIRM, "Claim next player"), (Action.BACK, "Unassign"), (Action.START, "Continue")]
        return [(Action.CONFIRM, "Join / add hotseat"), (Action.LEFT, "Colour"), (Action.ALT, "Rename"),
                (Action.BACK, "Leave"), (Action.START, "Continue")]

    def _free_color(self, start, step=1):
        used = {p.color for p in self.players}
        for k in range(1, len(PLAYER_COLORS) + 1):
            c = (start + step * k) % len(PLAYER_COLORS)
            if c not in used:
                return c
        return start

    def join(self, device):
        if self.session:
            for i, p in enumerate(self.players):
                if not self.assigned[i]:
                    p.device = device
                    p.pad_index = self.app.input.device_index(device)
                    self.assigned[i] = True
                    self.sound("join")
                    return
            self.sound("error")
            return
        if len(self.players) >= 4:
            self.sound("error")
            self.toast("Maximum 4 players")
            return
        pid = max((p.id for p in self.players), default=-1) + 1
        color = self._free_color(-1)
        taken = {p.name for p in self.players}
        name = f"Player {len(self.players) + 1}"
        while name in taken:
            name += "+"
        self.players.append(Player(pid, name, color, device, self.app.input.device_index(device)))
        self.sound("join")

    def on_disconnect(self, device):
        for i, p in enumerate(self.players):
            if p.device == device:
                if self.session:
                    self.assigned[i] = False
        if not self.session:
            self.players = [p for p in self.players if p.device != device]

    def on_action(self, event):
        a, dev = event.action, event.device
        owned = self._owned(dev)
        if a is Action.CONFIRM:
            self.join(dev)
        elif a is Action.BACK:
            if owned:
                i = owned[-1]
                if self.session:
                    self.assigned[i] = False
                else:
                    self.players.pop(i)
                self.sound("back")
            elif not any(self.assigned if self.session else self.players):
                self.sound("back")
                self.pop()
        elif a in (Action.LEFT, Action.RIGHT) and owned and not self.session:
            pl = self.players[owned[-1]]
            pl.color = self._free_color(pl.color, -1 if a is Action.LEFT else 1)
            self.sound("move")
        elif a is Action.ALT and owned and not self.session:
            pl = self.players[owned[-1]]

            def rename(text, pl=pl):
                if text:
                    pl.name = text[:16]
            self.app.text_input(f"Name for {pl.name}", pl.name, rename, 16)
        elif a is Action.START:
            self.proceed()

    def proceed(self):
        if self.session:
            if not all(self.assigned):
                self.sound("error")
                self.toast("Every player needs a controller")
                return
            self.sound("start")
            save_session(self.app, self.session)
            self.app.manager.reset(RoundIntro(self.app, self.session))
            return
        if not self.players:
            self.sound("error")
            self.toast("At least one player must join")
            return
        self.sound("confirm")
        self.push(GameSelect(self.app, self.players))

    def draw_body(self, p):
        a = self.app
        m = p.margin
        w = (DESIGN_W - 2 * m - 3 * 20) / 4
        slots = self.players if self.session else self.players + [None] * (4 - len(self.players))
        for i, pl in enumerate(slots[:4]):
            x = m + i * (w + 20)
            y = 120
            if pl is None:
                p.panel(x, y, w, 380, color=(38, 38, 50))
                alpha = int(255 * pulse(self.time + i, 2.5, 0.35, 1.0))
                p.text("Press A", x + w / 2, y + 160, 30, a.theme.text_dim, "center", alpha=alpha)
                p.text("to join", x + w / 2, y + 200, 22, a.theme.text_dim, "center")
                p.hit(lambda: self.join(KEYBOARD), x, y, w, 380)
                continue
            ready = self.assigned[i] if self.session else True
            p.panel(x, y, w, 380, border=pl.rgb if ready else None)
            p.rect(x, y, w, 70, pl.rgb, radius=12)
            p.text(pl.name, x + w / 2, y + 18, 30, (20, 20, 20), "center", bold=True, width=w - 20)
            p.text(f"P{i + 1}", x + 16, y + 90, 22, a.theme.text_dim)
            if ready:
                p.text(device_label(a, pl.device), x + 16, y + 130, 20, width=w - 32)
                shared = sum(1 for q in self.players if q.device == pl.device) > 1
                if shared:
                    p.text("(hotseat: shared)", x + 16, y + 160, 18, a.theme.text_dim)
            else:
                p.text("Waiting for controller...", x + 16, y + 130, 20, a.theme.text_dim, width=w - 32)
            if self.session:
                p.text(f"{pl.points} pts", x + 16, y + 200, 26, a.theme.accent)
        p.wrapped("A joins (again on the same controller adds a hotseat player). Left/Right changes colour, "
                  "X renames, B leaves. Start continues." if not self.session else
                  "Controllers may have changed since the session was saved: claim each player in order.",
                  m + 20, 530, DESIGN_W - 2 * m - 40, 20, a.theme.text_dim)


# ------------------------------------------------------------------------------------ game select
class GameSelect(BaseScreen):
    title = "Choose games"
    columns = 4

    def __init__(self, app, players):
        super().__init__(app)
        self.players = players
        self.index = 0
        self.top_row = 0
        self.challenge_idx = {}
        self.selected = []   # [(file, challenge id)]
        devices = [p.device for p in players]
        self.shared = len(set(devices)) < len(devices)
        self.race = race_plan(app, list(enumerate(players)))

    @property
    def subtitle(self):
        return f"{len(self.players)} players • {len(self.selected)} selected"

    def hints(self):
        return [(Action.CONFIRM, "Add/remove"), (Action.PREV, "Challenge"), (Action.START, "Continue"),
                (Action.BACK, "Back")]

    def on_enter(self):
        self.app.clear_health()

    def challenge(self, game):
        chs = game.get("challenges") or [{"id": "main", "name": "Match", "mode": "manual"}]
        return chs[self.challenge_idx.get(game["_file"], 0) % len(chs)]

    def status(self, game):
        return compat(self.app, game, self.challenge(game), len(self.players), self.shared)

    def toggle(self, i):
        games = self.app.games
        if not games:
            return
        self.index = i
        g = games[i]
        key = next((s for s in self.selected if s[0] == g["_file"]), None)
        if key:
            self.selected.remove(key)
            self.sound("refund")
            return
        problem, _bracket = self.status(g)
        if problem:
            self.sound("error")
            self.toast(f"{g['meta']['name']}: {problem}")
            return
        self.selected.append((g["_file"], self.challenge(g).get("id")))
        self.sound("buy")

    def on_action(self, event):
        a = event.action
        games = self.app.games
        n, c = len(games), self.columns
        if a is Action.LEFT and self.index % c:
            self.index -= 1
        elif a is Action.RIGHT and self.index % c < c - 1 and self.index + 1 < n:
            self.index += 1
        elif a is Action.UP and self.index >= c:
            self.index -= c
        elif a is Action.DOWN and self.index + c < n:
            self.index += c
        elif a in (Action.PREV, Action.NEXT) and games:
            g = games[self.index]
            self.challenge_idx[g["_file"]] = self.challenge_idx.get(g["_file"], 0) + (1 if a is Action.NEXT else -1)
            self.selected = [s for s in self.selected if s[0] != g["_file"]]
        elif a is Action.CONFIRM:
            self.toggle(self.index)
        elif a is Action.START:
            self.proceed()
        else:
            return super().on_action(event)
        if a in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN, Action.PREV, Action.NEXT):
            self.sound("move")

    def proceed(self):
        games = self.app.games
        entries = list(self.selected)
        if not entries and games:
            g = games[self.index]
            if self.status(g)[0]:
                self.sound("error")
                self.toast("Select at least one playable game")
                return
            entries = [(g["_file"], self.challenge(g).get("id"))]
        if not entries:
            self.sound("error")
            self.toast("No games: add one from the main menu")
            return
        bracket_only = False
        for f, cid in entries:
            g = self.app.game_by_file(f)
            if compat(self.app, g, get_challenge(g, cid), len(self.players), self.shared)[1]:
                bracket_only = True
        self.sound("confirm")
        self.push(PlaylistOptions(self.app, self.players, entries, bracket_only))

    def draw_body(self, p):
        a = self.app
        games = a.games
        m = p.margin
        if not games:
            p.wrapped("No games yet. Use 'Add Game' in the main menu to set one up.", m + 20, 140,
                      DESIGN_W - 2 * m, 26)
            return
        c = self.columns
        gap = 18
        w = (DESIGN_W - 2 * m - gap * (c - 1)) / c
        h = 250
        row = self.index // c
        if row < self.top_row:
            self.top_row = row
        elif row > self.top_row + 1:
            self.top_row = row - 1
        sel_files = [s[0] for s in self.selected]
        for i, g in enumerate(games):
            r = i // c
            if not self.top_row <= r <= self.top_row + 1:
                continue
            x = m + (i % c) * (w + gap)
            y = 100 + (r - self.top_row) * (h + gap)
            focused = i == self.index
            ch = self.challenge(g)
            problem, bracket = self.status(g)
            p.panel(x, y, w, h, focused, border=a.theme.accent if g["_file"] in sel_files else None)
            p.cover(a.image_path(g), g["meta"]["name"], x + 8, y + 8, w - 16, 130)
            p.text(g["meta"]["name"], x + 12, y + 146, 22, bold=True, width=w - 24)
            p.text(f"{ch.get('name', '')}", x + 12, y + 174, 18, a.theme.text_dim, width=w - 24)
            cx = x + 12
            cx += p.chip(mode_label(ch, self.race), cx, y + 202, (90, 90, 130), 15, (240, 240, 240)) + 6
            p.chip(f"{g['meta'].get('players', 2)}P", cx, y + 202, (70, 70, 90), 15, (240, 240, 240))
            if g["_file"] in sel_files:
                order = sel_files.index(g["_file"]) + 1
                p.circle(x + w - 22, y + 22, 16, a.theme.accent)
                p.text(str(order), x + w - 22, y + 10, 20, (20, 20, 20), "center", bold=True)
            if problem:
                p.rect(x, y, w, h, (0, 0, 0), radius=12, alpha=150)
                p.wrapped(problem, x + 14, y + 60, w - 28, 18, a.theme.bad, max_lines=3)
            elif bracket:
                p.chip("bracket only", x + w - 120, y + 202, a.theme.accent, 15)
            p.hit(lambda i=i: self.toggle(i), x, y, w, h)
        g = games[self.index]
        desc = self.challenge(g).get("description") or g["meta"].get("description", "")
        p.wrapped(desc, m + 20, 640 - p.margin, DESIGN_W - 2 * m - 40, 20, a.theme.text_dim, max_lines=2)


# ------------------------------------------------------------------------------------ playlist options
class PlaylistOptions(FormScreen):
    title = "Session options"

    def __init__(self, app, players, entries, bracket_only=False):
        n = len(players)
        kinds, labels = [], []
        if len(entries) == 1 and not bracket_only:
            kinds.append("single")
            labels.append("Single game")
        if not bracket_only:
            kinds.append("gauntlet")
            labels.append(f"Gauntlet ({len(entries)} game{'s' * (len(entries) > 1)})")
        if n >= 3:
            kinds.append("bracket")
            labels.append("Tournament bracket (1v1 knockout)")
        g = app.game_by_file(entries[0][0])
        best = get_challenge(g, entries[0][1]).get("best_of", 1) if g else 1
        fields = [
            Field("kind", "Format", "choice", kinds[0] if kinds else "gauntlet", kinds, labels,
                  help="Single game, several rounds across games, or a knockout bracket."),
            Field("rounds", "Rounds", "int", max(3, len(entries)), lo=1, hi=30,
                  help="How many rounds the gauntlet lasts (games repeat in order)."),
            Field("shuffle", "Shuffle games", "bool", False, help="Pick a random game each round."),
            Field("best_of", "Best of", "choice", best if best in (1, 3, 5, 7) else 1, [1, 3, 5, 7],
                  help="Each round is a series: first to win the majority."),
            Field("points", "Starting points", "int", app.settings.starting_points, lo=0, hi=200,
                  help="Points every player starts with for the shop."),
            Field("start", "Start!", "button", on_press=self.start),
        ]
        super().__init__(app, fields)
        self.players, self.entries = players, entries
        if not kinds:
            self.toast("Bracket needs 3+ players for these games")
        self.changed(None)

    def changed(self, field):
        kind = self.field("kind").value
        self.field("rounds").enabled = kind == "gauntlet"
        self.field("shuffle").enabled = kind == "gauntlet" and len(self.entries) > 1

    def hints(self):
        return [(Action.LEFT, "Change"), (Action.START, "Start"), (Action.BACK, "Back")]

    def on_action(self, event):
        if event.action is Action.START:
            self.start()
        else:
            super().on_action(event)

    def start(self):
        v = self.values()
        if not self.field("kind").options:
            self.sound("error")
            return
        entries = [{"game": f, "challenge": c} for f, c in self.entries]
        playlist = Playlist(v["kind"], entries, v["rounds"], v["shuffle"], v["best_of"])
        for i, pl in enumerate(self.players):
            pl.pad_index = self.app.input.device_index(pl.device)
        session = Session(self.players, playlist, v["points"])
        save_session(self.app, session)
        self.sound("start")
        self.app.manager.reset(RoundIntro(self.app, session))


# ------------------------------------------------------------------------------------ round intro
class PauseMixin:
    def pause_menu(self):
        def chosen(choice):
            if choice == "Standings":
                self.push(StandingsScreen(self.app, self.session, view_only=True))
            elif choice == "Save & exit to menu":
                save_session(self.app, self.session)
                self.app.manager.reset()
            elif choice == "Abandon session":
                self.app.confirm("Abandon this session? Progress is lost.", self.abandon)
        self.app.choose("Session paused", ["Continue", "Standings", "Save & exit to menu", "Abandon session"],
                        chosen, "Paused")

    def abandon(self):
        if self.session.pending:
            self.session.abort_match()
        clear_saved_session(self.app)
        self.app.manager.reset()


class RoundIntro(PauseMixin, BaseScreen):
    def __init__(self, app, session):
        super().__init__(app)
        self.session = session
        self.rnd = None
        self.game = None
        self.challenge = None
        self.race = None

    def on_enter(self):
        s = self.session
        if s.pending:
            s.abort_match()
            self.toast("The interrupted match was refunded")
        self.rnd = s.next_round()
        if self.rnd is None:
            save_session(self.app, s)
            self.replace(FinalScreen(self.app, s))
            return
        save_session(self.app, s)
        self.game = self.app.game_by_file(self.rnd.game)
        self.challenge = get_challenge(self.game, self.rnd.challenge) if self.game else None
        self.race = race_plan(self.app, [(pid, s.player(pid)) for pid in self.rnd.players])
        self.title = self.rnd.label
        total = s.playlist.total_rounds
        self.subtitle = f"Round {self.rnd.number}" + (f" of {total}" if total else "")
        self.sound("start")

    def hints(self):
        return [(Action.CONFIRM, "Go to shop"), (Action.BACK, "Pause")]

    def on_action(self, event):
        if self.rnd is None:
            return
        if event.action is Action.BACK:
            self.sound("back")
            self.pause_menu()
        elif event.action in (Action.CONFIRM, Action.START):
            if not self.game:
                self.app.choose(f"Game file '{self.rnd.game}' is missing.", ["Skip round (draw)", "Back"],
                                lambda c: c and c.startswith("Skip") and self.skip())
                return
            self.sound("confirm")
            self.push(ShopScreen(self.app, self.session, self.rnd, self.game, self.challenge))

    def skip(self):
        v = Verdict(list(self.rnd.players), [], draw=True, reason="skipped", manual=True)
        # a skipped round counts as decided: add draws until the series ends
        while not self.rnd.decided:
            self.session.record_match(v, self.app.settings, {"game": self.rnd.game, "skipped": True})
        save_session(self.app, self.session)
        self.app.manager.reset(RoundIntro(self.app, self.session))

    def draw_body(self, p):
        if self.rnd is None:
            return
        a, s, rnd = self.app, self.session, self.rnd
        m = p.margin
        if self.game:
            p.cover(a.image_path(self.game), self.game["meta"]["name"], m + 20, 110, 380, 285)
            p.text(self.game["meta"]["name"], m + 440, 110, 34, bold=True, width=DESIGN_W - m * 2 - 460)
            ch = self.challenge
            p.text(f"{ch.get('name', '')}  •  {mode_label(ch, self.race)}", m + 440, 156, 24,
                   a.theme.accent)
            p.wrapped(ch.get("description") or self.game["meta"].get("description", ""), m + 440, 196,
                      DESIGN_W - m * 2 - 460, 22, max_lines=4)
        else:
            p.text(f"Missing game: {rnd.game}", m + 20, 120, 28, a.theme.bad)
        if rnd.best_of > 1:
            wins = rnd.series_wins()
            score = " - ".join(str(wins[pid]) for pid in rnd.players)
            p.text(f"Best of {rnd.best_of}  •  Match {len(rnd.matches) + 1}  •  Series {score}",
                   m + 440, 320, 22, a.theme.text_dim)
        y = 430
        w = (DESIGN_W - 2 * m - 40 - 3 * 16) / 4
        for i, pid in enumerate(rnd.players):
            pl = s.player(pid)
            x = m + 20 + i * (w + 16)
            p.panel(x, y, w, 120, border=pl.rgb)
            draw_player_chip(p, pl, x + 14, y + 14, w - 28)
            p.text(f"{pl.points} pts", x + 14, y + 60, 26, a.theme.accent)
            p.text(f"{pl.wins}W {pl.losses}L" + (f"  🔥{pl.streak}" if pl.streak > 1 else ""), x + 14, y + 92,
                   18, a.theme.text_dim)
        if len(rnd.players) < len(s.players):
            out = [q.name for q in s.players if q.id not in rnd.players]
            p.text("Sitting out: " + ", ".join(out), m + 20, 570, 20, a.theme.text_dim)


# ------------------------------------------------------------------------------------ shop
class ShopScreen(PauseMixin, BaseScreen):
    visible_rows = 6

    def __init__(self, app, session, rnd, game, challenge):
        super().__init__(app)
        self.session, self.rnd, self.game, self.challenge = session, rnd, game, challenge
        self.title = "Shop"
        self.subtitle = f"{game['meta']['name']} • {challenge.get('name', '')}"
        self.pids = list(rnd.players)
        st = app.settings
        self.carts = {pid: PlayerCart(session.player(pid), session.player(pid).points, st.max_items)
                      for pid in self.pids}
        self.cursor = {pid: 0 for pid in self.pids}
        self.scroll = {pid: 0 for pid in self.pids}
        self.filter = {pid: 0 for pid in self.pids}
        self.target = {}           # pid -> [item, choice index]
        self.items = list(game.get("shop", []))
        self.categories = ["all"] + sorted({i.get("category", "buff") for i in self.items})
        self.wagers = st.wagers and len(self.pids) >= 2
        self.all_ready_at = None

    def hints(self):
        return [(Action.CONFIRM, "Buy"), (Action.BACK, "Refund"), (Action.PREV, "Category"),
                (Action.START, "Ready")]

    def rows(self, pid):
        cat = self.categories[self.filter[pid] % len(self.categories)]
        rows = [i for i in self.items if cat == "all" or i.get("category") == cat]
        if self.wagers:
            rows.append("wager")
        return rows

    def owner(self, device, want_ready=False):
        users = [pid for pid in self.pids if self.session.player(pid).device == device]
        if not users and device in (KEYBOARD, KEYBOARD2):
            users = [pid for pid in self.pids if not is_pad(self.session.player(pid).device)]
        for pid in users:
            if not self.carts[pid].ready:
                return pid
        return users[-1] if users and want_ready else None

    def buy(self, pid, item, chosen=None):
        cart = self.carts[pid]
        reason = cart.why_not(item)
        if reason:
            self.sound("error")
            self.toast(f"{self.session.player(pid).name}: {reason}")
            return
        if chosen is None and needs_target_pick(item, len(self.pids)):
            others = [q for q in self.pids if q != pid]
            self.target[pid] = [item, 0, others]
            self.sound("move")
            return
        cart.buy(item, resolve_targets(item, pid, self.pids, chosen))
        self.sound("buy")

    def on_action(self, event):
        a = event.action
        pid = self.owner(event.device, want_ready=a in (Action.START, Action.BACK))
        if pid is None:
            if a is Action.BACK:
                self.pause_menu_shop()
            return
        cart = self.carts[pid]
        if pid in self.target:
            item, idx, others = self.target[pid]
            if a in (Action.LEFT, Action.UP):
                self.target[pid][1] = (idx - 1) % len(others)
                self.sound("move")
            elif a in (Action.RIGHT, Action.DOWN):
                self.target[pid][1] = (idx + 1) % len(others)
                self.sound("move")
            elif a is Action.CONFIRM:
                del self.target[pid]
                self.buy(pid, item, others[idx])
            elif a is Action.BACK:
                del self.target[pid]
                self.sound("back")
            return
        if cart.ready:
            if a in (Action.START, Action.BACK):
                cart.ready = False
                self.all_ready_at = None
                self.sound("back")
            return
        rows = self.rows(pid)
        cur = min(self.cursor[pid], max(0, len(rows) - 1))
        row = rows[cur] if rows else None
        if a is Action.UP and rows:
            self.cursor[pid] = (cur - 1) % len(rows)
            self.sound("move")
        elif a is Action.DOWN and rows:
            self.cursor[pid] = (cur + 1) % len(rows)
            self.sound("move")
        elif a in (Action.PREV, Action.NEXT) and len(self.categories) > 1:
            self.filter[pid] += 1 if a is Action.NEXT else -1
            self.cursor[pid] = 0
            self.scroll[pid] = 0
            self.sound("move")
        elif a in (Action.LEFT, Action.RIGHT) and row == "wager":
            if cart.set_wager(cart.wager + (1 if a is Action.RIGHT else -1)):
                self.sound("move")
            else:
                self.sound("error")
        elif a is Action.CONFIRM and row is not None and row != "wager":
            self.buy(pid, row)
        elif a is Action.BACK:
            if cart.entries:
                cart.refund()
                self.sound("refund")
            elif cart.wager:
                cart.set_wager(0)
                self.sound("refund")
            else:
                self.pause_menu_shop()
        elif a is Action.START:
            cart.ready = True
            self.sound("ready")
        self._clamp_scroll(pid)

    def pause_menu_shop(self):
        def chosen(c):
            if c == "Back to round intro":
                self.pop()
            elif c == "Session menu":
                self.pause_menu()
        self.app.choose("Leave the shop?", ["Keep shopping", "Back to round intro", "Session menu"], chosen)

    def _clamp_scroll(self, pid):
        cur = self.cursor[pid]
        if cur < self.scroll[pid]:
            self.scroll[pid] = cur
        elif cur >= self.scroll[pid] + self.visible_rows:
            self.scroll[pid] = cur - self.visible_rows + 1

    def click_row(self, pid, index):
        if self.carts[pid].ready:
            return
        self.cursor[pid] = index
        row = self.rows(pid)[index]
        if row != "wager":
            self.buy(pid, row)

    def update(self, dt):
        super().update(dt)
        if all(c.ready for c in self.carts.values()):
            if self.all_ready_at is None:
                self.all_ready_at = self.time
            elif self.time - self.all_ready_at > 0.6:
                self.all_ready_at = None
                for c in self.carts.values():
                    c.ready = False
                self.push(PreMatch(self.app, self.session, self.rnd, self.game, self.challenge, self.carts))
                self.sound("start")

    def draw_body(self, p):
        m = p.margin
        n = len(self.pids)
        gap = 14
        w = (DESIGN_W - 2 * m - gap * (n - 1)) / n
        for k, pid in enumerate(self.pids):
            self._draw_panel(p, pid, m + k * (w + gap), 92, w, DESIGN_H - 92 - m - 44)

    def _draw_panel(self, p, pid, x, y, w, h):
        a = self.app
        pl = self.session.player(pid)
        cart = self.carts[pid]
        p.panel(x, y, w, h, border=pl.rgb)
        p.rect(x, y, w, 48, pl.rgb, radius=12)
        p.text(pl.name, x + 14, y + 10, 24, (20, 20, 20), bold=True, width=w - 110)
        p.text(f"{cart.remaining}", x + w - 14, y + 6, 30, (20, 20, 20), "right", bold=True)
        cat = self.categories[self.filter[pid] % len(self.categories)]
        if len(self.categories) > 1:
            p.text(f"◀ {cat.title()} ▶", x + w / 2, y + 56, 18, a.theme.text_dim, "center")
        rows = self.rows(pid)
        ry = y + 84
        row_h = 46
        cur = min(self.cursor[pid], max(0, len(rows) - 1))
        for i in range(self.scroll[pid], min(len(rows), self.scroll[pid] + self.visible_rows)):
            row = rows[i]
            focused = i == cur and not cart.ready
            p.rect(x + 8, ry, w - 16, row_h - 6, (70, 70, 96) if focused else (52, 52, 68), radius=8)
            if row == "wager":
                txt = f"Wager: ◀ {cart.wager} ▶" if focused else f"Wager: {cart.wager}"
                p.text(txt, x + 20, ry + 9, 20, a.theme.accent, width=w - 40)
            else:
                blocked = cart.why_not(row)
                col = a.theme.text if not blocked else a.theme.text_dim
                p.rect(x + 14, ry + 12, 8, 16, CATEGORY_COLORS.get(row.get("category"), (150, 150, 150)), radius=3)
                count = cart.count(row)
                label = row["name"] + (f" ×{count}" if count else "")
                p.text(label, x + 30, ry + 9, 20, col, width=w - 100)
                p.text(str(row["cost"]), x + w - 22, ry + 9, 20, a.theme.accent if not blocked else col, "right")
            p.hit(lambda pid=pid, i=i: self.click_row(pid, i), x + 8, ry, w - 16, row_h - 6)
            ry += row_h
        if rows and not cart.ready:
            row = rows[cur]
            if row == "wager":
                desc = "Bet points: winners split every wager, draws refund. Left/Right to change."
            else:
                desc = row.get("description") or ""
                reason = cart.why_not(row)
                tgt = row.get("target", "self")
                desc = f"[{tgt}] {desc}" + (f"  ({reason})" if reason else "")
            p.wrapped(desc, x + 14, y + 84 + self.visible_rows * row_h + 4, w - 28, 17, a.theme.text_dim,
                      max_lines=3)
        cy = y + h - 150
        p.text(f"Cart ({len(cart.entries)}/{cart.max_items or '∞'})", x + 14, cy, 18, a.theme.text_dim)
        for i, e in enumerate(cart.entries[-4:]):
            tg = ", ".join(self.session.player(t).name for t in e.targets if t != pid)
            p.text(f"• {e.item['name']}" + (f" → {tg}" if tg else ""), x + 14, cy + 24 + i * 24, 17,
                   width=w - 28)
        if pid in self.target:
            item, idx, others = self.target[pid]
            p.rect(x + 6, y + 80, w - 12, 200, (15, 15, 22), radius=10, alpha=235)
            p.text(f"{item['name']}: target?", x + w / 2, y + 96, 20, a.theme.accent, "center", width=w - 30)
            for j, q in enumerate(others):
                o = self.session.player(q)
                fy = y + 132 + j * 40
                p.panel(x + 20, fy, w - 40, 34, j == idx, color=(60, 60, 82))
                p.text(o.name, x + w / 2, fy + 6, 20, o.rgb, "center")
        if cart.ready:
            p.rect(x, y + h / 2 - 40, w, 80, (0, 0, 0), alpha=180)
            p.text("READY", x + w / 2, y + h / 2 - 22, 40, a.theme.good, "center", bold=True)


# ------------------------------------------------------------------------------------ pre-match
class PreMatch(BaseScreen):
    title = "Get ready"

    def __init__(self, app, session, rnd, game, challenge, carts):
        super().__init__(app)
        self.session, self.rnd, self.game, self.challenge, self.carts = session, rnd, game, challenge, carts
        self.subtitle = f"{game['meta']['name']} • {challenge.get('name', '')}"
        self.race = (race_plan(app, [(pid, session.player(pid)) for pid in rnd.players])
                     if challenge.get("mode") == "turns" else RacePlan(False))

    def on_enter(self):
        self.app.clear_health()
        self.errors = self.app.health(self.game)

    def hints(self):
        return [(Action.START, "Launch!"), (Action.BACK, "Back to shop")]

    def on_action(self, event):
        if event.action in (Action.START, Action.CONFIRM):
            self.launch()
        else:
            super().on_action(event)

    def launch(self):
        if self.errors:
            def chosen(c):
                if c == "Play elsewhere & report result":
                    self.session.begin_match(self.carts)
                    self.app.manager.reset(ManualResult(self.app, self.session, self.rnd, self.game,
                                                        self.challenge, "Report the result of the match"))
            self.app.choose("Cannot launch: " + "; ".join(self.errors),
                            ["Back", "Play elsewhere & report result"], chosen)
            self.sound("error")
            return
        self.session.begin_match(self.carts)
        save_session(self.app, self.session)
        self.sound("start")
        self.app.manager.reset(MatchScreen(self.app, self.session, self.rnd, self.game, self.challenge))

    def draw_body(self, p):
        a = self.app
        m = p.margin
        mode = self.challenge.get("mode")
        y = 100
        if self.race.race:
            p.text("Race! Everyone plays in their own window at the same time - first to finish wins.",
                   m + 20, y, 22, width=DESIGN_W - 2 * m - 40)
        elif mode == "turns":
            order = ", ".join(self.session.player(pid).name for pid in self.rnd.players)
            p.text(f"Take turns: {order}. Each turn uses controller port 1.", m + 20, y, 22,
                   width=DESIGN_W - 2 * m - 40)
        else:
            p.text(MODE_LABELS.get(mode, ""), m + 20, y, 22)
        y += 44
        for i, pid in enumerate(self.rnd.players):
            pl = self.session.player(pid)
            cart = self.carts[pid]
            p.panel(m + 20, y, DESIGN_W - 2 * m - 40, 84, border=pl.rgb)
            draw_player_chip(p, pl, m + 36, y + 10, 320)
            where = f"Window {i + 1}" if self.race.race else f"Port {1 if mode == 'turns' else i + 1}"
            p.text(f"{where}: {device_label(a, pl.device)}", m + 380, y + 14, 20, a.theme.text_dim, width=520)
            p.text(f"{cart.remaining} pts left" + (f" • wager {cart.wager}" if cart.wager else ""),
                   DESIGN_W - m - 40, y + 14, 20, a.theme.accent, "right")
            items = []
            for e in cart.entries:
                tg = ", ".join(self.session.player(t).name for t in e.targets if t != pid)
                items.append(e.item["name"] + (f" → {tg}" if tg else ""))
            p.text("Items: " + (", ".join(items) or "none"), m + 36, y + 50, 18, width=DESIGN_W - 2 * m - 80)
            y += 96
        if self.errors:
            p.wrapped("Cannot launch: " + "; ".join(self.errors), m + 20, y + 10, DESIGN_W - 2 * m - 40, 22,
                      a.theme.bad)
        else:
            if self.race.note and mode == "turns":
                p.text("Note: " + self.race.note, m + 20, y + 10, 20, a.theme.accent, width=DESIGN_W - 2 * m - 40)
                y += 32
            p.wrapped("RetroArch takes over your controllers during the match. Hold Select+Start for "
                      f"{FORFEIT_HOLD:.1f}s to forfeit. Press Esc in this window for the match menu.",
                      m + 20, y + 10, DESIGN_W - 2 * m - 40, 20, a.theme.text_dim)


# ------------------------------------------------------------------------------------ match
class MatchScreen(BaseScreen):
    low_fps = True

    def __init__(self, app, session, rnd, game, challenge):
        super().__init__(app)
        self.session, self.rnd, self.game, self.challenge = session, rnd, game, challenge
        self.title = game["meta"]["name"]
        self.subtitle = challenge.get("name", "")
        self.runner = None
        self.snap = {"phase": "idle", "message": "", "values": {}, "warnings": []}
        self.hold = {}
        self.done = False
        self.max_seen = {}

    def participants(self):
        return make_participants(self.app, [(pid, self.session.player(pid)) for pid in self.rnd.players])

    def purchases(self):
        items = {i.get("id"): i for i in self.game.get("shop", [])}
        out = []
        for pu in (self.session.pending or {}).get("purchases", []):
            item = items.get(pu["item"])
            if item:
                out.append(Purchase(item, pu["buyer"], pu["targets"]))
        return out

    def on_enter(self):
        self.start_runner()

    def start_runner(self):
        self.done = False
        self.runner = MatchRunner(self.app.launcher, self.game, self.challenge, self.participants(),
                                  self.purchases(), self.app.settings, screen=self.app.desktop_size())
        self.app.race_windowed(self.runner.race.race or self.runner.stage)
        self.runner.start()

    def on_exit(self):
        if self.runner and not self.runner.finished:
            self.runner.cancel()
            self.runner.join(8)
        self.app.race_windowed(False)
        if self.session.pending and not self.done:
            self.session.abort_match()
            save_session(self.app, self.session)

    def hints(self):
        return [(Action.BACK, "Match menu (Esc)"), (Action.SELECT, "+Start hold: forfeit")]

    def on_action(self, event):
        if is_pad(event.device):
            return  # RetroArch owns controllers during the match
        if event.action is Action.BACK:
            self.menu()

    def menu(self):
        mode = self.challenge.get("mode")
        turn = mode == "turns" and not (self.runner and self.runner.race.race)
        opts = ["Keep playing", "End turn early" if turn else "End now & report result", "Forfeit...",
                "Cancel match (refund)"]

        def chosen(c):
            if not self.runner or self.runner.finished:
                return
            if c and c.startswith("End"):
                self.runner.end()
            elif c == "Forfeit...":
                names = [self.session.player(pid).name for pid in self.rnd.players]
                self.app.choose("Who forfeits?", names, self._forfeit_name)
            elif c == "Cancel match (refund)":
                self.runner.cancel()
        self.app.choose("Match menu", opts, chosen)

    def _forfeit_name(self, name):
        for pid in self.rnd.players:
            if self.session.player(pid).name == name:
                self.runner.forfeit(pid)

    def _check_forfeit(self, dt):
        turn = self.snap.get("turn")
        for pid in self.rnd.players:
            dev = self.session.player(pid).device
            if self.app.input.is_held(dev, Action.SELECT, Action.START):
                self.hold[dev] = self.hold.get(dev, 0) + dt
                if self.hold[dev] >= FORFEIT_HOLD:
                    users = [q for q in self.rnd.players if self.session.player(q).device == dev]
                    who = turn if turn in users else users[0]
                    self.hold[dev] = -999
                    self.runner.forfeit(who)
                    self.toast(f"{self.session.player(who).name} forfeits")
            elif self.hold.get(dev, 0) > 0:
                self.hold[dev] = 0

    def update(self, dt):
        super().update(dt)
        if not self.runner or self.done:
            return
        self.snap = self.runner.snapshot()
        for k, v in self.snap.get("values", {}).items():
            if v is not None:
                self.max_seen[k] = max(self.max_seen.get(k, 0), v)
        self._check_forfeit(dt)
        phase = self.snap["phase"]
        if not self.runner.finished:
            return
        self.runner.join(2)
        self.done = True
        self.app.race_windowed(False)
        self.app.request_focus()
        if phase == "finished" and self.runner.verdict:
            turns = [{"player": r.player, "success": r.success, "time": r.time, "value": r.value,
                      "reason": r.reason} for r in self.runner.turn_results]
            extra = {"turns": turns} if turns else {}
            if self.runner.race.race:
                extra["race"] = True
            finish_match(self.app, self.session, self.rnd, self.game, self.challenge, self.runner.verdict,
                         extra or None)
        elif phase == "no_verdict":
            self.app.manager.reset(ManualResult(self.app, self.session, self.rnd, self.game, self.challenge,
                                                "No automatic result: who won?"))
        elif phase == "cancelled":
            self.session.abort_match()
            save_session(self.app, self.session)
            self.toast("Match cancelled; points refunded")
            self.app.manager.reset(RoundIntro(self.app, self.session))
        else:
            self.sound("error")
            self.app.choose(self.snap.get("message") or "Match failed",
                            ["Retry", "Report result manually", "Cancel match (refund)"], self._error_choice,
                            "Match error", cancel_value="Retry")

    def _error_choice(self, c):
        if c == "Retry":
            self.app.clear_health()
            self.start_runner()
        elif c == "Report result manually":
            self.app.manager.reset(ManualResult(self.app, self.session, self.rnd, self.game, self.challenge,
                                                "Who won?"))
        else:
            self.session.abort_match()
            save_session(self.app, self.session)
            self.app.manager.reset(RoundIntro(self.app, self.session))

    # -- live values --------------------------------------------------------------------
    def player_status(self, pid):
        """("bar", value, fraction) for a live value, else ("text", label, color)."""
        a, s = self.app, self.snap
        v = s.get("values", {}).get(pid)
        race = s.get("players", {}).get(pid)
        if race and race["status"] not in ("racing", "waiting"):
            label = {"finished": "FINISHED", "out": "OUT", "done": "TIME"}.get(race["status"], "")
            return ("text", f"{label}  {race['value'] if race['value'] is not None else '-'} in "
                            f"{race['time']:.1f}s ({race['reason']})",
                    a.theme.good if race["status"] == "finished" else a.theme.text_dim)
        if race and race["status"] == "waiting" and v is None:
            return ("text", "waiting for the game to start", a.theme.text_dim)
        if v is not None:
            win = self.challenge.get("win") or {}
            if win.get("type") in ("reach",) and win.get("value"):
                frac = v / max(1, win["value"])
            else:
                frac = v / max(1, self.max_seen.get(pid, 1))
            return ("bar", v, frac)
        done = [r for r in (self.runner.turn_results if self.runner else []) if r.player == pid]
        txt = (f"{done[0].value} in {done[0].time:.1f}s ({done[0].reason})" if done else
               ("waiting" if self.challenge.get("mode") == "turns" else
                "manual result" if self.challenge.get("mode") == "manual" else "—"))
        return ("text", txt, a.theme.text_dim)

    def power_ups(self, pid):
        """[(item name, is_buff)] for the items bought into this match that affect player `pid`."""
        out = []
        for pu in self.purchases():
            targets = list(pu.targets) or [pu.buyer]
            if pid in targets:
                out.append((pu.item.get("name", pu.item.get("id", "?")), pu.item.get("category") != "debuff"))
        return out

    def headline(self):
        s = self.snap
        phase, turn = s.get("phase"), s.get("turn")
        big = {"launching": "Launching...", "waiting": "Starting RetroArch...", "playing": "FIGHT!",
               "finished": "Finished!", "no_verdict": "Match over", "error": "Error", "cancelled": "Cancelled",
               "idle": "Preparing..."}.get(phase, phase)
        if turn is not None and self.session.player(turn):
            big = f"{self.session.player(turn).name}'s turn"
        elif s.get("race") and phase == "playing":
            big = "RACE!"
        return big

    def clock(self):
        rem = self.snap.get("remaining")
        if rem is None:
            return None
        mins, secs = divmod(max(0, int(rem)), 60)
        return f"{mins}:{secs:02d}"

    # -- drawing ----------------------------------------------------------------------------
    def draw(self, surface):
        w, h = surface.get_size()
        if h and w / h >= STRIP_ASPECT:
            design_h = DESIGN_W * h / w
            with self.app.painter.design(DESIGN_W, design_h):
                self.draw_strip(self.app.painter, design_h)
            return
        super().draw(surface)

    def draw_strip(self, p, H):
        """Scoreboard strip under the game windows: players left and right, the task in the middle."""
        a = self.app
        th = a.theme
        p.rect(0, 0, DESIGN_W, H, th.bg)
        pids = list(self.rnd.players)
        m, gap = 10, 10
        center_w = 420 if len(pids) <= 2 else 340
        left = pids[:(len(pids) + 1) // 2]
        right = pids[len(left):]
        side_w = (DESIGN_W - center_w - 2 * m - 2 * gap) / 2
        cx = m + side_w + gap
        turn = self.snap.get("turn")
        for group, x0 in ((left, m), (right, cx + center_w + gap)):
            if not group:
                continue
            cw = (side_w - gap * (len(group) - 1)) / len(group)
            for i, pid in enumerate(group):
                self._strip_player(p, pid, x0 + i * (cw + gap), m, cw, H - 2 * m,
                                   turn is None or turn == pid)
        # the task
        y = m
        p.text(self.subtitle or self.title, cx + center_w / 2, y, 22, th.accent, "center", bold=True,
               width=center_w)
        y += 30
        clock = self.clock()
        p.text(clock or self.headline(), cx + center_w / 2, y, 34 if clock else 26, th.text, "center",
               bold=True, width=center_w)
        y += 44
        warn = self.snap.get("warnings", [])
        msg = ("⚠ " + warn[-1]) if warn else (self.snap.get("message") or "")
        if msg and y + 18 <= H - m:
            p.text(msg, cx + center_w / 2, y, 16, th.bad if warn else th.text_dim, "center", width=center_w)
            y += 24
        desc = self.challenge.get("description", "")
        lines = int((H - m - y) // 20)
        if desc and lines > 0:
            p.wrapped(desc, cx, y, center_w, 15, th.text_dim, max_lines=min(3, lines))

    def _strip_player(self, p, pid, x, y, w, h, active):
        th = self.app.theme
        pl = self.session.player(pid)
        p.panel(x, y, w, h, border=pl.rgb if active else None)
        pad = 12
        draw_player_chip(p, pl, x + pad, y + pad, w * 0.6, size=20)
        kind, a, b = self.player_status(pid)
        if kind == "bar":
            p.text(str(a), x + w - pad, y + pad - 4, 34, None, "right", bold=True)
            p.bar(x + pad, y + pad + 44, w - 2 * pad, 16, b, pl.rgb)
        else:
            p.text(a, x + pad, y + pad + 40, 18, b, width=w - 2 * pad)
        ups = self.power_ups(pid)
        py = y + pad + 72
        if ups and py + 24 <= y + h:
            px = x + pad
            for name, buff in ups:
                chip_w = p.measure(name, 15, True) + 18
                if px + chip_w > x + w - pad:
                    p.text("…", px, py + 2, 16, th.text_dim)
                    break
                px += p.chip(name, px, py, th.good if buff else th.bad, size=15) + 6
        elif py + 18 <= y + h:
            p.text("No power-ups", x + pad, py + 2, 15, th.text_dim)

    def draw_body(self, p):
        a = self.app
        m = p.margin
        s = self.snap
        turn = s.get("turn")
        y = 110
        p.text(self.headline(), DESIGN_W / 2, y, 48, a.theme.accent, "center", bold=True)
        p.text(s.get("message", ""), DESIGN_W / 2, y + 66, 22, a.theme.text_dim, "center",
               width=DESIGN_W - 2 * m)
        clock = self.clock()
        if clock:
            p.text(clock, DESIGN_W - m - 20, y, 48, a.theme.text, "right", bold=True)
        y = 230
        for pid in self.rnd.players:
            pl = self.session.player(pid)
            active = turn is None or turn == pid
            p.panel(m + 20, y, DESIGN_W - 2 * m - 40, 64, border=pl.rgb if active else None)
            draw_player_chip(p, pl, m + 36, y + 14, 260)
            kind, v, extra = self.player_status(pid)
            if kind == "bar":
                p.bar(m + 320, y + 22, 640, 20, extra, pl.rgb)
                p.text(str(v), DESIGN_W - m - 40, y + 16, 26, None, "right")
            else:
                p.text(v, m + 320, y + 18, 22, extra, width=700)
            y += 76
        for i, w in enumerate(s.get("warnings", [])[-3:]):
            p.text("⚠ " + w, m + 20, DESIGN_H - m - 150 + i * 28, 20, a.theme.bad, width=DESIGN_W - 2 * m)


class ManualResult(BaseScreen):
    title = "Report result"

    def __init__(self, app, session, rnd, game, challenge, prompt="Who won?"):
        super().__init__(app)
        self.session, self.rnd, self.game, self.challenge = session, rnd, game, challenge
        self.prompt = prompt
        self.options = [("win", pid) for pid in rnd.players] + [("draw", None), ("refund", None)]
        self.index = 0

    def hints(self):
        return [(Action.CONFIRM, "Confirm"), (Action.UP, "Choose")]

    def label(self, opt):
        kind, pid = opt
        if kind == "win":
            return f"{self.session.player(pid).name} wins"
        return "Draw" if kind == "draw" else "Not played (refund points)"

    def on_action(self, event):
        a = event.action
        if a in (Action.UP, Action.DOWN):
            self.index = (self.index + (1 if a is Action.DOWN else -1)) % len(self.options)
            self.sound("move")
        elif a is Action.CONFIRM:
            self.pick(self.index)

    def pick(self, i):
        kind, pid = self.options[i]
        players = list(self.rnd.players)
        if kind == "refund":
            self.session.abort_match()
            save_session(self.app, self.session)
            self.app.manager.reset(RoundIntro(self.app, self.session))
            return
        if kind == "draw":
            v = Verdict(players, [], draw=True, reason="reported draw", manual=True)
        else:
            v = Verdict([pid], [q for q in players if q != pid], reason="reported", manual=True)
        self.sound("confirm")
        finish_match(self.app, self.session, self.rnd, self.game, self.challenge, v)

    def draw_body(self, p):
        a = self.app
        m = p.margin
        p.text(self.prompt, m + 20, 110, 28)
        y = 170
        for i, opt in enumerate(self.options):
            focused = i == self.index
            pl = self.session.player(opt[1]) if opt[1] is not None else None
            p.panel(m + 20, y, 600, 50, focused, border=pl.rgb if pl and focused else None,
                    color=(60, 60, 82) if focused else None)
            p.text(self.label(opt), m + 40, y + 12, 24, pl.rgb if pl else a.theme.text)
            p.hit(lambda i=i: self.pick(i), m + 20, y, 600, 50)
            y += 60


# ------------------------------------------------------------------------------------ results
class ResultsScreen(BaseScreen):
    title = "Results"

    def __init__(self, app, session, rnd, game, verdict, payouts, achievements=()):
        super().__init__(app)
        self.session, self.rnd, self.game, self.verdict, self.payouts = session, rnd, game, verdict, payouts
        self.achievements = list(achievements)
        self.counters = {pid: CountUp(0, row["total"], 1.2) for pid, row in payouts.items()}
        self.confetti = Confetti(seed=len(rnd.matches)) if verdict.winners and not verdict.draw else None

    def on_enter(self):
        self.sound("draw" if self.verdict.draw else "win")
        for name, ach in self.achievements:
            self.toast(f"🏆 {name}: {ACHIEVEMENTS[ach][0]}")
        if self.achievements:
            self.sound("achievement")

    def hints(self):
        return [(Action.CONFIRM, "Continue")]

    def update(self, dt):
        super().update(dt)
        for c in self.counters.values():
            c.update(dt)
        if self.confetti:
            self.confetti.update(dt)

    def on_action(self, event):
        if event.action in (Action.CONFIRM, Action.START):
            self.sound("confirm")
            if self.rnd.decided:
                self.app.manager.reset(StandingsScreen(self.app, self.session))
            else:
                self.app.manager.reset(RoundIntro(self.app, self.session))

    def draw_body(self, p):
        a = self.app
        m = p.margin
        v = self.verdict
        names = self.session.names()
        if v.draw:
            banner = "DRAW"
        elif v.winners:
            banner = " & ".join(names.get(w, "?") for w in v.winners) + " WINS!"
        else:
            banner = "Nobody wins"
        col = self.session.player(v.winners[0]).rgb if v.winners and not v.draw else a.theme.accent
        p.text(banner, DESIGN_W / 2, 100, 56, col, "center", bold=True)
        reason = v.reason + (" (reported)" if v.manual else "")
        p.text(reason, DESIGN_W / 2, 172, 22, a.theme.text_dim, "center")
        y = 220
        cols = [("Base", "base"), ("Catch-up", "catchup"), ("Streak", "streak"), ("Wager", "wager")]
        p.text("Player", m + 40, y, 18, a.theme.text_dim)
        for j, (label, _k) in enumerate(cols):
            p.text(label, 560 + j * 120, y, 18, a.theme.text_dim, "center")
        p.text("Total", 1080, y, 18, a.theme.text_dim, "center")
        y += 30
        for pid, row in self.payouts.items():
            pl = self.session.player(pid)
            p.panel(m + 20, y, DESIGN_W - 2 * m - 40, 56, border=pl.rgb if row["result"] == "win" else None)
            draw_player_chip(p, pl, m + 36, y + 10, 300, extra=f"  ({row['result']})")
            for j, (_label, k) in enumerate(cols):
                p.text(f"+{row[k]}" if row[k] else "—", 560 + j * 120, y + 14, 22, None, "center")
            p.text(f"+{self.counters[pid].value}", 1080, y + 12, 28, a.theme.accent, "center", bold=True)
            p.text(f"= {pl.points}", DESIGN_W - m - 30, y + 14, 22, a.theme.text_dim, "right")
            y += 64
        if self.rnd.best_of > 1:
            wins = self.rnd.series_wins()
            series = "  ".join(f"{names[q]} {wins[q]}" for q in self.rnd.players)
            state = "Series over" if self.rnd.decided else f"Best of {self.rnd.best_of} continues"
            p.text(f"{state}:  {series}", DESIGN_W / 2, y + 10, 22, a.theme.text, "center")
        if self.confetti:
            self.confetti.draw(p)


class StandingsScreen(BaseScreen):
    title = "Standings"

    def __init__(self, app, session, view_only=False):
        super().__init__(app)
        self.session, self.view_only = session, view_only

    def hints(self):
        return [(Action.CONFIRM, "Back" if self.view_only else "Next round")]

    def on_action(self, event):
        if self.view_only:
            if event.action in (Action.CONFIRM, Action.BACK, Action.START):
                self.pop()
            return
        if event.action in (Action.CONFIRM, Action.START):
            self.sound("confirm")
            self.app.manager.reset(RoundIntro(self.app, self.session))
        elif event.action is Action.BACK:
            self.app.choose("Leave?", ["Stay", "Save & exit to menu"],
                            lambda c: (save_session(self.app, self.session), self.app.manager.reset())
                            if c == "Save & exit to menu" else None)

    def draw_body(self, p):
        a = self.app
        m = p.margin
        s = self.session
        total = s.playlist.total_rounds
        done = sum(1 for r in s.rounds if r.decided)
        self.subtitle = f"{done} of {total} rounds" if total else f"{done} matches played"
        y = 110
        for rank, pl in enumerate(s.standings(), 1):
            p.panel(m + 20, y, 640, 60, border=pl.rgb if rank == 1 else None)
            p.text(f"#{rank}", m + 40, y + 14, 28, a.theme.accent, bold=True)
            draw_player_chip(p, pl, m + 110, y + 12, 260)
            p.text(f"{pl.points} pts", m + 420, y + 14, 24)
            p.text(f"{pl.wins}W {pl.losses}L {pl.draws}D", m + 520, y + 18, 18, a.theme.text_dim)
            y += 70
        if s.playlist.kind == "bracket":
            self.draw_bracket(p, m + 700, 110)

    def draw_bracket(self, p, x, y):
        a = self.app
        s = self.session
        names = s.names()
        for st, (players, byes, rows) in enumerate(s.playlist.bracket_stages(s)):
            p.text(s.playlist.stage_label(len(players)), x, y, 20, a.theme.accent, bold=True)
            y += 30
            for b in byes:
                p.text(f"{names[b]} (bye)", x + 10, y, 18, a.theme.text_dim)
                y += 24
            for pair, rnd in rows:
                wtxt = ""
                if rnd is not None and rnd.decided:
                    wtxt = " → " + names[s.playlist.bracket_winner(rnd)]
                p.text(f"{names[pair[0]]} vs {names[pair[1]]}{wtxt}", x + 10, y, 18, width=500)
                y += 24
            y += 10


class FinalScreen(BaseScreen):
    title = "Champion"

    def __init__(self, app, session):
        super().__init__(app)
        self.session = session
        self.confetti = Confetti(200, seed=7)
        self.new = []

    def on_enter(self):
        s = self.session
        s.finished = True
        if not getattr(s, "_stats_recorded", False):
            s._stats_recorded = True
            self.new = self.app.stats.record_session(s)
            try:
                self.app.stats.save()
            except OSError:
                pass
            clear_saved_session(self.app)
        self.sound("win")
        for name, ach in self.new:
            self.toast(f"🏆 {name}: {ACHIEVEMENTS[ach][0]}")

    def update(self, dt):
        super().update(dt)
        self.confetti.update(dt)
        if self.confetti.done:
            self.confetti = Confetti(120, seed=int(self.time))

    def hints(self):
        return [(Action.CONFIRM, "Main menu"), (Action.ALT, "Rematch")]

    def on_action(self, event):
        if event.action in (Action.CONFIRM, Action.START, Action.BACK):
            self.sound("confirm")
            self.app.manager.reset()
        elif event.action is Action.ALT:
            self.rematch()

    def rematch(self):
        old = self.session
        players = [Player(p.id, p.name, p.color, p.device, p.pad_index) for p in old.players]
        session = Session(players, Playlist.from_dict(old.playlist.to_dict()), self.app.settings.starting_points)
        save_session(self.app, session)
        self.sound("start")
        self.app.manager.reset(RoundIntro(self.app, session))

    def draw_body(self, p):
        a = self.app
        champ = self.session.champion() or self.session.standings()[0]
        p.text("🏆", DESIGN_W / 2, 100, 80, a.theme.accent, "center")
        p.text(champ.name, DESIGN_W / 2, 200, 64, champ.rgb, "center", bold=True)
        p.text("is the Gauntlet champion!", DESIGN_W / 2, 280, 28, None, "center")
        y = 350
        for rank, pl in enumerate(self.session.standings(), 1):
            p.text(f"#{rank}  {pl.name}  —  {pl.points} pts  ({pl.wins}W {pl.losses}L)", DESIGN_W / 2, y, 24,
                   pl.rgb, "center")
            y += 36
        self.confetti.draw(p)
