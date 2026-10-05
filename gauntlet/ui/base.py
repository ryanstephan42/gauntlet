"""Screen base classes, form fields and modal overlays shared by every UI screen."""
from ..controls import hint_footer
from ..inputmap import Action, KEYBOARD
from ..layout import DESIGN_H, DESIGN_W
from ..osk import ROWS, SPECIALS, OnScreenKeyboard
from ..screens import Screen
from ..widgets import ListView


class BaseScreen(Screen):
    title = ""
    subtitle = ""

    def __init__(self, app):
        self.app = app
        self.time = 0.0

    # convenience ------------------------------------------------------------------
    @property
    def settings(self):
        return self.app.settings

    def sound(self, name):
        self.app.audio.play(name)

    def toast(self, text):
        self.app.toasts.show(text)

    def push(self, screen):
        self.app.manager.push(screen)

    def pop(self):
        self.app.manager.pop()

    def replace(self, screen):
        self.app.manager.replace(screen)

    def hints(self):
        return [(Action.CONFIRM, "Select"), (Action.BACK, "Back")]

    # events -------------------------------------------------------------------------
    def handle(self, event):
        self.on_action(event)

    def on_action(self, event):
        if event.action is Action.BACK:
            self.sound("back")
            self.pop()

    def update(self, dt):
        self.time += dt

    def draw(self, surface):
        p = self.app.painter
        p.header(self.title, self.subtitle)
        self.draw_body(p)
        p.footer(hint_footer(self.app.last_device, self.hints()))

    def draw_body(self, p):
        pass


# ------------------------------------------------------------------------------------- menus
class MenuScreen(BaseScreen):
    """Vertical menu of (label, callback, enabled, description) rows."""
    visible = 9
    row_h = 52
    top = 110
    width = 560

    def __init__(self, app):
        super().__init__(app)
        self.list = ListView([], self.visible)

    def rows(self):
        return []

    def on_enter(self):
        self.refresh()

    def on_resume(self):
        self.refresh()

    def refresh(self):
        index = self.list.index
        self.list = ListView(self.rows(), self.visible)
        self.list.index = min(index, max(0, len(self.list.items) - 1))
        self.list.handle(None)

    def activate(self, row):
        callback, enabled = row[1], row[2] if len(row) > 2 else True
        if not enabled or callback is None:
            self.sound("error")
            return
        self.sound("confirm")
        callback()

    def on_action(self, event):
        a = event.action
        if a in (Action.UP, Action.DOWN):
            self.list.handle(a)
            self.sound("move")
        elif a is Action.CONFIRM and self.list.items:
            self.activate(self.list.items[self.list.index])
        else:
            super().on_action(event)

    def focus_and_activate(self, index):
        self.list.index = index
        self.activate(self.list.items[index])

    def draw_body(self, p):
        x = p.margin + 20
        y = self.top
        for i, row in enumerate(self.list.visible_items):
            idx = self.list.top + i
            focused = idx == self.list.index
            enabled = row[2] if len(row) > 2 else True
            p.panel(x, y, self.width, self.row_h - 8, focused, color=(60, 60, 82) if focused else None)
            color = self.app.theme.text if enabled else self.app.theme.text_dim
            p.text(row[0], x + 18, y + 9, 26, color, width=self.width - 36)
            p.hit(lambda idx=idx: self.focus_and_activate(idx), x, y, self.width, self.row_h - 8)
            y += self.row_h
        if self.list.items:
            row = self.list.items[self.list.index]
            if len(row) > 3 and row[3]:
                dx = x + self.width + 40
                p.panel(dx, self.top, DESIGN_W - dx - p.margin, 300)
                p.wrapped(row[3], dx + 20, self.top + 18, DESIGN_W - dx - p.margin - 40, 22)


# ------------------------------------------------------------------------------------- forms
class Field:
    """A form row. kind: choice | int | bool | text | button | info."""

    def __init__(self, key, label, kind="info", value=None, options=None, labels=None, lo=0, hi=999,
                 step=1, on_press=None, help="", enabled=True, fmt=None, max_len=24):
        self.key, self.label, self.kind, self.value = key, label, kind, value
        self.options = list(options or [])
        self.labels = labels
        self.lo, self.hi, self.step = lo, hi, step
        self.on_press = on_press
        self.help = help
        self.enabled = enabled
        self.fmt = fmt
        self.max_len = max_len

    def display(self):
        if self.fmt:
            return self.fmt(self.value)
        if self.kind == "bool":
            return "On" if self.value else "Off"
        if self.kind == "choice":
            if self.labels and self.value in self.options:
                return self.labels[self.options.index(self.value)]
            return str(self.value)
        if self.kind == "button":
            return ""
        return "" if self.value is None else str(self.value)

    def adjust(self, direction, fast=False):
        if not self.enabled:
            return False
        if self.kind == "choice" and self.options:
            i = self.options.index(self.value) if self.value in self.options else 0
            self.value = self.options[(i + direction) % len(self.options)]
            return True
        if self.kind == "int":
            step = self.step * (10 if fast else 1)
            v = (self.value or 0) + direction * step
            self.value = max(self.lo, min(self.hi, v))
            return True
        if self.kind == "bool":
            self.value = not self.value
            return True
        return False


class FormScreen(BaseScreen):
    """Editable list of Fields. LEFT/RIGHT adjust, CONFIRM toggles/edits/presses, PREV/NEXT x10."""
    label_w = 380
    visible = 10

    def __init__(self, app, fields=()):
        super().__init__(app)
        self.fields = list(fields)
        self.index = 0
        self.top = 0

    @property
    def focused(self):
        return self.fields[self.index] if self.fields else None

    def field(self, key):
        return next((f for f in self.fields if f.key == key), None)

    def values(self):
        return {f.key: f.value for f in self.fields if f.kind not in ("button", "info")}

    def changed(self, field):
        """Hook: a field's value changed."""

    def _move(self, d):
        if not self.fields:
            return
        n = len(self.fields)
        for _ in range(n):
            self.index = (self.index + d) % n
            if self.fields[self.index].kind != "info":
                break
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + self.visible:
            self.top = self.index - self.visible + 1
        self.sound("move")

    def press(self, f):
        if not f.enabled:
            self.sound("error")
            return
        if f.kind == "button" and f.on_press:
            self.sound("confirm")
            f.on_press()
        elif f.kind == "bool":
            f.adjust(1)
            self.sound("move")
            self.changed(f)
        elif f.kind == "text":
            def done(text, f=f):
                if text is not None:
                    f.value = text
                    self.changed(f)
            self.app.text_input(f.label, f.value or "", done, f.max_len)
        elif f.kind in ("choice", "int"):
            f.adjust(1)
            self.sound("move")
            self.changed(f)

    def on_action(self, event):
        a, f = event.action, self.focused
        if a is Action.UP:
            self._move(-1)
        elif a is Action.DOWN:
            self._move(1)
        elif a in (Action.LEFT, Action.RIGHT, Action.PREV, Action.NEXT) and f:
            d = -1 if a in (Action.LEFT, Action.PREV) else 1
            if f.adjust(d, fast=a in (Action.PREV, Action.NEXT)):
                self.sound("move")
                self.changed(f)
        elif a is Action.CONFIRM and f:
            self.press(f)
        else:
            super().on_action(event)

    def click(self, index):
        self.index = index
        self.press(self.fields[index])

    def draw_body(self, p):
        x, y, w = p.margin + 20, 100, DESIGN_W - 2 * p.margin - 40
        if self.fields and self.top > 0:
            p.text("▲", x + w / 2, y - 22, 18, self.app.theme.text_dim, "center")
        for i, f in enumerate(self.fields[self.top:self.top + self.visible]):
            idx = self.top + i
            focused = idx == self.index
            if f.kind == "info":
                p.text(f.label, x + 6, y + 12, 22, self.app.theme.accent, bold=True, width=w)
                y += 46
                continue
            p.panel(x, y, w, 40, focused, color=(60, 60, 82) if focused else None)
            col = self.app.theme.text if f.enabled else self.app.theme.text_dim
            p.text(f.label, x + 16, y + 7, 22, col, width=self.label_w - 20)
            value = f.display()
            if f.kind in ("choice", "int") and focused:
                value = f"◀ {value} ▶"
            elif f.kind == "text" and focused:
                value = f"{value}  ✎"
            p.text(value, x + self.label_w, y + 7, 22, self.app.theme.accent if focused else col,
                   width=w - self.label_w - 16)
            p.hit(lambda idx=idx: self.click(idx), x, y, w, 40)
            y += 46
        if len(self.fields) > self.top + self.visible:
            p.text("▼", x + w / 2, y - 4, 18, self.app.theme.text_dim, "center")
        f = self.focused
        if f and f.help:
            p.wrapped(f.help, x, DESIGN_H - p.margin - 90, w, 20, self.app.theme.text_dim, max_lines=2)

    def hints(self):
        return [(Action.CONFIRM, "Edit"), (Action.LEFT, "Change"), (Action.BACK, "Back")]


# ------------------------------------------------------------------------------------- overlays
class Overlay:
    """Modal layer drawn above the current screen; gets all input until closed."""
    wants_text = False
    closed = False

    def __init__(self, app):
        self.app = app

    def close(self):
        self.closed = True

    def handle(self, event):
        pass

    def update(self, dt):
        pass

    def draw(self, p):
        pass


class ChoiceOverlay(Overlay):
    def __init__(self, app, message, options, on_result, title="", cancel_value=None):
        super().__init__(app)
        self.message, self.options, self.on_result = message, list(options), on_result
        self.title = title
        self.index = 0
        self.cancel_value = cancel_value

    def finish(self, value):
        self.close()
        if self.on_result:
            self.on_result(value)

    def handle(self, event):
        a = event.action
        if a in (Action.UP, Action.LEFT):
            self.index = (self.index - 1) % len(self.options)
            self.app.audio.play("move")
        elif a in (Action.DOWN, Action.RIGHT):
            self.index = (self.index + 1) % len(self.options)
            self.app.audio.play("move")
        elif a is Action.CONFIRM:
            self.app.audio.play("confirm")
            self.finish(self.options[self.index])
        elif a is Action.BACK:
            self.app.audio.play("back")
            self.finish(self.cancel_value)

    def click(self, i):
        self.index = i
        self.finish(self.options[i])

    def draw(self, p):
        p.dim()
        w = 640
        lines_h = 30 * max(1, min(6, len(self.message) // 48 + 1 + self.message.count("\n")))
        h = 110 + lines_h + 50 * len(self.options)
        x, y = (DESIGN_W - w) / 2, max(20, (DESIGN_H - h) / 2)
        p.panel(x, y, w, h, border=self.app.theme.accent)
        ty = y + 20
        if self.title:
            p.text(self.title, x + w / 2, ty, 28, self.app.theme.accent, "center", bold=True)
            ty += 40
        ty += p.wrapped(self.message, x + 30, ty, w - 60, 22, max_lines=6) + 14
        for i, opt in enumerate(self.options):
            focused = i == self.index
            p.panel(x + 40, ty, w - 80, 42, focused, color=(70, 70, 96) if focused else (55, 55, 72))
            p.text(str(opt), x + w / 2, ty + 8, 22, None, "center", width=w - 100)
            p.hit(lambda i=i: self.click(i), x + 40, ty, w - 80, 42)
            ty += 50


class TextOverlay(Overlay):
    """On-screen keyboard (gamepad) + physical keyboard typing."""
    wants_text = True

    def __init__(self, app, title, text, on_done, max_len=24):
        super().__init__(app)
        self.title = title
        self.osk = OnScreenKeyboard(text, max_len)
        self.on_done = on_done

    def finish(self, value):
        self.close()
        self.on_done(value)

    def type_text(self, text):
        for ch in text:
            if len(self.osk.text) < self.osk.max_len and ch.isprintable():
                self.osk.text += ch

    def handle(self, event):
        if event.device == KEYBOARD and event.action is Action.BACK and event.key == "escape":
            self.finish(None)
            return
        if event.device == KEYBOARD and event.action is Action.CONFIRM and event.key in ("return", "enter"):
            self.finish(self.osk.text.strip() or None)
            return
        if event.action is Action.SELECT:
            self.finish(None)
            return
        self.osk.handle(event.action)
        self.app.audio.play("move")
        if self.osk.done:
            self.finish(self.osk.text.strip() or None)

    def click_key(self, row, col):
        self.osk.row, self.osk.col = row, col
        self.osk.handle(Action.CONFIRM)
        if self.osk.done:
            self.finish(self.osk.text.strip() or None)

    def draw(self, p):
        p.dim()
        w, h = 720, 470
        x, y = (DESIGN_W - w) / 2, (DESIGN_H - h) / 2
        p.panel(x, y, w, h, border=self.app.theme.accent)
        p.text(self.title, x + 30, y + 18, 26, self.app.theme.accent, bold=True)
        p.rect(x + 30, y + 60, w - 60, 48, (20, 20, 28), radius=8)
        caret = "_" if int(self.app.time * 2) % 2 == 0 else " "
        p.text(self.osk.text + caret, x + 44, y + 70, 26)
        ky = y + 130
        for r, row in enumerate(ROWS + [SPECIALS]):
            keys = list(row) if r < len(ROWS) else row
            kw = 64 if r < len(ROWS) else 200
            total = len(keys) * (kw + 8) - 8
            kx = x + (w - total) / 2
            for c, k in enumerate(keys):
                focused = self.osk.row == r and self.osk.col == c
                p.panel(kx, ky, kw, 42, focused, color=(80, 80, 110) if focused else (55, 55, 72))
                p.text(k, kx + kw / 2, ky + 8, 22, None, "center")
                p.hit(lambda r=r, c=c: self.click_key(r, c), kx, ky, kw, 42)
                kx += kw + 8
            ky += 50
        p.text("Type on a keyboard or use the pad. Start/Enter = done, B = delete, Select/Esc = cancel",
               x + w / 2, y + h - 34, 16, self.app.theme.text_dim, "center")


class ToastLayer:
    def __init__(self, app, seconds=3.0):
        from ..widgets import ToastQueue
        self.app = app
        self.queue = ToastQueue(seconds)

    def show(self, text):
        self.queue.show(text)

    def update(self, dt):
        self.queue.update(dt)

    @property
    def messages(self):
        return self.queue.messages

    def draw(self, p):
        y = DESIGN_H - p.margin - 90
        for msg in reversed(self.queue.messages[-4:]):
            w = min(DESIGN_W - 80, p.measure(msg, 22) + 40)
            p.rect((DESIGN_W - w) / 2, y, w, 40, (10, 10, 14), radius=10, alpha=225)
            p.text(msg, DESIGN_W / 2, y + 8, 22, None, "center", width=w - 30)
            y -= 48
