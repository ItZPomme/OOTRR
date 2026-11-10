"""Inspection des scripts d'événements (Event/EventFlow/*.bfevfl.zs).

    python -m ootrr.tools.events --romfs ROMFS Dm_Kokiri_0155              # acteurs, points d'entrée
    python -m ootrr.tools.events --romfs ROMFS DoorOfTime --entry DoorOfTime_Draw   # déroulé d'un point d'entrée
    python -m ootrr.tools.events --romfs ROMFS DoorOfTime --find Item_Ocarina_Time  # événements qui citent un texte
    python -m ootrr.tools.events --file mod.bfevfl --entry ...              # fichier déjà décompressé

Rappels sur le format (voir docs/FORMATS.md) : un événement fait 0x30 octets (type à +8 :
0 action, 1 question, 2 fork, 3 join, 4 sous-séquence) ; les réponses d'une question sont des
« cas » (valeur, événement suivant) et, dans les scripts du jeu, 0 = oui / 1 = non.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from ..formats.evfl import (ACTOR_SIZE, ENTRY_SIZE, EVENT_SIZE, NO_EVENT, _dic_names, _flowchart_full, _header,
                            _q, _string_at, string_refs)

TYPES = {0: "arg", 1: "conteneur", 2: "int", 3: "bool", 4: "float", 5: "texte", 6: "wtexte",
         7: "int[]", 8: "bool[]", 9: "float[]", 10: "texte[]", 11: "wtexte[]", 12: "acteur"}


def param_value(d: bytes, p: int, reloc: int) -> str:
    kind, _, n = struct.unpack_from("<BBH", d, p)
    if kind == 5:
        return repr(_string_at(d, _q(d, p + 0x10), reloc))
    if kind == 2:
        return str(struct.unpack_from("<i", d, p + 0x10)[0])
    if kind == 3:
        return str(bool(struct.unpack_from("<I", d, p + 0x10)[0]))
    if kind == 4:
        return f"{struct.unpack_from('<f', d, p + 0x10)[0]:g}"
    return f"<{TYPES.get(kind, kind)} n={n}>"


def params(d: bytes, p: int, reloc: int) -> dict[str, str]:
    if not p:
        return {}
    n = struct.unpack_from("<H", d, p + 2)[0]
    names = _dic_names(d, _q(d, p + 8))
    return {names[i]: param_value(d, _q(d, p + 0x10 + 8 * i), reloc) for i in range(n)}


def describe(d: bytes) -> list[str]:
    reloc, _ = _header(d)
    fc = _flowchart_full(d)
    out = [f"{_string_at(d, _q(d, fc['fc'] + 0x20), reloc)} : {fc['n_actors']} acteurs, "
           f"{fc['n_events']} événements, {fc['n_entries']} points d'entrée"]
    for ai in range(fc["n_actors"]):
        a = fc["actors"] + ai * ACTOR_SIZE
        nact, nq = struct.unpack_from("<HH", d, a + 0x30)
        acts = [_string_at(d, _q(d, _q(d, a + 0x18) + 8 * k), reloc) for k in range(nact)]
        qs = [_string_at(d, _q(d, _q(d, a + 0x20) + 8 * k), reloc) for k in range(nq)]
        sec = _string_at(d, _q(d, a + 8), reloc)
        out.append(f"  acteur {ai} {_string_at(d, _q(d, a), reloc)}{f' ({sec})' if sec else ''} "
                   f"actions={acts} questions={qs}")
    names = _dic_names(d, fc["entry_dic"])
    for i, name in enumerate(names):
        main = struct.unpack_from("<H", d, fc["entries"] + i * ENTRY_SIZE + 0x1C)[0]
        out.append(f"  entrée {name} -> {main}")
    return out


def event_line(d: bytes, i: int) -> tuple[str, list[int]]:
    reloc, _ = _header(d)
    fc = _flowchart_full(d)
    o = fc["events"] + i * EVENT_SIZE
    t = d[o + 8]
    if t == 0:
        nxt, ai, k = struct.unpack_from("<HHH", d, o + 0x0A)
        a = fc["actors"] + ai * ACTOR_SIZE
        name = f"{_string_at(d, _q(d, a), reloc)}.{_string_at(d, _q(d, _q(d, a + 0x18) + 8 * k), reloc)}"
        return f"{i}: {name} {params(d, _q(d, o + 0x10), reloc)} -> {nxt}", [nxt]
    if t == 1:
        n, ai, k = struct.unpack_from("<HHH", d, o + 0x0A)
        a = fc["actors"] + ai * ACTOR_SIZE
        name = f"{_string_at(d, _q(d, a), reloc)}.{_string_at(d, _q(d, _q(d, a + 0x20) + 8 * k), reloc)}"
        cases = [struct.unpack_from("<IH", d, _q(d, o + 0x18) + 8 * c) for c in range(n)]
        return f"{i}: SI {name} {params(d, _q(d, o + 0x10), reloc)} cas={cases}", [c[1] for c in cases]
    if t == 2:
        n, join = struct.unpack_from("<HH", d, o + 0x0A)
        forks = [struct.unpack_from("<H", d, _q(d, o + 0x10) + 2 * c)[0] for c in range(n)]
        return f"{i}: FORK {forks} join={join}", forks + [join]
    if t == 3:
        nxt = struct.unpack_from("<H", d, o + 0x0A)[0]
        return f"{i}: JOIN -> {nxt}", [nxt]
    nxt = struct.unpack_from("<H", d, o + 0x0A)[0]
    flow, entry = _string_at(d, _q(d, o + 0x18), reloc), _string_at(d, _q(d, o + 0x20), reloc)
    return f"{i}: SOUS-SÉQUENCE {flow or '(ce fichier)'}:{entry} {params(d, _q(d, o + 0x10), reloc)} -> {nxt}", [nxt]


def trace(d: bytes, entry: str, limit: int = 400) -> list[str]:
    fc = _flowchart_full(d)
    names = _dic_names(d, fc["entry_dic"])
    if entry not in names:
        raise SystemExit(f"point d'entrée inconnu : {entry} (connus : {', '.join(names)})")
    start = struct.unpack_from("<H", d, fc["entries"] + names.index(entry) * ENTRY_SIZE + 0x1C)[0]
    seen, todo, out = set(), [start], []
    while todo and len(seen) < limit:
        i = todo.pop(0)
        if i == NO_EVENT or i in seen:
            continue
        seen.add(i)
        line, nxt = event_line(d, i)
        out.append(line)
        todo += nxt
    return out


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("flow", nargs="?", help="nom du script (ex. DoorOfTime)")
    p.add_argument("--romfs", help="RomFS extraite du jeu")
    p.add_argument("--file", help="fichier .bfevfl déjà décompressé")
    p.add_argument("--entry", help="dérouler ce point d'entrée")
    p.add_argument("--find", help="lister les événements qui citent ce texte")
    args = p.parse_args(argv)
    if args.file:
        d = Path(args.file).read_bytes()
    else:
        from ..formats.zs import ZsCodec
        romfs = Path(args.romfs)
        d = ZsCodec(romfs).decompress(romfs / "Event" / "EventFlow" / f"{args.flow}.bfevfl.zs")
    if args.entry:
        print("\n".join(trace(d, args.entry)))
    elif args.find:
        fc = _flowchart_full(d)
        owners = sorted((_q(d, fc["events"] + i * EVENT_SIZE + 0x10), i) for i in range(fc["n_events"]))
        hits = set()
        for slot in string_refs(d).get(args.find, []):
            best = [i for p_, i in owners if p_ and p_ <= slot]
            if best:
                hits.add(best[-1])
        for i in sorted(hits):
            print(event_line(d, i)[0])
    else:
        print("\n".join(describe(d)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
