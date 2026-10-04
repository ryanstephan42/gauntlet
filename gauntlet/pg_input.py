"""pygame -> InputEvent translation with joystick hot-plug, stick edge detection and held state."""
import pygame

from . import inputmap as im


class PygameInput:
    def __init__(self, slots=None, split_keyboard=False):
        self.slots = slots
        self.split_keyboard = split_keyboard
        self.pads = {}
        self.pad_index = {}     # instance id -> device index (RetroArch joypad index)
        self.axis_state = {}    # (instance, axis) -> last emitted action or None
        self.held = {}          # device -> set of held actions
        self.on_disconnect = None
        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            self._add(i)

    def __getattr__(self, name):
        # tolerate partially constructed instances (tests build them with __new__)
        defaults = {"pad_index": dict, "axis_state": dict, "held": dict, "on_disconnect": lambda: None,
                    "split_keyboard": lambda: False}
        if name in defaults:
            value = defaults[name]()
            setattr(self, name, value)
            return value
        raise AttributeError(name)

    def _add(self, index):
        pad = pygame.joystick.Joystick(index)
        self.pads[pad.get_instance_id()] = pad
        self.pad_index[pad.get_instance_id()] = index

    def pad_name(self, device):
        if not im.is_pad(device):
            return "Keyboard" if device == im.KEYBOARD else "Keyboard (right)"
        pad = self.pads.get(int(device.split(":", 1)[1]))
        return pad.get_name() if pad else "Disconnected pad"

    def device_index(self, device):
        if not im.is_pad(device):
            return None
        return self.pad_index.get(int(device.split(":", 1)[1]))

    def is_held(self, device, *actions):
        held = self.held.get(device, set())
        return all(a in held for a in actions)

    def _press(self, device, action):
        self.held.setdefault(device, set()).add(action)
        return im.InputEvent(device, action)

    def translate(self, event):
        """Returns an InputEvent or None."""
        t = event.type
        if t == pygame.KEYDOWN:
            ev = im.key_to_event(pygame.key.name(event.key), self.split_keyboard)
            if ev:
                self.held.setdefault(ev.device, set()).add(ev.action)
            return ev
        if t == pygame.KEYUP:
            ev = im.key_to_event(pygame.key.name(event.key), self.split_keyboard)
            if ev:
                self.held.get(ev.device, set()).discard(ev.action)
            return None
        if t == pygame.JOYDEVICEADDED:
            self._add(event.device_index)
            return None
        if t == pygame.JOYDEVICEREMOVED:
            instance_id = getattr(event, "instance_id", None)
            if instance_id is None:
                return None
            self.pads.pop(instance_id, None)
            self.pad_index.pop(instance_id, None)
            device = im.pad_device(instance_id)
            self.held.pop(device, None)
            if self.slots:
                self.slots.on_disconnect(device)
            if self.on_disconnect:
                self.on_disconnect(device)
            return None
        if t == pygame.JOYBUTTONDOWN:
            action = im.button_to_action(event.button)
            return self._press(im.pad_device(event.instance_id), action) if action else None
        if t == pygame.JOYBUTTONUP:
            action = im.button_to_action(event.button)
            if action:
                self.held.get(im.pad_device(event.instance_id), set()).discard(action)
            return None
        if t == pygame.JOYHATMOTION:
            action = im.hat_to_action(event.value)
            return im.InputEvent(im.pad_device(event.instance_id), action) if action else None
        if t == pygame.JOYAXISMOTION:
            key = (event.instance_id, event.axis)
            action = im.axis_to_action(event.axis, event.value)
            if action == self.axis_state.get(key):
                return None  # still held in the same direction: no repeat spam
            self.axis_state[key] = action
            return im.InputEvent(im.pad_device(event.instance_id), action) if action else None
        return None
