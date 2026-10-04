"""Typed values in emulated RAM: size/endian/sign/bitmask encoding and host-layout mapping."""
from dataclasses import dataclass

LAYOUT_XOR = {"linear": 0, "swap16": 1, "swap32": 3}


def parse_int(value):
    """Accept ints or strings like '0x1F', '$1F', '31'."""
    if isinstance(value, bool):
        raise ValueError("boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip().replace("_", "")
        if text.startswith("$"):
            return int(text[1:], 16)
        return int(text, 0)
    raise ValueError(f"not an integer: {value!r}")


def host_address(address, layout="linear"):
    return address ^ LAYOUT_XOR.get(layout, 0)


@dataclass(frozen=True)
class Var:
    """A value in RAM. `address` is in the console's logical (native) byte order."""
    address: int
    size: int = 1
    endian: str = "little"
    signed: bool = False
    mask: int = None
    bit: int = None

    @classmethod
    def from_spec(cls, spec, address=None, defaults=None):
        d = dict(defaults or {})
        d.update({k: v for k, v in spec.items() if v is not None})
        addr = parse_int(address if address is not None else d["address"])
        mask = d.get("mask")
        bit = d.get("bit")
        return cls(addr, int(d.get("size", 1)), d.get("endian", "little"), bool(d.get("signed", False)),
                   parse_int(mask) if mask is not None else None, int(bit) if bit is not None else None)

    def host_addresses(self, layout):
        return [host_address(self.address + i, layout) for i in range(self.size)]

    def decode(self, raw):
        """raw: logical-order bytes -> int (masked/bit-extracted)."""
        value = int.from_bytes(bytes(raw), self.endian, signed=self.signed)
        if self.bit is not None:
            return (int.from_bytes(bytes(raw), self.endian) >> self.bit) & 1
        if self.mask is not None:
            return int.from_bytes(bytes(raw), self.endian) & self.mask
        return value

    def encode(self, value):
        bits = self.size * 8
        lo = -(1 << (bits - 1)) if self.signed else 0
        hi = (1 << (bits - 1)) - 1 if self.signed else (1 << bits) - 1
        value = max(lo, min(hi, int(value)))
        return value.to_bytes(self.size, self.endian, signed=self.signed)

    def merge(self, old_raw, value):
        """Apply value to old bytes honouring bit/mask (read-modify-write)."""
        if self.bit is None and self.mask is None:
            return self.encode(value)
        old = int.from_bytes(bytes(old_raw), self.endian)
        if self.bit is not None:
            new = (old | (1 << self.bit)) if value else (old & ~(1 << self.bit))
        else:
            new = (old & ~self.mask) | (int(value) & self.mask)
        return (new & ((1 << (self.size * 8)) - 1)).to_bytes(self.size, self.endian)

    @property
    def needs_read_for_write(self):
        return self.bit is not None or self.mask is not None


def _runs(pairs):
    """[(host_addr, byte)] -> contiguous [(start, bytes)] runs."""
    runs = []
    for addr, byte in sorted(pairs):
        if runs and runs[-1][0] + len(runs[-1][1]) == addr:
            runs[-1][1].append(byte)
        else:
            runs.append((addr, bytearray([byte])))
    return [(a, bytes(b)) for a, b in runs]


class Memory:
    """Read/write typed Vars through a client exposing read_bytes/write_bytes (host addresses)."""

    def __init__(self, client, layout="linear"):
        self.client = client
        self.layout = layout

    def read_raw(self, var):
        hosts = var.host_addresses(self.layout)
        start, end = min(hosts), max(hosts)
        data = self.client.read_bytes(start, end - start + 1)
        if data is None or len(data) < end - start + 1:
            return None
        return bytes(data[h - start] for h in hosts)

    def read(self, var):
        raw = self.read_raw(var)
        return None if raw is None else var.decode(raw)

    def write(self, var, value):
        """Returns True if every byte was acknowledged."""
        if var.needs_read_for_write:
            old = self.read_raw(var)
            if old is None:
                return False
            raw = var.merge(old, value)
        else:
            raw = var.encode(value)
        ok = True
        for start, chunk in _runs(zip(var.host_addresses(self.layout), raw)):
            written = self.client.write_bytes(start, chunk)
            ok = ok and written == len(chunk)
        return ok


def var_for(spec, port=None, defaults=None):
    """Build a Var from a config spec; per-player addresses ({"1": .., "2": ..}) or a
    stride pick the address for `port` (1-based)."""
    addr = spec["address"]
    if isinstance(addr, dict):
        if str(port) not in addr:
            raise KeyError(f"no address for player {port}")
        address = parse_int(addr[str(port)])
    else:
        address = parse_int(addr)
        if spec.get("stride") is not None and port:
            address += parse_int(spec["stride"]) * (port - 1)
    return Var.from_spec(spec, address=address, defaults=defaults)


def is_per_player(spec):
    return isinstance(spec.get("address"), dict) or spec.get("stride") is not None


def compare(op, actual, expected):
    return {
        "eq": actual == expected, "ne": actual != expected, "ge": actual >= expected,
        "gt": actual > expected, "le": actual <= expected, "lt": actual < expected,
    }[op]
