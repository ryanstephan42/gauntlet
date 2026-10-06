"""Tool screens: settings, input remap, games manager, add-game wizard, memory lab, stats, file browser."""
import copy
import glob
import logging
import os
import queue
import shutil
import threading
import time

import pygame

from .. import inputmap as im
from ..actions import Effect, EffectContext
from ..detect import cores_for_system, scan_roms
from ..games import delete_game, duplicate_game, save_game, slugify, strip_private
from ..inputmap import Action
from ..layout import DESIGN_H, DESIGN_W
from ..memlab import FILTERS, MAX_REGION, RamSearch, Watch
from ..memory import Memory, Var, parse_int, read_metric
from ..packs import export_pack, import_pack
from ..presets import TEMPLATES, game_from_preset, generic_items, match_presets, template
from ..match import Participant, build_config
from ..retroarch import COMMANDS, Launcher
from ..schema import validate_game
from ..startstate import (clear_folder, find_start_state, newest_state, save_capture, search_dirs,
                          state_filename)
from ..stats import ACHIEVEMENTS
from ..systems import SYSTEMS, guess_system
from .base import BaseScreen, Field, FormScreen, MenuScreen

log = logging.getLogger("gauntlet.ui.tools")

MODE_LABELS = {"versus": "Versus (simultaneous)", "turns": "Single-player (race or turns)", "coop": "Co-op",
               "manual": "Manual (players report)"}
WIN_LABELS = {"reach": "First to reach value", "eliminate": "Eliminate (drop to value)",
              "compare": "Best value when time is up", "equals": "Value equals", "bit_set": "Bit becomes set"}
FILTER_LABELS = {"eq": "equals value", "ne": "not equal to value", "gt": "greater than value",
                 "lt": "less than value", "changed": "changed", "unchanged": "unchanged",
                 "increased": "increased", "decreased": "decreased"}
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
RESOLUTIONS = ["1024x768", "1280x720", "1280x800", "1600x900", "1920x1080"]


def hex_addr(value, width=6):
    return f"0x{value:0{width}X}"


def address_text(addr):
    """Config address (str or per-player map) -> editable text ('0x10-0x20' for per-player)."""
    if isinstance(addr, dict):
        return "-".join(str(addr[k]) for k in sorted(addr, key=int))
    return str(addr or "")


def parse_address(text):
    """'0x2EFC' -> '0x2EFC'; '0x2EFC-0x30AA' / '0x2EFC,0x30AA' -> {"1": .., "2": ..}. None if invalid."""
    parts = [p for p in text.replace(",", "-").replace(" ", "-").replace(";", "-").split("-") if p]
    if not parts:
        return None
    try:
        parts = [hex_addr(parse_int(p), 1) for p in parts]
    except (TypeError, ValueError):
        return None
    if len(parts) == 1:
        return parts[0]
    return {str(i + 1): a for i, a in enumerate(parts)}


def live_memory(app, game):
    client = app.launcher.client(timeout=0.4)
    mem = (game or {}).get("memory", {})
    return client, Memory(client, mem.get("layout", "linear")), {"endian": mem.get("endian", "little")}


# ------------------------------------------------------------------------------------ file browser
class FileBrowser(MenuScreen):
    title = "Choose a file"
    width = 760
    visible = 10

    def __init__(self, app, start, on_pick, exts=None, pick_dir=False, title=None):
        super().__init__(app)
        start = os.path.expanduser(start or "~")
        while start and not os.path.isdir(start) and os.path.dirname(start) != start:
            start = os.path.dirname(start)
        self.path = start if os.path.isdir(start) else os.path.expanduser("~")
        self.exts = tuple(e.lower() for e in exts) if exts else None
        self.on_pick = on_pick
        self.pick_dir = pick_dir
        if title:
            self.title = title

    @property
    def subtitle(self):
        return self.path

    def rows(self):
        rows = []
        if self.pick_dir:
            rows.append(("[ Use this folder ]", lambda: self.pick(self.path), True, self.path))
        parent = os.path.dirname(self.path.rstrip(os.sep)) or os.sep
        if parent != self.path:
            rows.append((".. (up)", lambda: self.cd(parent), True, parent))
        try:
            entries = sorted(os.scandir(self.path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError as e:
            entries = []
            rows.append((f"(cannot read folder: {e.strerror})", None, False, ""))
        for e in entries:
            if e.name.startswith("."):
                continue
            try:
                is_dir = e.is_dir()
            except OSError:
                continue
            if is_dir:
                rows.append((e.name + "/", lambda p=e.path: self.cd(p), True, e.path))
            elif not self.pick_dir and (not self.exts or os.path.splitext(e.name)[1].lower() in self.exts):
                rows.append((e.name, lambda p=e.path: self.pick(p), True, e.path))
        return rows

    def cd(self, path):
        self.path = path
        self.list.index = 0
        self.refresh()
        self.list.index, self.list.top = 0, 0

    def pick(self, path):
        self.pop()
        self.on_pick(path)

    def draw_body(self, p):
        x, y = p.margin + 20, self.top
        for i, row in enumerate(self.list.visible_items):
            idx = self.list.top + i
            focused = idx == self.list.index
            p.panel(x, y, DESIGN_W - 2 * x, self.row_h - 8, focused, color=(60, 60, 82) if focused else None)
            color = self.app.theme.accent if row[0].endswith("/") or row[0].startswith(("[", "..")) \
                else self.app.theme.text
            p.text(row[0], x + 18, y + 9, 24, color, width=DESIGN_W - 2 * x - 36)
            p.hit(lambda idx=idx: self.focus_and_activate(idx), x, y, DESIGN_W - 2 * x, self.row_h - 8)
            y += self.row_h - 4
        if not self.list.items:
            p.text("(empty)", x + 18, y + 9, 24, self.app.theme.text_dim)


# ------------------------------------------------------------------------------------ settings
class SettingsScreen(FormScreen):
    title = "Settings"
    subtitle = "Changes are saved when you leave this screen"

    def __init__(self, app):
        s = app.settings
        labels = [i.label for i in app.launcher.installs]
        res = f"{s.width}x{s.height}"
        resolutions = RESOLUTIONS if res in RESOLUTIONS else RESOLUTIONS + [res]
        F = Field
        self.rom_dir, self.core_dir = s.rom_dir, s.core_dir
        fields = [
            F("h1", "Points & economy", "info"),
            F("starting_points", "Starting points", "int", s.starting_points, lo=0, hi=999,
              help="Points every player starts a session with (spent in the shop)."),
            F("win_points", "Points for a win", "int", s.win_points, lo=0, hi=99),
            F("loss_points", "Points for a loss", "int", s.loss_points, lo=0, hi=99),
            F("draw_points", "Points for a draw", "int", s.draw_points, lo=0, hi=99),
            F("catchup_step", "Catch-up: +1 per N points behind", "int", s.catchup_step, lo=1, hi=99,
              help="Players who are behind the leader earn a bonus: 1 point per N points behind."),
            F("catchup_max", "Catch-up bonus cap", "int", s.catchup_max, lo=0, hi=20),
            F("streak_bonus", "Win-streak bonus", "int", s.streak_bonus, lo=0, hi=20),
            F("streak_max", "Streak bonus cap", "int", s.streak_max, lo=0, hi=20),
            F("max_items", "Max shop items per match", "int", s.max_items, lo=0, hi=10),
            F("wagers", "Wagers", "bool", s.wagers, help="Let players bet points on a match."),
            F("h2", "Display", "info"),
            F("fullscreen", "Fullscreen", "bool", s.fullscreen),
            F("tv_mode", "TV mode (bigger margins for couch play)", "bool", s.tv_mode),
            F("resolution", "Window size", "choice", res, options=resolutions),
            F("h3", "Audio", "info"),
            F("sound", "Sound effects", "bool", s.sound),
            F("volume", "Volume", "int", int(round(s.volume * 100)), lo=0, hi=100, step=5,
              fmt=lambda v: f"{v}%"),
            F("h4", "Controls", "info"),
            F("split_keyboard", "Split keyboard (2 players)", "bool", s.split_keyboard,
              help="Second player uses I/J/K/L + U/O/P/Y on the same keyboard."),
            F("remap", "Remap menu controls...", "button", on_press=lambda: self.push(InputRemap(app)),
              help="In-game controls are configured in RetroArch itself."),
            F("h5", "RetroArch", "info"),
            F("preferred_install", "RetroArch install", "choice", s.preferred_install,
              options=[""] + labels, labels=["Auto (first found)"] + labels,
              help="Detected: " + (", ".join(labels) or "none - install RetroArch or RetroDECK")),
            F("rom_dir", "ROM folder", "button", on_press=self.pick_rom_dir,
              fmt=lambda _v: self.rom_dir or "auto-detect", help="Where your ROMs live (blank = auto-detect)."),
            F("core_dir", "Extra core folder", "button", on_press=self.pick_core_dir,
              fmt=lambda _v: self.core_dir or "auto-detect"),
            F("clear_dirs", "Reset folders to auto-detect", "button", on_press=self.clear_dirs),
            F("retroarch_port", "Network command port", "int", s.retroarch_port, lo=1024, hi=65535),
            F("boot_timeout", "Boot timeout (seconds)", "int", int(s.boot_timeout), lo=5, hi=180, step=5),
            F("close_delay", "Close delay after a result (s)", "int", int(s.close_delay), lo=0, hi=30),
            F("assign_ports", "Map player controllers to ports", "bool", s.assign_ports,
              help="Player 1's pad drives port 1, player 2's pad port 2, ..."),
            F("simultaneous_play", "Single-player challenges", "bool", s.simultaneous_play,
              fmt=lambda v: "Race (all at once)" if v else "Take turns",
              help="Race: one RetroArch window per player, first to finish ends it for everyone."),
            F("race_mute_others", "Race: only player 1's window has sound", "bool", s.race_mute_others),
            F("race_place_windows", "Float match windows into place (Hyprland/Sway)", "bool",
              s.race_place_windows),
            F("stage_layout", "Match layout", "bool", s.stage_layout,
              fmt=lambda v: "Games on top, scoreboard below" if v else "Game fills the screen",
              help="Hyprland/Sway: game windows share the top, Gauntlet shows live scores in a strip below."),
            F("stage_hud_percent", "Scoreboard height (% of screen)", "int", s.stage_hud_percent,
              lo=10, hi=50, step=5),
            F("start_countdown", "Countdown before the clock starts (s)", "int", s.start_countdown, lo=0, hi=10,
              help="The game waits paused on its first frame while 3-2-1 counts down (0 = off)."),
            F("match_border", "Player-colour window border (px)", "int", s.match_border, lo=0, hi=30, step=2,
              help="Hyprland: frame each player's game window in their colour (0 = off)."),
            F("race_input_driver", "Race: RetroArch input driver", "choice", s.race_input_driver,
              options=["", "udev", "x", "sdl2"], labels=["Auto", "udev", "x", "sdl2"],
              help="udev lets every window read the keyboard without focus (needs the 'input' group)."),
            F("save", "Save & back", "button", on_press=self.close),
        ]
        super().__init__(app, fields)
        self.index = 1

    def pick_rom_dir(self):
        def done(path):
            self.rom_dir = path
        self.push(FileBrowser(self.app, self.rom_dir or "~", done, pick_dir=True, title="ROM folder"))

    def pick_core_dir(self):
        def done(path):
            self.core_dir = path
        self.push(FileBrowser(self.app, self.core_dir or "~", done, pick_dir=True, title="Core folder"))

    def clear_dirs(self):
        self.rom_dir = self.core_dir = ""
        self.toast("Folders will be auto-detected")

    def changed(self, field):
        if field.key == "volume":
            self.app.audio.set_volume(field.value / 100)
            self.sound("tick")

    def apply(self):
        s, a = self.settings, self.app
        v = self.values()
        old_display = (s.fullscreen, s.tv_mode, s.width, s.height)
        old_launch = (s.preferred_install, s.rom_dir, s.core_dir)
        for key in ("starting_points", "win_points", "loss_points", "draw_points", "catchup_step",
                    "catchup_max", "streak_bonus", "streak_max", "max_items", "wagers", "fullscreen",
                    "tv_mode", "sound", "split_keyboard", "preferred_install", "retroarch_port",
                    "assign_ports", "simultaneous_play", "race_mute_others", "race_input_driver",
                    "race_place_windows", "stage_layout", "stage_hud_percent",
                    "match_border", "start_countdown"):
            setattr(s, key, v[key])
        s.width, s.height = (int(n) for n in v["resolution"].split("x"))
        s.volume = v["volume"] / 100
        s.boot_timeout = float(v["boot_timeout"])
        s.close_delay = float(v["close_delay"])
        s.rom_dir, s.core_dir = self.rom_dir, self.core_dir
        errors = s.validate()
        if errors:
            a.alert("\n".join(errors), "Invalid settings")
            return False
        a.save_settings()
        a.input.split_keyboard = s.split_keyboard
        if (s.fullscreen, s.tv_mode, s.width, s.height) != old_display:
            a.apply_display()
        if a.audio.enabled != (s.sound and a.audio_allowed):
            from .audio import Audio
            a.audio = Audio(s.sound and a.audio_allowed, s.volume)
        if (s.preferred_install, s.rom_dir, s.core_dir) != old_launch and isinstance(a.launcher, Launcher):
            a.launcher = Launcher(s)
        a.clear_health()
        return True

    def close(self):
        if self.apply():
            self.toast("Settings saved")
            self.pop()

    def on_action(self, event):
        if event.action is Action.BACK:
            self.sound("back")
            self.close()
            return
        super().on_action(event)


class InputRemap(BaseScreen):
    title = "Remap menu controls"
    subtitle = "Gauntlet menus only - in-game buttons are set in RetroArch"
    ACTIONS = [Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT, Action.CONFIRM, Action.BACK,
               Action.START, Action.ALT, Action.SELECT, Action.PREV, Action.NEXT]
    WAIT = 6.0

    def __init__(self, app):
        super().__init__(app)
        self.index = 0
        self.waiting = None
        self.wait_left = 0.0

    @property
    def capture_raw(self):
        return self.waiting is not None

    def capture(self, ev):
        s, action = self.settings, self.waiting
        if ev.type == pygame.KEYDOWN:
            name = pygame.key.name(ev.key)
            if name == "escape":
                self.waiting = None
                self.sound("back")
                return
            s.key_bindings = dict(s.key_bindings, **{name: action.value})
            self.toast(f"{name} -> {action.value}")
        elif ev.type == pygame.JOYBUTTONDOWN:
            s.button_bindings = dict(s.button_bindings, **{str(ev.button): action.value})
            self.toast(f"Button {ev.button} -> {action.value}")
        else:
            return
        self.waiting = None
        im.apply_bindings(s.key_bindings, s.button_bindings)
        self.app.save_settings()
        self.sound("confirm")

    def reset(self):
        self.settings.key_bindings, self.settings.button_bindings = {}, {}
        im.apply_bindings({}, {})
        self.app.save_settings()
        self.toast("Controls reset to defaults")

    def hints(self):
        return [(Action.CONFIRM, "Rebind"), (Action.BACK, "Back")]

    def on_action(self, event):
        n = len(self.ACTIONS) + 1
        if event.action is Action.UP:
            self.index = (self.index - 1) % n
            self.sound("move")
        elif event.action is Action.DOWN:
            self.index = (self.index + 1) % n
            self.sound("move")
        elif event.action is Action.CONFIRM:
            self.activate(self.index)
        else:
            super().on_action(event)

    def activate(self, index):
        self.index = index
        if index < len(self.ACTIONS):
            self.waiting = self.ACTIONS[index]
            self.wait_left = self.WAIT
            self.sound("confirm")
        else:
            self.app.confirm("Reset all menu controls to defaults?", self.reset)

    def update(self, dt):
        super().update(dt)
        if self.waiting is not None:
            self.wait_left -= dt
            if self.wait_left <= 0:
                self.waiting = None

    @staticmethod
    def bound(action):
        keys = [k for k, a in im.KEY_BINDINGS.items() if a is action]
        buttons = [str(b) for b, a in sorted(im.BUTTON_BINDINGS.items()) if a is action]
        return ", ".join(keys), ", ".join(buttons)

    def draw_body(self, p):
        x, y, w = p.margin + 20, 96, DESIGN_W - 2 * p.margin - 40
        p.text("Action", x + 16, y, 18, self.app.theme.text_dim)
        p.text("Keys", x + 260, y, 18, self.app.theme.text_dim)
        p.text("Pad buttons", x + 760, y, 18, self.app.theme.text_dim)
        y += 28
        for i in range(len(self.ACTIONS) + 1):
            focused = i == self.index
            p.panel(x, y, w, 38, focused, color=(60, 60, 82) if focused else None)
            if i < len(self.ACTIONS):
                action = self.ACTIONS[i]
                keys, buttons = self.bound(action)
                p.text(action.value.title(), x + 16, y + 7, 22)
                if self.waiting is action:
                    p.text(f"Press a key or pad button... ({int(self.wait_left) + 1})  Esc = cancel",
                           x + 260, y + 7, 22, self.app.theme.accent)
                else:
                    p.text(keys, x + 260, y + 7, 20, self.app.theme.text_dim, width=480)
                    p.text(buttons, x + 760, y + 7, 20, self.app.theme.text_dim, width=w - 780)
            else:
                p.text("Reset to defaults", x + 16, y + 7, 22, self.app.theme.accent)
            p.hit(lambda i=i: self.activate(i), x, y, w, 38)
            y += 43


# ------------------------------------------------------------------------------------ stats
class StatsScreen(BaseScreen):
    title = "Stats & Achievements"
    TABS = ("Leaderboard", "Achievements", "History")
    VISIBLE = 13

    def __init__(self, app):
        super().__init__(app)
        self.tab = 0
        self.scroll = 0

    def hints(self):
        return [(Action.LEFT, "Tab"), (Action.UP, "Scroll"), (Action.SELECT, "Reset stats"),
                (Action.BACK, "Back")]

    def rows(self):
        data = self.app.stats.data
        if self.tab == 0:
            return self.app.stats.leaderboard()
        if self.tab == 1:
            return list(ACHIEVEMENTS.items())
        return list(reversed(data.get("history", [])))

    def set_tab(self, t):
        self.tab = t % len(self.TABS)
        self.scroll = 0
        self.sound("move")

    def on_action(self, event):
        a = event.action
        if a in (Action.LEFT, Action.PREV):
            self.set_tab(self.tab - 1)
        elif a in (Action.RIGHT, Action.NEXT):
            self.set_tab(self.tab + 1)
        elif a in (Action.UP, Action.DOWN):
            limit = max(0, len(self.rows()) - self.VISIBLE)
            self.scroll = max(0, min(limit, self.scroll + (1 if a is Action.DOWN else -1)))
        elif a is Action.SELECT:
            self.app.confirm("Erase all stats, achievements and history?", self.reset_stats)
        else:
            super().on_action(event)

    def reset_stats(self):
        st = self.app.stats
        st.data = {"players": {}, "games": {}, "history": [], "achievements": {}}
        try:
            st.save()
        except OSError:
            pass
        self.toast("Stats erased")

    def draw_body(self, p):
        th = self.app.theme
        x = p.margin + 20
        cx = x
        for i, name in enumerate(self.TABS):
            w = p.measure(name, 22, True) + 40
            p.panel(cx, 92, w, 40, i == self.tab, color=(70, 70, 100) if i == self.tab else None)
            p.text(name, cx + w / 2, 100, 22, th.accent if i == self.tab else th.text, "center", bold=True)
            p.hit(lambda i=i: self.set_tab(i), cx, 92, w, 40)
            cx += w + 12
        rows = self.rows()
        y = 150
        if not rows:
            p.text("Nothing here yet - play a session!", x, y + 20, 24, th.text_dim)
            return
        visible = rows[self.scroll:self.scroll + self.VISIBLE]
        if self.tab == 0:
            cols = [("Player", 0), ("Sessions won", 300), ("Wins", 470), ("Losses", 560), ("Draws", 660),
                    ("Win %", 760), ("Best streak", 860), ("Points", 1010)]
            for label, off in cols:
                p.text(label, x + off, y, 18, th.text_dim)
            y += 30
            for rank, r in enumerate(visible, self.scroll + 1):
                p.panel(x - 8, y - 4, DESIGN_W - 2 * x + 16, 34, rank == 1, alpha=180)
                vals = [f"{rank}. {r['name']}", r.get("sessions_won", 0), r.get("wins", 0), r.get("losses", 0),
                        r.get("draws", 0), f"{r['win_rate'] * 100:.0f}%", r.get("best_streak", 0),
                        r.get("points_earned", 0)]
                for (label, off), v in zip(cols, vals):
                    p.text(str(v), x + off, y + 2, 22, th.accent if rank == 1 else th.text, width=280)
                y += 38
        elif self.tab == 1:
            holders = {}
            for name, achs in self.app.stats.data.get("achievements", {}).items():
                for ach in achs:
                    holders.setdefault(ach, []).append(name)
            for ach, (title, desc) in visible:
                who = holders.get(ach, [])
                p.panel(x - 8, y - 4, DESIGN_W - 2 * x + 16, 38, bool(who), alpha=180)
                p.text(title, x + 4, y + 3, 22, th.accent if who else th.text_dim, bold=True, width=230)
                p.text(desc, x + 250, y + 5, 19, th.text if who else th.text_dim, width=520)
                p.text(", ".join(who) or "locked", x + 790, y + 5, 19, th.good if who else th.text_dim,
                       width=DESIGN_W - 2 * x - 800)
                y += 44
        else:
            for h in visible:
                when = time.strftime("%b %d %H:%M", time.localtime(h.get("time", 0)))
                result = "Draw" if h.get("draw") else "Winner: " + ", ".join(h.get("winners", []))
                p.text(when, x, y, 19, th.text_dim, width=150)
                p.text(h.get("game", "?"), x + 160, y, 20, width=360)
                p.text(str(h.get("round", "")), x + 530, y, 19, th.text_dim, width=150)
                p.text(result, x + 690, y, 20, th.accent, width=280)
                p.text(h.get("reason", ""), x + 980, y, 17, th.text_dim, width=DESIGN_W - x - 1000)
                y += 36
        if len(rows) > self.scroll + self.VISIBLE:
            p.text("▼ more", DESIGN_W / 2, y + 4, 18, th.text_dim, "center")


# ------------------------------------------------------------------------------------ games manager
class GamesManager(MenuScreen):
    title = "Manage Games"
    width = 600

    @property
    def subtitle(self):
        return f"{len(self.app.games)} game(s) in {self.settings.data_path}"

    def rows(self):
        a = self.app
        rows = []
        for g in a.games:
            meta = g["meta"]
            errors = a.health(g)
            label = meta["name"] + ("   [!]" if errors else "")
            sysname = SYSTEMS[meta["system"]].name if meta.get("system") in SYSTEMS else meta.get("system", "?")
            desc = (f"{sysname} - core {meta.get('core')}\nROM: {meta.get('rom')}\n"
                    f"{len(g.get('challenges', []))} challenge(s), {len(g.get('shop', []))} shop item(s)\n\n")
            desc += ("Problems:\n- " + "\n- ".join(errors)) if errors else "Ready to play."
            rows.append((label, lambda g=g: self.game_menu(g), True, desc))
        for fn, errs in sorted(a.problems.items()):
            rows.append((f"[broken] {fn}", lambda fn=fn, errs=errs: self.problem_menu(fn, errs), True,
                         "This file was skipped:\n- " + "\n- ".join(errs[:8])))
        rows += [
            ("+ Add a game", lambda: self.push(WizardScreen(a)), True, "Start the Add Game wizard."),
            ("Import pack (.zip)...", self.import_pack, True,
             "Import games, cover art and RetroArch configs shared by someone else."),
            ("Export all games", lambda: self.export(a.games, "all_games"), bool(a.games),
             "Write every game into one zip pack."),
            ("Re-check health", self.recheck, True, "Look for RetroArch, cores and ROMs again."),
        ]
        return rows

    def recheck(self):
        self.app.reload_games()
        self.refresh()
        self.toast("Health re-checked")

    def game_menu(self, g):
        name = g["meta"]["name"]

        def chosen(c):
            a = self.app
            if c == "Edit":
                self.push(WizardScreen(a, game=g))
            elif c == "Duplicate":
                fn, errors = duplicate_game(g, self.settings.data_path)
                self.toast(f"Created {fn}" if fn else "Duplicate failed: " + "; ".join(errors[:2]))
                self.recheck()
            elif c == "Delete":
                def delete():
                    delete_game(g, self.settings.data_path)
                    self.toast(f"Deleted {name}")
                    self.recheck()
                a.confirm(f"Delete {name}? This removes {g['_file']}.", delete, yes="Delete", no="Keep")
            elif c == "Export pack":
                self.export([g], slugify(name))
            elif c == "Memory Lab":
                self.push(MemoryLab(a, g))
        self.app.choose(name, ["Edit", "Duplicate", "Delete", "Export pack", "Memory Lab", "Cancel"],
                        chosen, title="Game")

    def problem_menu(self, fn, errs):
        def chosen(c):
            if c == "Delete file":
                try:
                    os.remove(os.path.join(self.settings.data_path, fn))
                    self.toast(f"Deleted {fn}")
                except OSError as e:
                    self.toast(f"Could not delete: {e}")
                self.recheck()
        self.app.choose("\n".join(errs[:5]), ["Keep", "Delete file"], chosen, title=fn)

    def export(self, games, name):
        st = self.settings
        out = os.path.join(st.sub_state("exports"), f"{name}.zip")
        try:
            export_pack(games, out, st.assets_path, st.config_path, search_dirs(st))
        except OSError as e:
            self.app.alert(f"Export failed: {e}")
            return
        self.app.alert(f"Saved {len(games)} game(s) to\n{out}", "Exported")

    def import_pack(self):
        def picked(path):
            st = self.settings
            try:
                names, errors = import_pack(path, st.data_path, st.assets_path, st.config_path,
                                            st.start_states_path)
            except (OSError, ValueError) as e:
                self.app.alert(f"Could not import: {e}")
                return
            msg = f"Imported {len(names)} game(s): " + ", ".join(names) if names else "No games imported."
            if errors:
                msg += "\n" + "\n".join(errors[:4])
            self.recheck()
            self.app.alert(msg, "Import")
        start = os.path.expanduser("~/Downloads")
        self.push(FileBrowser(self.app, start, picked, exts=(".zip",), title="Import pack"))


# ------------------------------------------------------------------------------------ wizard
STEPS = ["System", "Core", "ROM", "Details", "Challenges", "Shop", "Review"]


def title_from_rom(rom):
    base = os.path.splitext(os.path.basename(rom or ""))[0]
    clean = base.split("(")[0].split("[")[0].strip()
    return clean or base


class WizardScreen(FormScreen):
    """Add/edit a game without touching JSON: system -> core -> ROM -> details -> challenges -> shop."""

    def __init__(self, app, game=None):
        super().__init__(app)
        self.editing = game is not None
        if game is not None:
            self.game = copy.deepcopy(strip_private(game))
            self.game["schema_version"] = 2
            self.filename = game.get("_file")
            self.step = len(STEPS) - 1
        else:
            self.game = {"schema_version": 2,
                         "meta": {"name": "", "system": "snes", "core": "", "rom": "", "players": 2,
                                  "description": ""},
                         "memory": {"layout": "linear", "endian": "little"}, "challenges": [], "shop": []}
            self.filename = None
            self.step = 0
        self.preset_choice = ""
        self.build()

    @property
    def meta(self):
        return self.game["meta"]

    @property
    def title(self):
        return ("Edit: " + self.meta["name"]) if self.editing else "Add Game"

    @property
    def subtitle(self):
        return f"Step {self.step + 1}/{len(STEPS)}: {STEPS[self.step]}   " + " > ".join(
            s if i != self.step else f"[{s}]" for i, s in enumerate(STEPS))

    def hints(self):
        return [(Action.CONFIRM, "Edit"), (Action.LEFT, "Change"), (Action.START, "Next"),
                (Action.BACK, "Back")]

    # -- step construction -----------------------------------------------------------------
    def build(self, keep_key=None):
        F = Field
        m = self.meta
        system = SYSTEMS.get(m.get("system"))
        fields = []
        if self.step == 0:
            ids = list(SYSTEMS)
            fields = [
                F("system", "System", "choice", m.get("system") or "snes", options=ids,
                  labels=[SYSTEMS[i].name for i in ids], help="Which console is the game for?"),
                F("browse", "Or pick a ROM file directly...", "button", on_press=self.browse_rom,
                  help="Choose a ROM file; the system is guessed from its folder and extension."),
            ]
        elif self.step == 1:
            installed = cores_for_system(m["system"], self.app.launcher.core_dirs)
            names = [c for c, _p in installed]
            missing = [c for c in system.cores if c not in names] if system else []
            options = names + missing + ([m["core"]] if m.get("core") and m["core"] not in names + missing else [])
            labels = names + [f"{c} (not installed)" for c in missing] + options[len(names) + len(missing):]
            value = m.get("core") if m.get("core") in options else (options[0] if options else "")
            help_text = (f"Found {len(names)} installed core(s)." if names else
                         "No installed core found for this system. Install one in RetroArch "
                         "(Online Updater > Core Downloader), or pick one anyway.")
            fields = [F("core", "Emulator core", "choice", value, options=options, labels=labels, help=help_text)]
        elif self.step == 2:
            roms = self.scan()
            current = m.get("rom") or ""
            options = [r for r in roms]
            labels = [os.path.basename(r) for r in roms]
            resolved = self.resolve_rom(current) if current else None
            value = resolved if resolved in options else current
            if current and value not in options:
                options.append(current)
                labels.append(os.path.basename(current))
            if not value and options:
                value = options[0]
            fields = [
                F("rom", "ROM", "choice", value, options=options, labels=labels,
                  help=f"{len(roms)} ROM(s) found in: " + (", ".join(self.app.launcher.rom_dirs) or "no ROM folders")
                  if roms else "No ROMs found for this system - use Browse."),
                F("browse", "Browse for a ROM file...", "button", on_press=self.browse_rom),
            ]
        elif self.step == 3:
            presets = match_presets(m["system"], m.get("rom") or m.get("name"))
            fields = [
                F("name", "Name", "text", m.get("name") or title_from_rom(m.get("rom")), max_len=40),
                F("players", "Max players", "int", min(m.get("players", 2), system.max_players if system else 4),
                  lo=1, hi=system.max_players if system else 4,
                  help="How many players the game supports at once (versus/co-op)."),
                F("description", "Description", "text", m.get("description", ""), max_len=80),
                F("image", "Cover art", "button", on_press=self.pick_image,
                  fmt=lambda _v: m.get("image") or "generated", help="PNG/JPG copied into the assets folder. "
                  "You can also grab a screenshot in the Memory Lab."),
            ]
            if presets and not self.editing:
                fields.append(F("preset", "Use preset", "choice", presets[0]["id"],
                                options=[""] + [p["id"] for p in presets],
                                labels=["No (build my own)"] + [p.get("title", p["id"]) + (
                                    "" if p.get("verified") else " (unverified)") for p in presets],
                                help="A preset fills in verified RAM addresses, challenges and shop items."))
        elif self.step == 4:
            fields.append(F("i", "Challenges (at least one)", "info"))
            for i, ch in enumerate(self.game["challenges"]):
                fields.append(F(f"ch{i}", ch.get("name", "?"), "button", on_press=lambda i=i: self.challenge_menu(i),
                                fmt=lambda _v, ch=ch: MODE_LABELS.get(ch.get("mode"), ch.get("mode", "")),
                                help=ch.get("description", "")))
            fields.append(F("add", "+ Add challenge from a template...", "button", on_press=self.add_challenge,
                            help="Templates: first-to-N, last standing, high score, time trial, survival, co-op."))
        elif self.step == 5:
            fields.append(F("i", "Shop items (optional)", "info"))
            for i, item in enumerate(self.game["shop"]):
                fields.append(F(f"it{i}", item.get("name", "?"), "button", on_press=lambda i=i: self.item_menu(i),
                                fmt=lambda _v, it=item: f"{it.get('cost')} pts - {it.get('category')} - "
                                                        f"{it.get('target')}",
                                help=item.get("description", "")))
            fields += [
                F("add_generic", "+ Add a generic item...", "button", on_press=self.add_generic,
                  help="Works with any game: fast-forward, slow motion, freeze frame, mute, taunts."),
                F("add_custom", "+ Create a custom RAM item...", "button",
                  on_press=lambda: self.push(ItemEditor(self.app, self, None))),
            ]
        else:
            errors = validate_game(self.game)
            sysname = system.name if system else m.get("system")
            fields = [
                F("i1", f"{m.get('name') or '(no name)'} - {sysname} - {m.get('core')}", "info"),
                F("i2", f"ROM: {m.get('rom')}", "info"),
                F("i3", f"{len(self.game['challenges'])} challenge(s), {len(self.game['shop'])} shop item(s)",
                  "info"),
            ]
            if errors:
                fields.append(F("ie", "Problems: " + "; ".join(errors[:3]), "info"))
            fields += [
                F("save", "Save game", "button", on_press=self.save, enabled=not errors),
                F("lab", "Test in Memory Lab...", "button",
                  on_press=lambda: self.push(MemoryLab(self.app, self.game))),
                F("goto0", "Change system / core / ROM", "button", on_press=lambda: self.goto(0)),
                F("goto3", "Change name / players / art", "button", on_press=lambda: self.goto(3)),
                F("goto4", "Edit challenges", "button", on_press=lambda: self.goto(4)),
                F("goto5", "Edit shop", "button", on_press=lambda: self.goto(5)),
            ]
        if self.step < len(STEPS) - 1:
            fields.append(F("next", "Next  >", "button", on_press=self.next))
        self.fields = fields
        self.index, self.top = 0, 0
        target = keep_key
        for i, f in enumerate(self.fields):
            if (target and f.key == target) or (not target and f.kind != "info"):
                self.index = i
                break
        if self.index >= self.visible:
            self.top = self.index - self.visible + 1

    def scan(self):
        found = []
        for d in self.app.launcher.rom_dirs:
            found += [r for r in scan_roms(d, self.meta["system"]) if r not in found]
        return found

    def resolve_rom(self, rom):
        from ..detect import find_rom
        return find_rom(rom, self.meta["system"], self.app.launcher.rom_dirs, self.settings.data_path)

    def portable_rom(self, path):
        """Store ROMs found in a ROM folder by bare filename (portable); others by absolute path."""
        base = os.path.basename(path)
        if self.resolve_rom(base) == path:
            return base
        for d in self.app.launcher.rom_dirs:
            if path.startswith(d.rstrip(os.sep) + os.sep):
                return os.path.relpath(path, d)
        return path

    # -- navigation --------------------------------------------------------------------------
    def commit(self):
        """Copy the current step's field values into the draft game."""
        m = self.meta
        v = self.values()
        if self.step == 0 and "system" in v and v["system"] != m.get("system"):
            m["system"] = v["system"]
            sysm = SYSTEMS[v["system"]]
            self.game["memory"] = {"layout": sysm.layout, "endian": sysm.endian}
            m["core"] = ""
            m["players"] = min(m.get("players", 2), sysm.max_players)
        elif self.step == 1 and "core" in v:
            m["core"] = v["core"]
        elif self.step == 2 and v.get("rom"):
            m["rom"] = self.portable_rom(v["rom"]) if os.path.isabs(v["rom"]) else v["rom"]
        elif self.step == 3:
            m["name"] = (v.get("name") or "").strip()
            m["players"] = v.get("players", 2)
            m["description"] = v.get("description") or ""
            self.preset_choice = v.get("preset", "")

    def check_step(self):
        m = self.meta
        if self.step == 1 and not m.get("core"):
            return "Choose an emulator core."
        if self.step == 2 and not m.get("rom"):
            return "Choose a ROM."
        if self.step == 3 and not m.get("name"):
            return "Give the game a name."
        if self.step == 4 and not self.game["challenges"]:
            return "Add at least one challenge."
        return None

    def next(self):
        self.commit()
        problem = self.check_step()
        if problem:
            self.sound("error")
            self.toast(problem)
            return
        if self.step == 3 and self.preset_choice:
            self.apply_preset(self.preset_choice)
        self.step = min(len(STEPS) - 1, self.step + 1)
        self.build()

    def goto(self, step):
        self.commit()
        self.step = step
        self.build()

    def apply_preset(self, preset_id):
        preset = next((p for p in match_presets(self.meta["system"], self.meta.get("rom") or "")
                       if p["id"] == preset_id), None)
        if not preset:
            return
        m = self.meta
        game = game_from_preset(preset, core=m.get("core"), rom=m.get("rom"), name=m.get("name"),
                                image=m.get("image"))
        game["meta"]["players"] = min(game["meta"].get("players", m.get("players", 2)), m.get("players", 2)) \
            if m.get("players") else game["meta"].get("players", 2)
        if m.get("description"):
            game["meta"]["description"] = m["description"]
        self.game = game
        self.toast(f"Preset applied: {len(game['challenges'])} challenge(s), {len(game.get('shop', []))} item(s)")
        self.game.setdefault("shop", [])

    def on_action(self, event):
        a = event.action
        if a is Action.START:
            if self.step < len(STEPS) - 1:
                self.sound("confirm")
                self.next()
            elif self.field("save").enabled:
                self.save()
            return
        if a is Action.BACK:
            self.sound("back")
            if self.step > 0 and not (self.editing and self.step == len(STEPS) - 1):
                self.commit()
                self.step -= 1
                self.build()
            else:
                self.app.confirm("Leave without saving?", self.pop, yes="Leave", no="Stay")
            return
        super().on_action(event)

    def on_resume(self):
        key = self.focused.key if self.focused else None
        self.build(keep_key=key)

    # -- actions -------------------------------------------------------------------------------
    def browse_rom(self):
        system = SYSTEMS.get(self.meta.get("system"))
        exts = sorted({e for s in SYSTEMS.values() for e in s.extensions}) if self.step == 0 else \
            (system.extensions if system else None)
        dirs = self.app.launcher.rom_dirs
        start = dirs[0] if dirs else "~"
        if dirs and system:
            for folder in system.rom_folders:
                if os.path.isdir(os.path.join(dirs[0], folder)):
                    start = os.path.join(dirs[0], folder)
                    break

        def picked(path):
            guessed = guess_system(path)
            if guessed and guessed != self.meta.get("system"):
                self.meta["system"] = guessed
                sysm = SYSTEMS[guessed]
                self.game["memory"] = {"layout": sysm.layout, "endian": sysm.endian}
                self.meta["core"] = ""
            self.meta["rom"] = self.portable_rom(path)
            if not self.meta.get("name"):
                self.meta["name"] = title_from_rom(path)
            if not self.meta.get("core"):
                cores = cores_for_system(self.meta["system"], self.app.launcher.core_dirs)
                if cores:
                    self.meta["core"] = cores[0][0]
            self.step = 1 if self.step == 0 else self.step
            self.build()
        self.push(FileBrowser(self.app, start, picked, exts=exts, title="Choose a ROM"))

    def pick_image(self):
        def picked(path):
            assets = self.settings.assets_path
            os.makedirs(assets, exist_ok=True)
            name = slugify(self.meta.get("name") or "game") + os.path.splitext(path)[1].lower()
            try:
                if os.path.abspath(path) != os.path.abspath(os.path.join(assets, name)):
                    shutil.copyfile(path, os.path.join(assets, name))
            except OSError as e:
                self.toast(f"Could not copy image: {e}")
                return
            self.meta["image"] = name
            self.toast("Cover art set")
        self.push(FileBrowser(self.app, "~/Pictures", picked, exts=IMAGE_EXTS, title="Cover art"))

    def challenge_menu(self, i):
        ch = self.game["challenges"][i]

        def chosen(c):
            if c == "Edit":
                self.push(ChallengeEditor(self.app, self, ch, i))
            elif c == "Delete":
                self.game["challenges"].pop(i)
                self.build()
            elif c == "Move up" and i > 0:
                lst = self.game["challenges"]
                lst[i - 1], lst[i] = lst[i], lst[i - 1]
                self.build()
        self.app.choose(ch.get("name", ""), ["Edit", "Move up", "Delete", "Cancel"], chosen, title="Challenge")

    def add_challenge(self):
        labels = [label for _tid, label, _d in TEMPLATES]

        def chosen(c):
            if c is None:
                return
            tid = next(t for t, label, _d in TEMPLATES if label == c)
            ch = template(tid)
            ch.setdefault("name", c.split(" (")[0])
            ch.setdefault("id", tid)
            if ch["mode"] != "manual":
                ch.setdefault("metric", {"address": "0x0", "size": 1})
            self.push(ChallengeEditor(self.app, self, ch, None))
        self.app.choose("Pick a template - you can tweak everything next.", labels, chosen, title="New challenge")

    def set_challenge(self, index, ch):
        others = [c.get("id") for j, c in enumerate(self.game["challenges"]) if j != index]
        base = slugify(ch.get("id") or ch.get("name") or "challenge")
        cid, n = base, 2
        while cid in others:
            cid, n = f"{base}_{n}", n + 1
        ch["id"] = cid
        if index is None:
            self.game["challenges"].append(ch)
        else:
            self.game["challenges"][index] = ch

    def item_menu(self, i):
        item = self.game["shop"][i]

        def chosen(c):
            if c == "Edit":
                self.push(ItemEditor(self.app, self, item, i))
            elif c == "Delete":
                self.game["shop"].pop(i)
                self.build()
        self.app.choose(item.get("name", ""), ["Edit", "Delete", "Cancel"], chosen, title="Shop item")

    def add_generic(self):
        have = {it.get("id") for it in self.game["shop"]}
        items = [it for it in generic_items() if it["id"] not in have]
        if not items:
            self.toast("All generic items already added")
            return

        def chosen(c):
            if c == "All of them":
                self.game["shop"] += copy.deepcopy(items)
            else:
                it = next((it for it in items if it["name"] == c), None)
                if it:
                    self.game["shop"].append(copy.deepcopy(it))
            self.build(keep_key="add_generic")
        self.app.choose("Add which item?", [it["name"] for it in items] + ["All of them", "Cancel"], chosen,
                        title="Generic items")

    def set_item(self, index, item):
        others = [it.get("id") for j, it in enumerate(self.game["shop"]) if j != index]
        base = slugify(item.get("id") or item.get("name") or "item")
        iid, n = base, 2
        while iid in others:
            iid, n = f"{base}_{n}", n + 1
        item["id"] = iid
        if index is None:
            self.game["shop"].append(item)
        else:
            self.game["shop"][index] = item

    def save(self):
        self.commit()
        fn, errors = save_game(self.game, self.settings.data_path, self.filename)
        if errors:
            self.app.alert("\n".join(errors[:6]), "Cannot save")
            return
        self.app.reload_games()
        self.sound("win")
        self.toast(f"Saved {self.meta['name']} ({fn})")
        self.pop()


class _SubEditor(FormScreen):
    """Shared plumbing for the challenge / shop-item editors (rebuild on structural changes)."""
    structural = ()

    def changed(self, field):
        if field.key in self.structural:
            self.collect()
            self.rebuild(field.key)

    def rebuild(self, keep):
        self.fields = self.make_fields()
        self.index = next((i for i, f in enumerate(self.fields) if f.key == keep), 0)
        self.top = max(0, self.index - self.visible + 1) if self.index >= self.visible else 0

    def on_resume(self):
        self.collect()
        self.rebuild(self.focused.key if self.focused else None)

    def hints(self):
        return [(Action.CONFIRM, "Edit"), (Action.LEFT, "Change"), (Action.START, "Done"),
                (Action.BACK, "Cancel")]

    def on_action(self, event):
        if event.action is Action.START:
            self.done()
            return
        if event.action is Action.BACK:
            self.sound("back")
            self.app.confirm("Discard changes?", self.pop, yes="Discard", no="Keep editing")
            return
        super().on_action(event)


class ChallengeEditor(_SubEditor):
    structural = ("mode", "win_type", "use_ready")

    def __init__(self, app, wizard, challenge, index=None):
        super().__init__(app)
        self.wizard = wizard
        self.slot = index
        self.ch = copy.deepcopy(challenge)
        self.title = "Edit challenge" if index is not None else "New challenge"
        self.fields = self.make_fields()
        self.index = 0

    @property
    def subtitle(self):
        return self.wizard.meta.get("name", "")

    def make_fields(self):
        F = Field
        ch = self.ch
        mode = ch.get("mode", "manual")
        metric = ch.get("metric") or {}
        win = ch.get("win") or {}
        ready = ch.get("ready")
        fields = [
            F("name", "Name", "text", ch.get("name", ""), max_len=32),
            F("description", "Description", "text", ch.get("description", ""), max_len=80),
            F("mode", "Mode", "choice", mode, options=list(MODE_LABELS), labels=list(MODE_LABELS.values()),
              help="Versus: everyone plays at once in one game. Single-player: a 1-player game; everyone races "
                   "in their own window (or takes turns when controllers are shared). "
                   "Co-op: team goal. Manual: no RAM watching, players report the result."),
        ]
        if mode != "manual":
            fields += [
                F("h1", "What to watch (a RAM value)", "info"),
                F("address", "Address", "text", address_text(metric.get("address")), max_len=60,
                  help="Hex address from the Memory Lab, e.g. 0x0E00. Different address per player? "
                       "Separate them with '-' (P1-P2-...), e.g. 0x2EFC-0x30AA."),
                F("stride", "Per-player stride", "text", metric.get("stride", ""), max_len=10,
                  help="Optional: player N reads address + stride x (N-1). Leave blank if not needed."),
                F("size", "Size (bytes)", "choice", metric.get("size", 1), options=[1, 2, 4]),
                F("signed", "Signed", "bool", bool(metric.get("signed"))),
                F("endian", "Byte order", "choice", metric.get("endian", ""), options=["", "little", "big"],
                  labels=["system default", "little", "big"]),
                F("pick", "Find it in the Memory Lab...", "button", on_press=self.open_lab),
                F("test", "Test read (running game)", "button", on_press=self.test_read,
                  help="Reads the value from a RetroArch that is already running (e.g. from the Memory Lab)."),
                F("h2", "How to win", "info"),
                F("win_type", "Win when", "choice", win.get("type", "reach"),
                  options=list(WIN_LABELS), labels=list(WIN_LABELS.values())),
            ]
            wt = win.get("type", "reach")
            if wt in ("reach", "equals", "eliminate"):
                fields.append(F("win_value", "Target value", "int", int(win.get("value", 0)), lo=-99999, hi=99999,
                                help="Reach: value >= target. Eliminate: a player is out at <= target."))
            if wt == "bit_set":
                fields.append(F("bit", "Bit (0-7)", "int", int(metric.get("bit", 0)), lo=0, hi=31))
            if wt in ("compare", "reach"):
                fields.append(F("order", "Better is", "choice", win.get("order", "high"), options=["high", "low"],
                                labels=["higher", "lower"]))
        tl = ch.get("time_limit")
        fields += [
            F("h3", "Rules", "info"),
            F("time_limit", "Time limit", "int", int(tl or 0), lo=0, hi=3600, step=10,
              fmt=lambda v: f"{v // 60}:{v % 60:02d}" if v else "none"),
            F("on_timeout", "At time-out", "choice", ch.get("on_timeout", "compare"),
              options=["compare", "draw", "lose"], labels=["best value wins", "draw", "everyone loses"]),
            F("best_of", "Best of", "choice", ch.get("best_of", 1), options=[1, 3, 5, 7]),
            F("min_time", "Ignore results in first (s)", "int", int(ch.get("min_time", 2)), lo=0, hi=120,
              help="Avoid false wins while the game boots or RAM is garbage."),
        ]
        if mode != "manual":
            fields.append(F("use_ready", "Wait for a 'ready' value", "bool", bool(ready),
                            help="Only start refereeing once a RAM value matches (e.g. a level id)."))
            if ready:
                fields += [
                    F("ready_address", "Ready address", "text", address_text(ready.get("address")), max_len=20),
                    F("ready_size", "Ready size", "choice", ready.get("size", 1), options=[1, 2, 4]),
                    F("ready_op", "Ready when value", "choice", ready.get("op", "eq"),
                      options=["eq", "ne", "ge", "gt", "le", "lt"], labels=["=", "!=", ">=", ">", "<=", "<"]),
                    F("ready_value", "Ready value", "int", int(ready.get("value", 0)), lo=-99999, hi=99999),
                ]
        fields += [
            F("h4", "Start", "info"),
            F("start_state", "Start state", "button", on_press=self.start_state_menu,
              fmt=lambda _v: self.state_label(),
              help="Load a RetroArch save state when the match starts (e.g. character select with every "
                   "player joined), so nobody sits through intros. Every turn/round restarts from it."),
            F("done", "Done", "button", on_press=self.done),
        ]
        return fields

    def state_label(self):
        name = self.ch.get("start_state")
        if not name:
            return "none - boot normally"
        path, _name = find_start_state(self.settings, self.ch)
        return name if path else f"{name} (missing!)"

    def start_state_menu(self):
        self.collect()
        options = ["Capture from the game...", "Use a .state file..."]
        if self.ch.get("start_state"):
            options.append("Clear (boot normally)")
        options.append("Cancel")
        name = self.ch.get("start_state") or state_filename(self.wizard.game, self.ch)

        def set_state(new):
            self.ch["start_state"] = new
            self.rebuild("start_state")
            self.toast(f"Start state: {new}")

        def picked(path):
            try:
                save_capture(path, self.settings, name)
            except OSError as e:
                self.app.alert(f"Could not copy the state: {e}")
                return
            set_state(name)

        def chosen(c):
            if c == options[0]:
                self.push(StateCapture(self.app, self.wizard.game, name, set_state))
            elif c == options[1]:
                start = next((d for d in ("~/retrodeck/states", "~/.config/retroarch/states")
                              if os.path.isdir(os.path.expanduser(d))), self.settings.sub_state("states"))
                self.push(FileBrowser(self.app, start, picked, exts=STATE_EXTS,
                                      title="Choose a RetroArch save state"))
            elif c and c.startswith("Clear"):
                self.ch.pop("start_state", None)
                self.rebuild("start_state")
        self.app.choose("Start matches from a save state instead of booting the game.", options, chosen,
                        title="Start state")

    def collect(self):
        """Fields -> self.ch (keeps unknown keys such as per-player maps)."""
        v = self.values()
        ch = self.ch
        ch["name"] = (v.get("name") or "").strip()
        ch["description"] = v.get("description") or ""
        ch["mode"] = v.get("mode", ch.get("mode"))
        tl = v.get("time_limit", 0)
        ch["time_limit"] = tl or None
        ch["on_timeout"] = v.get("on_timeout", "compare")
        ch["best_of"] = v.get("best_of", 1)
        ch["min_time"] = v.get("min_time", 2)
        if ch["mode"] == "manual":
            for k in ("metric", "win", "ready"):
                ch.pop(k, None)
            return
        metric = ch.setdefault("metric", {"address": "0x0"})
        if "address" in v:
            parsed = parse_address(v["address"])
            metric["address"] = parsed if parsed is not None else v["address"]
            stride = (v.get("stride") or "").strip()
            if stride:
                metric["stride"] = stride
            else:
                metric.pop("stride", None)
            metric["size"] = v["size"]
            if v["signed"]:
                metric["signed"] = True
            else:
                metric.pop("signed", None)
            if v["endian"]:
                metric["endian"] = v["endian"]
            else:
                metric.pop("endian", None)
        win = ch.setdefault("win", {"type": "reach"})
        if "win_type" in v:
            win["type"] = v["win_type"]
        if "win_value" in v:
            win["value"] = v["win_value"]
        if "order" in v:
            win["order"] = v["order"]
        if "bit" in v:
            metric["bit"] = v["bit"]
        elif win.get("type") != "bit_set":
            metric.pop("bit", None)
        if win["type"] in ("reach", "equals", "eliminate"):
            win.setdefault("value", 0 if win["type"] == "eliminate" else 1)
        if "use_ready" in v:
            if not v["use_ready"]:
                ch.pop("ready", None)
            else:
                ready = ch.setdefault("ready", {"address": "0x0", "size": 1, "op": "eq", "value": 0})
                if "ready_address" in v:
                    parsed = parse_address(v["ready_address"])
                    ready["address"] = parsed if isinstance(parsed, str) else v["ready_address"]
                    ready["size"] = v["ready_size"]
                    ready["op"] = v["ready_op"]
                    ready["value"] = v["ready_value"]

    def open_lab(self):
        self.collect()

        def picked(spec):
            metric = self.ch.setdefault("metric", {})
            metric.update(spec)
            metric.pop("stride", None)
            self.toast(f"Address {spec['address']} selected")
        self.push(MemoryLab(self.app, self.wizard.game, on_pick=picked))

    def test_read(self):
        self.collect()
        client, mem, defaults = live_memory(self.app, self.wizard.game)
        try:
            ports = range(1, min(4, self.wizard.meta.get("players", 2)) + 1)
            values = []
            for port in ports:
                try:
                    values.append((port, read_metric(mem, self.ch["metric"], port, defaults)))
                except KeyError:
                    break
            if not values or all(v is None for _p, v in values):
                self.app.alert("No answer from RetroArch. Start the game first (Memory Lab), "
                               "and make sure the address is inside the core's memory map.", "Test read")
            else:
                self.app.alert("\n".join(f"Player {p}: {v}" for p, v in values), "Current value")
        except (ValueError, TypeError) as e:
            self.app.alert(f"Invalid address: {e}")
        finally:
            client.close()

    def done(self):
        self.collect()
        test = copy.deepcopy(self.wizard.game)
        test["challenges"] = [self.ch]
        test["meta"] = dict(test["meta"], name=test["meta"].get("name") or "x", core=test["meta"].get("core") or "x",
                            rom=test["meta"].get("rom") or "x")
        test["shop"] = []
        errors = [e.replace("challenges[0].", "").replace("challenges[0]: ", "") for e in validate_game(test)
                  if e.startswith("challenges[0]")]
        if not self.ch.get("name"):
            errors.insert(0, "give the challenge a name")
        if errors:
            self.sound("error")
            self.app.alert("\n".join(errors[:6]), "Fix these first")
            return
        self.wizard.set_challenge(self.slot, self.ch)
        self.sound("confirm")
        self.pop()


class ItemEditor(_SubEditor):
    structural = ("type",)

    def __init__(self, app, wizard, item, index=None):
        super().__init__(app)
        self.wizard = wizard
        self.slot = index
        self.item = copy.deepcopy(item) if item else {
            "name": "", "cost": 2, "category": "buff", "target": "self", "limit": 1, "description": "",
            "actions": [{"type": "memory_write", "address": "0x0", "size": 1, "op": "set", "value": 0}]}
        self.title = "Edit shop item" if item else "New shop item"
        self.fields = self.make_fields()
        self.index = 0

    @property
    def action(self):
        return self.item["actions"][0]

    def make_fields(self):
        F = Field
        it, a = self.item, self.action
        t = a.get("type", "memory_write")
        fields = [
            F("name", "Name", "text", it.get("name", ""), max_len=28),
            F("description", "Description", "text", it.get("description", ""), max_len=80),
            F("cost", "Cost (points)", "int", it.get("cost", 2), lo=0, hi=99),
            F("category", "Category", "choice", it.get("category", "buff"), options=["buff", "debuff", "chaos"]),
            F("target", "Affects", "choice", it.get("target", "self"), options=["self", "opponent", "others", "all"],
              labels=["the buyer", "one opponent (buyer picks)", "all opponents", "everyone"]),
            F("limit", "Max per player per match", "int", it.get("limit", 1), lo=1, hi=9),
            F("h1", "Effect" + (f"  (first of {len(it['actions'])} actions)" if len(it["actions"]) > 1 else ""),
              "info"),
        ]
        if t == "retroarch_config":
            fields.append(F("cfg", f"RetroArch config: {a.get('config_file') or 'inline settings'}", "info"))
        else:
            fields.append(F("type", "Type", "choice", t, options=["memory_write", "retroarch_command", "message"],
                            labels=["write to RAM", "RetroArch command", "on-screen message"]))
        if t == "memory_write":
            fields += [
                F("address", "Address", "text", address_text(a.get("address")), max_len=60,
                  help="Hex address. Different per player? Separate with '-', e.g. 0x0D7D-0x0DBD."),
                F("stride", "Per-player stride", "text", a.get("stride", ""), max_len=10),
                F("size", "Size (bytes)", "choice", a.get("size", 1), options=[1, 2, 4]),
                F("signed", "Signed", "bool", bool(a.get("signed"))),
                F("op", "Operation", "choice", a.get("op", "set"), options=["set", "add", "sub", "or", "and", "xor"]),
                F("value", "Value", "int", int(a.get("value", 0)), lo=-99999, hi=99999),
                F("freeze", "Keep re-applying (freeze)", "bool", bool(a.get("repeat")),
                  help="Writes the value again every half second while the effect lasts."),
            ]
        elif t == "retroarch_command":
            cmds = sorted(c for c in COMMANDS if c != "QUIT")
            fields.append(F("command", "Command", "choice", a.get("command", "FAST_FORWARD"), options=cmds))
        elif t == "message":
            fields.append(F("text", "Message", "text", a.get("text", ""), max_len=60,
                            help="{buyer} and {target} are replaced by player names."))
        fields += [
            F("delay", "Start after (s)", "int", int(a.get("delay", 0) or 0), lo=0, hi=600),
            F("duration", "Lasts (s)", "int", int(a.get("duration", 0) or 0), lo=0, hi=600,
              fmt=lambda v: f"{v}s" if v else "permanent / instant"),
        ]
        if t == "memory_write":
            fields.append(F("test", "Test write now (running game)", "button", on_press=self.test_write,
                            help="Applies the effect once to player 1 in an already running RetroArch."))
        fields.append(F("done", "Done", "button", on_press=self.done))
        return fields

    def collect(self):
        v = self.values()
        it, a = self.item, self.action
        it["name"] = (v.get("name") or "").strip()
        it["description"] = v.get("description") or ""
        for k in ("cost", "category", "target", "limit"):
            it[k] = v[k]
        if "type" in v and v["type"] != a.get("type"):
            new = {"type": v["type"]}
            if v["type"] == "memory_write":
                new.update(address="0x0", size=1, op="set", value=0)
            elif v["type"] == "retroarch_command":
                new["command"] = "FAST_FORWARD"
            else:
                new["text"] = "{buyer} strikes!"
            it["actions"][0] = a = new
            return
        if a.get("type") == "memory_write" and "address" in v:
            parsed = parse_address(v["address"])
            a["address"] = parsed if parsed is not None else v["address"]
            stride = (v.get("stride") or "").strip()
            if stride:
                a["stride"] = stride
            else:
                a.pop("stride", None)
            a["size"], a["op"], a["value"] = v["size"], v["op"], v["value"]
            if v["signed"]:
                a["signed"] = True
            else:
                a.pop("signed", None)
            if v["freeze"]:
                a["repeat"] = a.get("repeat") or 0.5
            else:
                a.pop("repeat", None)
        if "command" in v:
            a["command"] = v["command"]
        if "text" in v:
            a["text"] = v["text"] or ""
        for k in ("delay", "duration"):
            if k in v:
                if v[k]:
                    a[k] = v[k]
                else:
                    a.pop(k, None)

    def test_write(self):
        self.collect()
        client, mem, defaults = live_memory(self.app, self.wizard.game)
        action = {k: v for k, v in self.action.items() if k not in ("delay", "duration", "repeat", "when")}
        ctx = EffectContext(client, mem, defaults)
        try:
            if not client.is_ready():
                self.app.alert("RetroArch is not running. Start the game in the Memory Lab first.", "Test write")
                return
            effect = Effect(action, port=1, label=self.item.get("name") or "test")
            effect.tick(0.0, ctx)
            if ctx.errors or effect.failed:
                self.app.alert("The write failed: " + "; ".join(ctx.errors), "Test write")
            else:
                self.toast("Written - check the game!")
        except (KeyError, ValueError, TypeError) as e:
            self.app.alert(f"Invalid effect: {e}")
        finally:
            client.close()

    def done(self):
        self.collect()
        if not self.item.get("name"):
            self.app.alert("Give the item a name.")
            return
        test = copy.deepcopy(self.wizard.game)
        item = dict(copy.deepcopy(self.item), id=self.item.get("id") or "x")
        test["shop"] = [item]
        test["challenges"] = test.get("challenges") or [{"id": "m", "name": "m", "mode": "manual"}]
        test["meta"] = dict(test["meta"], name=test["meta"].get("name") or "x", core=test["meta"].get("core") or "x",
                            rom=test["meta"].get("rom") or "x")
        errors = [e.replace("shop[0].", "").replace("shop[0]: ", "") for e in validate_game(test)
                  if e.startswith("shop[0]")]
        if errors:
            self.sound("error")
            self.app.alert("\n".join(errors[:6]), "Fix these first")
            return
        self.wizard.set_item(self.slot, self.item)
        self.sound("confirm")
        self.pop()


# ------------------------------------------------------------------------------------ memory lab
def stop_retroarch(process, client):
    """Ask RetroArch to quit, then terminate/kill it if it lingers."""
    if process and process.poll() is None:
        try:
            client.quit()
            process.wait(4)
        except Exception:
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(3)
            except Exception:
                process.kill()
                try:
                    process.wait(2)
                except Exception:
                    pass
    if client:
        client.close()


class MemoryLabSetup(MenuScreen):
    title = "Memory Lab"
    subtitle = "Find the RAM addresses of scores, lives and health"

    def rows(self):
        a = self.app
        rows = [("Attach to a running RetroArch", lambda: self.push(MemoryLab(a, None)), True,
                 "Use a RetroArch you started yourself (network commands must be enabled on port "
                 f"{self.settings.retroarch_port}).")]
        for g in a.games:
            errors = a.health(g)
            rows.append((g["meta"]["name"] + ("   [!]" if errors else ""),
                         (lambda g=g: self.push(MemoryLab(a, g))) if not errors else None, not errors,
                         "Launch this game and search its memory." if not errors else "\n".join(errors)))
        return rows


class MemoryLab(FormScreen):
    """Launch (or attach to) RetroArch, then search RAM by value / change and watch addresses.

    All UDP traffic happens on one worker thread; the UI only enqueues jobs and reads results."""
    label_w = 420
    visible = 11
    SHOW = 24

    def __init__(self, app, game, on_pick=None):
        super().__init__(app)
        self.game = game
        self.on_pick = on_pick
        mem = (game or {}).get("memory", {})
        self.layout = mem.get("layout", "linear")
        self.endian = mem.get("endian", "little")
        self.system = SYSTEMS.get((game or {}).get("meta", {}).get("system"))
        self.phase, self.message = "starting", "Starting..."
        self.jobs = queue.Queue()
        self.stop = threading.Event()
        self.thread = None
        self.process = None
        self.client = None
        self.memory = None
        self.search = None
        self.busy = False
        self.watches = []
        self.live = {}
        self.dirty = False
        self.refresh_in = 0.0
        ram = self.system.ram_size if self.system else 0x20000
        self.regions = list(range(0, ram, MAX_REGION)) or [0]
        self.region_len = min(ram, MAX_REGION) or 0x20000
        self.fields = self.make_fields()
        self.index = next(i for i, f in enumerate(self.fields) if f.kind != "info")

    @property
    def title(self):
        return "Memory Lab" + (f": {self.game['meta']['name']}" if self.game else "")

    @property
    def subtitle(self):
        note = self.system.ram_note if self.system else ""
        return f"{self.phase.upper()} - {self.message}" + (f"   ({note})" if note else "")

    @property
    def pads_to_game(self):
        """While RetroArch is up, gamepads play the game; only keyboard/mouse drive this screen."""
        return self.phase in ("starting", "ready")

    def hints(self):
        return [(Action.CONFIRM, "Select"), (Action.LEFT, "Change"), (Action.ALT, "Refresh"),
                (Action.BACK, "Close")]

    # -- form ----------------------------------------------------------------------------------
    def make_fields(self):
        F = Field
        prev = {f.key: f.value for f in getattr(self, "fields", [])}
        g = lambda k, d: prev.get(k, d)  # noqa: E731
        fields = [
            F("size", "Value size", "choice", g("size", 1), options=[1, 2, 4], labels=["1 byte", "2 bytes", "4 bytes"]),
            F("signed", "Signed", "bool", g("signed", False)),
            F("endian", "Byte order", "choice", g("endian", self.endian), options=["little", "big"]),
            F("region", "Search region", "choice", g("region", self.regions[0]), options=self.regions,
              labels=[f"{hex_addr(r)}-{hex_addr(min(r + MAX_REGION, r + self.region_len) - 1)}"
                      for r in self.regions]),
            F("new", "New search (snapshot memory)", "button", on_press=self.new_search,
              help="Take a snapshot, change something in the game, then filter (e.g. 'decreased')."),
            F("filter", "Filter", "choice", g("filter", "eq"), options=list(FILTERS),
              labels=[FILTER_LABELS[f] for f in FILTERS]),
            F("value", "Value", "int", g("value", 0), lo=-2 ** 31, hi=2 ** 32 - 1,
              help="Used by the equals / greater / less filters. LB/RB change by 10."),
            F("apply", "Apply filter", "button", on_press=self.apply_filter),
        ]
        if self.game:
            fields.append(F("shot", "Use current screen as cover art", "button", on_press=self.screenshot))
        if self.search and self.search.candidates is not None:
            n = len(self.search.candidates)
            fields.append(F("h1", f"Candidates: {n}" + (f" (showing {self.SHOW})" if n > self.SHOW else "")
                            + "   history: " + " > ".join(str(h) for h in self.search.history[-6:]), "info"))
            for addr, _v in self.search.results(self.SHOW):
                fields.append(F(f"r{addr}", hex_addr(addr), "button", value=addr,
                                on_press=lambda addr=addr: self.address_menu(addr),
                                fmt=lambda _v, addr=addr: self.fmt_value(addr)))
        if self.watches:
            fields.append(F("h2", "Watches", "info"))
            for i, w in enumerate(self.watches):
                fields.append(F(f"w{i}", w.label, "button", on_press=lambda w=w: self.watch_menu(w),
                                fmt=lambda _v, w=w: "?" if w.value is None else f"{w.value}  ({hex(w.value & 0xFFFFFFFF)})"))
        return fields

    def rebuild(self):
        key = self.focused.key if self.focused else None
        self.fields = self.make_fields()
        self.index = next((i for i, f in enumerate(self.fields) if f.key == key), min(self.index, len(self.fields) - 1))
        if self.index < self.top or self.index >= self.top + self.visible:
            self.top = max(0, self.index - self.visible + 1)

    def changed(self, field):
        if field.key in ("size", "signed", "endian", "region") and self.search:
            self.search = None
            self.rebuild()
            self.toast("Search settings changed - take a new snapshot")

    def fmt_value(self, addr):
        v = self.live.get(addr)
        if v is None and self.search and self.search.values is not None:
            slot = (addr - self.search.start) // self.search.size
            if 0 <= slot < len(self.search.values):
                v = self.search.values[slot]
        return "?" if v is None else f"{v}   ({hex(v & 0xFFFFFFFF)})"

    def var(self, addr):
        f = self.field
        return Var(addr, f("size").value, f("endian").value, f("signed").value)

    # -- lifecycle -----------------------------------------------------------------------------
    def on_enter(self):
        self.thread = threading.Thread(target=self._worker, daemon=True, name="memlab")
        self.thread.start()

    def on_exit(self):
        self.stop.set()
        if self.thread:
            self.thread.join(2.0)
        self._shutdown_game()

    def _shutdown_game(self):
        stop_retroarch(self.process, self.client)

    def _worker(self):
        try:
            launcher = self.app.launcher
            self.client = launcher.client()
            self.memory = Memory(self.client, self.layout)
            if self.game:
                core, rom, errors = launcher.resolve(self.game)
                if errors:
                    raise RuntimeError("; ".join(errors))
                if self.client.is_ready():
                    raise RuntimeError("another RetroArch is already running on port "
                                       f"{self.settings.retroarch_port} - close it or use Attach")
                cfg = launcher.write_config("memlab", {"video_fullscreen": False})
                self.message = "Launching RetroArch..."
                self.process = launcher.launch(core, rom, cfg)
                self.message = "Waiting for RetroArch to answer..."
                ok = self.client.wait_until_ready(self.settings.boot_timeout, 0.5, self.process, self.stop)
            else:
                self.message = "Looking for RetroArch..."
                ok = self.client.wait_until_ready(5.0, 0.5, None, self.stop)
            if self.stop.is_set():
                return
            if not ok:
                raise RuntimeError("RetroArch did not answer (is network_cmd_enable on?)")
            self.phase, self.message = "ready", "Connected. Play in the RetroArch window, search here."
            while not self.stop.is_set():
                try:
                    job = self.jobs.get(timeout=0.25)
                except queue.Empty:
                    job = self._refresh
                if self.process and self.process.poll() is not None:
                    self.phase, self.message = "closed", "RetroArch was closed"
                    return
                self.busy = True
                try:
                    job()
                finally:
                    self.busy = False
        except Exception as e:  # report on screen instead of crashing the UI thread
            log.exception("memory lab worker")
            self.phase, self.message = "error", str(e)

    def run(self, job, busy_text=None):
        if self.phase != "ready":
            self.sound("error")
            self.toast("Not connected to RetroArch yet")
            return False
        if busy_text:
            self.message = busy_text
        self.jobs.put(job)
        return True

    def _refresh(self):
        if self.refresh_in > 0:
            return
        self.refresh_in = 0.5
        if self.search and self.search.candidates is not None:
            for addr, _v in self.search.results(self.SHOW):
                self.live[addr] = self.memory.read(self.var(addr))
        for w in self.watches:
            w.value = self.memory.read(w.var)

    def update(self, dt):
        super().update(dt)
        self.refresh_in -= dt
        if self.dirty:
            self.dirty = False
            self.rebuild()

    # -- actions -------------------------------------------------------------------------------
    def _make_search(self):
        f = self.field
        return RamSearch(self.client, self.layout, f("region").value, self.region_len, f("size").value,
                         f("endian").value, f("signed").value)

    def new_search(self):
        def job():
            s = self._make_search()
            t0 = time.monotonic()
            if s.reset():
                self.search = s
                self.live = {}
                self.message = f"Snapshot of {len(s.candidates)} values ({time.monotonic() - t0:.1f}s)"
                self.dirty = True
            else:
                self.message = "Could not read memory (address outside the core's memory map?)"
        self.run(job, "Reading memory...")

    def apply_filter(self):
        if not self.search:
            self.toast("Take a snapshot first (New search)")
            return
        op, value = self.field("filter").value, self.field("value").value

        def job():
            n = self.search.filter(op, value)
            self.live = {}
            self.message = "Read failed" if n is None else f"{n} candidate(s) left after '{FILTER_LABELS[op]}'"
            self.dirty = True
        self.run(job, "Filtering...")

    def spec(self, addr):
        spec = {"address": hex_addr(addr, 1), "size": self.field("size").value}
        if self.field("signed").value:
            spec["signed"] = True
        if self.field("endian").value != self.endian:
            spec["endian"] = self.field("endian").value
        return spec

    def address_menu(self, addr):
        options = ["Watch", "Write a value...", "Cancel"]
        if self.on_pick:
            options.insert(0, "Use for the challenge")

        def chosen(c):
            if c == "Use for the challenge":
                self.on_pick(self.spec(addr))
                self.pop()
            elif c == "Watch":
                f = self.field
                self.watches.append(Watch(addr, f("size").value, f("endian").value, f("signed").value))
                self.rebuild()
            elif c == "Write a value...":
                self.write_prompt(self.var(addr))
        self.app.choose(f"{hex_addr(addr)} = {self.fmt_value(addr)}", options, chosen, title="Address")

    def watch_menu(self, w):
        options = ["Write a value...", "Remove", "Cancel"]
        if self.on_pick:
            options.insert(0, "Use for the challenge")

        def chosen(c):
            if c == "Use for the challenge":
                spec = w.to_spec()
                if w.var.endian != self.endian:
                    spec["endian"] = w.var.endian
                self.on_pick(spec)
                self.pop()
            elif c == "Remove":
                self.watches.remove(w)
                self.rebuild()
            elif c == "Write a value...":
                self.write_prompt(w.var)
        self.app.choose(f"{w.label} = {w.value}", options, chosen, title="Watch")

    def write_prompt(self, var):
        def done(text):
            if text is None:
                return
            try:
                value = int(text, 0)
            except ValueError:
                self.toast("Not a number")
                return

            def job():
                ok = self.memory.write(var, value)
                self.message = f"Wrote {value} to {hex_addr(var.address)}" if ok else "Write failed"
                self.refresh_in = 0
            self.run(job)
        self.app.text_input(f"Value for {hex_addr(var.address)}", "", done, 12)

    def screenshot(self):
        shots = self.settings.sub_state("screenshots")

        def newest(after):
            files = [f for f in glob.glob(os.path.join(shots, "**", "*.png"), recursive=True)
                     if os.path.getmtime(f) >= after]
            return max(files, key=os.path.getmtime) if files else None

        def job():
            t0 = time.time() - 1
            self.client.command("SCREENSHOT")
            for _ in range(20):
                time.sleep(0.2)
                shot = newest(t0)
                if shot:
                    break
            else:
                self.message = f"No screenshot appeared in {shots}"
                return
            time.sleep(0.3)  # let RetroArch finish writing the file
            assets = self.settings.assets_path
            os.makedirs(assets, exist_ok=True)
            name = slugify(self.game["meta"]["name"]) + ".png"
            shutil.copyfile(shot, os.path.join(assets, name))
            self.game["meta"]["image"] = name
            if self.game.get("_file"):
                save_game(self.game, self.settings.data_path, self.game["_file"])
            self.message = f"Cover art saved as {name}"
        self.run(job, "Taking screenshot...")

    def on_action(self, event):
        if event.action is Action.ALT:
            self.refresh_in = 0
            return
        super().on_action(event)

    def draw_body(self, p):
        super().draw_body(p)
        th = self.app.theme
        color = {"ready": th.good, "error": th.bad, "closed": th.bad}.get(self.phase, th.accent)
        p.circle(DESIGN_W - p.margin - 16, 76, 8, color)
        if self.busy:
            p.text("working...", DESIGN_W - p.margin - 34, 66, 18, th.accent, "right")
        if self.phase == "error":
            p.wrapped(self.message, p.margin + 20, DESIGN_H - p.margin - 130, DESIGN_W - 2 * p.margin - 40, 20,
                      th.bad, max_lines=2)


STATE_EXTS = [".state", ".auto"] + [f".state{i}" for i in range(1, 10)]


def capture_config(game, settings, folder):
    """RetroArch config for capturing: every player can join, states land (flat) in `folder`."""
    players = max(1, min(int(game["meta"].get("players") or 2), settings.player_count or 1))
    parts = [Participant(i, f"P{i}", i, keyboard="keyboard2" if i == 2 and settings.split_keyboard else None)
             for i in range(1, players + 1)]
    extra = build_config(parts, [], settings)
    extra.update({"savestate_directory": folder, "video_fullscreen": False})
    return extra


class StateCapture(BaseScreen):
    """Launch the game, let the players reach the starting point and keep the newest save state."""
    title = "Capture start state"

    def __init__(self, app, game, name, on_saved):
        super().__init__(app)
        self.game, self.name, self.on_saved = game, name, on_saved
        self.phase, self.message = "starting", "Starting..."
        self.stop = threading.Event()
        self.save_now = threading.Event()
        self.thread = None
        self.process = None
        self.client = None
        self.folder = self.settings.sub_state("capture")
        self.captured = None   # path of the newest complete state
        self.captured_at = None
        self.kept = False

    @property
    def pads_to_game(self):
        """While RetroArch is up, gamepads play the game; only keyboard/mouse drive this screen."""
        return self.phase in ("starting", "ready")

    @property
    def subtitle(self):
        return self.game["meta"].get("name", "")

    def hints(self):
        return [(Action.CONFIRM, "Save state now"), (Action.START, "Keep it"), (Action.BACK, "Cancel")]

    # -- lifecycle -----------------------------------------------------------------------------
    def on_enter(self):
        self.thread = threading.Thread(target=self._worker, daemon=True, name="capture")
        self.thread.start()

    def on_exit(self):
        self.stop.set()
        if self.thread:
            self.thread.join(2.0)
        stop_retroarch(self.process, self.client)

    def _worker(self):
        try:
            launcher = self.app.launcher
            self.client = launcher.client()
            core, rom, errors = launcher.resolve(self.game)
            if errors:
                raise RuntimeError("; ".join(errors))
            if self.client.is_ready():
                raise RuntimeError("another RetroArch is already running on port "
                                   f"{self.settings.retroarch_port} - close it first")
            clear_folder(self.folder)
            cfg = launcher.write_config("capture", capture_config(self.game, self.settings, self.folder))
            self.message = "Launching RetroArch..."
            self.process = launcher.launch(core, rom, cfg)
            self.message = "Waiting for RetroArch to answer..."
            if not self.client.wait_until_ready(self.settings.boot_timeout, 0.5, self.process, self.stop):
                if not self.stop.is_set():
                    raise RuntimeError("RetroArch did not answer (is network_cmd_enable on?)")
                return
            self.phase, self.message = "ready", "Play to the starting point, then save a state."
            last = None
            while not self.stop.is_set():
                if self.save_now.is_set():
                    self.save_now.clear()
                    self.client.command("SAVE_STATE")
                last = self._poll_state(last)
                if self.process.poll() is not None:
                    self._poll_state(last)
                    self.phase = "closed"
                    return
                self.stop.wait(0.3)
        except Exception as e:  # shown on screen
            log.exception("state capture")
            self.phase, self.message = "error", str(e)

    def _poll_state(self, last):
        """Accept a state once its size/mtime are stable across two polls (RetroArch writes async)."""
        path = newest_state(self.folder)
        try:
            now = (path, os.path.getsize(path), os.path.getmtime(path)) if path else None
        except OSError:
            return None
        if now and now == last and now[1] > 0 and (self.captured, self.captured_at) != (path, now[2]):
            self.captured, self.captured_at = path, now[2]
            self.message = "State captured at " + time.strftime("%H:%M:%S", time.localtime(now[2]))
        return now

    def update(self, dt):
        super().update(dt)
        if self.phase == "closed" and not self.kept:
            self.app.request_focus()
            if self.captured:
                self.keep()
            else:
                self.phase, self.message = "error", "RetroArch closed before a state was saved"

    def keep(self):
        if not self.captured:
            self.sound("error")
            self.toast("Save a state first")
            return
        try:
            save_capture(self.captured, self.settings, self.name)
        except OSError as e:
            self.app.alert(f"Could not save the state: {e}")
            return
        self.kept = True
        self.sound("confirm")
        self.pop()
        self.on_saved(self.name)

    def on_action(self, event):
        if event.action is Action.CONFIRM:
            if self.phase == "ready":
                self.save_now.set()
                self.message = "Saving state..."
            else:
                self.sound("error")
            return
        if event.action is Action.START:
            self.keep()
            return
        super().on_action(event)

    def draw_body(self, p):
        th = self.app.theme
        x, w = p.margin + 20, DESIGN_W - 2 * p.margin - 40
        color = {"ready": th.good, "error": th.bad, "closed": th.accent}.get(self.phase, th.accent)
        p.circle(DESIGN_W - p.margin - 16, 76, 8, color)
        steps = [
            "1. Play to where the challenge should start - e.g. character select with every player joined.",
            "2. Save a state: RetroArch Quick Menu > Save State, your save-state hotkey, "
            "or press Confirm here.",
            "3. Close RetroArch (or press Start here) to keep the newest state.",
        ]
        y = 130
        for line in steps:
            y += p.wrapped(line, x, y, w, 24, th.text) + 14
        p.text(f"Saved as: {self.name}", x, y + 10, 22, th.text_dim)
        p.wrapped(self.message, x, y + 60, w, 26, color, max_lines=3)
