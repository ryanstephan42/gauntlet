"""Main pygame application: one loop, a screen stack, modal overlays, toasts, mouse + pads + keyboard."""
import logging
import os

import pygame

from .. import inputmap as im
from ..games import load_games
from ..retroarch import Launcher
from ..screens import ScreenManager
from ..stats import Stats
from ..theme import DEFAULT_THEME
from .audio import Audio
from .base import ChoiceOverlay, TextOverlay, ToastLayer
from .render import Painter

log = logging.getLogger("gauntlet.ui")

# Keep receiving controller events while RetroArch has focus (forfeit combo during matches).
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")


class App:
    def __init__(self, settings, launcher=None, size=None, audio=True, settings_path=None):
        self.settings = settings
        self.settings_path = settings_path
        self.theme = DEFAULT_THEME
        im.apply_bindings(settings.key_bindings, settings.button_bindings)
        pygame.init()
        pygame.display.set_caption("Gauntlet")
        self.size = size
        self.screen = None
        self.apply_display()
        self.painter = Painter(self.screen, self.theme, settings.tv_mode)
        self.audio_allowed = audio
        self.audio = Audio(audio and settings.sound, settings.volume)
        from ..pg_input import PygameInput
        self.input = PygameInput(split_keyboard=settings.split_keyboard)
        self.input.on_disconnect = self._pad_disconnected
        self.manager = ScreenManager(fade_seconds=0.12)
        self.overlays = []
        self.toasts = ToastLayer(self, self.theme.toast_seconds)
        self.launcher = launcher if launcher is not None else Launcher(settings)
        self.stats = Stats(os.path.join(settings.state_path, "stats.json"))
        self.games, self.problems = [], {}
        self.reload_games()
        self.last_device = im.KEYBOARD
        self.time = 0.0
        self.running = True
        self.clock = pygame.time.Clock()
        self._injected = []
        self._health = {}
        pygame.key.start_text_input()

    # -- display ---------------------------------------------------------------------------
    def apply_display(self):
        st = self.settings
        if self.size:
            self.screen = pygame.display.set_mode(self.size)
        elif st.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((st.width, st.height), pygame.RESIZABLE)
        if getattr(self, "painter", None):
            self.painter.set_surface(self.screen)
            self.painter.tv_mode = st.tv_mode

    # -- data ----------------------------------------------------------------------------------
    def reload_games(self):
        self.games, self.problems = load_games(self.settings.data_path)
        self._health = {}
        return self.games

    def game_by_file(self, filename):
        return next((g for g in self.games if g["_file"] == filename), None)

    def health(self, game):
        """Cached list of launch problems (missing core/ROM/RetroArch)."""
        key = game["_file"]
        if key not in self._health:
            try:
                self._health[key] = self.launcher.resolve(game)[2]
            except Exception as e:  # never let detection crash the UI
                self._health[key] = [str(e)]
        return self._health[key]

    def clear_health(self):
        self._health = {}

    @property
    def session_path(self):
        return os.path.join(self.settings.sub_state("sessions"), "current.json")

    def assets_dir(self):
        return self.settings.assets_path

    def image_path(self, game):
        image = game["meta"].get("image")
        return os.path.join(self.settings.assets_path, image) if image else None

    def save_settings(self):
        from ..settings import save_settings
        try:
            save_settings(self.settings, self.settings_path or "settings.json")
        except OSError as e:
            self.toasts.show(f"Could not save settings: {e}")

    # -- overlays -----------------------------------------------------------------------------
    def choose(self, message, options, on_result, title="", cancel_value=None):
        ov = ChoiceOverlay(self, message, options, on_result, title, cancel_value)
        self.overlays.append(ov)
        return ov

    def confirm(self, message, on_yes, yes="Yes", no="No", title=""):
        return self.choose(message, [yes, no], lambda r: on_yes() if r == yes else None, title)

    def alert(self, message, title="", on_close=None):
        return self.choose(message, ["OK"], lambda _r: on_close() if on_close else None, title)

    def text_input(self, title, text, on_done, max_len=24):
        ov = TextOverlay(self, title, text, on_done, max_len)
        self.overlays.append(ov)
        return ov

    def _pad_disconnected(self, device):
        self.toasts.show(f"Controller disconnected ({device})")
        cur = self.manager.current
        if cur and hasattr(cur, "on_disconnect"):
            cur.on_disconnect(device)

    # -- events --------------------------------------------------------------------------------
    def inject(self, event):
        """Queue an InputEvent (tests / automation)."""
        self._injected.append(event)

    def dispatch(self, event):
        if event is None or event.action is None:
            return
        self.last_device = event.device
        if self.overlays:
            self.overlays[-1].handle(event)
            self.overlays = [o for o in self.overlays if not o.closed]
            return
        self.manager.handle(event)

    def _text_mode(self):
        return bool(self.overlays) and self.overlays[-1].wants_text

    def process(self, ev):
        if ev.type == pygame.QUIT:
            self.quit()
            return
        if ev.type == pygame.VIDEORESIZE and not self.settings.fullscreen and not self.size:
            self.screen = pygame.display.get_surface()
            self.painter.set_surface(self.screen)
            return
        cur = self.manager.current
        if getattr(cur, "capture_raw", False) and not self.overlays and ev.type in (
                pygame.KEYDOWN, pygame.JOYBUTTONDOWN):
            cur.capture(ev)
            return
        if ev.type == pygame.TEXTINPUT:
            if self._text_mode():
                self.overlays[-1].type_text(ev.text)
            return
        if ev.type == pygame.MOUSEBUTTONDOWN:
            if ev.button == 1:
                payload = self.painter.hit_test(ev.pos)
                if callable(payload):
                    self.last_device = im.KEYBOARD
                    payload()
                    self.overlays = [o for o in self.overlays if not o.closed]
            elif ev.button == 3:
                self.dispatch(im.InputEvent(im.KEYBOARD, im.Action.BACK))
            return
        if ev.type == pygame.MOUSEWHEEL:
            action = im.Action.UP if ev.y > 0 else im.Action.DOWN
            self.dispatch(im.InputEvent(im.KEYBOARD, action))
            return
        translated = self.input.translate(ev)
        if translated is None:
            return
        if self._text_mode() and ev.type == pygame.KEYDOWN and translated.device in (im.KEYBOARD, im.KEYBOARD2):
            name = translated.key or ""
            if len(name) == 1 or name == "space":
                return  # typed characters arrive as TEXTINPUT
            if translated.device == im.KEYBOARD2:
                return
        self.dispatch(translated)

    # -- loop ------------------------------------------------------------------------------------
    def step(self, dt):
        for ev in pygame.event.get():
            self.process(ev)
            if not self.running:
                return
        while self._injected:
            self.dispatch(self._injected.pop(0))
        self.time += dt
        self.manager.update(dt)
        for o in self.overlays:
            o.update(dt)
        self.toasts.update(dt)
        if not self.manager.current and not self.manager._pending:
            self.running = False
            return
        self.draw()

    def draw(self):
        p = self.painter
        p.begin_frame()
        self.manager.draw(self.screen)
        if self.manager.fade > 0:
            p.dim(int(255 * self.manager.fade))
        for o in self.overlays:
            o.draw(p)
        self.toasts.draw(p)
        pygame.display.flip()

    def run(self, first_screen):
        self.manager.push(first_screen(self) if isinstance(first_screen, type) else first_screen)
        self.manager.update(1.0)
        while self.running:
            busy = getattr(self.manager.current, "low_fps", False)
            dt = self.clock.tick(20 if busy else 60) / 1000.0
            self.step(min(dt, 0.1))
        self.shutdown()

    def quit(self):
        self.running = False

    def shutdown(self):
        """Exit cleanly: stop matches (kills RetroArch), save state."""
        for screen in reversed(self.manager.stack):
            try:
                screen.on_exit()
            except Exception:
                log.exception("Error while closing %s", type(screen).__name__)
        self.manager.stack.clear()
        try:
            self.stats.save()
        except OSError:
            pass
        pygame.quit()
