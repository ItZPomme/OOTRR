"""Table des tailles de ressources (System/Resource/ResourceSizeTable*.rsizetable.zs).

Le jeu réserve pour chaque fichier la mémoire indiquée ici. Un fichier modifié
plus gros que son entrée fait planter le jeu : on met donc l'entrée à jour en
conservant la même marge que l'original (taille décompressée + marge).
Les entrées sont rangées par CRC32 du chemin ; les chemins dont le CRC32 entre
en collision sont dans une seconde table, par nom (160 octets).
"""

from __future__ import annotations

import struct
import zlib


class Restbl:
    def __init__(self, data: bytes) -> None:
        if data[:6] != b"RESTBL":
            raise ValueError("pas une table RESTBL")
        self.version, self.str_size, n_crc = struct.unpack_from("<III", data, 6)
        n_name = struct.unpack_from("<I", data, 18)[0]
        self.crc: dict[int, int] = {}
        off = 22
        for _ in range(n_crc):
            h, size = struct.unpack_from("<II", data, off)
            self.crc[h] = size
            off += 8
        self.names: dict[str, int] = {}
        for _ in range(n_name):
            name = bytes(data[off:off + self.str_size]).split(b"\0")[0].decode()
            off += self.str_size
            self.names[name] = struct.unpack_from("<I", data, off)[0]
            off += 4

    def has(self, path: str) -> bool:
        return path in self.names or zlib.crc32(path.encode()) in self.crc

    def get(self, path: str) -> int:
        if path in self.names:
            return self.names[path]
        h = zlib.crc32(path.encode())
        if h not in self.crc:
            raise KeyError(f"{path} absent de la table des tailles")
        return self.crc[h]

    def set(self, path: str, size: int) -> None:
        if path in self.names:
            self.names[path] = size
        else:
            self.crc[zlib.crc32(path.encode())] = size  # ajoute l'entrée si elle n'existe pas

    def resize_like(self, path: str, old_size: int, new_size: int) -> None:
        """Nouvelle entrée = nouvelle taille + la marge que le jeu prévoyait à l'origine."""
        margin = self.get(path) - old_size
        self.set(path, max(self.get(path), new_size + max(margin, 0)))

    def to_bytes(self) -> bytes:
        out = bytearray(b"RESTBL")
        out += struct.pack("<IIII", self.version, self.str_size, len(self.crc), len(self.names))
        for h in sorted(self.crc):
            out += struct.pack("<II", h, self.crc[h])
        for name in sorted(self.names):
            raw = name.encode()
            out += raw + bytes(self.str_size - len(raw)) + struct.pack("<I", self.names[name])
        return bytes(out)
