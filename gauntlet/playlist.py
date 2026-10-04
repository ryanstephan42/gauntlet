"""Playlists decide which game is played next: single, N-round gauntlet, or knockout bracket."""
import random

from .session import Round

KINDS = ("single", "gauntlet", "bracket")


def _pow2(n):
    p = 1
    while p < n:
        p *= 2
    return p


class Playlist:
    def __init__(self, kind="single", entries=(), rounds=1, shuffle=False, best_of=None):
        if kind not in KINDS:
            raise ValueError(f"unknown playlist kind {kind!r}")
        self.kind = kind
        self.entries = [dict(e) for e in entries]   # {"game": file, "challenge": id, "best_of": n}
        self.rounds = max(1, int(rounds))
        self.shuffle = shuffle
        self.best_of = best_of

    def to_dict(self):
        return {"kind": self.kind, "entries": self.entries, "rounds": self.rounds,
                "shuffle": self.shuffle, "best_of": self.best_of}

    @classmethod
    def from_dict(cls, d):
        return cls(d["kind"], d.get("entries", []), d.get("rounds", 1), d.get("shuffle", False),
                   d.get("best_of"))

    @property
    def total_rounds(self):
        """Known number of rounds (bracket: computed lazily, None)."""
        if self.kind == "single":
            return 1
        if self.kind == "gauntlet":
            return self.rounds
        return None

    def _entry(self, session, index):
        if not self.entries:
            raise ValueError("playlist has no games")
        if self.shuffle:
            return random.Random(session.seed + index).choice(self.entries)
        return self.entries[index % len(self.entries)]

    def _make(self, session, players, label="", stage=None, slot=None):
        number = len(session.rounds) + 1
        e = self._entry(session, number - 1)
        best_of = self.best_of or e.get("best_of") or 1
        return Round(number, e["game"], e.get("challenge") or "", list(players), best_of,
                     label or f"Round {number}", stage, slot)

    def next_round(self, session):
        all_ids = [p.id for p in session.players]
        if self.kind == "single":
            return None if session.rounds else self._make(session, all_ids, "Match")
        if self.kind == "gauntlet":
            if len(session.rounds) >= self.rounds:
                return None
            return self._make(session, all_ids)
        return self._next_bracket(session)

    # -- bracket ------------------------------------------------------------------
    @staticmethod
    def pairings(stage_players):
        """-> (byes, pairs). Top seeds get byes; others play highest vs lowest."""
        byes_n = _pow2(len(stage_players)) - len(stage_players)
        byes = stage_players[:byes_n]
        rest = stage_players[byes_n:]
        pairs = [(rest[i], rest[-1 - i]) for i in range(len(rest) // 2)]
        return byes, pairs

    @staticmethod
    def stage_label(n_players):
        return {2: "Final", 3: "Semifinal", 4: "Semifinal"}.get(n_players, "Quarterfinal")

    def _round_at(self, session, stage, slot):
        return next((r for r in session.rounds if r.stage == stage and r.slot == slot), None)

    @staticmethod
    def bracket_winner(rnd):
        winners = rnd.winners()
        if len(winners) == 1:
            return winners[0]
        return rnd.players[0]  # tie after the series: higher seed advances

    def bracket_stages(self, session):
        """[(stage_players, byes, [(pair, round_or_None)])] up to the first unresolved stage."""
        stages = []
        players = list(session.seeding)
        stage = 0
        while len(players) > 1:
            byes, pairs = self.pairings(players)
            rows = [(pair, self._round_at(session, stage, i)) for i, pair in enumerate(pairs)]
            stages.append((players, byes, rows))
            if not all(r is not None and r.decided for _, r in rows):
                break
            players = byes + [self.bracket_winner(r) for _, r in rows]
            stage += 1
        return stages

    def _next_bracket(self, session):
        stages = self.bracket_stages(session)
        if not stages:
            return None
        players, byes, rows = stages[-1]
        for slot, (pair, rnd) in enumerate(rows):
            if rnd is None:
                label = self.stage_label(len(players))
                if len(rows) > 1:
                    label += f" {slot + 1}"
                return self._make(session, pair, label, len(stages) - 1, slot)
            if not rnd.decided:
                return rnd
        return None  # final decided

    def placements(self, session):
        """Bracket: {pid: place} (1 = champion). Others: {}."""
        if self.kind != "bracket" or not session.rounds:
            return {}
        place = {}
        stages = self.bracket_stages(session)
        final_players, _byes, rows = stages[-1]
        if len(final_players) == 2 and rows and rows[0][1] is not None and rows[0][1].decided:
            winner = self.bracket_winner(rows[0][1])
            place[winner] = 1
            place[[p for p in rows[0][0] if p != winner][0]] = 2
        # earlier eliminations: later stage = better place
        next_place = 3
        for players, _byes, rows in reversed(stages[:-1] if place else stages):
            losers = []
            for pair, rnd in rows:
                if rnd is not None and rnd.decided:
                    w = self.bracket_winner(rnd)
                    losers += [p for p in pair if p != w and p not in place]
            for p in losers:
                place[p] = next_place
            next_place += len(losers)
        return place
