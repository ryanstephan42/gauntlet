"""Control-hint footer text per device kind (pygame-free)."""
from .inputmap import Action, KEYBOARD

LABELS = {
    "keyboard": {Action.CONFIRM: "Enter", Action.BACK: "Esc", Action.START: "Tab"},
    "pad": {Action.CONFIRM: "A", Action.BACK: "B", Action.START: "Start"},
}


def hint_footer(device, hints):
    """hints: list of (Action, text) -> 'A: Select   B: Back'."""
    kind = "keyboard" if device == KEYBOARD else "pad"
    return "   ".join(f"{LABELS[kind][a]}: {t}" for a, t in hints)
