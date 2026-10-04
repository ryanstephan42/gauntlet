"""Resolution-independent layout: design in a 1280x720 space, scale to window."""

DESIGN_W, DESIGN_H = 1280, 720


class Layout:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.scale = min(width / DESIGN_W, height / DESIGN_H)
        self.offset_x = (width - DESIGN_W * self.scale) / 2
        self.offset_y = (height - DESIGN_H * self.scale) / 2

    def px(self, value):
        return round(value * self.scale)

    def point(self, x, y):
        return (round(self.offset_x + x * self.scale), round(self.offset_y + y * self.scale))

    def rect(self, x, y, w, h):
        px, py = self.point(x, y)
        return (px, py, self.px(w), self.px(h))
