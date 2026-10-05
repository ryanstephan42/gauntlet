"""Match runner: launches RetroArch, applies purchased effects and referees the match.

Runs in a background thread; the UI polls `snapshot()` and may call forfeit()/cancel()/end().
Single-player ("turns") challenges either run one turn per player or, when every player has their
own controller, as a race: one RetroArch window per player, all at once (see race_setup()).
"""
import glob
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field

from .actions import Effect, EffectContext, EffectScheduler, collect_config
from .memory import Memory, compare, is_per_player, read_metric, var_for
from .referee import RaceReferee, Referee, TurnReferee, Verdict, forfeit_verdict, rank_turns
from . import startstate, winplace

log = logging.getLogger("gauntlet.match")


class MatchError(Exception):
    pass


# RetroArch keyboard binds for the second keyboard player (split keyboard mode).
KEYBOARD2_RA = {"up": "i", "down": "k", "left": "j", "right": "l", "a": "u", "b": "o",
                "start": "p", "select": "y"}
# RetroArch hotkeys whose default key is one of the keyboard2 keys (pause = p, frame advance = k, ...)
KEYBOARD2_HOTKEYS = ("input_pause_toggle", "input_frame_advance", "input_hold_fast_forward",
                     "input_movie_record_toggle", "input_netplay_game_watch", "input_cheat_index_plus",
                     "input_cheat_toggle")
PAD_BUTTONS = ("up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "l2", "r2", "l3", "r3",
               "start", "select")
NO_PAD = 15  # joypad index for keyboard players in a race window (no pad of theirs to listen to)


@dataclass
class Participant:
    key: object            # player id in the session
    name: str
    port: int = 1          # RetroArch port (1-based) in versus/coop
    pad_index: int = None  # joystick device index, if any
    keyboard: str = None   # "keyboard" / "keyboard2" / None
    color: tuple = None    # player colour (rgb), e.g. for window borders


@dataclass
class Purchase:
    item: dict
    buyer: object
    targets: list = field(default_factory=list)


def plan_effects(game, challenge, participants, purchases, turn_player=None):
    """Build Effects. In turns mode only effects targeting `turn_player` apply (on port 1)."""
    effects = []
    names = {p.key: p.name for p in participants}
    by_key = {p.key: p for p in participants}
    turns = challenge.get("mode") == "turns"
    delay = 1.0
    for pu in purchases:
        targets = pu.targets or [pu.buyer]
        for action in pu.item.get("actions", []):
            if action.get("type") == "retroarch_config":
                continue
            if action.get("type") == "memory_write" and is_per_player(action):
                apply_to = targets
            else:
                apply_to = targets[:1]  # global effect: once
            for target in apply_to:
                if turns:
                    if target != turn_player and not (action.get("type") != "memory_write"
                                                      and turn_player in targets):
                        continue
                    port = 1
                elif target in by_key:
                    port = by_key[target].port
                else:
                    continue
                label = f"{pu.item['name']} ({names.get(pu.buyer, '?')} -> {names.get(target, '?')})"
                effects.append(Effect(action, port, label, pu.buyer, target))
        if not turns or turn_player in targets:
            tgt = ", ".join(names.get(t, "?") for t in targets)
            msg = {"type": "message", "delay": delay,
                   "text": f"{names.get(pu.buyer, '?')} used {pu.item['name']} on {tgt}"}
            effects.append(Effect(msg, 1, "announce", pu.buyer, targets[0]))
            delay += 2.5
    for action in challenge.get("setup", []) or []:
        if turns:
            effects.append(Effect(action, 1, "setup"))
        elif action.get("type") == "memory_write" and is_per_player(action):
            effects.extend(Effect(action, p.port, "setup") for p in participants)
        else:
            effects.append(Effect(action, 1, "setup"))
    return effects


def build_config(participants, purchases, settings, turn_player=None):
    extra = collect_config([a for pu in purchases for a in pu.item.get("actions", [])],
                           settings.config_path)
    extra["input_max_users"] = max(1, len(participants)) if turn_player is None else 1
    if settings.assign_ports:
        for p in participants:
            if turn_player is not None and p.key != turn_player:
                continue
            port = 1 if turn_player is not None else p.port
            if p.pad_index is not None:
                extra[f"input_player{port}_joypad_index"] = p.pad_index
            if p.keyboard == "keyboard2":
                for button, key in KEYBOARD2_RA.items():
                    extra[f"input_player{port}_{button}"] = key
    if any(p.keyboard == "keyboard2" for p in participants):
        extra.update({k: "nul" for k in KEYBOARD2_HOTKEYS})
    return extra


@dataclass
class RacePlan:
    race: bool
    input_driver: str = None  # retroarch input_driver for every window (None = leave as configured)
    note: str = ""            # why not a race, or what the players must know


def udev_keyboard_available():
    """True if RetroArch's udev input driver could read the keyboard (Linux, user in the 'input' group)."""
    if not sys.platform.startswith("linux"):
        return False
    return any(os.access(dev, os.R_OK) for dev in glob.glob("/dev/input/event*"))


def race_setup(participants, settings, udev=None):
    """Decide whether a single-player challenge runs as a race (one window per player, all at once)."""
    if not settings.simultaneous_play:
        return RacePlan(False, note="taking turns (simultaneous play is off)")
    if len(participants) < 2:
        return RacePlan(False)
    devices = [p.keyboard or (("pad", p.pad_index) if p.pad_index is not None else None) for p in participants]
    if None in devices or len(set(devices)) < len(devices):
        return RacePlan(False, note="taking turns: players share a controller")
    if settings.retroarch_port + len(participants) - 1 > 65535:
        return RacePlan(False, note="taking turns: no free network ports")
    keyboards = sum(1 for p in participants if p.keyboard)
    if settings.race_input_driver:
        return RacePlan(True, settings.race_input_driver)
    if not keyboards:
        return RacePlan(True)
    if udev is None:
        udev = udev_keyboard_available()
    if udev:
        return RacePlan(True, "udev")
    if keyboards > 1:
        return RacePlan(False, note="taking turns: two keyboard players need the udev input driver "
                                    "(add yourself to the 'input' group)")
    return RacePlan(True, note="keyboard player: keep your RetroArch window focused")


def tile_rects(n, width, height, x=0, y=0):
    """Window rectangles (x, y, w, h) tiling an area: side by side for 2, a grid for more."""
    cols = 1 if n <= 1 else 2 if n <= 4 else 3
    rows = -(-n // cols)
    w, h = width // cols, height // rows
    return [(x + (i % cols) * w, y + (i // cols) * h, w, h) for i in range(n)]


def stage_rects(n, area, hud_percent=25):
    """Stage layout: `n` game windows tiled across the top of `area`, Gauntlet's scoreboard strip below.
    -> ([game rects], scoreboard rect)"""
    x, y, w, h = area
    hud_h = max(1, round(h * hud_percent / 100))
    return tile_rects(n, w, h - hud_h, x, y), (x, y + h - hud_h, w, hud_h)


def window_config(rect):
    """retroarch.cfg overrides for a windowed RetroArch at `rect` (honoured by X11/most desktops)."""
    extra = {"video_fullscreen": False, "video_windowed_fullscreen": False}
    if rect:
        x, y, w, h = rect
        extra.update({"video_window_save_positions": True, "video_windowed_position_x": x,
                      "video_windowed_position_y": y, "video_windowed_position_width": w,
                      "video_windowed_position_height": h})
    return extra


def race_config(participants, purchases, settings, index, rect=None, input_driver=None):
    """retroarch.cfg overrides for player `index`'s own window in a race."""
    p = participants[index]
    extra = build_config(participants, purchases, settings, turn_player=p.key)
    # each window must only hear its own player: no keyboard binds for pad players, no pad for keyboards
    for button in PAD_BUTTONS:
        key = f"input_player1_{button}"
        if p.keyboard == "keyboard2":
            extra[key] = KEYBOARD2_RA.get(button, "nul")
        elif p.keyboard != "keyboard":
            extra[key] = "nul"
    if p.keyboard:
        extra["input_player1_joypad_index"] = NO_PAD
    elif p.pad_index is not None:
        extra["input_player1_joypad_index"] = p.pad_index
    extra.update(window_config(rect))
    if index and settings.race_mute_others:
        extra["audio_mute_enable"] = True
    if input_driver:
        extra["input_driver"] = input_driver
    return extra


@dataclass
class Instance:
    """One player's RetroArch window in a race."""
    player: Participant
    port: int
    process: object = None
    client: object = None
    memory: object = None
    ctx: object = None
    sched: object = None
    alive: bool = True


class MatchRunner:
    def __init__(self, launcher, game, challenge, participants, purchases=(), settings=None, race=None,
                 screen=None, placer=None):
        """`race`: a RacePlan (None = decide with race_setup()); `screen`: (w, h) for tiling race windows;
        `placer`: a winplace backend for match windows (None = detect; False = leave them to RetroArch).
        With a backend and settings.stage_layout the games share the top of the screen and Gauntlet's
        window becomes a live scoreboard strip below them (`stage`)."""
        self.launcher = launcher
        self.settings = settings or launcher.settings
        self.game = game
        self.challenge = challenge
        self.participants = list(participants)
        self.purchases = list(purchases)
        self.mode = challenge.get("mode", "manual")
        if self.mode != "turns":
            race = RacePlan(False)
        self.race = race if race is not None else race_setup(self.participants, self.settings)
        self.screen = screen or (1920, 1080)
        self.instances = []
        if placer is None:
            placer = winplace.detect() if self.settings.race_place_windows else None
        self._backend = placer or None
        self.stage = bool(self._backend) and self.settings.stage_layout
        self._placer = None
        self._rects = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._end = threading.Event()
        self._forfeit = None
        self._thread = None
        self.process = None
        self.client = None
        self.verdict = None
        self.error = None
        self.turn_results = []
        self._snap = {"phase": "idle", "message": "", "values": {}, "remaining": None,
                      "elapsed": 0.0, "turn": None, "warnings": [], "verdict": None,
                      "race": self.race.race, "players": {}, "stage": self.stage, "hud": None}

    # -- UI API -----------------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run_safe, name="match", daemon=True)
        self._thread.start()

    def snapshot(self):
        with self._lock:
            snap = dict(self._snap)
            snap["values"] = dict(snap["values"])
            snap["warnings"] = list(snap["warnings"])
            snap["players"] = {k: dict(v) for k, v in snap["players"].items()}
            return snap

    @property
    def finished(self):
        return self._snap["phase"] in ("finished", "no_verdict", "error", "cancelled")

    def forfeit(self, key):
        self._forfeit = key
        self._end.set()

    def end(self):
        """Stop the match early (no verdict unless the referee already decided)."""
        self._end.set()

    def cancel(self):
        self._cancel.set()
        self._end.set()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    # -- internals ----------------------------------------------------------------
    def _set(self, **kw):
        with self._lock:
            self._snap.update(kw)

    def _warn(self, text):
        with self._lock:
            if text not in self._snap["warnings"]:
                self._snap["warnings"].append(text)
        log.warning(text)

    def _run_safe(self):
        final = None
        try:
            final = self._run()
        except MatchError as e:
            self.error = str(e)
            final = {"phase": "error", "message": str(e)}
            log.error("Match failed: %s", e)
        except Exception as e:  # keep the UI alive on unexpected failures
            log.exception("Match crashed")
            self.error = f"unexpected error: {e}"
            final = {"phase": "error", "message": self.error}
        finally:
            # windows are closed and Gauntlet's own window restored before the UI sees the end
            self._kill()
            if final:
                self._set(**final)

    def _run(self):
        core, rom, errors = self.launcher.resolve(self.game)
        if errors:
            raise MatchError("; ".join(errors))
        self.client = self.launcher.client()
        if self.client.status() is not None:
            raise MatchError(f"another RetroArch is already answering on port "
                             f"{self.settings.retroarch_port}; close it first")
        keys = [p.key for p in self.participants]
        self._rects = self._setup_windows(len(self.participants) if self.race.race else 1)
        if self.race.race:
            self.verdict = self._run_race(core, rom)
            self.turn_results = self._race_ref.results if self._race_ref else []
            if self._forfeit is not None:
                self.verdict = forfeit_verdict(keys, self._forfeit)
        elif self.mode == "turns":
            for p in self.participants:
                if self._cancel.is_set():
                    break
                self._end.clear()
                result = self._play_once(core, rom, turn_player=p)
                if self._forfeit is not None:
                    self.verdict = forfeit_verdict(keys, self._forfeit)
                    break
                if result is not None:
                    self.turn_results.append(result)
            if self.verdict is None and len(self.turn_results) == len(self.participants):
                self.verdict = rank_turns(self.challenge, self.turn_results)
        else:
            self.verdict = self._play_once(core, rom)
            if self._forfeit is not None and (self.verdict is None or self.verdict.forfeit is None):
                self.verdict = forfeit_verdict(keys, self._forfeit)
        if self._cancel.is_set():
            return {"phase": "cancelled", "message": "Match cancelled"}
        if self.verdict is None:
            return {"phase": "no_verdict", "message": "Match ended without a result"}
        return {"phase": "finished", "message": self.verdict.reason, "verdict": self.verdict.to_dict()}

    def _play_once(self, core, rom, turn_player=None):
        tag = f"{self.game['meta']['name']}" + (f" - {turn_player.name}'s turn" if turn_player else "")
        self._set(phase="launching", message=f"Launching {tag}", turn=turn_player.key if turn_player else None,
                  values={}, remaining=None, elapsed=0.0)
        extra = build_config(self.participants, self.purchases, self.settings,
                             turn_player.key if turn_player else None)
        if self._rects:
            extra.update(window_config(self._rects[0]))
        cfg = self.launcher.write_config("match", extra)
        slot = self._stage_start_state(rom)
        try:
            self.process = self.launcher.launch(core, rom, cfg, entry_slot=slot)
        except OSError as e:
            raise MatchError(f"cannot launch RetroArch: {e}")
        if self._placer and self._rects:
            self._placer.add(self.process.pid, self._rects[0], border=self._border(turn_player))
            self._placer.start(timeout=self.settings.boot_timeout + 60)
        self._set(phase="waiting", message="Waiting for RetroArch...")
        if not self.client.wait_until_ready(self.settings.boot_timeout, interval=0.3,
                                            process=self.process, cancel=self._cancel):
            if self._cancel.is_set():
                return None
            if self.process.poll() is not None:
                raise MatchError("RetroArch exited during startup (see retroarch.log in the state folder)")
            raise MatchError("RetroArch did not respond; is network_cmd_enable allowed?")
        if self._placer and self._rects:
            self._placer.refresh()
        try:
            return self._referee_loop(turn_player)
        finally:
            self._close()
            if self._placer:
                self._placer.forget(self.process.pid)

    def _stage_start_state(self, rom, states_dir=None):
        """Copy the challenge's start state into place (fresh for every launch/turn). -> slot or None."""
        path, name = startstate.find_start_state(self.settings, self.challenge)
        if not name:
            return None
        if not path:
            self._warn(f"Start state '{name}' not found - booting the game normally")
            return None
        try:
            startstate.stage(path, states_dir or self.settings.sub_state("states"), rom)
        except OSError as e:
            self._warn(f"Could not use start state '{name}': {e}")
            return None
        log.info("Using start state %s", path)
        return startstate.ENTRY_SLOT

    def _referee_loop(self, turn_player):
        mem_cfg = self.game.get("memory", {})
        memory = Memory(self.client, mem_cfg.get("layout", "linear"))
        defaults = {"endian": mem_cfg.get("endian", "little")}
        names = {p.key: p.name for p in self.participants}
        ctx = EffectContext(self.client, memory, defaults, names)
        sched = EffectScheduler(ctx, plan_effects(self.game, self.challenge, self.participants,
                                                  self.purchases, turn_player.key if turn_player else None))
        ch = self.challenge
        active = [turn_player] if turn_player else self.participants
        if self.mode == "turns":
            ref = TurnReferee(ch, turn_player.key)
        else:
            ref = Referee(ch, [p.key for p in active])
        metric = ch.get("metric")
        ready_spec = ch.get("ready")
        start = time.monotonic()
        failed_reads = 0
        poll = self.settings.poll_interval
        self._set(phase="playing", message="Match in progress")
        while True:
            now = time.monotonic() - start
            if self._end.is_set() or self._cancel.is_set():
                break
            if self.process.poll() is not None:
                log.info("RetroArch closed by the player")
                break
            sched.tick(now)
            for err in ctx.errors:
                self._warn(err)
            ctx.errors.clear()
            if self.mode != "manual" and metric:
                ready = True
                if ready_spec:
                    rv = memory.read(var_for(ready_spec, 1, defaults))
                    ready = rv is not None and compare(ready_spec.get("op", "eq"), rv, int(ready_spec["value"]))
                values = {}
                for p in active:
                    port = 1 if turn_player else (1 if self.mode == "coop" and not is_per_player(metric) else p.port)
                    try:
                        values[p.key] = read_metric(memory, metric, port, defaults)
                    except KeyError:
                        values[p.key] = None
                if all(v is None for v in values.values()):
                    failed_reads += 1
                    if failed_reads == 10:
                        self._warn("Cannot read the referee address; check the game's challenge setup")
                else:
                    failed_reads = 0
                if self.mode == "turns":
                    result = ref.update(values.get(turn_player.key), now, ready)
                else:
                    result = ref.update(values, now, ready)
                self._set(values=values, remaining=ref.remaining(now), elapsed=ref.elapsed(now),
                          message="Match in progress" if ref.started_at is not None else "Waiting for the game to start")
                if result is not None:
                    self._announce(result, names)
                    sched.finish_all()
                    self._end.wait(self.settings.close_delay)
                    return result
            else:
                self._set(elapsed=now)
            self._end.wait(poll)
        sched.finish_all()
        if self.mode == "turns":
            return ref.stop(time.monotonic() - start, "forfeit" if self._forfeit else "closed early")
        return None

    def _border(self, participant):
        """(rgb, width) for a window that belongs to one player; None for a shared window."""
        width = self.settings.match_border
        if participant is None or not participant.color or width <= 0:
            return None
        return tuple(participant.color), width

    def _setup_windows(self, n):
        """Rectangles for `n` game windows (None = RetroArch decides). In the stage layout Gauntlet's own
        window is floated into the scoreboard strip under them."""
        if self._backend and self._placer is None:
            self._placer = winplace.Placer(self._backend)
        area = self._placer.area() if self._placer else None
        if area and self.stage:
            rects, hud = stage_rects(n, area, self.settings.stage_hud_percent)
            self._placer.add(os.getpid(), hud, own=True)
            self._placer.start(timeout=self.settings.boot_timeout + 60)
            self._set(hud=hud)
            return rects
        if self.race.race:
            return tile_rects(n, area[2], area[3], area[0], area[1]) if area else tile_rects(n, *self.screen)
        return None

    # -- race: one window per player ---------------------------------------------------
    _race_ref = None

    def _run_race(self, core, rom):
        n = len(self.participants)
        base = self.settings.retroarch_port
        self.instances = [Instance(p, base + i, client=self.launcher.client(port=base + i))
                          for i, p in enumerate(self.participants)]
        for inst in self.instances[1:]:
            if inst.client.status() is not None:
                raise MatchError(f"another RetroArch is already answering on port {inst.port}; close it first")
        if self.race.note:
            self._warn(self.race.note)
        placer = self._placer
        rects = self._rects
        self._set(phase="launching", message=f"Launching {n} windows of {self.game['meta']['name']}")
        for i, inst in enumerate(self.instances):
            folder = f"p{i + 1}"
            extra = race_config(self.participants, self.purchases, self.settings, i, rects[i],
                                self.race.input_driver)
            cfg = self.launcher.write_config(f"race_{folder}", extra, port=inst.port, folder=folder)
            slot = self._stage_start_state(rom, self.settings.sub_state("states", folder))
            try:
                inst.process = self.launcher.launch(core, rom, cfg, entry_slot=slot,
                                                    log_name=f"retroarch_{folder}.log")
            except OSError as e:
                raise MatchError(f"cannot launch RetroArch: {e}")
            if placer:
                placer.add(inst.process.pid, rects[i], border=self._border(self.participants[i]))
        if placer:
            placer.start(timeout=self.settings.boot_timeout + 60)
        self._set(phase="waiting", message="Waiting for RetroArch...")
        deadline = time.monotonic() + self.settings.boot_timeout
        for i, inst in enumerate(self.instances):
            if not inst.client.wait_until_ready(max(0.5, deadline - time.monotonic()), interval=0.3,
                                                process=inst.process, cancel=self._cancel):
                if self._cancel.is_set():
                    return None
                who = f"{inst.player.name}'s RetroArch (retroarch_p{i + 1}.log in the state folder)"
                if inst.process.poll() is not None:
                    raise MatchError(f"{who} exited during startup")
                raise MatchError(f"{who} did not respond on port {inst.port}")
        if placer:
            placer.refresh()
        try:
            return self._race_loop()
        finally:
            self._close_race()

    def _race_loop(self):
        mem_cfg = self.game.get("memory", {})
        defaults = {"endian": mem_cfg.get("endian", "little")}
        names = {p.key: p.name for p in self.participants}
        for inst in self.instances:
            inst.memory = Memory(inst.client, mem_cfg.get("layout", "linear"))
            inst.ctx = EffectContext(inst.client, inst.memory, defaults, names)
            inst.sched = EffectScheduler(inst.ctx, plan_effects(self.game, self.challenge, self.participants,
                                                                self.purchases, inst.player.key))
        ch = self.challenge
        ref = self._race_ref = RaceReferee(ch, [p.key for p in self.participants])
        metric = ch.get("metric")
        ready_spec = ch.get("ready")
        start = time.monotonic()
        failed_reads = 0
        self._set(phase="playing", message="Race in progress")
        while True:
            now = time.monotonic() - start
            if self._end.is_set() or self._cancel.is_set():
                break
            for inst in self.instances:
                if inst.alive and inst.process.poll() is not None:
                    inst.alive = False
                    log.info("%s closed their RetroArch", inst.player.name)
                    if metric:
                        ref.drop(inst.player.key, now, "quit")
            live = [i for i in self.instances if i.alive]
            if not live:
                break
            for inst in live:
                inst.sched.tick(now)
                for err in inst.ctx.errors:
                    self._warn(err)
                inst.ctx.errors.clear()
            verdict = ref.verdict
            if metric and verdict is None:
                values, ready = {}, {}
                for inst in live:
                    key = inst.player.key
                    if ready_spec:
                        rv = inst.memory.read(var_for(ready_spec, 1, defaults))
                        ready[key] = rv is not None and compare(ready_spec.get("op", "eq"), rv,
                                                                int(ready_spec["value"]))
                    try:
                        values[key] = read_metric(inst.memory, metric, 1, defaults)
                    except KeyError:
                        values[key] = None
                if all(v is None for v in values.values()):
                    failed_reads += 1
                    if failed_reads == 10:
                        self._warn("Cannot read the referee address; check the game's challenge setup")
                else:
                    failed_reads = 0
                verdict = ref.update(values, now, ready)
                self._set(values=values, remaining=ref.remaining(now), elapsed=now,
                          players=self._race_players(ref, now),
                          message="Race in progress" if ref.started else "Waiting for the game to start")
            else:
                self._set(elapsed=now, players=self._race_players(ref, now) if metric else {})
            if verdict is not None:
                text = self._verdict_text(verdict, names)
                for inst in live:
                    try:
                        inst.client.show_msg(text)
                    except OSError:
                        pass
                    inst.sched.finish_all()
                self._end.wait(self.settings.close_delay)
                return verdict
            self._end.wait(self.settings.poll_interval)
        for inst in self.instances:
            if inst.sched:
                inst.sched.finish_all()
        return ref.verdict

    @staticmethod
    def _race_players(ref, now):
        elapsed = ref.elapsed(now)
        out = {}
        for key, r in ref.refs.items():
            res = r.result
            out[key] = {"status": ref.status(key), "time": elapsed[key],
                        "reason": res.reason if res else "", "value": res.value if res else r.last_value}
        return out

    def _close_race(self):
        for inst in self.instances:
            if inst.process and inst.process.poll() is None:
                inst.client.quit()
        for inst in self.instances:
            if inst.process:
                try:
                    inst.process.wait(5)
                except Exception:
                    pass
        self._kill()

    @staticmethod
    def _verdict_text(result, names):
        if result.draw:
            return "Draw!"
        if result.winners:
            return " & ".join(names.get(k, "?") for k in result.winners) + " wins!"
        return "Defeat!"

    def _announce(self, result, names):
        if isinstance(result, Verdict):
            text = self._verdict_text(result, names)
        else:
            text = f"{names.get(result.player, '?')}: {result.reason} ({result.time:.1f}s, {result.value})"
        try:
            self.client.show_msg(text)
        except OSError:
            pass

    def _close(self):
        if self.process and self.process.poll() is None:
            self.client.quit()
            try:
                self.process.wait(5)
            except Exception:
                pass
        self._kill()

    def _kill(self):
        if self._placer:
            self._placer.stop()
        for p in [self.process] + [i.process for i in self.instances]:
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(3)
                except Exception:
                    p.kill()
                    p.wait(3)


def play_match(game, active_items, settings, launcher=None):
    """Blocking helper kept for scripts: run the first challenge with one player."""
    from .games import get_challenge
    from .retroarch import Launcher
    launcher = launcher or Launcher(settings)
    runner = MatchRunner(launcher, game, get_challenge(game), [Participant(0, "Player 1")],
                         [Purchase(item, 0, [0]) for item in active_items], settings)
    runner.start()
    runner.join()
    if runner.error:
        raise MatchError(runner.error)
    return runner.verdict
