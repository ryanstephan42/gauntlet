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
    assert s.join(c) == 1 or s.slot_of(c) is not None
    assert s.slot_of(a) is None


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
