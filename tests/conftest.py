import pytest


@pytest.fixture(autouse=True)
def no_window_placement(monkeypatch):
    """Never drive the developer's real compositor (Hyprland/Sway) from tests."""
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.delenv("SWAYSOCK", raising=False)
