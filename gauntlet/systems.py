"""Catalog of supported systems: ROM extensions, preferred cores and memory layout.

`layout` describes how the libretro core exposes RAM to READ/WRITE_CORE_MEMORY
(rcheevos address space):
- "linear": logical byte A lives at host address A.
- "swap32": 32-bit words stored host little-endian (N64 RDRAM): byte A at A ^ 3.
- "swap16": 16-bit words byte-swapped (Genesis 68k RAM): byte A at A ^ 1.
`endian` is the console's native multi-byte order, used as the default for values.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class System:
    id: str
    name: str
    extensions: tuple
    cores: tuple
    folders: tuple = ()
    layout: str = "linear"
    endian: str = "little"
    max_players: int = 2
    ram_size: int = 0x10000
    ram_note: str = ""

    @property
    def rom_folders(self):
        return self.folders or (self.id,)


SYSTEMS = {s.id: s for s in (
    System("snes", "Super Nintendo", (".sfc", ".smc", ".zip"),
           ("snes9x", "bsnes", "snes9x2010", "bsnes_hd_beta", "mesen-s"),
           ("snes", "sfc", "snesna"), max_players=4, ram_size=0x20000,
           ram_note="$000000-$01FFFF = WRAM $7E0000-$7FFFFF"),
    System("n64", "Nintendo 64", (".z64", ".n64", ".v64", ".zip"),
           ("mupen64plus_next", "parallel_n64"), ("n64",), layout="swap32",
           endian="big", max_players=4, ram_size=0x800000,
           ram_note="$000000 = RDRAM $80000000"),
    System("nes", "Nintendo Entertainment System", (".nes", ".zip"),
           ("fceumm", "nestopia", "mesen", "quicknes"), ("nes", "famicom"),
           max_players=4, ram_size=0x800),
    System("genesis", "Sega Genesis / Mega Drive", (".md", ".gen", ".bin", ".smd", ".zip"),
           ("genesis_plus_gx", "picodrive", "blastem"), ("genesis", "megadrive"),
           layout="swap16", endian="big", max_players=4, ram_size=0x10000,
           ram_note="$000000 = 68k RAM $FF0000"),
    System("gba", "Game Boy Advance", (".gba", ".zip"), ("mgba", "vba_next", "gpsp"),
           ("gba",), max_players=1, ram_size=0x48000),
    System("gb", "Game Boy", (".gb", ".zip"), ("gambatte", "sameboy", "gearboy", "mgba"),
           ("gb",), max_players=1, ram_size=0x8000),
    System("gbc", "Game Boy Color", (".gbc", ".zip"), ("gambatte", "sameboy", "gearboy", "mgba"),
           ("gbc",), max_players=1, ram_size=0x8000),
    System("sms", "Sega Master System", (".sms", ".zip"), ("genesis_plus_gx", "picodrive", "gearsystem"),
           ("mastersystem", "sms"), max_players=2, ram_size=0x2000),
    System("pce", "PC Engine / TurboGrafx-16", (".pce", ".zip"),
           ("mednafen_pce_fast", "mednafen_pce", "geargrafx"), ("pcengine", "tg16", "pce"),
           max_players=5, ram_size=0x2000),
    System("psx", "PlayStation", (".cue", ".chd", ".pbp", ".m3u", ".iso"),
           ("swanstation", "pcsx_rearmed", "mednafen_psx_hw", "mednafen_psx"), ("psx", "ps1"),
           max_players=4, ram_size=0x200000),
    System("arcade", "Arcade", (".zip", ".7z"), ("fbneo", "mame2003_plus", "mame2010"),
           ("arcade", "fbneo", "mame"), max_players=4, ram_size=0x10000),
)}


def get_system(system_id):
    return SYSTEMS.get(system_id)


def guess_system(path):
    """Guess a system from a ROM path: parent folder name first, then extension."""
    import os
    parts = [p.lower() for p in os.path.normpath(path).split(os.sep)]
    for part in reversed(parts[:-1]):
        for system in SYSTEMS.values():
            if part in system.rom_folders:
                return system.id
    ext = os.path.splitext(path)[1].lower()
    for system in SYSTEMS.values():
        if ext in system.extensions and ext not in (".zip", ".bin", ".7z"):
            return system.id
    return None
