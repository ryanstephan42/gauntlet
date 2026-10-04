"""RetroArch UDP network-command client and process launcher.

Verified against RetroArch 1.22.2:
  GET_STATUS            -> "GET_STATUS PLAYING <system>,<content>,crc32=<hex>" | PAUSED | CONTENTLESS
  READ_CORE_MEMORY a n  -> "READ_CORE_MEMORY <a> XX XX .." | "READ_CORE_MEMORY <a> -1 <error>"
  WRITE_CORE_MEMORY a XX [XX..] -> "WRITE_CORE_MEMORY <a> <count>" | "... -1 <error>"
  SHOW_MSG/PAUSE_TOGGLE/QUIT/RESET/FAST_FORWARD/...: no reply.
Addresses use the rcheevos memory map of the loaded core.
"""
import logging
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass

from .detect import find_core, find_installs, find_rom, find_rom_dirs

log = logging.getLogger("gauntlet.retroarch")

# Hotkey commands that RetroArch accepts over the network (no reply).
COMMANDS = {
    "FAST_FORWARD", "FAST_FORWARD_HOLD", "SLOWMOTION", "SLOWMOTION_HOLD", "REWIND", "PAUSE_TOGGLE",
    "FRAMEADVANCE", "RESET", "SCREENSHOT", "MUTE", "VOLUME_UP", "VOLUME_DOWN", "SHADER_NEXT",
    "SHADER_PREV", "SHADER_TOGGLE", "CHEAT_TOGGLE", "STATE_SLOT_PLUS", "STATE_SLOT_MINUS",
    "SAVE_STATE", "LOAD_STATE", "FULLSCREEN_TOGGLE", "GRAB_MOUSE_TOGGLE", "MENU_TOGGLE",
    "OVERLAY_NEXT", "AI_SERVICE", "QUIT",
}


@dataclass
class Status:
    state: str
    system: str = ""
    content: str = ""
    crc: str = ""

    @property
    def running(self):
        return self.state in ("PLAYING", "PAUSED")


def parse_status(reply):
    if not reply:
        return None
    parts = reply.split(None, 2)
    if len(parts) < 2 or parts[0] != "GET_STATUS":
        return None
    status = Status(parts[1].upper())
    if len(parts) == 3:
        fields = parts[2].split(",")
        if fields and fields[-1].startswith("crc32="):
            status.crc = fields.pop()[6:]
        if fields:
            status.system = fields[0]
            status.content = ",".join(fields[1:])
    return status


class RetroArchClient:
    """Thread-safe UDP client. One socket; stale replies are drained before each request."""

    def __init__(self, host="127.0.0.1", port=55355, timeout=0.5, chunk=1024, retries=1):
        self.addr = (host, port)
        self.timeout = timeout
        self.chunk = chunk
        self.retries = retries
        self._sock = None
        self._lock = threading.Lock()

    def close(self):
        with self._lock:
            if self._sock:
                self._sock.close()
                self._sock = None

    def _socket(self):
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return self._sock

    def _drain(self, sock):
        sock.setblocking(False)
        try:
            while True:
                sock.recvfrom(65536)
        except (BlockingIOError, OSError):
            pass
        finally:
            sock.setblocking(True)

    def send(self, command, expect_reply=True, reply_prefix=None):
        """Send a command; returns reply text, "" when no reply expected, None on failure."""
        prefix = reply_prefix or command.split(" ", 1)[0]
        with self._lock:
            for _attempt in range(self.retries + 1 if expect_reply else 1):
                try:
                    sock = self._socket()
                    self._drain(sock)
                    sock.settimeout(self.timeout)
                    sock.sendto(command.encode(), self.addr)
                    if not expect_reply:
                        return ""
                    deadline = time.monotonic() + self.timeout
                    while True:
                        sock.settimeout(max(0.01, deadline - time.monotonic()))
                        text = sock.recvfrom(65536)[0].decode(errors="replace").strip()
                        if text.startswith(prefix):
                            return text
                except (OSError, socket.timeout) as e:
                    log.debug("UDP %r failed: %s", command[:60], e)
                    if isinstance(e, ConnectionRefusedError):
                        # ICMP port unreachable: nobody listening; drop socket state
                        self._sock = None
            return None

    # -- status ---------------------------------------------------------------
    def version(self):
        reply = self.send("VERSION", reply_prefix="")
        return reply if reply and reply[0].isdigit() else None

    def status(self):
        return parse_status(self.send("GET_STATUS"))

    def is_ready(self):
        status = parse_status(self.send("GET_STATUS"))
        return bool(status and status.running)

    def wait_until_ready(self, timeout=30.0, interval=0.5, process=None, cancel=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                return False
            if cancel is not None and cancel.is_set():
                return False
            if self.is_ready():
                return True
            time.sleep(interval)
        return False

    # -- memory ---------------------------------------------------------------
    def read_bytes(self, address, length):
        out = bytearray()
        while len(out) < length:
            n = min(self.chunk, length - len(out))
            part = self._read_chunk(address + len(out), n)
            if part is None:
                return None
            out += part
        return bytes(out)

    def _read_chunk(self, address, length):
        reply = self.send(f"READ_CORE_MEMORY {address:x} {length}")
        if not reply:
            return None
        parts = reply.split()
        if len(parts) < 3 or parts[2] == "-1":
            log.debug("read %x failed: %s", address, reply)
            return None
        try:
            return bytes(int(b, 16) for b in parts[2:])
        except ValueError:
            return None

    def write_bytes(self, address, data):
        """Returns number of bytes written (acknowledged or verified), or None."""
        data = bytes(data)
        total = 0
        for offset in range(0, len(data), self.chunk):
            part = data[offset:offset + self.chunk]
            addr = address + offset
            hexbytes = " ".join(f"{b:02X}" for b in part)
            reply = self.send(f"WRITE_CORE_MEMORY {addr:x} {hexbytes}")
            if reply:
                fields = reply.split()
                if len(fields) >= 3 and fields[2] != "-1":
                    total += len(part)
                    continue
                log.debug("write %x failed: %s", addr, reply)
                return None
            # Older RetroArch versions do not acknowledge writes: verify by reading back.
            if self._read_chunk(addr, len(part)) == part:
                total += len(part)
            else:
                return None
        return total

    # Backwards-compatible helpers (hex string addresses)
    def read_memory(self, address_hex, length=1):
        data = self.read_bytes(int(address_hex, 16), length)
        return None if data is None else list(data)

    def write_memory(self, address_hex, value):
        value = int(value)
        size = max(1, (value.bit_length() + 7) // 8)
        return self.write_bytes(int(address_hex, 16), value.to_bytes(size, "little")) is not None

    # -- commands -------------------------------------------------------------
    def command(self, name):
        name = name.strip().upper()
        if name.split(" ")[0] not in COMMANDS:
            raise ValueError(f"unknown RetroArch command {name!r}")
        self.send(name, expect_reply=False)

    def show_msg(self, text):
        text = " ".join(str(text).split())[:200]
        self.send(f"SHOW_MSG {text}", expect_reply=False)

    def pause_toggle(self):
        self.send("PAUSE_TOGGLE", expect_reply=False)

    def quit(self):
        for _ in range(2):
            self.send("QUIT", expect_reply=False)
            time.sleep(0.1)


def resolve_ra_config(config_file, config_dir):
    return os.path.join(config_dir, config_file)


def read_cfg(path):
    """Parse a RetroArch .cfg file into {key: value}."""
    values = {}
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def write_cfg(path, values):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for key, value in values.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            f.write(f'{key} = "{value}"\n')
    os.replace(tmp, path)


class Launcher:
    """Resolves cores/ROMs and starts RetroArch with a Gauntlet-owned appended config."""

    def __init__(self, settings, installs=None):
        self.settings = settings
        extra = settings.retroarch_command or ([settings.retroarch_path] if settings.retroarch_path else None)
        self.installs = installs if installs is not None else find_installs(extra)

    @property
    def install(self):
        return self.installs[0] if self.installs else None

    @property
    def core_dirs(self):
        dirs = [os.path.expanduser(self.settings.core_dir)] if self.settings.core_dir else []
        for inst in self.installs[:1]:
            dirs += [d for d in inst.core_dirs if d not in dirs]
        return dirs

    @property
    def rom_dirs(self):
        rom_dir = os.path.expanduser(self.settings.rom_dir) if self.settings.rom_dir else None
        return find_rom_dirs(rom_dir)

    def resolve(self, game):
        """-> (core_path, rom_path, errors)."""
        meta = game["meta"]
        errors = []
        if not self.install:
            errors.append("RetroArch not found (set retroarch_command in settings)")
        core = find_core(meta.get("core"), self.core_dirs)
        if not core:
            errors.append(f"core not found: {meta.get('core')}")
        rom = find_rom(meta.get("rom"), meta.get("system"), self.rom_dirs, self.settings.data_path)
        if not rom:
            errors.append(f"ROM not found: {meta.get('rom')}")
        return core, rom, errors

    def base_config(self):
        st = self.settings
        return {
            "network_cmd_enable": True,
            "network_cmd_port": st.retroarch_port,
            "config_save_on_exit": False,
            "pause_nonactive": False,
            "quit_press_twice": False,
            "savefile_directory": st.sub_state("saves"),
            "savestate_directory": st.sub_state("states"),
            "screenshot_directory": st.sub_state("screenshots"),
            "video_fullscreen": st.fullscreen,
        }

    def write_config(self, name, extra=None):
        cfg = self.base_config()
        cfg.update(extra or {})
        path = os.path.join(self.settings.sub_state("retroarch"), f"{name}.cfg")
        write_cfg(path, cfg)
        return path

    def command(self, core, rom, cfg_path):
        inst = self.install
        return list(inst.command) + ["-L", inst.core_arg(core), rom, "--appendconfig", cfg_path]

    def launch(self, core, rom, cfg_path):
        cmd = self.command(core, rom, cfg_path)
        log.info("Launching: %s", cmd)
        logfile = open(os.path.join(self.settings.sub_state("logs"), "retroarch.log"), "ab")
        try:
            return subprocess.Popen(cmd, stdout=logfile, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL)
        finally:
            logfile.close()

    def client(self, **kw):
        return RetroArchClient(self.settings.retroarch_host, self.settings.retroarch_port, **kw)
