"""Control-hint footer text per device kind (pygame-free)."""
from .inputmap import Action, KEYBOARD, KEYBOARD2

LABELS = {
    "keyboard": {Action.CONFIRM: "Enter", Action.BACK: "Esc", Action.START: "Tab", Action.ALT: "X",
                 Action.SELECT: "F2", Action.PREV: "Q", Action.NEXT: "E", Action.LEFT: "←/→",
                 Action.RIGHT: "→", Action.UP: "↑/↓", Action.DOWN: "↓"},
    "keyboard2": {Action.CONFIRM: "U", Action.BACK: "O", Action.START: "P", Action.ALT: "Y",
                  Action.SELECT: "F2", Action.PREV: "Q", Action.NEXT: "E", Action.LEFT: "J/L",
                  Action.RIGHT: "L", Action.UP: "I/K", Action.DOWN: "K"},
    "pad": {Action.CONFIRM: "A", Action.BACK: "B", Action.START: "Start", Action.ALT: "X",
            Action.SELECT: "Select", Action.PREV: "LB", Action.NEXT: "RB", Action.LEFT: "◀▶",
            Action.RIGHT: "▶", Action.UP: "▲▼", Action.DOWN: "▼"},
}


def hint_footer(device, hints):
    """hints: list of (Action, text) -> 'A: Select   B: Back'."""
    kind = "keyboard" if device in (KEYBOARD, None) else "keyboard2" if device == KEYBOARD2 else "pad"
    return "   ".join(f"{LABELS[kind].get(a, a.value)}: {t}" for a, t in hints)
