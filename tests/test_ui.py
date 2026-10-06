from gauntlet.controls import hint_footer
from gauntlet.inputmap import (Action, InputEvent, KEYBOARD, PlayerSlots, axis_to_action,
                               hat_to_action, key_to_action, pad_device)
from gauntlet.layout import Layout
from gauntlet.osk import OnScreenKeyboard
from gauntlet.screens import Screen, ScreenManager
from gauntlet.widgets import Grid, ListView, Modal, ProgressBar, ToastQueue, wrap_text


def test_mappings():
    assert key_to_action("return") is Action.CONFIRM
    assert hat_to_action((0, 1)) is Action.UP
    assert axis_to_action(0, 0.2) is None
    assert axis_to_action(1, 0.9) is Action.DOWN


def test_slots_join_leave_hotplug():
    s = PlayerSlots(2)
    a, b, c = pad_device(1), pad_device(2), KEYBOARD
    assert s.handle(InputEvent(a, Action.CONFIRM)) == 0
    assert s.handle(InputEvent(a, Action.CONFIRM)) == 0
    assert s.join(b) == 1
    assert s.join(c) is None
    s.on_disconnect(a)
    assert s.slot_of(b) == 1
    assert s.join(c) == 0
    assert s.slot_of(b) == 1
    assert s.slot_of(c) == 0
    assert s.slot_of(a) is None


def test_slots_leave_preserves_other_assignments():
    s = PlayerSlots(3)
    assert s.join("pad:1") == 0
    assert s.join("pad:2") == 1
    s.leave("pad:1")
    assert s.slot_of("pad:2") == 1
    assert s.join("pad:3") == 0


def test_pygame_joystick_lifecycle_events():
    from types import SimpleNamespace

    import pygame

    from gauntlet.pg_input import PygameInput

    inp = PygameInput.__new__(PygameInput)
    inp.pads = {}
    disconnected = []
    inp.slots = SimpleNamespace(on_disconnect=disconnected.append)
    added = []
    inp._add = added.append
    event = SimpleNamespace(type=pygame.JOYDEVICEADDED, device_index=2)
    assert inp.translate(event) is None
    assert added == [2]

    inp.pads[7] = object()
    event = SimpleNamespace(type=pygame.JOYDEVICEREMOVED, instance_id=7)
    assert inp.translate(event) is None
    assert 7 not in inp.pads
    assert disconnected == ["pad:7"]

    event = SimpleNamespace(type=pygame.JOYDEVICEREMOVED)
    assert inp.translate(event) is None


def test_list_scroll():
    lv = ListView(range(5), visible=2)
    for _ in range(3):
        lv.handle(Action.DOWN)
    assert lv.visible_items == [2, 3]
    assert lv.handle(Action.CONFIRM) == 3


def test_grid():
    g = Grid(range(5), columns=3)
    g.handle(Action.DOWN)
    assert g.index == 3
    g.handle(Action.RIGHT)
    g.handle(Action.RIGHT)
    assert g.index == 4


def test_modal_toast_progress_wrap():
    m = Modal("x", ["Yes", "No"])
    m.handle(Action.RIGHT)
    assert m.handle(Action.CONFIRM) == "No" and m.done
    t = ToastQueue(1.0)
    t.show("hi")
    t.update(1.5)
    assert t.messages == []
    assert ProgressBar(2).value == 1.0
    assert wrap_text("aa bb cc", 5) == ["aa bb", "cc"]


def test_osk():
    k = OnScreenKeyboard()
    k.handle(Action.CONFIRM)
    k.handle(Action.RIGHT)
    k.handle(Action.CONFIRM)
    assert k.text == "AB"
    k.handle(Action.BACK)
    assert k.text == "A"
    k.handle(Action.START)
    assert k.done


class Rec(Screen):
    def __init__(self, log, name):
        self.log, self.name = log, name

    def on_enter(self):
        self.log.append(("enter", self.name))

    def on_exit(self):
        self.log.append(("exit", self.name))

    def on_resume(self):
        self.log.append(("resume", self.name))


def test_screen_stack():
    log = []
    m = ScreenManager(fade_seconds=0.1)
    m.push(Rec(log, "a"))
    m.update(0.2)
    m.push(Rec(log, "b"))
    m.update(0.2)
    m.pop()
    m.update(0.2)
    assert log == [("enter", "a"), ("enter", "b"), ("exit", "b"), ("resume", "a")]
    assert m.current.name == "a"


def test_layout_and_hints():
    lay = Layout(2560, 1440)
    assert lay.scale == 2 and lay.px(10) == 20
    assert Layout(1280, 1000).offset_y == 140
    assert hint_footer(KEYBOARD, [(Action.CONFIRM, "Select")]) == "Enter: Select"
    assert hint_footer(pad_device(0), [(Action.BACK, "Back")]) == "B: Back"


def test_placeholder_initials():
    from gauntlet.ui.render import placeholder_initials
    assert placeholder_initials("Super Mario 64") == "SM64"
    assert placeholder_initials("Mortal Kombat II") == "MKII"
    assert placeholder_initials("Super Mario Kart") == "SMK"
    assert placeholder_initials("") == "?"


def test_glyph_filter_replaces_missing_symbols():
    from gauntlet.ui.render import GlyphFilter

    class FakeFont:
        def __init__(self, have):
            self.have = have

        def get_metrics(self, text):
            return [(0, 1, 0, 1, 1.0, 0.0) if c in self.have else None for c in text]

    g = GlyphFilter.__new__(GlyphFilter)
    g._cache = {}
    g._ft = FakeFont("◄►")
    assert g("◀ 3 ▶") == "◄ 3 ►"
    assert g("x ✎") == "x *"
    g._cache, g._ft = {}, FakeFont("◀▶✎")
    assert g("◀ 3 ▶ ✎") == "◀ 3 ▶ ✎"
    g._cache, g._ft = {}, FakeFont("")
    assert g("◀ a ▶ ▲") == "< a > ^"
    assert g("plain") == "plain"


def test_glyph_filter_real_font():
    import pygame
    pygame.font.init()
    from gauntlet.ui.render import FONT_CANDIDATES, GlyphFilter
    g = GlyphFilter(pygame.font.match_font(",".join(FONT_CANDIDATES)))
    out = g("◀ Gauntlet ▶ ✎ ∞")
    assert all(g.has(ch) for ch in out)


def test_every_ui_glyph_has_a_fallback():
    """Any non-ASCII character in the UI source must either render or have a GLYPH_FALLBACKS entry."""
    import pathlib

    import pygame
    pygame.font.init()
    from gauntlet.ui.render import FONT_CANDIDATES, GlyphFilter
    g = GlyphFilter(pygame.font.match_font(",".join(FONT_CANDIDATES)))
    src = "".join(f.read_text() for f in pathlib.Path("gauntlet").rglob("*.py"))
    chars = {c for c in src if ord(c) > 127}
    out = g("".join(sorted(chars)))
    assert all(g.has(ch) for ch in out), [c for c in out if not g.has(c)]


def test_glyph_filter_trophy_falls_back():
    from gauntlet.ui.render import GlyphFilter

    class FakeFont:
        def __init__(self, have):
            self.have = have

        def get_metrics(self, text):
            return [(0, 1, 0, 1, 1.0, 0.0) if c in self.have else None for c in text]

    g = GlyphFilter.__new__(GlyphFilter)
    g._cache, g._ft = {}, FakeFont("★")
    assert g("🏆 Win") == "★ Win"
    g._cache, g._ft = {}, FakeFont("")
    assert g("🏆 ⚠ 🔥2") == "* ! streak 2"


def test_header_subtitle_never_overlaps_title():
    import pygame
    pygame.font.init()
    from gauntlet.ui.render import DESIGN_W, Painter
    p = Painter(pygame.Surface((1280, 720)))
    drawn = []
    real = p.text
    p.text = lambda *a, **k: drawn.append((a, k, real(*a, **k))) or drawn[-1][2]
    p.header("Manage Games", "4 game(s) in " + "/very/long/path" * 20)
    (_, _, title_w), (sub_args, sub_kw, sub_w) = drawn
    assert sub_kw["width"] < DESIGN_W
    assert sub_args[1] - sub_w >= p.margin + title_w
