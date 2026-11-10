"""Vérifie que le writer BYML reproduit fidèlement les fichiers du jeu.

    python -m ootrr.tools.roundtrip --romfs "D:\\...\\romfs" [--glob "Banc/**/*.byml.zs"]
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from ..formats.byml import byml_version, read_byml, write_byml
from ..formats.zs import ZsCodec


def same(a, b, path="racine") -> str | None:
    if type(a) is not type(b):
        return f"{path} : type {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        if list(a) != list(b) and sorted(a, key=str) != sorted(b, key=str):
            return f"{path} : clés différentes"
        for k in a:
            r = same(a[k], b[k], f"{path}.{k}")
            if r:
                return r
    elif isinstance(a, list):
        if len(a) != len(b):
            return f"{path} : longueur {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            r = same(x, y, f"{path}[{i}]")
            if r:
                return r
    elif isinstance(a, float):
        if struct.pack("<d", a) != struct.pack("<d", b):
            return f"{path} : {a} != {b}"
    elif a != b:
        return f"{path} : {a!r} != {b!r}"
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--romfs", required=True)
    p.add_argument("--glob", default="Banc/**/*.byml.zs")
    args = p.parse_args(argv)
    romfs = Path(args.romfs)
    codec = ZsCodec(romfs)
    files = sorted(romfs.glob(args.glob))
    ok = identical = 0
    worst = 0
    for f in files:
        raw = codec.decompress(f)
        tree = read_byml(raw)
        out = write_byml(tree, byml_version(raw))
        err = same(tree, read_byml(out))
        if err:
            print(f"ÉCHEC {f.relative_to(romfs)} : {err}")
            continue
        ok += 1
        identical += out == raw
        worst = max(worst, len(out) - len(raw))
    print(f"{ok}/{len(files)} fichiers relus à l'identique, {identical} identiques à l'octet près, "
          f"écart de taille max {worst:+d} octets")
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
