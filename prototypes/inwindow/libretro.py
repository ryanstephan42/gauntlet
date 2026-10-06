"""Prototype (plan Phase 7.4): a minimal ctypes libretro frontend so Gauntlet could run cores itself.

Not wired into Gauntlet. It loads a core, runs frames on demand and hands back the picture, audio and
system RAM, which is enough to put several games and the scoreboard in one window.
Each Core copies the .so to a private file first: libretro cores keep global state, and dlopen would
return the same handle for the same path, so two instances of one core need two copies.
"""
import ctypes as C
import os
import shutil
import struct
import tempfile
import time
import zlib

EXPERIMENTAL = 0x10000
ENV_GET_CAN_DUPE = 3
ENV_SET_PERFORMANCE_LEVEL = 8
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_SET_HW_RENDER = 14
ENV_GET_VARIABLE = 15
ENV_GET_VARIABLE_UPDATE = 17
ENV_GET_LOG_INTERFACE = 27
ENV_GET_SAVE_DIRECTORY = 31
ENV_GET_INPUT_BITMASKS = 51 | EXPERIMENTAL
ENV_GET_CORE_OPTIONS_VERSION = 52

DEVICE_JOYPAD = 1
JOYPAD_MASK = 256
MEMORY_SYSTEM_RAM = 2
# RETRO_DEVICE_ID_JOYPAD_* bit numbers
B, Y, SELECT, START, UP, DOWN, LEFT, RIGHT, A, X, L, R = range(12)

PIXEL_0RGB1555, PIXEL_XRGB8888, PIXEL_RGB565 = 0, 1, 2

env_t = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
video_t = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
sample_t = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
batch_t = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
poll_t = C.CFUNCTYPE(None)
state_t = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
log_t = C.CFUNCTYPE(None, C.c_int, C.c_char_p)  # really variadic; only the format string is printed


class SystemInfo(C.Structure):
    _fields_ = [("library_name", C.c_char_p), ("library_version", C.c_char_p),
                ("valid_extensions", C.c_char_p), ("need_fullpath", C.c_bool), ("block_extract", C.c_bool)]


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


class Geometry(C.Structure):
    _fields_ = [("base_width", C.c_uint), ("base_height", C.c_uint), ("max_width", C.c_uint),
                ("max_height", C.c_uint), ("aspect_ratio", C.c_float)]


class Timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


class Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class LogCallback(C.Structure):
    _fields_ = [("log", log_t)]


class CoreError(RuntimeError):
    pass


def read_state(path):
    """The core's serialize blob from a RetroArch .state file (optionally RZIP-compressed, RASTATE-wrapped)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:6] == b"#RZIPv":
        total, = struct.unpack_from("<Q", data, 12)
        out, p = bytearray(), 20
        while p < len(data):
            n, = struct.unpack_from("<I", data, p)
            out += zlib.decompress(data[p + 4:p + 4 + n])
            p += 4 + n
        if len(out) != total:
            raise CoreError(f"{path}: RZIP says {total} bytes, got {len(out)}")
        data = bytes(out)
    if data[:7] == b"RASTATE":
        p = 8
        while p + 8 <= len(data):
            tag, n = data[p:p + 4], struct.unpack_from("<I", data, p + 4)[0]
            if tag == b"MEM ":
                return data[p + 8:p + 8 + n]
            p += 8 + ((n + 7) & ~7)
        raise CoreError(f"{path}: no MEM chunk")
    return data


class Core:
    def __init__(self, so_path, system_dir=None, options=None, verbose=False):
        self._tmp = tempfile.mkdtemp(prefix="gauntlet-core-")
        private = os.path.join(self._tmp, os.path.basename(so_path))
        shutil.copyfile(so_path, private)
        self.lib = C.CDLL(private)
        self.system_dir = (system_dir or self._tmp).encode()
        self._sysdir = C.c_char_p(self.system_dir)
        self.options = {k.encode(): v.encode() for k, v in (options or {}).items()}
        self.verbose = verbose
        self.pixel_format = PIXEL_0RGB1555
        self.frame = None          # (bytes, width, height, pitch) of the last picture
        self.audio = bytearray()   # interleaved s16 stereo since the last take_audio()
        self.buttons = 0           # RETRO_DEVICE_ID_JOYPAD_* bitmask for port 0
        self.hw_render_requested = False
        self.loaded = False
        self._log_cb = log_t(self._log)
        self._log_struct = LogCallback(self._log_cb)
        self._cbs = [env_t(self._env), video_t(self._video), sample_t(self._sample), batch_t(self._batch),
                     poll_t(self._poll), state_t(self._input)]
        L = self.lib
        L.retro_api_version.restype = C.c_uint
        if L.retro_api_version() != 1:
            raise CoreError("unsupported libretro API version")
        L.retro_set_environment(self._cbs[0])
        L.retro_set_video_refresh(self._cbs[1])
        L.retro_set_audio_sample(self._cbs[2])
        L.retro_set_audio_sample_batch(self._cbs[3])
        L.retro_set_input_poll(self._cbs[4])
        L.retro_set_input_state(self._cbs[5])
        L.retro_init()
        info = SystemInfo()
        L.retro_get_system_info(C.byref(info))
        self.name = (info.library_name or b"?").decode()
        self.version = (info.library_version or b"?").decode()
        self.need_fullpath = info.need_fullpath
        L.retro_load_game.restype = C.c_bool
        L.retro_serialize_size.restype = C.c_size_t
        L.retro_unserialize.restype = C.c_bool
        L.retro_unserialize.argtypes = [C.c_void_p, C.c_size_t]
        L.retro_serialize.restype = C.c_bool
        L.retro_serialize.argtypes = [C.c_void_p, C.c_size_t]
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.restype = C.c_size_t

    # -- callbacks ----------------------------------------------------------------------------
    def _log(self, level, fmt):
        if self.verbose and fmt:
            print(f"[{self.name}] {fmt.decode(errors='replace').rstrip()}")

    def _env(self, cmd, data):
        if cmd == ENV_GET_CAN_DUPE:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd in (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_SAVE_DIRECTORY):
            C.cast(data, C.POINTER(C.c_char_p))[0] = self._sysdir
            return True
        if cmd == ENV_SET_PIXEL_FORMAT:
            fmt = C.cast(data, C.POINTER(C.c_int))[0]
            if fmt not in (PIXEL_0RGB1555, PIXEL_XRGB8888, PIXEL_RGB565):
                return False
            self.pixel_format = fmt
            return True
        if cmd == ENV_GET_VARIABLE:
            var = Variable.from_address(data)
            value = self.options.get(var.key)
            if value is None:
                return False
            var.value = value  # points into the bytes kept alive in self.options
            return True
        if cmd == ENV_GET_VARIABLE_UPDATE:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == ENV_GET_LOG_INTERFACE:
            C.cast(data, C.POINTER(LogCallback))[0] = self._log_struct
            return True
        if cmd == ENV_GET_INPUT_BITMASKS:
            return True
        if cmd == ENV_GET_CORE_OPTIONS_VERSION:
            C.cast(data, C.POINTER(C.c_uint))[0] = 0
            return True
        if cmd == ENV_SET_PERFORMANCE_LEVEL:
            return True
        if cmd == ENV_SET_HW_RENDER:
            self.hw_render_requested = True
            return False  # no GL context in this prototype
        return False

    def _video(self, data, width, height, pitch):
        if data:  # NULL = same picture as last frame
            self.frame = (C.string_at(data, pitch * height), width, height, pitch)

    def _sample(self, left, right):
        self.audio += struct.pack("<hh", left, right)

    def _batch(self, data, frames):
        self.audio += C.string_at(data, frames * 4)
        return frames

    def _poll(self):
        pass

    def _input(self, port, device, index, id_):
        if port != 0 or device != DEVICE_JOYPAD:
            return 0
        if id_ == JOYPAD_MASK:
            return self.buttons
        return (self.buttons >> id_) & 1

    # -- API ----------------------------------------------------------------------------------
    def load(self, rom_path):
        with open(rom_path, "rb") as f:
            rom = f.read()
        self._rom_buf = C.create_string_buffer(rom, len(rom))
        game = GameInfo(rom_path.encode(), None if self.need_fullpath else C.cast(self._rom_buf, C.c_void_p),
                        0 if self.need_fullpath else len(rom), None)
        if not self.lib.retro_load_game(C.byref(game)):
            raise CoreError(f"{self.name} could not load {rom_path}"
                            + (" (it wants a hardware GL context)" if self.hw_render_requested else ""))
        self.loaded = True
        av = AVInfo()
        self.lib.retro_get_system_av_info(C.byref(av))
        self.fps, self.sample_rate = av.timing.fps, av.timing.sample_rate
        self.geometry = (av.geometry.base_width, av.geometry.base_height, av.geometry.aspect_ratio)

    def run(self):
        self.lib.retro_run()

    def load_state(self, blob):
        buf = C.create_string_buffer(bytes(blob), len(blob))
        if not self.lib.retro_unserialize(buf, len(blob)):
            raise CoreError(f"{self.name} rejected the state ({len(blob)} bytes, "
                            f"core expects {self.lib.retro_serialize_size()})")

    def save_state(self):
        n = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(n)
        if not self.lib.retro_serialize(buf, n):
            raise CoreError("serialize failed")
        return buf.raw

    def ram(self):
        """Live view of system RAM (SNES: the 128 KB WRAM at $7E0000); reads cost nothing, writes poke the game."""
        size = self.lib.retro_get_memory_size(MEMORY_SYSTEM_RAM)
        ptr = self.lib.retro_get_memory_data(MEMORY_SYSTEM_RAM)
        if not ptr or not size:
            return None
        return (C.c_uint8 * size).from_address(ptr)

    def take_audio(self):
        out, self.audio = bytes(self.audio), bytearray()
        return out

    def close(self):
        if self.loaded:
            self.lib.retro_unload_game()
            self.loaded = False
        self.lib.retro_deinit()
        shutil.rmtree(self._tmp, ignore_errors=True)


def to_surface(pygame, frame, pixel_format):
    """A pygame Surface over the core's picture (no per-pixel Python work)."""
    data, w, h, pitch = frame
    if pixel_format == PIXEL_XRGB8888:  # the X byte is garbage, so no alpha mask
        surf = pygame.Surface((pitch // 4, h), depth=32, masks=(0xFF0000, 0xFF00, 0xFF, 0))
    else:
        masks = (0xF800, 0x07E0, 0x001F, 0) if pixel_format == PIXEL_RGB565 else (0x7C00, 0x03E0, 0x001F, 0)
        surf = pygame.Surface((pitch // 2, h), depth=16, masks=masks)
    surf.get_buffer().write(data)
    return surf.subsurface((0, 0, w, h))


class Stopwatch:
    def __init__(self):
        self.samples = []

    def __enter__(self):
        self._t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.samples.append((time.perf_counter() - self._t) * 1000)

    def summary(self):
        s = sorted(self.samples)
        if not s:
            return "n/a"
        return f"mean {sum(s) / len(s):.2f} ms, p95 {s[int(len(s) * 0.95)]:.2f} ms, max {s[-1]:.2f} ms"
