"""Memory Lab: RAM search (snapshot + filters) and watch list over the RetroArch client."""
from .memory import LAYOUT_XOR, Var

FILTERS = ("eq", "ne", "gt", "lt", "changed", "unchanged", "increased", "decreased")
MAX_REGION = 0x200000


def logical_bytes(raw, start, layout):
    """Host-order bytes read from host address `start` -> logical-order bytes.
    `start` and len(raw) must be multiples of 4 for swapped layouts."""
    x = LAYOUT_XOR.get(layout, 0)
    if not x:
        return bytes(raw)
    out = bytearray(len(raw))
    for i in range(len(raw)):
        out[i] = raw[i ^ x]
    return bytes(out)


def decode_all(data, size, endian, signed, step=None):
    step = step or size
    return [int.from_bytes(data[i:i + size], endian, signed=signed)
            for i in range(0, len(data) - size + 1, step)]


class RamSearch:
    def __init__(self, client, layout="linear", start=0, length=0x20000, size=1, endian="little",
                 signed=False):
        self.client = client
        self.layout = layout
        self.start = start - start % 4
        self.length = min(MAX_REGION, (length + 3) // 4 * 4)
        self.size, self.endian, self.signed = size, endian, signed
        self.values = None        # value per candidate slot (index -> value)
        self.candidates = None    # list of slot indexes
        self.history = []

    def _read(self):
        raw = self.client.read_bytes(self.start, self.length)
        if raw is None:
            return None
        return decode_all(logical_bytes(raw, self.start, self.layout), self.size, self.endian, self.signed)

    def address_of(self, slot):
        return self.start + slot * self.size

    def reset(self):
        values = self._read()
        if values is None:
            return False
        self.values = values
        self.candidates = list(range(len(values)))
        self.history = [len(self.candidates)]
        return True

    def filter(self, op, value=None):
        if op not in FILTERS:
            raise ValueError(op)
        if self.values is None and not self.reset():
            return None
        new = self._read()
        if new is None:
            return None
        old = self.values
        tests = {
            "eq": lambda i: new[i] == value, "ne": lambda i: new[i] != value,
            "gt": lambda i: new[i] > value, "lt": lambda i: new[i] < value,
            "changed": lambda i: new[i] != old[i], "unchanged": lambda i: new[i] == old[i],
            "increased": lambda i: new[i] > old[i], "decreased": lambda i: new[i] < old[i],
        }
        test = tests[op]
        self.candidates = [i for i in self.candidates if test(i)]
        self.values = new
        self.history.append(len(self.candidates))
        return len(self.candidates)

    def results(self, limit=200):
        return [(self.address_of(i), self.values[i]) for i in self.candidates[:limit]]


class Watch:
    def __init__(self, address, size=1, endian="little", signed=False, label=""):
        self.var = Var(address, size, endian, signed)
        self.label = label or f"0x{address:06X}"
        self.value = None

    def to_spec(self):
        spec = {"address": f"0x{self.var.address:X}", "size": self.var.size}
        if self.var.signed:
            spec["signed"] = True
        return spec
