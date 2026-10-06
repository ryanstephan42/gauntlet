"""Device-independent input abstraction (pygame-free)."""
import enum
from dataclasses import dataclass


class Action(enum.Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    CONFIRM = "confirm"
    BACK = "back"
    START = "start"
    ALT = "alt"          # X/Y face buttons: secondary action (rename, cycle, ...)
    SELECT = "select"    # Back/Select button
    PREV = "prev"        # shoulder L
    NEXT = "next"        # shoulder R


KEYBOARD = "keyboard"
KEYBOARD2 = "keyboard2"

# Generic key names -> actions (pygame backend translates key codes to names).
DEFAULT_KEY_BINDINGS = {
    "up": Action.UP, "w": Action.UP,
    "down": Action.DOWN, "s": Action.DOWN,
    "left": Action.LEFT, "a": Action.LEFT,
    "right": Action.RIGHT, "d": Action.RIGHT,
    "return": Action.CONFIRM, "space": Action.CONFIRM, "enter": Action.CONFIRM,
    "escape": Action.BACK, "backspace": Action.BACK,
    "tab": Action.START,
    "x": Action.ALT, "f2": Action.SELECT,
    "q": Action.PREV, "page up": Action.PREV,
    "e": Action.NEXT, "page down": Action.NEXT,
}
KEY_BINDINGS = dict(DEFAULT_KEY_BINDINGS)

# Second player on the same keyboard (matches the RetroArch binds Gauntlet writes for that port).
KEYBOARD2_BINDINGS = {
    "i": Action.UP, "k": Action.DOWN, "j": Action.LEFT, "l": Action.RIGHT,
    "u": Action.CONFIRM, "o": Action.BACK, "p": Action.START, "y": Action.ALT,
}

# Gamepad button index -> action (SDL joystick order for XInput-style pads).
DEFAULT_BUTTON_BINDINGS = {0: Action.CONFIRM, 1: Action.BACK, 2: Action.ALT, 3: Action.ALT,
                           4: Action.PREV, 5: Action.NEXT, 6: Action.SELECT, 7: Action.START,
                           9: Action.START}
BUTTON_BINDINGS = dict(DEFAULT_BUTTON_BINDINGS)
HAT_BINDINGS = {(0, 1): Action.UP, (0, -1): Action.DOWN, (-1, 0): Action.LEFT, (1, 0): Action.RIGHT}
AXIS_DEADZONE = 0.6


@dataclass(frozen=True)
class InputEvent:
    device: str  # KEYBOARD, KEYBOARD2 or "pad:<id>"
    action: Action
    key: str = None  # key name for keyboard events (text entry / rebinding)


def pad_device(instance_id):
    return f"pad:{instance_id}"


def is_pad(device):
    return isinstance(device, str) and device.startswith("pad:")


def apply_bindings(key_bindings=None, button_bindings=None):
    """Install user overrides ({name: action-value}) on top of the defaults."""
    KEY_BINDINGS.clear()
    KEY_BINDINGS.update(DEFAULT_KEY_BINDINGS)
    for name, action in (key_bindings or {}).items():
        try:
            KEY_BINDINGS[str(name).lower()] = Action(action)
        except ValueError:
            pass
    BUTTON_BINDINGS.clear()
    BUTTON_BINDINGS.update(DEFAULT_BUTTON_BINDINGS)
    for button, action in (button_bindings or {}).items():
        try:
            BUTTON_BINDINGS[int(button)] = Action(action)
        except ValueError:
            pass


def key_to_action(name):
    return KEY_BINDINGS.get(name)


def key_to_event(name, split_keyboard=False):
    """Key name -> InputEvent (routes keyboard2 keys when the keyboard is split)."""
    if split_keyboard and name in KEYBOARD2_BINDINGS:
        return InputEvent(KEYBOARD2, KEYBOARD2_BINDINGS[name], name)
    action = KEY_BINDINGS.get(name)
    return InputEvent(KEYBOARD, action, name) if action else None


def button_to_action(button):
    return BUTTON_BINDINGS.get(button)


def hat_to_action(value):
    return HAT_BINDINGS.get(tuple(value))


def axis_to_action(axis, value):
    """Left stick: axis 0 horizontal, axis 1 vertical. Returns None inside deadzone."""
    if abs(value) < AXIS_DEADZONE or axis not in (0, 1):
        return None
    if axis == 0:
        return Action.RIGHT if value > 0 else Action.LEFT
    return Action.DOWN if value > 0 else Action.UP


class PlayerSlots:
    """'Press A to join' assignment of devices to player slots (1-4)."""

    def __init__(self, max_players=4):
        if not 1 <= max_players <= 4:
            raise ValueError("max_players must be 1-4")
        self.max_players = max_players
        self.slots = [None] * max_players

    def join(self, device):
        """Returns slot index for device, or None if full. Idempotent."""
        if device in self.slots:
            return self.slots.index(device)
        try:
            slot = self.slots.index(None)
        except ValueError:
            return None
        self.slots[slot] = device
        return slot

    def leave(self, device):
        if device in self.slots:
            self.slots[self.slots.index(device)] = None

    def slot_of(self, device):
        slot = self.slots.index(device) if device in self.slots else None
        return slot if slot is not None and self.slots[slot] is not None else None

    def handle(self, event):
        """Join on CONFIRM, leave on BACK; returns slot or None."""
        if event.action is Action.CONFIRM:
            return self.join(event.device)
        if event.action is Action.BACK:
            self.leave(event.device)
        return None

    def on_disconnect(self, device):
        """Hot-unplug: free the slot (keyboards are never unplugged)."""
        if is_pad(device):
            self.leave(device)
