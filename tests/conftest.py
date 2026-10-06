import pytest


@pytest.fixture(autouse=True)
def no_window_placement(monkeypatch):
    """Never drive the developer's real compositor (Hyprland/Sway) from tests."""
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.delenv("SWAYSOCK", raising=False)


@pytest.fixture(autouse=True)
def no_physical_gamepads(monkeypatch):
    """Keep the developer's real controllers out of UI tests (a held pad button made them flaky)."""
    import pygame

    joy = {getattr(pygame, n) for n in ("JOYAXISMOTION", "JOYBALLMOTION", "JOYHATMOTION", "JOYBUTTONDOWN",
                                         "JOYBUTTONUP", "JOYDEVICEADDED", "JOYDEVICEREMOVED",
                                         "CONTROLLERAXISMOTION", "CONTROLLERBUTTONDOWN", "CONTROLLERBUTTONUP",
                                         "CONTROLLERDEVICEADDED", "CONTROLLERDEVICEREMOVED",
                                         "CONTROLLERDEVICEREMAPPED") if hasattr(pygame, n)}
    real_get = pygame.event.get

    def get(*args, **kwargs):
        return [e for e in real_get(*args, **kwargs) if e.type not in joy]

    monkeypatch.setattr(pygame.event, "get", get)
    monkeypatch.setattr(pygame.joystick, "get_count", lambda: 0)
