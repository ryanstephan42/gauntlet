"""Synthesised UI sound effects (no assets, no numpy). Silently disabled if audio is unavailable."""
import array
import logging
import math

import pygame

log = logging.getLogger("gauntlet.audio")

RATE = 22050

# name -> list of (frequency Hz, duration s); frequency 0 = rest
SOUNDS = {
    "move": [(660, 0.03)],
    "confirm": [(880, 0.05), (1320, 0.06)],
    "back": [(440, 0.05), (330, 0.06)],
    "error": [(200, 0.09), (0, 0.03), (200, 0.09)],
    "buy": [(988, 0.05), (1319, 0.08)],
    "refund": [(784, 0.05), (523, 0.08)],
    "join": [(523, 0.05), (659, 0.05), (784, 0.08)],
    "ready": [(784, 0.06), (1047, 0.1)],
    "start": [(523, 0.08), (659, 0.08), (784, 0.08), (1047, 0.2)],
    "win": [(523, 0.1), (659, 0.1), (784, 0.1), (1047, 0.12), (0, 0.04), (784, 0.08), (1047, 0.3)],
    "draw": [(440, 0.15), (440, 0.15)],
    "tick": [(1200, 0.02)],
    "achievement": [(1047, 0.07), (1319, 0.07), (1568, 0.07), (2093, 0.18)],
}


def synth(notes, volume=0.5):
    """-> 16-bit signed mono samples (array) for a list of (freq, seconds)."""
    out = array.array("h")
    amp = int(32767 * max(0.0, min(1.0, volume)) * 0.6)
    for freq, dur in notes:
        n = int(RATE * dur)
        for i in range(n):
            if freq <= 0:
                out.append(0)
                continue
            env = min(1.0, i / 80) * min(1.0, (n - i) / 200)
            # square-ish wave softened with a sine component: retro but not harsh
            phase = (i * freq / RATE) % 1.0
            v = 0.55 * (1 if phase < 0.5 else -1) + 0.45 * math.sin(2 * math.pi * phase)
            out.append(int(amp * env * v))
    return out


class Audio:
    def __init__(self, enabled=True, volume=0.6):
        self.enabled = False
        self.volume = volume
        self._sounds = {}
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 1, 512)
            freq, _size, channels = pygame.mixer.get_init()
            for name, notes in SOUNDS.items():
                samples = synth(notes)
                if channels == 2:
                    stereo = array.array("h")
                    for s in samples:
                        stereo.extend((s, s))
                    samples = stereo
                self._sounds[name] = pygame.mixer.Sound(buffer=samples.tobytes())
            self.enabled = True
            self.set_volume(volume)
        except (pygame.error, ValueError, TypeError) as e:
            log.info("Audio disabled: %s", e)

    def set_volume(self, volume):
        self.volume = max(0.0, min(1.0, volume))
        for s in self._sounds.values():
            s.set_volume(self.volume)

    def play(self, name):
        if self.enabled and name in self._sounds:
            try:
                self._sounds[name].play()
            except pygame.error:
                pass
