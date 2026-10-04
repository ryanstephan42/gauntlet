"""Pure shop/points logic (no pygame) so it is easy to test."""


class Shop:
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
