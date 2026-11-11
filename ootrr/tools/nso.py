"""Décompresse un exécutable NSO (exefs/main) en image mémoire brute, pour l'analyse.

    python -m ootrr.tools.nso EXEFS/main output/native/main.bin

L'image produite place chaque segment (.text, .rodata, .data) à son adresse mémoire ;
elle se désassemble avec l'objdump de devkitA64 :
    aarch64-none-elf-objdump -D -b binary -m aarch64 --start-address=0x... main.bin
Le résultat contient du code du jeu : il reste dans output/ (ignoré par git).
"""
import argparse
import hashlib
import struct
import sys


def lz4_block(src: bytes, size: int) -> bytes:
    """Décompression LZ4 « block » (sans en-tête de trame)."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        ml = token & 15
        if ml == 15:
            while True:
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        start = len(out) - off
        if off >= ml:
            out += out[start:start + ml]
        else:
            for k in range(ml):
                out.append(out[start + k])
    if len(out) != size:
        raise ValueError(f"taille LZ4 inattendue : {len(out):#x} au lieu de {size:#x}")
    return bytes(out)


def read_nso(data: bytes) -> dict:
    if data[:4] != b"NSO0":
        raise ValueError("pas un NSO")
    flags = struct.unpack_from("<I", data, 0xC)[0]
    segs = []
    for k, base in enumerate((0x10, 0x20, 0x30)):
        foff, moff, size = struct.unpack_from("<3I", data, base)
        csize = struct.unpack_from("<I", data, 0x60 + 4 * k)[0]
        raw = data[foff:foff + csize]
        body = lz4_block(raw, size) if flags & (1 << k) else raw[:size]
        if flags & (1 << (k + 3)):
            want = data[0xA0 + 0x20 * k:0xC0 + 0x20 * k]
            if hashlib.sha256(body).digest() != want:
                raise ValueError(f"segment {k} : empreinte SHA-256 invalide")
        segs.append((moff, body))
    bss = struct.unpack_from("<I", data, 0x3C)[0]
    return {
        "build_id": data[0x40:0x60].hex().upper(),
        "segments": segs,
        "bss": bss,
        "dynstr": struct.unpack_from("<2I", data, 0x90),
        "dynsym": struct.unpack_from("<2I", data, 0x98),
    }


def image(nso: dict) -> bytes:
    end = max(m + len(b) for m, b in nso["segments"])
    img = bytearray(end)
    for moff, body in nso["segments"]:
        img[moff:moff + len(body)] = body
    return bytes(img)


def apply_relocations(img: bytes) -> bytes:
    """Applique les relocations R_AARCH64_RELATIVE (base 0) : les pointeurs des tables et
    vtables deviennent des adresses relatives au module, comme le ferait rtld avec base = 0."""
    img = bytearray(img)
    mod0 = struct.unpack_from("<I", img, 4)[0]
    if img[mod0:mod0 + 4] != b"MOD0":
        raise ValueError("en-tête MOD0 introuvable")
    dyn = mod0 + struct.unpack_from("<i", img, mod0 + 4)[0]
    tags = {}
    off = dyn
    while True:
        tag, val = struct.unpack_from("<qQ", img, off)
        off += 16
        if tag == 0:
            break
        tags.setdefault(tag, val)
    count = 0
    for start_tag, size_tag, ent in ((7, 8, 24),):  # DT_RELA, DT_RELASZ
        start, size = tags.get(start_tag), tags.get(size_tag, 0)
        if start is None:
            continue
        for r in range(start, start + size, ent):
            where, info, addend = struct.unpack_from("<QQq", img, r)
            if info & 0xFFFFFFFF == 1027:  # R_AARCH64_RELATIVE
                struct.pack_into("<Q", img, where, addend & 0xFFFFFFFFFFFFFFFF)
                count += 1
    print(f"{count} relocations appliquées")
    return bytes(img)


def make_elf(img: bytes, segments: list[tuple[int, int, int]], bss: int) -> bytes:
    """ELF64 AArch64 minimal (en-têtes de programme seulement) à partir de l'image mémoire.
    segments = [(adresse, taille, droits PF_*)] ; la .bss suit le dernier segment."""
    phnum = len(segments)
    head = 64 + 56 * phnum
    base_off = (head + 0xFFF) & ~0xFFF
    out = bytearray(base_off)
    struct.pack_into("<4sBBBBB7xHHIQQQIHHHHHH", out, 0, b"\x7fELF", 2, 1, 1, 0, 0,
                     3, 183, 1, 0, 64, 0, 0, 64, 56, phnum, 64, 0, 0)  # ET_DYN, EM_AARCH64
    for k, (addr, size, flags) in enumerate(segments):
        memsz = size + (bss if k == phnum - 1 else 0)
        struct.pack_into("<IIQQQQQQ", out, 64 + 56 * k, 1, flags, base_off + addr,
                         addr, addr, size, memsz, 0x1000)
    out += img
    return bytes(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("nso")
    p.add_argument("out")
    a = p.parse_args(argv)
    with open(a.nso, "rb") as f:
        nso = read_nso(f.read())
    img = image(nso)
    with open(a.out, "wb") as f:
        f.write(img)
    names = (".text", ".rodata", ".data")
    print("build id", nso["build_id"])
    for name, (moff, body) in zip(names, nso["segments"]):
        print(f"{name:8} {moff:#010x} - {moff + len(body):#010x}")
    print(f"bss      {nso['bss']:#x} octets")


if __name__ == "__main__":
    sys.exit(main())
