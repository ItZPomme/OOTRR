"""Multiworld room codes: what the host shares so the others can join (docs/MULTIWORLD.md, "Joining").

A code holds the host's address (IPv4 and port) and the room hash (`multiworld.room_hash`, 10 hex digits), plus a
check byte, written in Crockford base 32 (no I, L, O, U; read case-insensitively, I/L read as 1 and O as 0) in
groups of four: `K7QM-29XD-...`. 12 bytes -> 20 characters.

The hash lets the server refuse a code from another game (and a joiner see at once that a code is wrong); the code
gives no access to anything but the room: a joiner then asks the server for their own player's data only.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_READ = {c: i for i, c in enumerate(ALPHABET)} | {"I": 1, "L": 1, "O": 0}
VERSION = 1


class CodeError(ValueError):
    pass


@dataclass(frozen=True)
class RoomCode:
    host: str  # IPv4 address
    port: int
    room_hash: str  # 10 hex digits

    def __str__(self) -> str:
        return encode(self)


def _check(data: bytes) -> int:
    c = VERSION
    for b in data:
        c = (c * 31 + b) & 0xFF
    return c


def encode(code: RoomCode) -> str:
    try:
        ip = ipaddress.IPv4Address(code.host).packed
    except ipaddress.AddressValueError as exc:
        raise CodeError(f"not an IPv4 address: {code.host}") from exc
    if not 0 < code.port < 65536:
        raise CodeError(f"bad port {code.port}")
    try:
        h = bytes.fromhex(code.room_hash)
    except ValueError as exc:
        raise CodeError(f"bad room hash {code.room_hash}") from exc
    if len(h) != 5:
        raise CodeError(f"bad room hash {code.room_hash}")
    data = ip + code.port.to_bytes(2, "big") + h
    data += bytes([_check(data)])
    n = int.from_bytes(data, "big")
    chars = []
    for _ in range(len(data) * 8 // 5 + (1 if len(data) * 8 % 5 else 0)):
        chars.append(ALPHABET[n & 31])
        n >>= 5
    text = "".join(reversed(chars))
    return "-".join(text[i:i + 4] for i in range(0, len(text), 4))


def decode(text: str) -> RoomCode:
    clean = "".join(ch for ch in text.upper() if ch not in "- \t")
    if len(clean) != 20:
        raise CodeError("a room code has 20 characters (e.g. K7QM-29XD-...)")
    n = 0
    for ch in clean:
        if ch not in _READ:
            raise CodeError(f"not a room code character: {ch}")
        n = n * 32 + _READ[ch]
    data = n.to_bytes(13, "big")[-12:]
    if n >> 96:
        raise CodeError("not a room code")
    if _check(data[:11]) != data[11]:
        raise CodeError("this room code is mistyped (check failed)")
    host = str(ipaddress.IPv4Address(data[:4]))
    port = int.from_bytes(data[4:6], "big")
    return RoomCode(host, port, data[6:11].hex().upper())
