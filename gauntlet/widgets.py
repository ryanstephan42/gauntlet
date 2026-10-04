"""Widget state models (pygame-free); rendering is done by the UI layer."""
from .inputmap import Action


class ListView:
    """Scrolling focusable list."""

    def __init__(self, items, visible=8):
        self.items = list(items)
        self.visible = max(1, visible)
        self.index = 0
        self.top = 0

    def handle(self, action):
        if not self.items:
            return None
        if action is Action.UP:
            self.index = (self.index - 1) % len(self.items)
        elif action is Action.DOWN:
            self.index = (self.index + 1) % len(self.items)
        elif action is Action.CONFIRM:
            return self.items[self.index]
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + self.visible:
            self.top = self.index - self.visible + 1
        return None

    @property
    def visible_items(self):
        return self.items[self.top:self.top + self.visible]


class Grid:
    """Focusable card grid (e.g. game cards with cover art)."""

    def __init__(self, items, columns=3):
        self.items = list(items)
        self.columns = max(1, columns)
        self.index = 0

    def handle(self, action):
        n = len(self.items)
        if not n:
            return None
        c = self.columns
        if action is Action.LEFT and self.index % c:
            self.index -= 1
        elif action is Action.RIGHT and self.index % c < c - 1 and self.index + 1 < n:
            self.index += 1
        elif action is Action.UP and self.index - c >= 0:
            self.index -= c
        elif action is Action.DOWN and self.index + c < n:
            self.index += c
        elif action is Action.CONFIRM:
            return self.items[self.index]
        return None


class Button:
    def __init__(self, label, on_press=None):
        self.label, self.on_press = label, on_press

    def handle(self, action):
        if action is Action.CONFIRM and self.on_press:
            self.on_press()
            return True
        return False


class Modal:
    """Choice dialog; returns the chosen option on CONFIRM, None on BACK."""

    def __init__(self, message, options=("OK",)):
        self.message, self.options = message, list(options)
        self.index = 0
        self.done = False
        self.result = None

    def handle(self, action):
        if action in (Action.LEFT, Action.UP):
            self.index = (self.index - 1) % len(self.options)
        elif action in (Action.RIGHT, Action.DOWN):
            self.index = (self.index + 1) % len(self.options)
        elif action is Action.CONFIRM:
            self.done, self.result = True, self.options[self.index]
        elif action is Action.BACK:
            self.done, self.result = True, None
        return self.result


class ToastQueue:
    def __init__(self, seconds=3.0):
        self.seconds = seconds
        self._toasts = []  # [message, remaining]

    def show(self, message):
        self._toasts.append([message, self.seconds])

    def update(self, dt):
        for t in self._toasts:
            t[1] -= dt
        self._toasts = [t for t in self._toasts if t[1] > 0]

    @property
    def messages(self):
        return [t[0] for t in self._toasts]


class ProgressBar:
    def __init__(self, value=0.0):
        self.value = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = min(1.0, max(0.0, float(v)))


def wrap_text(text, max_width, measure=len):
    """Greedy word wrap; `measure(str)` returns width (default: char count)."""
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if current and measure(candidate) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines
