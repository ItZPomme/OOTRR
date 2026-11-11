"""Cherche dans le code (output/native/main.bin) les constantes 32 bits construites par MOVZ + MOVK.

    python -m ootrr.tools.const output/native/main.bin 0x128d0120 OptionData.CameraRotateSpeed

Un nom (sans 0x) est converti en MurmurHash3, le hachage des noms GameData et des écrans.
"""
import argparse
import sys
from array import array

from ..formats.gamedata import flag_hash
from .xref import TEXT_END, function_start


def find_consts(img: bytes, values: set[int], text_end: int = TEXT_END):
    words = array("I")
    words.frombytes(img[:text_end - text_end % 4])
    lows = {}
    for v in values:
        lows.setdefault(v & 0xFFFF, []).append(v)
    out = []
    n = len(words)
    for i in range(n):
        w = words[i]
        # MOVZ Wd/Xd, #imm16 (hw = 0)
        if (w & 0x7FE00000) != 0x52800000:
            continue
        lo = (w >> 5) & 0xFFFF
        if lo not in lows:
            continue
        rd = w & 31
        for j in range(i + 1, min(i + 8, n)):
            k = words[j]
            # MOVK Wd/Xd, #imm16, LSL #16
            if (k & 0x7FE00000) == 0x72A00000 and (k & 31) == rd:
                v = lo | (((k >> 5) & 0xFFFF) << 16)
                if v in values:
                    out.append((i * 4, v))
                break
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("image")
    p.add_argument("what", nargs="+")
    a = p.parse_args(argv)
    names = {}
    for w in a.what:
        v = int(w, 16) if w.startswith("0x") else flag_hash(w)
        names[v] = w
    img = open(a.image, "rb").read()
    for addr, v in find_consts(img, set(names)):
        print(f"{addr:#x} (fonction ~{function_start(img, addr):#x}) -> {names[v]} ({v:#x})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
