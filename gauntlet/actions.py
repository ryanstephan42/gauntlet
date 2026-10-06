"""Shop-item / setup actions: a handler registry plus a per-match effect scheduler.

Every action may have: delay (s), duration (s), repeat (s, re-apply interval = freeze),
when (condition var + op + value). Handlers:
  memory_write      op set|add|sub|or|and|xor, value, min/max clamp, restore (after duration)
  retroarch_command command (toggle commands are sent again when duration ends)
  message           SHOW_MSG text ({buyer}/{target} placeholders)
  retroarch_config  applied at launch via the appended config (see collect_config)
"""
import logging
import os

from .memory import _runs as byte_runs, compare, var_for
from .retroarch import read_cfg

log = logging.getLogger("gauntlet.actions")

WRITE_RETRIES = 3
TOGGLE_COMMANDS = {"FAST_FORWARD", "SLOWMOTION", "MUTE", "PAUSE_TOGGLE", "SHADER_TOGGLE",
                   "GRAB_MOUSE_TOGGLE", "FULLSCREEN_TOGGLE"}


class EffectContext:
    def __init__(self, client, memory, defaults=None, names=None):
        self.client = client
        self.memory = memory
        self.defaults = defaults or {}
        self.names = names or {}
        self.errors = []

    def var(self, spec, port):
        return var_for(spec, port, self.defaults)


def _apply_op(op, current, value, action):
    result = {
        "set": value, "add": current + value, "sub": current - value,
        "or": current | value, "and": current & value, "xor": current ^ value,
    }[op]
    if "min" in action:
        result = max(int(action["min"]), result)
    if "max" in action:
        result = min(int(action["max"]), result)
    return result


def _write_with_retry(ctx, var, value):
    return any(ctx.memory.write(var, value) for _ in range(WRITE_RETRIES))


class Effect:
    """One scheduled action for one port."""

    def __init__(self, action, port=1, label="", buyer=None, target=None):
        self.action = action
        self.port = port
        self.label = label
        self.buyer, self.target = buyer, target
        self.delay = float(action.get("delay", 0) or 0)
        self.duration = action.get("duration")
        self.repeat = action.get("repeat")
        self.started_at = None
        self.last_applied = None
        self.original = None
        self.done = False
        self.failed = False

    def _ready(self, ctx):
        cond = self.action.get("when")
        if not cond:
            return True
        try:
            value = ctx.memory.read(ctx.var(cond, self.port))
        except (KeyError, ValueError):
            return False
        return value is not None and compare(cond.get("op", "eq"), value, int(cond["value"]))

    def tick(self, now, ctx):
        """`now` = seconds since match start."""
        if self.done or now < self.delay:
            return
        if self.started_at is None:
            if not self._ready(ctx):
                return
            self.started_at = now
            self._apply(ctx, first=True)
            self.last_applied = now
            if not self.duration and not self.repeat:
                self.done = True
            return
        if self.duration and now - self.started_at >= float(self.duration):
            self._finish(ctx)
            self.done = True
            return
        if self.repeat and now - self.last_applied >= float(self.repeat):
            self._apply(ctx, first=False)
            self.last_applied = now

    def _apply(self, ctx, first):
        handler = HANDLERS[self.action["type"]]
        try:
            ok = handler.apply(self, ctx, first)
        except (KeyError, ValueError) as e:
            ok = False
            log.warning("effect %s failed: %s", self.label, e)
        if not ok and first:
            self.failed = True
            ctx.errors.append(f"{self.label or self.action['type']} could not be applied")

    def _finish(self, ctx):
        handler = HANDLERS[self.action["type"]]
        try:
            handler.finish(self, ctx)
        except (KeyError, ValueError) as e:
            log.warning("effect %s finish failed: %s", self.label, e)


class Handler:
    def apply(self, effect, ctx, first):
        return True

    def finish(self, effect, ctx):
        pass


class MemoryWrite(Handler):
    def apply(self, effect, ctx, first):
        a = effect.action
        var = ctx.var(a, effect.port)
        if first and effect.duration and a.get("restore", True):
            effect.original = ctx.memory.read_raw(var)
        op = a.get("op", "set")
        if op == "set" or var.bit is not None or var.mask is not None:
            value = _apply_op("set", 0, int(a["value"]), a)
        else:
            current = ctx.memory.read(var)
            if current is None:
                return False
            value = _apply_op(op, current, int(a["value"]), a)
        return _write_with_retry(ctx, var, value)

    def finish(self, effect, ctx):
        a = effect.action
        if effect.original is not None and a.get("restore", True):
            var = ctx.var(a, effect.port)
            pairs = zip(var.host_addresses(ctx.memory.layout), effect.original)
            for start, chunk in byte_runs(pairs):
                ctx.client.write_bytes(start, chunk)


class RetroArchCommand(Handler):
    def apply(self, effect, ctx, first):
        if first:
            ctx.client.command(effect.action["command"])
        return True

    def finish(self, effect, ctx):
        cmd = effect.action["command"]
        if cmd in TOGGLE_COMMANDS:
            ctx.client.command(cmd)


class Message(Handler):
    def apply(self, effect, ctx, first):
        text = effect.action["text"].format(
            buyer=ctx.names.get(effect.buyer, "?"), target=ctx.names.get(effect.target, "?"))
        ctx.client.show_msg(text)
        return True


class LaunchOnly(Handler):
    """retroarch_config is applied at launch time; nothing to do while running."""


HANDLERS = {
    "memory_write": MemoryWrite(),
    "retroarch_command": RetroArchCommand(),
    "message": Message(),
    "retroarch_config": LaunchOnly(),
}


def register_handler(action_type, handler):
    HANDLERS[action_type] = handler


class EffectScheduler:
    def __init__(self, ctx, effects=()):
        self.ctx = ctx
        self.effects = list(effects)

    def add(self, effect):
        self.effects.append(effect)

    def tick(self, now):
        for e in self.effects:
            if not e.done:
                e.tick(now, self.ctx)

    def finish_all(self):
        """End-of-match: restore timed effects that are still active."""
        for e in self.effects:
            if not e.done and e.started_at is not None and e.duration:
                e._finish(self.ctx)
            e.done = True

    @property
    def failures(self):
        return [e for e in self.effects if e.failed]


def collect_config(actions, config_dir):
    """Merge retroarch_config actions into one {key: value} dict for --appendconfig."""
    merged = {}
    for a in actions:
        if a.get("type") != "retroarch_config":
            continue
        if a.get("config_file"):
            path = os.path.join(config_dir, a["config_file"])
            try:
                merged.update(read_cfg(path))
            except OSError as e:
                log.warning("cannot read RetroArch config %s: %s", path, e)
        merged.update(a.get("settings") or {})
    return merged
