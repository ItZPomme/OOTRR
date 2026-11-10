"""Fichiers de messages MSBT (Mals/<langue>.Product.*.sarc.zs) : lecture et réécriture des textes.

Sections utilisées : LBL1 (noms des messages -> indice) et TXT2 (textes UTF-16 avec balises
de contrôle 0x000E groupe, type, taille, données). Les autres sections sont recopiées telles quelles.
Seul le texte d'un message existant peut être remplacé (les noms ne changent pas).
"""

from __future__ import annotations

import struct


def _sections(d: bytes):
    n = struct.unpack_from("<H", d, 0x0E)[0]
    o = 0x20
    out = []
    for _ in range(n):
        magic, size = d[o:o + 4], struct.unpack_from("<I", d, o + 4)[0]
        out.append((magic, o, size))
        o = (o + 0x10 + size + 15) // 16 * 16
    return out


def read_labels(d: bytes) -> dict[str, int]:
    for magic, o, size in _sections(d):
        if magic == b"LBL1":
            base = o + 0x10
            count = struct.unpack_from("<I", d, base)[0]
            labels = {}
            for i in range(count):
                n, off = struct.unpack_from("<II", d, base + 4 + 8 * i)
                p = base + off
                for _ in range(n):
                    ln = d[p]
                    name = d[p + 1:p + 1 + ln].decode("utf-8")
                    labels[name] = struct.unpack_from("<I", d, p + 1 + ln)[0]
                    p += 1 + ln + 4
            return labels
    raise ValueError("section LBL1 absente")


def unit(d: bytes) -> int:
    """Taille d'un caractère : 1 (UTF-8, octet 0x0C = 0) ou 2 (UTF-16)."""
    return 1 if d[0x0C] == 0 else 2


def read_texts(d: bytes) -> list[bytes]:
    """Textes bruts (avec balises, sans le 0 final)."""
    zero = b"\0" * unit(d)
    for magic, o, size in _sections(d):
        if magic == b"TXT2":
            base = o + 0x10
            count = struct.unpack_from("<I", d, base)[0]
            offs = [struct.unpack_from("<I", d, base + 4 + 4 * i)[0] for i in range(count)] + [size]
            out = []
            for i in range(count):
                raw = d[base + offs[i]:base + offs[i + 1]]
                if raw.endswith(zero):
                    raw = raw[:-len(zero)]
                out.append(raw)
            return out
    raise ValueError("section TXT2 absente")


def replace_texts(d: bytes, changes: dict[str, bytes]) -> bytes:
    """Remplace le texte (UTF-16LE brut, balises comprises) des messages nommés."""
    labels = read_labels(d)
    texts = read_texts(d)
    for name, raw in changes.items():
        if name not in labels:
            raise KeyError(f"message introuvable : {name}")
        texts[labels[name]] = raw
    body = bytearray(struct.pack("<I", len(texts)))
    data = bytearray()
    start = 4 + 4 * len(texts)
    for t in texts:
        body += struct.pack("<I", start + len(data))
        data += t + b"\0" * unit(d)
    txt2 = bytes(body + data)
    out = bytearray(d[:0x20])
    for magic, o, size in _sections(d):
        if magic == b"TXT2":
            sec = d[o:o + 0x10]
            out += sec[:4] + struct.pack("<I", len(txt2)) + sec[8:] + txt2
        else:
            out += d[o:o + 0x10 + size]
        while len(out) % 16:
            out.append(0xAB)
    struct.pack_into("<I", out, 0x12, len(out))
    return bytes(out)


def label_hash(name: str, buckets: int) -> int:
    h = 0
    for b in name.encode("utf-8"):
        h = (h * 0x492 + b) & 0xFFFFFFFF
    return h % buckets


def add_messages(d: bytes, new: dict[str, bytes]) -> bytes:
    """Ajoute des messages (nom -> texte brut) : nouvelles étiquettes LBL1 et textes TXT2."""
    labels = read_labels(d)
    texts = read_texts(d)
    lbl = next(s for s in _sections(d) if s[0] == b"LBL1")
    buckets = struct.unpack_from("<I", d, lbl[1] + 0x10)[0]
    for name, raw in new.items():
        if name in labels:
            texts[labels[name]] = raw
        else:
            labels[name] = len(texts)
            texts.append(raw)
    groups: list[list[tuple[str, int]]] = [[] for _ in range(buckets)]
    for name, index in labels.items():
        groups[label_hash(name, buckets)].append((name, index))
    head = bytearray(struct.pack("<I", buckets))
    data = bytearray()
    start = 4 + 8 * buckets
    for g in groups:
        head += struct.pack("<II", len(g), start + len(data))
        for name, index in g:
            raw = name.encode("utf-8")
            data += bytes([len(raw)]) + raw + struct.pack("<I", index)
    lbl1 = bytes(head + data)
    zero = b"\0" * unit(d)
    tbody = bytearray(struct.pack("<I", len(texts)))
    tdata = bytearray()
    tstart = 4 + 4 * len(texts)
    for t in texts:
        tbody += struct.pack("<I", tstart + len(tdata))
        tdata += t + zero
    txt2 = bytes(tbody + tdata)
    out = bytearray(d[:0x20])
    for magic, o, size in _sections(d):
        sec = d[o:o + 0x10]
        if magic == b"LBL1":
            out += sec[:4] + struct.pack("<I", len(lbl1)) + sec[8:] + lbl1
        elif magic == b"TXT2":
            out += sec[:4] + struct.pack("<I", len(txt2)) + sec[8:] + txt2
        elif magic == b"ATR1":
            raise ValueError("section ATR1 non prise en charge pour l'ajout de messages")
        else:
            out += d[o:o + 0x10 + size]
        while len(out) % 16:
            out.append(0xAB)
    struct.pack_into("<I", out, 0x12, len(out))
    return bytes(out)


def tag(group: int, typ: int, data: bytes = b"") -> bytes:
    """Balise de contrôle (format UTF-8)."""
    return b"\x0e" + struct.pack("<HHH", group, typ, len(data)) + data


def plain(raw: bytes, u: int = 1) -> str:
    """Texte lisible : balises remplacées par [groupe:type:données hexa]."""
    out = []
    text = bytearray()
    i = 0
    enc = "utf-8" if u == 1 else "utf-16-le"

    def flush():
        if text:
            out.append(bytes(text).decode(enc, "replace"))
            text.clear()
    while i < len(raw):
        ch = raw[i] if u == 1 else struct.unpack_from("<H", raw, i)[0]
        if ch == 0x0E:
            flush()
            group, typ, size = struct.unpack_from("<HHH", raw, i + u)
            out.append(f"[{group}:{typ}:{raw[i + u + 6:i + u + 6 + size].hex()}]")
            i += u + 6 + size
        elif ch == 0x0F:
            flush()
            group, typ = struct.unpack_from("<HH", raw, i + u)
            out.append(f"[/{group}:{typ}]")
            i += u + 4
        else:
            text += raw[i:i + u]
            i += u
    flush()
    return "".join(out)
