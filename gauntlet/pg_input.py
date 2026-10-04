"""pygame -> InputEvent translation with joystick hot-plug."""
import pygame

from . import inputmap as im


class PygameInput:
    def __init__(self, slots=None):
        self.slots = slots
        self.pads = {}
        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            self._add(i)

    def _add(self, index):
        pad = pygame.joystick.Joystick(index)
        self.pads[pad.get_instance_id()] = pad

    def translate(self, event):
        """Returns an InputEvent or None."""
        t = event.type
        if t == pygame.KEYDOWN:
            action = im.key_to_action(pygame.key.name(event.key))
            return im.InputEvent(im.KEYBOARD, action) if action else None
        if t == pygame.JOYDEVICEADDED:
            self._add(event.device_index)
            return None
        elif t == pygame.JOYDEVICEREMOVED:
            instance_id = getattr(event, "instance_id", None)
            if instance_id is None:
                return None
            self.pads.pop(instance_id, None)
            if self.slots:
                self.slots.on_disconnect(im.pad_device(instance_id))
            return None
        elif t == pygame.JOYBUTTONDOWN:
            action = im.button_to_action(event.button)
        elif t == pygame.JOYHATMOTION:
            action = im.hat_to_action(event.value)
        elif t == pygame.JOYAXISMOTION:
            action = im.axis_to_action(event.axis, event.value)
        else:
            return None
        return im.InputEvent(im.pad_device(event.instance_id), action) if action else None
