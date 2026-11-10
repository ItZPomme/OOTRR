"""Vérifie qu'un mod installé correspond à son patch JSON.

    python -m ootrr.tools.verify --romfs "D:\\...\\romfs" --mod "%APPDATA%\\eden\\load\\<id>\\OoTRR" --patch output\\..._patch.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import zstandard

from ..formats.byml import read_byml
from ..formats.restbl import Restbl
from ..formats.zs import ZsCodec
from ..patch import chest_changes, pickup_changes


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--romfs", required=True)
    p.add_argument("--mod", required=True)
    p.add_argument("--patch", required=True)
    args = p.parse_args(argv)
    codec = ZsCodec(args.romfs)
    mod = Path(args.mod) / "romfs"
    patch_data = json.loads(Path(args.patch).read_text(encoding="utf-8"))
    changes = chest_changes(patch_data)
    ground, pickups = pickup_changes(patch_data)
    changes.update(ground)
    removed = {int(h) for h in patch_data.get("removed_actors") or []}

    restbl_file = next((mod / "System" / "Resource").glob("*.rsizetable.zs"))
    restbl = Restbl(zstandard.ZstdDecompressor().decompress(restbl_file.read_bytes(), max_output_size=1 << 28))

    seen: dict[int, int] = {h: 0 for h in set(changes) | {int(h) for h in patch_data.get("removed_actors") or []}}
    errors = 0
    for f in sorted((mod / "Banc").rglob("*.bcett.byml.zs")):
        raw = codec.decompress(f)
        rel = f.relative_to(mod).as_posix()[:-3]
        if restbl.get(rel) < len(raw):
            print(f"ERREUR taille : {rel} {len(raw)} > {restbl.get(rel)}")
            errors += 1
        for actor in read_byml(raw).get("Actors", []):
            h = actor.get("Hash")
            if h not in changes and h not in removed:
                continue
            seen[h] += 1
            if h in removed:
                print(f"ERREUR acteur censé être retiré : {f.name} {h} {actor.get('Gyaml')}")
                errors += 1
                continue
            dyn = actor.get("Dynamic", {})
            for key, value in changes[h].items():
                got = actor.get("Gyaml") if key == "Gyaml" else dyn.get(key)
                if got != value:
                    print(f"ERREUR {f.name} {h} {key}: {got!r} au lieu de {value!r}")
                    errors += 1
    flags = json.loads(Path(args.patch).read_text(encoding="utf-8")).get("start_flags") or {}
    if flags:
        from ..formats.gamedata import enum_value, flag_hash, index
        gd_file = next((mod / "GameData").glob("GameDataList*.byml.zs"))
        raw = codec.decompress(gd_file)
        rel = gd_file.relative_to(mod).as_posix()[:-3]
        if restbl.get(rel) < len(raw):
            print(f"ERREUR taille : {rel} {len(raw)} > {restbl.get(rel)}")
            errors += 1
        idx = index(read_byml(raw))
        for name, value in flags.items():
            section, entry = idx[flag_hash(name)]
            got = entry["DefaultValue"]
            if section == "Enum":
                value = enum_value(entry, value)
            if got != value:
                print(f"ERREUR drapeau {name} = {got!r} au lieu de {value!r}")
                errors += 1
        print(f"{len(flags)} drapeaux de départ vérifiés")
    if pickups:
        rows = {r["__RowId"]: r for r in read_byml(codec.decompress(next((mod / "RSDB").glob("ActorInfo.*.zs"))))}
        for name, item in pickups.items():
            if not (mod / "Pack" / "Actor" / f"{name}.pack.zs").exists():
                print(f"ERREUR archive absente : {name}")
                errors += 1
            item = item.partition("@")[0]
            if rows.get(name, {}).get("ActorName") != item:
                print(f"ERREUR ActorInfo {name} : {rows.get(name, {}).get('ActorName')!r} au lieu de {item!r}")
                errors += 1
            if not restbl.has(f"Pack/Actor/{name}.pack"):
                print(f"ERREUR table des tailles : {name}")
                errors += 1
        print(f"{len(pickups)} objets ramassables sur mesure vérifiés")
    if removed:
        print(f"{len(removed)} acteurs retirés vérifiés")
    missing = [h for h, n in seen.items() if n == 0 and h not in removed]
    for h in missing:
        print(f"ERREUR coffre absent du mod : {h}")
    errors += len(missing)
    print(f"{len(changes)} coffres vérifiés dans {sum(1 for _ in (mod / 'Banc').rglob('*.zs'))} cartes, "
          f"{sum(seen.values())} occurrences, {errors} erreur(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
