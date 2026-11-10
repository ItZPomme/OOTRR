"""Inventaire des coffres et objets placés dans les cartes du jeu (Banc/*.bcett.byml.zs).

    python -m ootrr.tools.inventory --romfs "D:\\...\\romfs" --out inventaire

Produit :
  chests.json    un enregistrement par coffre (zone, fichier, hash, contenu, événement, position)
  drops.json     liste des valeurs Drop__DropActor rencontrées, avec leur nombre
  inventory.txt  résumé lisible par zone
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ..formats.byml import read_byml
from ..formats.zs import ZsCodec


def scan(romfs: Path):
    codec = ZsCodec(romfs)
    chests, drops = [], Counter()
    files = sorted((romfs / "Banc").rglob("*.bcett.byml.zs"))
    for i, path in enumerate(files, 1):
        print(f"\r[{i}/{len(files)}] {path.parent.name:<28}", end="", file=sys.stderr)
        root = read_byml(codec.decompress(path))
        for actor in root.get("Actors", []) or []:
            dyn = actor.get("Dynamic") or {}
            drop = dyn.get("Drop__DropActor")
            if drop is None:
                continue
            drops[drop] += 1
            gyaml = actor.get("Gyaml", "")
            chests.append({
                "area": path.parent.name,
                "file": path.name,
                "hash": actor.get("Hash"),
                "actor": gyaml,
                "is_chest": "TBox" in gyaml,
                "drop": drop,
                "event": dyn.get("GetEventName"),
                "name": actor.get("Name"),
                "pos": [round(v, 2) for v in actor.get("Translate", [0, 0, 0])],
                "dynamic": {k: v for k, v in dyn.items() if k not in ("Drop__DropActor", "GetEventName")},
            })
    print(file=sys.stderr)
    return chests, drops


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--romfs", required=True)
    p.add_argument("--out", default="inventaire")
    args = p.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    chests, drops = scan(Path(args.romfs))
    (out / "chests.json").write_text(json.dumps(chests, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "drops.json").write_text(json.dumps(drops.most_common(), indent=1, ensure_ascii=False), encoding="utf-8")

    by_area = defaultdict(list)
    for c in chests:
        by_area[c["area"]].append(c)
    lines = []
    for area in sorted(by_area):
        items = by_area[area]
        lines.append(f"[{area}]  {sum(c['is_chest'] for c in items)} coffres, {len(items)} acteurs avec contenu")
        for c in sorted(items, key=lambda c: (c["file"], c["actor"])):
            age = "adulte" if "_Adult_" in c["file"] else "enfant" if "_Child_" in c["file"] else "-"
            lines.append(f"   {age:<7} {c['actor']:<28} {c['drop']:<32} {c['event'] or '':<40} {c['hash']}")
    (out / "inventory.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(chests)} acteurs avec contenu ({sum(c['is_chest'] for c in chests)} coffres), "
          f"{len(drops)} contenus différents -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
