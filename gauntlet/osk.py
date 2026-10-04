"""On-screen keyboard model for gamepad text entry (pygame-free)."""
from .inputmap import Action

ROWS = ["ABCDEFGHI", "JKLMNOPQR", "STUVWXYZ_", "123456789", "0.-"]
SPECIALS = ["SPACE", "DEL", "DONE"]


class OnScreenKeyboard:
    def __init__(self, text="", max_len=16):
        self.text = text[:max_len]
        self.max_len = max_len
        self.row = 0
        self.col = 0
        self.done = False
        self.cancelled = False

    def _row_len(self):
        return len(SPECIALS) if self.row == len(ROWS) else len(ROWS[self.row])

    def _clamp(self):
        self.col = min(self.col, self._row_len() - 1)

    @property
    def focused(self):
        return SPECIALS[self.col] if self.row == len(ROWS) else ROWS[self.row][self.col]

    def handle(self, action):
        if action is Action.UP:
            self.row = (self.row - 1) % (len(ROWS) + 1)
            self._clamp()
        elif action is Action.DOWN:
            self.row = (self.row + 1) % (len(ROWS) + 1)
            self._clamp()
        elif action is Action.LEFT:
            self.col = (self.col - 1) % self._row_len()
        elif action is Action.RIGHT:
            self.col = (self.col + 1) % self._row_len()
        elif action is Action.CONFIRM:
            self._press(self.focused)
        elif action is Action.BACK:
            self.text = self.text[:-1]
        elif action is Action.START:
            self.done = True
        return self.text

    def _press(self, key):
        if key == "DONE":
            self.done = True
        elif key == "DEL":
            self.text = self.text[:-1]
        elif len(self.text) < self.max_len:
            self.text += " " if key == "SPACE" else key
