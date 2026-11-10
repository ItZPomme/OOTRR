"""Archives SARC (conteneur de fichiers Nintendo) : lecture et écriture."""

from __future__ import annotations

import struct


def _parse(data: bytes):
    if data[:4] != b"SARC":
        raise ValueError("pas une archive SARC")
    e = "<" if data[6:8] == b"\xff\xfe" else ">"
    data_offset = struct.unpack_from(e + "I", data, 0x0C)[0]
    pos = struct.unpack_from(e + "H", data, 0x04)[0]
    if data[pos:pos + 4] != b"SFAT":
        raise ValueError("bloc SFAT manquant")
    sfat_len, count, hash_key = struct.unpack_from(e + "HHI", data, pos + 4)
    nodes = []
    p = pos + sfat_len
    for _ in range(count):
        _hash, attrs, start, end = struct.unpack_from(e + "IIII", data, p)
        nodes.append((attrs, start, end))
        p += 16
    if data[p:p + 4] != b"SFNT":
        raise ValueError("bloc SFNT manquant")
    names_start = p + struct.unpack_from(e + "H", data, p + 4)[0]
    out = []
    for i, (attrs, start, end) in enumerate(nodes):
        if attrs >> 24:
            off = names_start + (attrs & 0xFFFFFF) * 4
            name = data[off:data.index(b"\0", off)].decode("utf-8")
        else:
            name = f"file_{i}"
        out.append((name, data[data_offset + start:data_offset + end], data_offset + start))
    return e, hash_key, out


def read_sarc(data: bytes) -> dict[str, bytes]:
    return {name: blob for name, blob, _ in _parse(data)[2]}


class Sarc:
    """Archive modifiable qui conserve l'alignement d'origine de chaque fichier."""

    def __init__(self, data: bytes) -> None:
        self.endian, self.hash_key, entries = _parse(data)
        self.files: dict[str, bytes] = {}
        self.align: dict[str, int] = {}
        for name, blob, abs_off in entries:
            self.files[name] = blob
            a = 4
            while a < 0x2000 and abs_off % (a * 2) == 0:
                a *= 2
            self.align[name] = a

    def _hash(self, name: str) -> int:
        h = 0
        for b in name.encode("utf-8"):
            h = (h * self.hash_key + b) & 0xFFFFFFFF
        return h

    def to_bytes(self) -> bytes:
        e = self.endian
        names = sorted(self.files, key=self._hash)
        sfnt = bytearray()
        name_offs = {}
        for n in names:
            name_offs[n] = len(sfnt) // 4
            sfnt += n.encode("utf-8") + b"\0"
            while len(sfnt) % 4:
                sfnt.append(0)
        header_len = 0x14 + 0x0C + 16 * len(names) + 8 + len(sfnt)
        max_align = max([self.align.get(n, 8) for n in names] + [4])
        data_offset = (header_len + max_align - 1) // max_align * max_align
        blob = bytearray()
        ranges = {}
        for n in names:
            a = self.align.get(n, 8)
            while (data_offset + len(blob)) % a:
                blob.append(0)
            start = len(blob)
            blob += self.files[n]
            ranges[n] = (start, len(blob))
        out = bytearray()
        out += b"SARC" + struct.pack(e + "HH", 0x14, 0xFEFF)
        out += struct.pack(e + "IIHH", 0, data_offset, 0x100, 0)
        out += b"SFAT" + struct.pack(e + "HHI", 0x0C, len(names), self.hash_key)
        for n in names:
            out += struct.pack(e + "IIII", self._hash(n), 0x01000000 | name_offs[n], *ranges[n])
        out += b"SFNT" + struct.pack(e + "HH", 8, 0) + sfnt
        out += bytes(data_offset - len(out))
        out += blob
        struct.pack_into(e + "I", out, 0x08, len(out))
        return bytes(out)
