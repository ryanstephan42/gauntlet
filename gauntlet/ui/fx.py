"""Tiny animation helpers: tweens, count-up numbers, pulses and confetti."""
import math
import random


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


class Tween:
    def __init__(self, start, end, duration=0.4, ease=ease_out):
        self.start, self.end, self.duration, self.ease = start, end, max(1e-6, duration), ease
        self.t = 0.0

    def update(self, dt):
        self.t = min(self.duration, self.t + dt)

    @property
    def done(self):
        return self.t >= self.duration

    @property
    def value(self):
        return self.start + (self.end - self.start) * self.ease(self.t / self.duration)


class CountUp(Tween):
    """Integer counter animating from start to end."""

    @property
    def value(self):
        return int(round(super().value))


def pulse(time, speed=3.0, lo=0.6, hi=1.0):
    return lo + (hi - lo) * (0.5 + 0.5 * math.sin(time * speed))


class Confetti:
    COLORS = [(232, 72, 85), (66, 135, 245), (60, 200, 110), (245, 190, 50), (200, 120, 255)]

    def __init__(self, count=120, width=1280, seed=None):
        rnd = random.Random(seed)
        self.parts = [[rnd.uniform(0, width), rnd.uniform(-400, 0), rnd.uniform(-40, 40),
                       rnd.uniform(120, 260), rnd.choice(self.COLORS), rnd.uniform(4, 9)]
                      for _ in range(count)]

    def update(self, dt):
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt

    def draw(self, painter):
        for x, y, _vx, _vy, color, size in self.parts:
            if 0 <= y <= 720:
                painter.rect(x, y, size, size * 0.6, color)

    @property
    def done(self):
        return all(p[1] > 720 for p in self.parts)
