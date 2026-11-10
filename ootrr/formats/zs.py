"""Décompression Zstandard avec les dictionnaires du jeu (Pack/ZsDic.pack.zs)."""

from __future__ import annotations

from pathlib import Path

try:
    import zstandard
except ModuleNotFoundError:  # message clair plutôt qu'une trace Python
    raise SystemExit("Erreur : la bibliothèque « zstandard » est requise pour lire les fichiers du jeu.\n"
                     "Installe-la avec :  python -m pip install -r requirements.txt") from None

from .sarc import read_sarc


class ZsCodec:
    def __init__(self, romfs: Path | str) -> None:
        romfs = Path(romfs)
        raw = zstandard.ZstdDecompressor().decompress((romfs / "Pack" / "ZsDic.pack.zs").read_bytes())
        self.dicts = {name: zstandard.ZstdCompressionDict(data) for name, data in read_sarc(raw).items()}

    def _dict_for(self, name: str) -> zstandard.ZstdCompressionDict | None:
        if name.endswith(".bcett.byml.zs"):
            return self.dicts.get("bcett.byml.zsdic")
        if name.endswith(".pack.zs"):
            return self.dicts.get("pack.zsdic")
        return self.dicts.get("zs.zsdic")

    def decompress(self, path: Path | str) -> bytes:
        path = Path(path)
        d = self._dict_for(path.name)
        dctx = zstandard.ZstdDecompressor(dict_data=d) if d else zstandard.ZstdDecompressor()
        return dctx.decompress(path.read_bytes(), max_output_size=1 << 30)

    def compress(self, name: str, data: bytes, level: int = 16) -> bytes:
        d = self._dict_for(name)
        cctx = zstandard.ZstdCompressor(level=level, dict_data=d) if d else zstandard.ZstdCompressor(level=level)
        return cctx.compress(data)
