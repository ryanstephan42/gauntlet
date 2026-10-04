"""Detect RetroArch installs, libretro cores and ROM folders."""
import glob
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field

from .systems import SYSTEMS

log = logging.getLogger("gauntlet.detect")

CORE_SUFFIXES = ("_libretro.so", "_libretro.dll", "_libretro.dylib")

RETRODECK_ID = "net.retrodeck.retrodeck"
RETRODECK_RA = "/app/retrodeck/components/retroarch"
LIBRETRO_FLATPAK_ID = "org.libretro.RetroArch"


@dataclass
class Install:
    """A runnable RetroArch. `command` is the argv prefix (before -L ...)."""
    label: str
    command: list
    core_dirs: list = field(default_factory=list)
    sandbox_core_dir: str = ""
    host_core_dir: str = ""
    sandboxed: bool = False

    def core_arg(self, core_path):
        """Translate a host core path to the path seen inside a sandbox."""
        if self.sandboxed and self.host_core_dir and core_path.startswith(self.host_core_dir):
            return self.sandbox_core_dir + core_path[len(self.host_core_dir):]
        return core_path

    def to_dict(self):
        return {"label": self.label, "command": list(self.command), "core_dirs": list(self.core_dirs)}


def _flatpak_files(app_id):
    for base in (os.path.expanduser("~/.local/share/flatpak"), "/var/lib/flatpak"):
        path = os.path.join(base, "app", app_id, "current", "active", "files")
        if os.path.isdir(path):
            return path
    return None


def find_installs(extra_command=None):
    """All detected installs, best first. `extra_command` (list) from settings wins."""
    installs = []
    if extra_command:
        installs.append(Install("Custom", list(extra_command), native_core_dirs()))
    files = _flatpak_files(RETRODECK_ID)
    if files and shutil.which("flatpak"):
        host = os.path.join(files, "retrodeck", "components", "retroarch", "rd_extras", "cores")
        installs.append(Install(
            "RetroDECK (flatpak)",
            ["flatpak", "run", f"--command={RETRODECK_RA}/bin/retroarch", RETRODECK_ID],
            [host], f"{RETRODECK_RA}/rd_extras/cores", host, sandboxed=True))
    files = _flatpak_files(LIBRETRO_FLATPAK_ID)
    if files and shutil.which("flatpak"):
        cores = os.path.expanduser(f"~/.var/app/{LIBRETRO_FLATPAK_ID}/config/retroarch/cores")
        installs.append(Install("RetroArch (flatpak)", ["flatpak", "run", LIBRETRO_FLATPAK_ID], [cores]))
    native = shutil.which("retroarch")
    for candidate in _platform_binaries():
        if not native and os.path.isfile(candidate):
            native = candidate
    if native:
        installs.append(Install("RetroArch", [native], native_core_dirs(native)))
    return installs


def _platform_binaries():
    if sys.platform.startswith("win"):
        return [r"C:\RetroArch-Win64\retroarch.exe", r"C:\RetroArch\retroarch.exe",
                os.path.expandvars(r"%APPDATA%\RetroArch\retroarch.exe")]
    if sys.platform == "darwin":
        return ["/Applications/RetroArch.app/Contents/MacOS/RetroArch"]
    return ["/usr/bin/retroarch", "/usr/local/bin/retroarch"]


def native_core_dirs(binary=None):
    dirs = [os.path.expanduser("~/.config/retroarch/cores"), "/usr/lib/libretro",
            "/usr/lib/x86_64-linux-gnu/libretro", "/usr/local/lib/libretro", "/usr/lib64/libretro",
            os.path.expanduser("~/Library/Application Support/RetroArch/cores")]
    if binary:
        dirs.insert(0, os.path.join(os.path.dirname(binary), "cores"))
    return [d for d in dirs if os.path.isdir(d)]


def list_cores(core_dirs):
    """{core_name: path} for every libretro core found (first dir wins)."""
    cores = {}
    for d in core_dirs:
        for suffix in CORE_SUFFIXES:
            for path in sorted(glob.glob(os.path.join(glob.escape(d), "*" + suffix))):
                name = os.path.basename(path)[: -len(suffix)]
                cores.setdefault(name, path)
    return cores


def find_core(name_or_path, core_dirs):
    """Resolve a core given by path or by short name ('snes9x')."""
    if not name_or_path:
        return None
    if os.path.isabs(name_or_path) or os.sep in name_or_path:
        if os.path.isfile(name_or_path):
            return name_or_path
        name_or_path = os.path.basename(name_or_path)
    name = name_or_path
    for suffix in CORE_SUFFIXES + ("_libretro",):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return list_cores(core_dirs).get(name)


def cores_for_system(system_id, core_dirs):
    """Installed cores suitable for a system, preferred order first."""
    system = SYSTEMS.get(system_id)
    if not system:
        return []
    available = list_cores(core_dirs)
    return [(c, available[c]) for c in system.cores if c in available]


ROM_DIR_CANDIDATES = ("~/retrodeck/roms", "~/RetroPie/roms", "~/ROMs", "~/roms", "~/Games/roms")


def find_rom_dirs(extra=None):
    dirs = []
    for d in ([extra] if extra else []) + [os.path.expanduser(p) for p in ROM_DIR_CANDIDATES]:
        if d and os.path.isdir(d) and d not in dirs:
            dirs.append(d)
    return dirs


def scan_roms(rom_dir, system_id):
    """ROM files for a system inside rom_dir/<system folder>/ (non-recursive + 1 level)."""
    system = SYSTEMS.get(system_id)
    if not system or not rom_dir or not os.path.isdir(rom_dir):
        return []
    found = []
    for folder in system.rom_folders:
        base = os.path.join(rom_dir, folder)
        if not os.path.isdir(base):
            continue
        for pattern in ("*", os.path.join("*", "*")):
            for path in glob.glob(os.path.join(glob.escape(base), pattern)):
                if os.path.isfile(path) and os.path.splitext(path)[1].lower() in system.extensions:
                    found.append(path)
    return sorted(set(found), key=lambda p: os.path.basename(p).lower())


def find_rom(rom, system_id, rom_dirs, base_dir=None):
    """Resolve a ROM given by absolute path, a path relative to a rom dir, or a bare filename."""
    if not rom:
        return None
    rom = os.path.expanduser(rom)
    if os.path.isabs(rom):
        return rom if os.path.isfile(rom) else None
    candidates = []
    system = SYSTEMS.get(system_id)
    for d in rom_dirs:
        candidates.append(os.path.join(d, rom))
        for folder in (system.rom_folders if system else ()):
            candidates.append(os.path.join(d, folder, rom))
            candidates.append(os.path.join(d, folder, os.path.basename(rom)))
    if base_dir:
        candidates.append(os.path.join(base_dir, rom))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None
