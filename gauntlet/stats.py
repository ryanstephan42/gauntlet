"""Persistent stats, leaderboard and achievements (state/stats.json)."""
import json
import os
import time

ACHIEVEMENTS = {
    "first_win": ("First Blood", "Win a match"),
    "on_fire": ("On Fire", "Win 3 matches in a row"),
    "champion": ("Champion", "Win a whole session"),
    "flawless": ("Flawless", "Win every match of a session (3+ matches)"),
    "underdog": ("Underdog", "Win a match while in last place"),
    "high_roller": ("High Roller", "Win a pot of 5+ points"),
    "shopaholic": ("Shopaholic", "Buy 10 shop items"),
    "veteran": ("Veteran", "Play 25 matches"),
    "saboteur": ("Saboteur", "Win a match after debuffing an opponent"),
}


def _blank_player():
    return {"matches": 0, "wins": 0, "losses": 0, "draws": 0, "points_earned": 0, "items": 0,
            "sessions": 0, "sessions_won": 0, "best_streak": 0, "streak": 0, "last_played": 0}


class Stats:
    def __init__(self, path):
        self.path = path
        self.data = {"players": {}, "games": {}, "history": [], "achievements": {}}
        try:
            with open(path) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)

    def player(self, name):
        rec = self.data["players"].setdefault(name, _blank_player())
        for k, v in _blank_player().items():
            rec.setdefault(k, v)
        return rec

    def unlocked(self, name):
        return self.data["achievements"].get(name, [])

    def _unlock(self, name, ach, out):
        got = self.data["achievements"].setdefault(name, [])
        if ach not in got:
            got.append(ach)
            out.append((name, ach))

    def record_match(self, session, rnd, match, game_name, shop_items=None):
        """Returns newly unlocked [(player_name, achievement_id)]."""
        new = []
        v = match["verdict"]
        names = session.names()
        before = {pid: session.player(pid).points - row["total"] for pid, row in match["payouts"].items()}
        lowest = min(before.values()) if before else 0
        debuffers = {pu["buyer"] for pu in match.get("purchases", [])
                     if (shop_items or {}).get(pu.get("item"), {}).get("category") == "debuff"
                     and any(t != pu["buyer"] for t in pu.get("targets", []))}
        g = self.data["games"].setdefault(game_name, {"plays": 0, "draws": 0})
        g["plays"] += 1
        if v["draw"]:
            g["draws"] += 1
        for pid, row in match["payouts"].items():
            name = names.get(pid, str(pid))
            rec = self.player(name)
            rec["matches"] += 1
            rec["points_earned"] += row["total"]
            rec["last_played"] = time.time()
            rec["items"] += sum(1 for pu in match.get("purchases", []) if pu["buyer"] == pid)
            if row["result"] == "win":
                rec["wins"] += 1
                rec["streak"] += 1
                rec["best_streak"] = max(rec["best_streak"], rec["streak"])
                self._unlock(name, "first_win", new)
                if rec["streak"] >= 3:
                    self._unlock(name, "on_fire", new)
                if len(before) > 1 and before[pid] == lowest and list(before.values()).count(lowest) == 1:
                    self._unlock(name, "underdog", new)
                if row.get("wager", 0) >= 5:
                    self._unlock(name, "high_roller", new)
                if pid in debuffers:
                    self._unlock(name, "saboteur", new)
            elif row["result"] == "draw":
                rec["draws"] += 1
                rec["streak"] = 0
            else:
                rec["losses"] += 1
                rec["streak"] = 0
            if rec["items"] >= 10:
                self._unlock(name, "shopaholic", new)
            if rec["matches"] >= 25:
                self._unlock(name, "veteran", new)
        self.data["history"].append({"time": match.get("time", time.time()), "game": game_name,
                                     "round": rnd.label, "winners": [names.get(w, "?") for w in v["winners"]],
                                     "draw": v["draw"], "reason": v.get("reason", "")})
        self.data["history"] = self.data["history"][-200:]
        return new

    def record_session(self, session):
        new = []
        standings = session.standings()
        if not standings:
            return new
        champ = standings[0]
        matches = [m for r in session.rounds for m in r.matches]
        for p in session.players:
            rec = self.player(p.name)
            rec["sessions"] += 1
        rec = self.player(champ.name)
        rec["sessions_won"] += 1
        self._unlock(champ.name, "champion", new)
        if len(matches) >= 3 and all(champ.id in m["verdict"]["winners"] and not m["verdict"]["draw"]
                                     for m in matches if champ.id in m["payouts"]):
            self._unlock(champ.name, "flawless", new)
        return new

    def leaderboard(self):
        rows = []
        for name, rec in self.data["players"].items():
            played = rec.get("matches", 0)
            rate = rec.get("wins", 0) / played if played else 0.0
            rows.append(dict(rec, name=name, win_rate=rate))
        rows.sort(key=lambda r: (-r.get("sessions_won", 0), -r.get("wins", 0), -r["win_rate"], r["name"]))
        return rows
