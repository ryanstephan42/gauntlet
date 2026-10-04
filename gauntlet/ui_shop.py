import pygame

from .controls import hint_footer
from .economy import Shop
from .inputmap import Action, KEYBOARD
from .layout import DESIGN_H, DESIGN_W, Layout
from .pg_input import PygameInput
from .screens import Screen, ScreenManager
from .theme import DEFAULT_THEME as T
from .widgets import ListView, ToastQueue, wrap_text


class ShopScreen(Screen):
    """Gamepad/keyboard navigable shop. Result in .purchased/.points/.start once .finished."""

    def __init__(self, game, points):
        self.game = game
        self.shop = Shop(game.get("shop", []), points)
        self.list = ListView(range(len(self.shop.items)), visible=5)
        self.toasts = ToastQueue(T.toast_seconds)
        self.finished = False
        self.start = False
        self.device = KEYBOARD
        self.font = None

    def handle(self, event):
        self.device = event.device
        a = event.action
        if a is Action.BACK:
            self.finished = True
        elif a is Action.START:
            self.finished, self.start = True, True
        elif a is Action.CONFIRM:
            i = self.list.items[self.list.index] if self.list.items else None
            if i is None:
                return
            item = self.shop.items[i]
            if self.shop.is_bought(item):
                self.shop.refund(i)
                self.toasts.show(f"Refunded {item['name']}")
            elif self.shop.buy(i):
                self.toasts.show(f"Bought {item['name']}")
            else:
                self.toasts.show("Not enough points")
        else:
            self.list.handle(a)

    def update(self, dt):
        self.toasts.update(dt)

    def draw(self, surf):
        if self.font is None:
            self.font = pygame.font.Font(None, T.font_size)
            self.small = pygame.font.Font(None, 26)
        surf.fill(T.bg)
        p = T.padding
        surf.blit(self.font.render(f"SHOP: {self.game['meta']['name']}", True, T.accent), (50, 40))
        surf.blit(self.font.render(f"Your Points: {self.shop.points}", True, T.text), (50, 85))
        y = 140
        for i in self.list.visible_items:
            item = self.shop.items[i]
            focused = i == self.list.items[self.list.index]
            bought = self.shop.is_bought(item)
            color = T.good if bought else T.text if self.shop.can_buy(item) else T.text_dim
            pygame.draw.rect(surf, T.panel, (40, y, DESIGN_W - 80, 70), border_radius=8)
            if focused:
                pygame.draw.rect(surf, T.focus, (40, y, DESIGN_W - 80, 70), 3, border_radius=8)
            label = f"{item['name']} ({item['cost']} pts)" + (" [BOUGHT]" if bought else "")
            surf.blit(self.font.render(label, True, color), (40 + p, y + 6))
            desc = wrap_text(item.get("description", ""), 110)
            surf.blit(self.small.render(desc[0] if desc else "", True, T.text_dim), (40 + p, y + 40))
            y += 80
        for n, msg in enumerate(self.toasts.messages[-3:]):
            surf.blit(self.font.render(msg, True, T.accent), (50, DESIGN_H - 140 + n * 30))
        footer = hint_footer(self.device, [(Action.CONFIRM, "Buy/Refund"),
                                           (Action.START, "Start match"), (Action.BACK, "Cancel")])
        surf.blit(self.font.render(footer, True, T.focus), (50, DESIGN_H - 50))


def run_shop(screen, game, points):
    """Returns (purchased_items, remaining_points, start_match)."""
    layout = Layout(*screen.get_size())
    canvas = pygame.Surface((DESIGN_W, DESIGN_H))
    inp = PygameInput()
    manager = ScreenManager()
    shop_screen = ShopScreen(game, points)
    manager.push(shop_screen)
    clock = pygame.time.Clock()
    while True:
        dt = clock.tick(30) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return [], points, False
            if event.type == pygame.VIDEORESIZE:
                layout = Layout(*screen.get_size())
            ie = inp.translate(event)
            if ie:
                manager.handle(ie)
        manager.update(dt)
        if shop_screen.finished:
            if shop_screen.start:
                return shop_screen.shop.purchased, shop_screen.shop.points, True
            return [], points, False
        manager.draw(canvas)
        if manager.fade > 0:
            veil = pygame.Surface((DESIGN_W, DESIGN_H))
            veil.set_alpha(int(255 * manager.fade))
            canvas.blit(veil, (0, 0))
        screen.fill((0, 0, 0))
        w, h = layout.px(DESIGN_W), layout.px(DESIGN_H)
        screen.blit(pygame.transform.smoothscale(canvas, (w, h)), layout.point(0, 0))
        pygame.display.flip()
