"""Referee: decides matches from polled RAM values (pure logic, no I/O).

Modes
  versus  all players at once; `values` maps player -> metric value
  coop    everyone together against one metric; all win or all lose
  turns   one player at a time (TurnReferee), results ranked by rank_turns()
  manual  no automatic verdict (players report the result)
Win types: reach (>= value), equals, bit_set (metric.bit is 1),
           eliminate (player is out when value <= win.value), compare (best at time limit).
"""
from dataclasses import dataclass, field


@dataclass
class Verdict:
    winners: list
    losers: list
    draw: bool = False
    reason: str = ""
    scores: dict = field(default_factory=dict)
    times: dict = field(default_factory=dict)
    manual: bool = False
    forfeit: object = None

    def to_dict(self):
        return {"winners": list(self.winners), "losers": list(self.losers), "draw": self.draw,
                "reason": self.reason, "scores": dict(self.scores), "times": dict(self.times),
                "manual": self.manual, "forfeit": self.forfeit}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def hit(win, value):
    """Does a single value satisfy the (non-compare) win condition?"""
    t = win["type"]
    if value is None:
        return False
    if t == "reach":
        return value >= win["value"]
    if t == "equals":
        return value == win["value"]
    if t == "bit_set":
        return value == 1
    if t == "eliminate":
        return value <= win.get("value", 0)
    return False


def _best(values, order):
    present = {k: v for k, v in values.items() if v is not None}
    if not present:
        return []
    best = max(present.values()) if order == "high" else min(present.values())
    return [k for k, v in present.items() if v == best]


def manual_verdict(players, winners, reason="decided by players"):
    winners = list(winners)
    return Verdict(winners, [p for p in players if p not in winners], draw=len(winners) != 1,
                   reason=reason, manual=True)


def forfeit_verdict(players, quitter):
    others = [p for p in players if p != quitter]
    return Verdict(others, [quitter], draw=len(others) > 1, reason="forfeit", forfeit=quitter)


class Referee:
    """Live referee for versus/coop. Feed update(values, now, ready) every poll."""

    def __init__(self, challenge, players, confirm=2):
        self.ch = challenge
        self.mode = challenge.get("mode", "versus")
        self.win = challenge.get("win") or {}
        self.players = list(players)
        self.confirm = max(1, confirm)
        self.time_limit = challenge.get("time_limit")
        self.min_time = float(challenge.get("min_time", 0) or 0)
        self.started_at = None
        self.streak = {}
        self.eliminated = []
        self.last_values = {}
        self.verdict = None

    def elapsed(self, now):
        return 0.0 if self.started_at is None else now - self.started_at

    def remaining(self, now):
        if not self.time_limit or self.started_at is None:
            return None
        return max(0.0, self.time_limit - self.elapsed(now))

    def _confirmed(self, key, cond):
        self.streak[key] = self.streak.get(key, 0) + 1 if cond else 0
        return self.streak[key] >= self.confirm

    def update(self, values, now, ready=True):
        if self.verdict or self.mode == "manual":
            return self.verdict
        if self.started_at is None:
            if not ready:
                return None
            self.started_at = now
        self.last_values = dict(values)
        t = self.elapsed(now)
        if t >= self.min_time:
            self.verdict = self._coop(values) if self.mode == "coop" else self._versus(values)
        if self.verdict is None and self.time_limit and t >= self.time_limit:
            self.verdict = self.on_timeout(values)
        return self.verdict

    def _versus(self, values):
        wt = self.win.get("type")
        if wt == "compare":
            return None
        if wt == "eliminate":
            for p in self.players:
                if p not in self.eliminated and self._confirmed(p, hit(self.win, values.get(p))):
                    self.eliminated.append(p)
            alive = [p for p in self.players if p not in self.eliminated]
            if len(alive) == 1:
                return Verdict(alive, self.eliminated[:], reason="last one standing",
                               scores=dict(values))
            if not alive:
                return Verdict([], self.players[:], draw=True, reason="everyone was eliminated",
                               scores=dict(values))
            return None
        reached = [p for p in self.players if self._confirmed(p, hit(self.win, values.get(p)))]
        if not reached:
            return None
        reason = f"reached {self.win.get('value')}" if wt == "reach" else "goal met"
        return Verdict(reached, [p for p in self.players if p not in reached],
                       draw=len(reached) > 1, reason=reason, scores=dict(values))

    def _coop(self, values):
        value = next(iter(values.values()), None)
        wt = self.win.get("type")
        if wt == "compare":
            return None
        if self._confirmed("coop", hit(self.win, value)):
            if wt == "eliminate":
                return Verdict([], self.players[:], reason="the team was defeated", scores=dict(values))
            return Verdict(self.players[:], [], reason="team goal reached", scores=dict(values))
        return None

    def on_timeout(self, values):
        policy = self.ch.get("on_timeout", "compare")
        if self.mode == "coop":
            if policy == "draw":
                return Verdict(self.players[:], [], draw=True, reason="time up", scores=dict(values))
            if self.win.get("type") == "eliminate":  # survived until the end
                return Verdict(self.players[:], [], reason="survived", scores=dict(values))
            return Verdict([], self.players[:], reason="time up", scores=dict(values))
        if policy == "draw":
            return Verdict(self.players[:], [], draw=True, reason="time up", scores=dict(values))
        pool = {p: v for p, v in values.items() if p not in self.eliminated}
        best = _best(pool, self.win.get("order", "high"))
        if not best:
            return Verdict(self.players[:], [], draw=True, reason="time up", scores=dict(values))
        return Verdict(best, [p for p in self.players if p not in best], draw=len(best) > 1,
                       reason="time up: best score", scores=dict(values))


@dataclass
class TurnResult:
    player: object
    success: bool
    time: float
    value: object
    reason: str = ""


class TurnReferee:
    """One player's turn of a 'turns' challenge."""

    def __init__(self, challenge, player, confirm=2):
        self.ch = challenge
        self.win = challenge.get("win") or {}
        self.player = player
        self.confirm = max(1, confirm)
        self.time_limit = challenge.get("time_limit")
        self.min_time = float(challenge.get("min_time", 0) or 0)
        self.started_at = None
        self.streak = 0
        self.last_value = None
        self.result = None

    def elapsed(self, now):
        return 0.0 if self.started_at is None else now - self.started_at

    def remaining(self, now):
        if not self.time_limit or self.started_at is None:
            return None
        return max(0.0, self.time_limit - self.elapsed(now))

    def update(self, value, now, ready=True):
        if self.result:
            return self.result
        if self.started_at is None:
            if not ready:
                return None
            self.started_at = now
        self.last_value = value
        t = self.elapsed(now)
        wt = self.win.get("type")
        if t >= self.min_time and wt != "compare":
            self.streak = self.streak + 1 if hit(self.win, value) else 0
            if self.streak >= self.confirm:
                success = wt != "eliminate"
                self.result = TurnResult(self.player, success, round(t, 2), value,
                                         "goal reached" if success else "eliminated")
                return self.result
        if self.time_limit and t >= self.time_limit:
            success = wt in ("compare", "eliminate")
            self.result = TurnResult(self.player, success, float(self.time_limit), value, "time up")
        return self.result

    def stop(self, now, reason="ended early"):
        """Turn ended without a result (emulator closed): record what we have."""
        if not self.result:
            self.result = TurnResult(self.player, False, round(self.elapsed(now), 2), self.last_value, reason)
        return self.result


def rank_turns(challenge, results):
    """Turn results -> Verdict."""
    win = challenge.get("win") or {}
    wt = win.get("type")
    players = [r.player for r in results]
    scores = {r.player: r.value for r in results}
    times = {r.player: r.time for r in results}
    order = win.get("order", "high")
    if wt == "compare":
        best = _best(scores, order)
        reason = "highest score" if order == "high" else "lowest score"
    elif wt == "eliminate":
        best = _best(times, "high")
        reason = "survived the longest"
    else:
        done = {r.player: r.time for r in results if r.success}
        if done:
            best = _best(done, "low")
            reason = "fastest to the goal"
        else:
            best = _best(scores, order)
            reason = "nobody finished: best score"
    if not best:
        return Verdict(players, [], draw=True, reason="no results", scores=scores, times=times)
    return Verdict(best, [p for p in players if p not in best], draw=len(best) > 1,
                   reason=reason, scores=scores, times=times)
