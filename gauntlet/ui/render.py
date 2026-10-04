"""Painter: resolution-independent drawing in a 1280x720 design space with hit regions."""
import hashlib
import os

import pygame

from ..layout import DESIGN_H, DESIGN_W, Layout
from ..theme import DEFAULT_THEME

FONT_CANDIDATES = ("dejavusans", "notosans", "liberationsans", "arial", "freesans")


class Painter:
    def __init__(self, surface, theme=DEFAULT_THEME, tv_mode=False):
        self.theme = theme
        self.tv_mode = tv_mode
        self._fonts = {}
        self._images = {}
        self._font_name = pygame.font.match_font(",".join(FONT_CANDIDATES))
        self.hits = []
        self.set_surface(surface)

    # -- setup ----------------------------------------------------------------------------
    def set_surface(self, surface):
        self.surface = surface
        w, h = surface.get_size()
        self.layout = Layout(w, h)
        self._fonts.clear()
        self._images.clear()

    @property
    def margin(self):
        """Design-space safe margin (TV overscan)."""
        return 48 if self.tv_mode else 24

    @property
    def font_scale(self):
        return 1.2 if self.tv_mode else 1.0

    def begin_frame(self):
        self.hits = []
        self.surface.fill((0, 0, 0))
        self.rect(0, 0, DESIGN_W, DESIGN_H, self.theme.bg)

    # -- primitives ---------------------------------------------------------------------------
    def font(self, size, bold=False):
        px = max(8, self.layout.px(size * self.font_scale))
        key = (px, bold)
        if key not in self._fonts:
            f = pygame.font.Font(self._font_name, px)
            f.set_bold(bold)
            self._fonts[key] = f
        return self._fonts[key]

    def measure(self, text, size=24, bold=False):
        """Text width in design units."""
        return self.font(size, bold).size(str(text))[0] / max(self.layout.scale, 1e-6)

    def fit(self, text, width, size=24, bold=False):
        text = str(text)
        if self.measure(text, size, bold) <= width:
            return text
        while text and self.measure(text + "…", size, bold) > width:
            text = text[:-1]
        return text + "…"

    def text(self, text, x, y, size=24, color=None, align="left", bold=False, width=None, alpha=255):
        """Draw text with its top at design y; returns the design-space width drawn."""
        text = str(text)
        if width:
            text = self.fit(text, width, size, bold)
        surf = self.font(size, bold).render(text, True, color or self.theme.text)
        if alpha < 255:
            surf.set_alpha(alpha)
        px, py = self.layout.point(x, y)
        if align == "center":
            px -= surf.get_width() // 2
        elif align == "right":
            px -= surf.get_width()
        self.surface.blit(surf, (px, py))
        return surf.get_width() / max(self.layout.scale, 1e-6)

    def wrapped(self, text, x, y, width, size=22, color=None, line_gap=1.25, max_lines=None):
        from ..widgets import wrap_text
        lines = wrap_text(str(text), width, lambda s: self.measure(s, size))
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = self.fit(lines[-1] + " …", width, size)
        for i, line in enumerate(lines):
            self.text(line, x, y + i * size * line_gap * self.font_scale, size, color)
        return len(lines) * size * line_gap * self.font_scale

    def rect(self, x, y, w, h, color, radius=0, width=0, alpha=255):
        r = pygame.Rect(self.layout.rect(x, y, w, h))
        if alpha < 255:
            s = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.rect(s, (*color[:3], alpha), s.get_rect(), width, border_radius=self.layout.px(radius))
            self.surface.blit(s, r.topleft)
        else:
            pygame.draw.rect(self.surface, color, r, self.layout.px(width) if width else 0,
                             border_radius=self.layout.px(radius))
        return r

    def panel(self, x, y, w, h, focused=False, color=None, border=None, alpha=255):
        self.rect(x, y, w, h, color or self.theme.panel, radius=12, alpha=alpha)
        if focused or border:
            self.rect(x, y, w, h, border or self.theme.focus, radius=12, width=3)

    def bar(self, x, y, w, h, frac, color=None, back=None):
        frac = max(0.0, min(1.0, frac))
        self.rect(x, y, w, h, back or (25, 25, 32), radius=h // 2)
        if frac > 0:
            self.rect(x, y, max(h, w * frac), h, color or self.theme.accent, radius=h // 2)

    def circle(self, x, y, r, color):
        pygame.draw.circle(self.surface, color, self.layout.point(x, y), max(1, self.layout.px(r)))

    def dim(self, alpha=160):
        s = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
        s.fill((0, 0, 0, alpha))
        self.surface.blit(s, (0, 0))

    # -- hit regions (mouse) ----------------------------------------------------------------
    def hit(self, payload, x, y, w, h):
        self.hits.append((pygame.Rect(self.layout.rect(x, y, w, h)), payload))

    def hit_test(self, pos):
        for rect, payload in reversed(self.hits):
            if rect.collidepoint(pos):
                return payload
        return None

    # -- images -------------------------------------------------------------------------------
    def load_image(self, path):
        if path not in self._images:
            img = None
            if path and os.path.isfile(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                except (pygame.error, OSError):
                    img = None
            self._images[path] = img
        return self._images[path]

    def cover(self, path, title, x, y, w, h):
        """Cover art scaled to fit, or a generated placeholder card."""
        r = pygame.Rect(self.layout.rect(x, y, w, h))
        img = self.load_image(path) if path else None
        if img:
            iw, ih = img.get_size()
            scale = min(r.w / iw, r.h / ih)
            size = (max(1, int(iw * scale)), max(1, int(ih * scale)))
            key = (path, size)
            if key not in self._images:
                self._images[key] = pygame.transform.smoothscale(img, size)
            scaled = self._images[key]
            self.surface.blit(scaled, (r.x + (r.w - size[0]) // 2, r.y + (r.h - size[1]) // 2))
            return
        digest = hashlib.md5(str(title).encode()).digest()
        c1 = (60 + digest[0] % 120, 60 + digest[1] % 120, 80 + digest[2] % 120)
        c2 = tuple(max(0, v - 50) for v in c1)
        for i in range(r.h):
            t = i / max(1, r.h - 1)
            col = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
            pygame.draw.line(self.surface, col, (r.x, r.y + i), (r.right - 1, r.y + i))
        initials = "".join(w[0] for w in str(title).split()[:3]).upper() or "?"
        self.text(initials, x + w / 2, y + h / 2 - 30, 52, (255, 255, 255), "center", bold=True)

    # -- composite helpers ------------------------------------------------------------------
    def header(self, title, subtitle=None):
        m = self.margin
        self.text(title, m, m - 4, 40, self.theme.accent, bold=True)
        if subtitle:
            self.text(subtitle, DESIGN_W - m, m + 8, 22, self.theme.text_dim, "right")

    def footer(self, text):
        m = self.margin
        self.rect(0, DESIGN_H - m - 34, DESIGN_W, m + 34, (20, 20, 28))
        self.text(text, DESIGN_W / 2, DESIGN_H - m - 28, 20, self.theme.text_dim, "center",
                  width=DESIGN_W - 2 * m)

    def chip(self, text, x, y, color, size=18, text_color=(20, 20, 20)):
        w = self.measure(text, size, True) + 18
        self.rect(x, y, w, size + 10, color, radius=(size + 10) // 2)
        self.text(text, x + 9, y + 4, size, text_color, bold=True)
        return w
