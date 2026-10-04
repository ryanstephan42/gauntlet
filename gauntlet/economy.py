"""Pure shop/points logic (no pygame) so it is easy to test."""
from dataclasses import dataclass, field


class Shop:
    """Single-player shop kept for simple scripts (one purchase per item)."""

    def __init__(self, items, points):
        self.items = list(items)
        self.points = points
        self.purchased = []

    def is_bought(self, item):
        return any(p is item for p in self.purchased)

    def can_buy(self, item):
        return not self.is_bought(item) and self.points >= item["cost"]

    def buy(self, index):
        if not 0 <= index < len(self.items):
            return False
        item = self.items[index]
        if not self.can_buy(item):
            return False
        self.points -= item["cost"]
        self.purchased.append(item)
        return True

    def refund(self, index):
        if not 0 <= index < len(self.items):
            return False
        item = self.items[index]
        if not self.is_bought(item):
            return False
        self.purchased = [p for p in self.purchased if p is not item]
        self.points += item["cost"]
        return True


# --------------------------------------------------------------------------- targets
def needs_target_pick(item, n_players):
    return item.get("target", "self") == "opponent" and n_players > 2


def resolve_targets(item, buyer, players, chosen=None):
    """Player ids an item affects. `players` are the ids in this match."""
    target = item.get("target", "self")
    others = [p for p in players if p != buyer]
    if target == "self":
        return [buyer]
    if target == "all":
        return list(players)
    if target == "others":
        return others
    if chosen is not None and chosen in others:
        return [chosen]
    return others[:1]


# --------------------------------------------------------------------------- per-player cart
@dataclass
class CartEntry:
    item: dict
    targets: list


@dataclass
class PlayerCart:
    """One player's purchases for the next match. Points are only spent on commit()."""
    player: object
    budget: int
    max_items: int = 3
    entries: list = field(default_factory=list)
    wager: int = 0
    ready: bool = False

    @property
    def spent(self):
        return sum(e.item["cost"] for e in self.entries) + self.wager

    @property
    def remaining(self):
        return self.budget - self.spent

    def count(self, item):
        return sum(1 for e in self.entries if e.item.get("id") == item.get("id"))

    def why_not(self, item):
        """None if buyable, else a short reason."""
        if self.ready:
            return "ready"
        if self.max_items and len(self.entries) >= self.max_items:
            return f"max {self.max_items} items"
        limit = item.get("limit", 1)
        if limit and self.count(item) >= limit:
            return "limit reached"
        if item["cost"] > self.remaining:
            return "not enough points"
        return None

    def buy(self, item, targets):
        if self.why_not(item):
            return False
        self.entries.append(CartEntry(item, list(targets)))
        return True

    def refund(self, index=None):
        """Refund entry `index` (default: last)."""
        if self.ready or not self.entries:
            return False
        self.entries.pop(-1 if index is None else index)
        return True

    def set_wager(self, amount):
        amount = max(0, int(amount))
        if amount > self.budget - (self.spent - self.wager):
            return False
        self.wager = amount
        return True


# --------------------------------------------------------------------------- payouts
def catchup_bonus(points, leader_points, step, cap):
    if step <= 0 or cap <= 0:
        return 0
    return min(cap, max(0, leader_points - points) // step)


def compute_payouts(settings, verdict, players, wagers=None):
    """players: {id: {"points": int, "streak": int}} -> {id: breakdown dict}.

    points in `players` are the balances *after* shop spending (wagers already deducted).
    """
    wagers = {k: v for k, v in (wagers or {}).items() if v}
    leader = max((p["points"] for p in players.values()), default=0)
    winners = set(verdict.winners)
    out = {}
    for pid, p in players.items():
        row = {"base": 0, "catchup": 0, "streak": 0, "wager": 0, "result": "loss"}
        if verdict.draw and pid in winners:
            row["base"], row["result"] = settings.draw_points, "draw"
        elif pid in winners:
            row["base"], row["result"] = settings.win_points, "win"
        else:
            row["base"] = settings.loss_points
        if row["result"] == "win":
            streak = p.get("streak", 0) + 1
            row["streak"] = settings.streak_bonus * min(max(0, streak - 1), settings.streak_max)
        row["catchup"] = catchup_bonus(p["points"], leader, settings.catchup_step, settings.catchup_max)
        out[pid] = row
    pot = sum(wagers.values())
    if pot:
        if verdict.draw or not winners:
            for pid, amount in wagers.items():
                if pid in out:
                    out[pid]["wager"] = amount
        else:
            ordered = [pid for pid in verdict.winners if pid in out]
            share, extra = divmod(pot, len(ordered))
            for i, pid in enumerate(ordered):
                out[pid]["wager"] = share + (1 if i < extra else 0)
    for row in out.values():
        row["total"] = row["base"] + row["catchup"] + row["streak"] + row["wager"]
    return out
