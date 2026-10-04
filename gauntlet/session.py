"""Session model: players, playlist, rounds (best-of series), points and save/resume."""
import json
import os
import random
import time
import uuid
from dataclasses import asdict, dataclass, field

from .economy import compute_payouts
from .referee import Verdict

PLAYER_COLORS = [(232, 72, 85), (66, 135, 245), (60, 200, 110), (245, 190, 50)]


@dataclass
class Player:
    id: int
    name: str
    color: int = 0
    device: str = ""        # "pad:<instance>", "keyboard", "keyboard2"
    pad_index: int = None   # joystick device index for RetroArch port mapping
    points: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    streak: int = 0
    best_streak: int = 0
    spent: int = 0
    items_bought: int = 0

    @property
    def rgb(self):
        return PLAYER_COLORS[self.color % len(PLAYER_COLORS)]


@dataclass
class Round:
    number: int
    game: str                  # game file name
    challenge: str
    players: list
    best_of: int = 1
    label: str = ""
    stage: int = None          # bracket stage
    slot: int = None           # bracket slot within the stage
    matches: list = field(default_factory=list)

    def series_wins(self):
        wins = {p: 0 for p in self.players}
        for m in self.matches:
            v = m["verdict"]
            if not v["draw"]:
                for w in v["winners"]:
                    if w in wins:
                        wins[w] += 1
        return wins

    @property
    def decided(self):
        if not self.matches:
            return False
        wins = self.series_wins()
        need = self.best_of // 2 + 1
        top = max(wins.values(), default=0)
        if top >= need:
            return True
        leaders = [p for p, w in wins.items() if w == top]
        if len(self.matches) >= self.best_of and len(leaders) == 1:
            return True
        return len(self.matches) >= self.best_of * 2 + 1  # too many draws: stop

    def winners(self):
        wins = self.series_wins()
        top = max(wins.values(), default=0)
        if top == 0:
            return []
        return [p for p, w in wins.items() if w == top]


class Session:
    def __init__(self, players, playlist, starting_points=10, seed=None):
        self.id = uuid.uuid4().hex[:8]
        self.created = time.time()
        self.players = list(players)
        self.playlist = playlist
        self.rounds = []
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.pending = None      # {"spend": {pid: amount}, "wagers": {...}, "purchases": [...]}
        self.finished = False
        for p in self.players:
            p.points = starting_points
        self.seeding = [p.id for p in self.players]
        random.Random(self.seed).shuffle(self.seeding)

    # -- lookups --------------------------------------------------------------
    def player(self, pid):
        return next((p for p in self.players if p.id == pid), None)

    def names(self):
        return {p.id: p.name for p in self.players}

    @property
    def current_round(self):
        if self.rounds and not self.rounds[-1].decided:
            return self.rounds[-1]
        return None

    def next_round(self):
        """Current undecided round, or a newly created one, or None when the session is over."""
        if self.current_round:
            return self.current_round
        rnd = self.playlist.next_round(self)
        if rnd is None:
            self.finished = True
        else:
            self.rounds.append(rnd)
        return rnd

    # -- match lifecycle --------------------------------------------------------
    def begin_match(self, carts):
        """Deduct shop spending; carts: {pid: PlayerCart}."""
        spend, wagers, purchases = {}, {}, []
        for pid, cart in carts.items():
            p = self.player(pid)
            spend[pid] = cart.spent
            wagers[pid] = cart.wager
            p.points -= cart.spent
            p.spent += cart.spent - cart.wager
            p.items_bought += len(cart.entries)
            for e in cart.entries:
                purchases.append({"item": e.item.get("id"), "name": e.item["name"], "buyer": pid,
                                  "targets": list(e.targets)})
        self.pending = {"spend": spend, "wagers": wagers, "purchases": purchases}

    def abort_match(self):
        """Match could not be played: refund everything spent in the shop."""
        if not self.pending:
            return
        for pid, amount in self.pending["spend"].items():
            p = self.player(pid)
            p.points += amount
        for pu in self.pending["purchases"]:
            p = self.player(pu["buyer"])
            p.items_bought -= 1
        for pid, amount in self.pending["spend"].items():
            self.player(pid).spent -= amount - self.pending["wagers"].get(pid, 0)
        self.pending = None

    def record_match(self, verdict, settings, extra=None):
        """Apply a verdict to the current round; returns the payout breakdown."""
        rnd = self.current_round
        if rnd is None:
            raise RuntimeError("no round in progress")
        pending = self.pending or {"spend": {}, "wagers": {}, "purchases": []}
        players = {pid: {"points": self.player(pid).points, "streak": self.player(pid).streak}
                   for pid in rnd.players}
        payouts = compute_payouts(settings, verdict, players, pending["wagers"])
        for pid, row in payouts.items():
            p = self.player(pid)
            p.points += row["total"]
            if row["result"] == "win":
                p.wins += 1
                p.streak += 1
                p.best_streak = max(p.best_streak, p.streak)
            elif row["result"] == "draw":
                p.draws += 1
                p.streak = 0
            else:
                p.losses += 1
                p.streak = 0
        match = {"verdict": verdict.to_dict(), "payouts": payouts, "purchases": pending["purchases"],
                 "wagers": pending["wagers"], "time": time.time()}
        if extra:
            match.update(extra)
        rnd.matches.append(match)
        self.pending = None
        return payouts

    # -- results ------------------------------------------------------------------
    def standings(self):
        place = self.playlist.placements(self) if hasattr(self.playlist, "placements") else {}
        return sorted(self.players, key=lambda p: (place.get(p.id, 99), -p.points, -p.wins, p.losses, p.id))

    def champion(self):
        if not self.finished:
            return None
        return self.standings()[0]

    # -- persistence ---------------------------------------------------------------
    def to_dict(self):
        return {
            "version": 1, "id": self.id, "created": self.created, "seed": self.seed,
            "seeding": self.seeding, "finished": self.finished, "pending": self.pending,
            "players": [asdict(p) for p in self.players],
            "playlist": self.playlist.to_dict(),
            "rounds": [asdict(r) for r in self.rounds],
        }

    @classmethod
    def from_dict(cls, d):
        from .playlist import Playlist
        s = cls.__new__(cls)
        s.id, s.created, s.seed = d["id"], d["created"], d["seed"]
        s.seeding, s.finished, s.pending = d["seeding"], d["finished"], d.get("pending")
        s.players = [Player(**p) for p in d["players"]]
        s.playlist = Playlist.from_dict(d["playlist"])
        s.rounds = [Round(**r) for r in d["rounds"]]
        _fix_keys(s)
        return s

    def save(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.to_dict(), f, indent=1)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls.from_dict(json.load(f))


def _fix_keys(s):
    """JSON turns int dict keys into strings; convert back."""
    def ints(d):
        return {int(k): v for k, v in d.items()} if isinstance(d, dict) else d
    if s.pending:
        s.pending["spend"] = ints(s.pending["spend"])
        s.pending["wagers"] = ints(s.pending["wagers"])
    for r in s.rounds:
        for m in r.matches:
            m["payouts"] = ints(m["payouts"])
            m["wagers"] = ints(m.get("wagers", {}))


def verdict_of(match):
    return Verdict.from_dict(match["verdict"])
