"""Screen stack manager with simple fade transitions (pygame-free)."""


class Screen:
    manager = None

    def on_enter(self): ...
    def on_exit(self): ...
    def on_pause(self): ...
    def on_resume(self): ...

    def handle(self, event):
        """Handle an InputEvent."""

    def update(self, dt): ...
    def draw(self, surface): ...


class ScreenManager:
    def __init__(self, fade_seconds=0.2):
        self.stack = []
        self.fade_seconds = fade_seconds
        self._fade = 0.0
        self._pending = []

    @property
    def current(self):
        return self.stack[-1] if self.stack else None

    @property
    def fade(self):
        """0.0 (none) .. 1.0 (fully faded) for the draw layer to apply."""
        return self._fade

    def push(self, screen):
        self._pending.append(("push", screen))

    def pop(self):
        self._pending.append(("pop", None))

    def replace(self, screen):
        self._pending.append(("replace", screen))

    def reset(self, screen=None):
        """Pop back to the root screen, then optionally push `screen`."""
        self._pending.append(("root", None))
        if screen is not None:
            self._pending.append(("push", screen))

    def _apply(self, op, screen):
        if op == "root":
            while len(self.stack) > 1:
                self.stack.pop().on_exit()
            if self.current:
                self.current.on_resume()
        elif op == "push":
            if self.current:
                self.current.on_pause()
            screen.manager = self
            self.stack.append(screen)
            screen.on_enter()
        elif op == "pop" and self.stack:
            old = self.stack.pop()
            old.on_exit()
            if self.current:
                self.current.on_resume()
        elif op == "replace":
            if self.stack:
                self.stack.pop().on_exit()
            screen.manager = self
            self.stack.append(screen)
            screen.on_enter()

    def handle(self, event):
        if self.current and not self._pending:
            self.current.handle(event)

    def update(self, dt):
        if self._pending:
            # fade out, then apply queued changes, then fade back in
            self._fade = min(1.0, self._fade + dt / max(self.fade_seconds, 1e-9))
            if self._fade >= 1.0:
                for op, screen in self._pending:
                    self._apply(op, screen)
                self._pending.clear()
        elif self._fade > 0:
            self._fade = max(0.0, self._fade - dt / max(self.fade_seconds, 1e-9))
        if self.current:
            self.current.update(dt)

    def draw(self, surface):
        if self.current:
            self.current.draw(surface)
