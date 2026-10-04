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


KEYBOARD = "keyboard"

# Generic key names -> actions (pygame backend translates key codes to names).
KEY_BINDINGS = {
    "up": Action.UP, "w": Action.UP,
    "down": Action.DOWN, "s": Action.DOWN,
    "left": Action.LEFT, "a": Action.LEFT,
    "right": Action.RIGHT, "d": Action.RIGHT,
    "return": Action.CONFIRM, "space": Action.CONFIRM,
    "escape": Action.BACK, "backspace": Action.BACK,
    "tab": Action.START,
}

# Gamepad button index -> action (SDL game-controller style: A, B, ..., Start).
BUTTON_BINDINGS = {0: Action.CONFIRM, 1: Action.BACK, 7: Action.START, 9: Action.START}
HAT_BINDINGS = {(0, 1): Action.UP, (0, -1): Action.DOWN, (-1, 0): Action.LEFT, (1, 0): Action.RIGHT}
AXIS_DEADZONE = 0.6


@dataclass(frozen=True)
class InputEvent:
    device: str  # KEYBOARD or "pad:<id>"
    action: Action


def pad_device(instance_id):
    return f"pad:{instance_id}"


def key_to_action(name):
    return KEY_BINDINGS.get(name)


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
        self.slots = []

    def join(self, device):
        """Returns slot index for device, or None if full. Idempotent."""
        if device in self.slots:
            return self.slots.index(device)
        if len(self.slots) >= self.max_players:
            return None
        self.slots.append(device)
        return len(self.slots) - 1

    def leave(self, device):
        if device in self.slots:
            self.slots.remove(device)

    def slot_of(self, device):
        return self.slots.index(device) if device in self.slots else None

    def handle(self, event):
        """Join on CONFIRM, leave on BACK; returns slot or None."""
        if event.action is Action.CONFIRM:
            return self.join(event.device)
        if event.action is Action.BACK:
            self.leave(event.device)
        return None

    def on_disconnect(self, device):
        """Hot-unplug: free the slot (keyboard is never unplugged)."""
        if device != KEYBOARD:
            self.leave(device)
