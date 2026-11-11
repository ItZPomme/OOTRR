"""Cherche dans l'image du code (output/native/main.bin) les références à une adresse ou à une chaîne.

    python -m ootrr.tools.xref output/native/main.bin SeqQueryGetSelectedOptionType
    python -m ootrr.tools.xref output/native/main.bin 0x3d80e7d

Reconnaît les paires ADRP + ADD / LDR (le moyen habituel de charger une adresse en AArch64)
et les pointeurs 64 bits écrits tels quels dans les données (tables, vtables).
Les adresses affichées sont relatives au début du module (celles d'objdump sur main.bin).
"""
import argparse
import re
import struct
import sys
from array import array

TEXT_END = 0x3C461D0  # fin de .text (en-tête NSO du jeu, version 131072)


def _sx(v: int, bits: int) -> int:
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def code_refs(img: bytes, targets: set[int], text_end: int = TEXT_END):
    """Renvoie [(adresse de l'instruction, cible)] pour les ADRP + ADD/LDR qui visent une cible."""
    words = array("I")
    words.frombytes(img[:text_end - text_end % 4])
    pages = {t & ~0xFFF for t in targets}
    found = []
    n = len(words)
    for i in range(n):
        w = words[i]
        if (w & 0x9F000000) != 0x90000000:
            continue
        imm = ((w >> 29) & 3) | (((w >> 5) & 0x7FFFF) << 2)
        page = ((i * 4) & ~0xFFF) + (_sx(imm, 21) << 12)
        if page not in pages:
            continue
        rd = w & 31
        for j in range(i + 1, min(i + 12, n)):
            v = words[j]
            if (v & 0xFFC00000) == 0x91000000 and ((v >> 5) & 31) == rd:  # ADD Xd, Xn, #imm
                t = page + ((v >> 10) & 0xFFF)
            elif (v & 0x3FC00000) == 0x39400000 and ((v >> 5) & 31) == rd:  # LDR (unsigned offset)
                size = v >> 30
                t = page + (((v >> 10) & 0xFFF) << size)
            else:
                continue
            if t in targets:
                found.append((j * 4, t))
            break
    return found


def data_refs(img: bytes, targets: set[int], start: int = TEXT_END):
    found = []
    for off in range(start + (-start % 8), len(img) - 7, 8):
        v = struct.unpack_from("<Q", img, off)[0]
        if v in targets:
            found.append((off, v))
    return found


def function_start(img: bytes, addr: int, limit: int = 0x4000) -> int:
    """Estimation du début de fonction : remonte jusqu'après un RET / B inconditionnel."""
    a = addr - 4
    while a > 0 and addr - a < limit:
        w = struct.unpack_from("<I", img, a)[0]
        if w == 0xD65F03C0 or (w & 0xFC000000) == 0x14000000:
            return a + 4
        a -= 4
    return a


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("image")
    p.add_argument("what", nargs="+", help="adresse (0x...) ou chaîne exacte")
    p.add_argument("--data", action="store_true", help="chercher aussi les pointeurs dans les données")
    a = p.parse_args(argv)
    img = open(a.image, "rb").read()
    targets = {}
    for w in a.what:
        if w.startswith("0x"):
            targets[int(w, 16)] = w
        else:
            for m in re.finditer(re.escape(w.encode()) + b"\0", img):
                if m.start() == 0 or img[m.start() - 1] == 0:
                    targets[m.start()] = w
    if not targets:
        print("rien trouvé")
        return 1
    for t, name in sorted(targets.items()):
        print(f"cible {t:#x} = {name}")
    for ins, t in code_refs(img, set(targets)):
        print(f"  code {ins:#x} (fonction ~{function_start(img, ins):#x}) -> {targets[t]}")
    if a.data:
        for off, t in data_refs(img, set(targets)):
            print(f"  données {off:#x} -> {targets[t]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
