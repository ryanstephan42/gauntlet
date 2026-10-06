"""Referee: decides matches from polled RAM values (pure logic, no I/O).

Modes
  versus  all players at once; `values` maps player -> metric value
  coop    everyone together against one metric; all win or all lose
  turns   single-player challenge: one player at a time (TurnReferee), results ranked by rank_turns(),
          or everyone at once in their own emulator (RaceReferee: first to finish ends it for all)
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


class RaceReferee:
    """Single-player challenge played by everyone at once, one emulator each.

    Each player has their own TurnReferee (own ready gate and clock). The race ends as soon as it is
    decided: someone reaches the goal, or only one player is left in a survival race.
    Otherwise it ends when every player has a result and is ranked like turns.
    """

    def __init__(self, challenge, players, confirm=2):
        self.ch = challenge
        self.win = challenge.get("win") or {}
        self.players = list(players)
        self.refs = {p: TurnReferee(challenge, p, confirm) for p in self.players}
        self.verdict = None

    @property
    def results(self):
        return [self.refs[p].result for p in self.players if self.refs[p].result]

    @property
    def started(self):
        return any(r.started_at is not None for r in self.refs.values())

    def status(self, player):
        ref = self.refs[player]
        r = ref.result
        if r is None:
            return "racing" if ref.started_at is not None else "waiting"
        if r.reason == "goal reached":
            return "finished"
        return "out" if not r.success else "done"

    def remaining(self, now):
        rem = [r.remaining(now) for r in self.refs.values() if r.result is None]
        rem = [x for x in rem if x is not None]
        return max(rem) if rem else None

    def elapsed(self, now):
        return {p: r.result.time if r.result else round(r.elapsed(now), 2) for p, r in self.refs.items()}

    def drop(self, player, now, reason="quit"):
        """A player's emulator closed (or they gave up): they are out with what they had."""
        if self.verdict is None and player in self.refs:
            self.refs[player].stop(now, reason)
            self.verdict = self._decide()
        return self.verdict

    def update(self, values, now, ready=None):
        if self.verdict:
            return self.verdict
        ready = ready or {}
        for p in self.players:
            ref = self.refs[p]
            if ref.result is None:
                ref.update(values.get(p), now, ready.get(p, True))
        self.verdict = self._decide()
        return self.verdict

    def _scores(self):
        return {p: (r.result.value if r.result else r.last_value) for p, r in self.refs.items()}

    def _decide(self):
        wt = self.win.get("type")
        results = {p: self.refs[p].result for p in self.players}
        pending = [p for p, r in results.items() if r is None]
        if wt in ("reach", "equals", "bit_set"):
            done = [p for p, r in results.items() if r and r.reason == "goal reached"]
            if done:  # decided the moment someone finishes; finishing on the same poll is a tie
                return Verdict(done, [p for p in self.players if p not in done], draw=len(done) > 1,
                               reason="first to the goal", scores=self._scores(),
                               times={p: r.time for p, r in results.items() if r})
        if wt == "eliminate" and len(self.players) > 1 and len(pending) == 1:
            out = [p for p, r in results.items() if r and not r.success]
            if len(out) == len(self.players) - 1:
                last = pending[0]
                return Verdict([last], out, reason="last one standing", scores=self._scores(),
                               times={p: r.time for p, r in results.items() if r})
        if pending:
            return None
        return rank_turns(self.ch, [results[p] for p in self.players])
