"""Match runner: launches RetroArch, applies purchased effects and referees the match.

Runs in a background thread; the UI polls `snapshot()` and may call forfeit()/cancel()/end().
"""
import logging
import threading
import time
from dataclasses import dataclass, field

from .actions import Effect, EffectContext, EffectScheduler, collect_config
from .memory import Memory, compare, is_per_player, var_for
from .referee import Referee, TurnReferee, Verdict, forfeit_verdict, rank_turns

log = logging.getLogger("gauntlet.match")


class MatchError(Exception):
    pass


# RetroArch keyboard binds for the second keyboard player (split keyboard mode).
KEYBOARD2_RA = {"up": "i", "down": "k", "left": "j", "right": "l", "a": "u", "b": "o",
                "start": "p", "select": "y"}


@dataclass
class Participant:
    key: object            # player id in the session
    name: str
    port: int = 1          # RetroArch port (1-based) in versus/coop
    pad_index: int = None  # joystick device index, if any
    keyboard: str = None   # "keyboard" / "keyboard2" / None


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
    return extra


class MatchRunner:
    def __init__(self, launcher, game, challenge, participants, purchases=(), settings=None):
        self.launcher = launcher
        self.settings = settings or launcher.settings
        self.game = game
        self.challenge = challenge
        self.participants = list(participants)
        self.purchases = list(purchases)
        self.mode = challenge.get("mode", "manual")
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
                      "elapsed": 0.0, "turn": None, "warnings": [], "verdict": None}

    # -- UI API -----------------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run_safe, name="match", daemon=True)
        self._thread.start()

    def snapshot(self):
        with self._lock:
            snap = dict(self._snap)
            snap["values"] = dict(snap["values"])
            snap["warnings"] = list(snap["warnings"])
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
        try:
            self._run()
        except MatchError as e:
            self.error = str(e)
            self._set(phase="error", message=str(e))
            log.error("Match failed: %s", e)
        except Exception as e:  # keep the UI alive on unexpected failures
            log.exception("Match crashed")
            self.error = f"unexpected error: {e}"
            self._set(phase="error", message=self.error)
        finally:
            self._kill()

    def _run(self):
        core, rom, errors = self.launcher.resolve(self.game)
        if errors:
            raise MatchError("; ".join(errors))
        self.client = self.launcher.client()
        if self.client.status() is not None:
            raise MatchError(f"another RetroArch is already answering on port "
                             f"{self.settings.retroarch_port}; close it first")
        keys = [p.key for p in self.participants]
        if self.mode == "turns":
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
            self._set(phase="cancelled", message="Match cancelled")
        elif self.verdict is None:
            self._set(phase="no_verdict", message="Match ended without a result")
        else:
            self._set(phase="finished", message=self.verdict.reason, verdict=self.verdict.to_dict())

    def _play_once(self, core, rom, turn_player=None):
        tag = f"{self.game['meta']['name']}" + (f" - {turn_player.name}'s turn" if turn_player else "")
        self._set(phase="launching", message=f"Launching {tag}", turn=turn_player.key if turn_player else None,
                  values={}, remaining=None, elapsed=0.0)
        extra = build_config(self.participants, self.purchases, self.settings,
                             turn_player.key if turn_player else None)
        cfg = self.launcher.write_config("match", extra)
        try:
            self.process = self.launcher.launch(core, rom, cfg)
        except OSError as e:
            raise MatchError(f"cannot launch RetroArch: {e}")
        self._set(phase="waiting", message="Waiting for RetroArch...")
        if not self.client.wait_until_ready(self.settings.boot_timeout, interval=0.3,
                                            process=self.process, cancel=self._cancel):
            if self._cancel.is_set():
                return None
            if self.process.poll() is not None:
                raise MatchError("RetroArch exited during startup (see retroarch.log in the state folder)")
            raise MatchError("RetroArch did not respond; is network_cmd_enable allowed?")
        try:
            return self._referee_loop(turn_player)
        finally:
            self._close()

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
                        values[p.key] = memory.read(var_for(metric, port, defaults))
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

    def _announce(self, result, names):
        if isinstance(result, Verdict):
            if result.draw:
                text = "Draw!"
            elif result.winners:
                text = " & ".join(names.get(k, "?") for k in result.winners) + " wins!"
            else:
                text = "Defeat!"
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
        p = self.process
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(3)
            except Exception:
                p.kill()


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
