"""Central theme: colours and design-unit sizes (see layout.py)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    bg: tuple = (30, 30, 40)
    panel: tuple = (45, 45, 60)
    text: tuple = (255, 255, 255)
    text_dim: tuple = (160, 160, 175)
    accent: tuple = (255, 215, 0)
    focus: tuple = (100, 100, 255)
    good: tuple = (0, 255, 0)
    bad: tuple = (255, 80, 80)
    font_size: int = 36
    padding: int = 16
    toast_seconds: float = 3.0


DEFAULT_THEME = Theme()
