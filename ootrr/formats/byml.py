"""Lecture et écriture des fichiers BYML (versions 2 à 7, little ou big endian).

Les types numériques sont conservés exactement grâce à des sous-classes :
  int    -> 0xD1 (int32)      Float  -> 0xD2 (float32, la valeur par défaut des float)
  U32    -> 0xD3 (uint32)     F64    -> 0xD6 (double)
  I64    -> 0xD4 (int64)      U64    -> 0xD5 (uint64)
  Binary -> 0xA1, FileData -> 0xA2, HashDict -> 0x20/0x21
"""

from __future__ import annotations

import struct
from typing import Any


class U32(int):
    pass


class I64(int):
    pass


class U64(int):
    pass


class F64(float):
    pass


class Binary(bytes):
    pass


class FileData(bytes):
    align: int = 0


class HashDict(dict):
    """Dictionnaire indexé par hash (clés entières)."""

    def __init__(self, *args, hash_size: int = 4, **kw):
        super().__init__(*args, **kw)
        self.hash_size = hash_size


# ---------------------------------------------------------------- lecture
class BymlReader:
    def __init__(self, data: bytes) -> None:
        self.d = data
        if data[:2] == b"YB":
            self.e = "<"
        elif data[:2] == b"BY":
            self.e = ">"
        else:
            raise ValueError("pas un fichier BYML")
        self.version, key_off, str_off, root_off = struct.unpack_from(self.e + "HIII", data, 2)
        self.keys = self._string_table(key_off) if key_off else []
        self.strings = self._string_table(str_off) if str_off else []
        self.root_off = root_off

    def _u24(self, off: int) -> int:
        return int.from_bytes(self.d[off:off + 3], "little" if self.e == "<" else "big")

    def _u32(self, off: int) -> int:
        return struct.unpack_from(self.e + "I", self.d, off)[0]

    def _string_table(self, off: int) -> list[str]:
        if self.d[off] != 0xC2:
            raise ValueError(f"table de chaînes attendue à 0x{off:x}")
        n = self._u24(off + 1)
        offs = [self._u32(off + 4 + 4 * i) for i in range(n + 1)]
        out = []
        for i in range(n):
            s = off + offs[i]
            out.append(self.d[s:self.d.index(b"\0", s)].decode("utf-8"))
        return out

    def root(self) -> Any:
        if not self.root_off:
            return None
        return self._node(self.d[self.root_off], self.root_off)

    def _value(self, t: int, raw_off: int) -> Any:
        v = self._u32(raw_off)
        e = self.e
        if t in (0xC0, 0xC1, 0x20, 0x21):
            return self._node(t, v)
        if t == 0xA0:
            return self.strings[v]
        if t == 0xA1:
            size = self._u32(v)
            return Binary(self.d[v + 4:v + 4 + size])
        if t == 0xA2:
            size, align = struct.unpack_from(e + "II", self.d, v)
            fd = FileData(self.d[v + 8:v + 8 + size])
            fd.align = align
            return fd
        if t == 0xD0:
            return bool(v)
        if t == 0xD1:
            return struct.unpack_from(e + "i", self.d, raw_off)[0]
        if t == 0xD2:
            return struct.unpack_from(e + "f", self.d, raw_off)[0]
        if t == 0xD3:
            return U32(v)
        if t == 0xD4:
            return I64(struct.unpack_from(e + "q", self.d, v)[0])
        if t == 0xD5:
            return U64(struct.unpack_from(e + "Q", self.d, v)[0])
        if t == 0xD6:
            return F64(struct.unpack_from(e + "d", self.d, v)[0])
        if t == 0xFF:
            return None
        raise ValueError(f"type BYML inconnu 0x{t:02x}")

    def _node(self, t: int, off: int) -> Any:
        if self.d[off] != t:
            raise ValueError(f"type 0x{t:02x} attendu à 0x{off:x}, trouvé 0x{self.d[off]:02x}")
        n = self._u24(off + 1)
        if t == 0xC0:
            types = self.d[off + 4:off + 4 + n]
            vals = off + 4 + ((n + 3) & ~3)
            return [self._value(types[i], vals + 4 * i) for i in range(n)]
        if t == 0xC1:
            out = {}
            for i in range(n):
                p = off + 4 + 8 * i
                out[self.keys[self._u24(p)]] = self._value(self.d[p + 3], p + 4)
            return out
        if t in (0x20, 0x21):
            hsize = 4 if t == 0x20 else 8
            entry = hsize + 4
            types_off = off + 4 + entry * n
            out = HashDict(hash_size=hsize)
            for i in range(n):
                p = off + 4 + entry * i
                h = int.from_bytes(self.d[p:p + hsize], "little" if self.e == "<" else "big")
                out[h] = self._value(self.d[types_off + i], p + hsize)
            return out
        raise ValueError(f"nœud conteneur inconnu 0x{t:02x}")


def read_byml(data: bytes) -> Any:
    return BymlReader(data).root()


def byml_version(data: bytes) -> int:
    return struct.unpack_from("<H" if data[:2] == b"YB" else ">H", data, 2)[0]


# ---------------------------------------------------------------- écriture
def _type_of(v: Any) -> int:
    if v is None:
        return 0xFF
    if isinstance(v, bool):
        return 0xD0
    if isinstance(v, str):
        return 0xA0
    if isinstance(v, FileData):
        return 0xA2
    if isinstance(v, (Binary, bytes)):
        return 0xA1
    if isinstance(v, U32):
        return 0xD3
    if isinstance(v, I64):
        return 0xD4
    if isinstance(v, U64):
        return 0xD5
    if isinstance(v, int):
        return 0xD1
    if isinstance(v, F64):
        return 0xD6
    if isinstance(v, float):
        return 0xD2
    if isinstance(v, HashDict):
        return 0x20 if v.hash_size == 4 else 0x21
    if isinstance(v, dict):
        return 0xC1
    if isinstance(v, list):
        return 0xC0
    raise TypeError(f"type non sérialisable en BYML : {type(v).__name__}")


_CONTAINERS = (0xC0, 0xC1, 0x20, 0x21)
_OFFSET_TYPES = (0xA1, 0xA2, 0xD4, 0xD5, 0xD6)


def _sort_key(s: str) -> bytes:
    return s.encode("utf-8")


class BymlWriter:
    def __init__(self, version: int = 7, endian: str = "<") -> None:
        self.version = version
        self.e = endian
        self.buf = bytearray()

    def _collect(self, v: Any, keys: set, strings: set) -> None:
        t = _type_of(v)
        if t == 0xA0:
            strings.add(v)
        elif t == 0xC1:
            for k, x in v.items():
                keys.add(k)
                self._collect(x, keys, strings)
        elif t in (0x20, 0x21):
            for x in v.values():
                self._collect(x, keys, strings)
        elif t == 0xC0:
            for x in v:
                self._collect(x, keys, strings)

    def _align(self, n: int = 4) -> None:
        while len(self.buf) % n:
            self.buf.append(0)

    def _put(self, fmt: str, *vals) -> int:
        off = len(self.buf)
        self.buf += struct.pack(self.e + fmt, *vals)
        return off

    def _u24(self, n: int) -> bytes:
        return n.to_bytes(3, "little" if self.e == "<" else "big")

    def _set_u32(self, off: int, v: int) -> None:
        struct.pack_into(self.e + "I", self.buf, off, v)

    def _string_table(self, items: list[str]) -> int:
        start = len(self.buf)
        self.buf += bytes([0xC2]) + self._u24(len(items))
        table = len(self.buf)
        self.buf += bytes(4 * (len(items) + 1))
        for i, s in enumerate(items):
            self._set_u32(table + 4 * i, len(self.buf) - start)
            self.buf += s.encode("utf-8") + b"\0"
        self._set_u32(table + 4 * len(items), len(self.buf) - start)
        self._align(4)
        return start

    def _inline(self, t: int, v: Any) -> bytes:
        e = self.e
        if t == 0xA0:
            return struct.pack(e + "I", self.str_index[v])
        if t == 0xD0:
            return struct.pack(e + "I", 1 if v else 0)
        if t == 0xD1:
            return struct.pack(e + "i", v)
        if t == 0xD2:
            return struct.pack(e + "f", v)
        if t == 0xD3:
            return struct.pack(e + "I", v)
        if t == 0xFF:
            return b"\0\0\0\0"
        raise AssertionError(t)

    def _fingerprint(self, t: int, v: Any):
        """Identité structurelle d'une valeur, pour partager les sous-arbres identiques."""
        if t == 0xC0:
            return (t, tuple(self._fingerprint(_type_of(x), x) for x in v))
        if t in (0xC1, 0x20, 0x21):
            return (t, tuple(sorted((str(k), self._fingerprint(_type_of(x), x)) for k, x in v.items())))
        if t in (0xD2, 0xD6):
            return (t, struct.pack("<d", v))
        if t in (0xA1, 0xA2):
            return (t, bytes(v), getattr(v, "align", None))
        return (t, v)

    def _write_offset_value(self, t: int, v: Any) -> int:
        key = self._fingerprint(t, v)
        off = self.shared.get(key)
        if off is None:
            off = self._write_offset_value_new(t, v)
            self.shared[key] = off
        return off

    def _write_offset_value_new(self, t: int, v: Any) -> int:
        if t in _CONTAINERS:
            return self._container(t, v)
        if t == 0xA1:
            self._align(4)
            off = self._put("I", len(v))
            self.buf += v
            return off
        if t == 0xA2:
            self._align(4)
            off = self._put("II", len(v), getattr(v, "align", 0))
            self.buf += v
            return off
        self._align(8 if self.version >= 7 else 4)
        fmt = {0xD4: "q", 0xD5: "Q", 0xD6: "d"}[t]
        return self._put(fmt, v)

    def _container(self, t: int, v: Any) -> int:
        self._align(4)
        start = len(self.buf)
        pending: list[tuple[int, int, Any]] = []  # (emplacement, type, valeur)

        if t == 0xC0:
            types = [_type_of(x) for x in v]
            self.buf += bytes([t]) + self._u24(len(v)) + bytes(types)
            self._align(4)
            for x, xt in zip(v, types):
                slot = len(self.buf)
                if xt in _CONTAINERS or xt in _OFFSET_TYPES:
                    self.buf += bytes(4)
                    pending.append((slot, xt, x))
                else:
                    self.buf += self._inline(xt, x)
        elif t == 0xC1:
            items = sorted(v.items(), key=lambda kv: _sort_key(kv[0]))
            self.buf += bytes([t]) + self._u24(len(items))
            for k, x in items:
                xt = _type_of(x)
                self.buf += self._u24(self.key_index[k]) + bytes([xt])
                slot = len(self.buf)
                if xt in _CONTAINERS or xt in _OFFSET_TYPES:
                    self.buf += bytes(4)
                    pending.append((slot, xt, x))
                else:
                    self.buf += self._inline(xt, x)
        else:
            hsize = 4 if t == 0x20 else 8
            items = sorted(v.items())
            self.buf += bytes([t]) + self._u24(len(items))
            types = []
            for h, x in items:
                xt = _type_of(x)
                types.append(xt)
                self.buf += int(h).to_bytes(hsize, "little" if self.e == "<" else "big")
                slot = len(self.buf)
                if xt in _CONTAINERS or xt in _OFFSET_TYPES:
                    self.buf += bytes(4)
                    pending.append((slot, xt, x))
                else:
                    self.buf += self._inline(xt, x)
            self.buf += bytes(types)
            self._align(4)

        for slot, xt, x in pending:
            self._set_u32(slot, self._write_offset_value(xt, x))
        return start

    def write(self, root: Any) -> bytes:
        keys: set[str] = set()
        strings: set[str] = set()
        if root is not None:
            self._collect(root, keys, strings)
        key_list = sorted(keys, key=_sort_key)
        str_list = sorted(strings, key=_sort_key)
        self.key_index = {k: i for i, k in enumerate(key_list)}
        self.str_index = {s: i for i, s in enumerate(str_list)}
        self.shared: dict = {}

        self.buf = bytearray(b"YB" if self.e == "<" else b"BY")
        self._put("HIII", self.version, 0, 0, 0)
        key_off = self._string_table(key_list) if key_list else 0
        str_off = self._string_table(str_list) if str_list else 0
        root_off = 0
        if root is not None:
            root_off = self._container(_type_of(root), root)
        struct.pack_into(self.e + "III", self.buf, 4, key_off, str_off, root_off)
        self._align(4)
        return bytes(self.buf)


def write_byml(root: Any, version: int = 7, endian: str = "<") -> bytes:
    return BymlWriter(version, endian).write(root)
