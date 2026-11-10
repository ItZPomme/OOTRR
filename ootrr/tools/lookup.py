"""Recherches rapides dans les données du jeu.

    python -m ootrr.tools.lookup --romfs ROMFS flag IsGet.Item_Hookshot PlayerStatus.MaxLife
    python -m ootrr.tools.lookup --romfs ROMFS exp Defeat_Ganon_IsAfter_Ready_Exp     # expression booléenne
    python -m ootrr.tools.lookup --romfs ROMFS msg EventFlowMsg/Enemy_Event Enemy_Scrub_Business_Heart_01
    python -m ootrr.tools.lookup --romfs ROMFS actor Banc/KokiriForest Npc_Kokiri_Mido   # acteurs d'une zone
    python -m ootrr.tools.lookup --romfs ROMFS rsdb PouchActorInfo Item_Ocarina_Time

Les drapeaux de sauvegarde sont identifiés par le MurmurHash3 de leur nom : un nom inconnu du
jeu n'est simplement pas trouvé. Voir docs/GAME_KNOWLEDGE.md pour les noms déjà découverts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..formats.byml import read_byml
from ..formats.gamedata import flag_hash, index
from ..formats.zs import ZsCodec


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--romfs", required=True)
    p.add_argument("kind", choices=("flag", "exp", "msg", "actor", "rsdb"))
    p.add_argument("args", nargs="+")
    a = p.parse_args(argv)
    romfs = Path(a.romfs)
    codec = ZsCodec(romfs)
    if a.kind in ("flag", "exp"):
        idx = index(read_byml(codec.decompress(next((romfs / "GameData").glob("GameDataList*.byml.zs")))))
        names = {}
        for name in a.args:
            entry = idx.get(flag_hash(name))
            if entry is None:
                print(f"{name} : absent")
                continue
            section, e = entry
            if section == "BoolExp":
                # code 0 Bool, 10 expression, 1/12 Enum (égal / à partir de), 2 valeur d'enum,
                # 15 Int + 16 constante (égalité), 3 ET, 4 OU, 5 NON (notation postfixe)
                print(f"{name} : BoolExp {e['Values']}")
            else:
                print(f"{name} : {section} défaut={e.get('DefaultValue')!r}"
                      + (f" valeurs={e['RawValues']}" if "RawValues" in e else ""))
    elif a.kind == "msg":
        from ..formats.msbt import plain, read_labels, read_texts, unit
        from ..formats.sarc import read_sarc
        lang = "USen"
        files = read_sarc(codec.decompress(next((romfs / "Mals").glob(f"{lang}.*.sarc.zs"))))
        d = files[a.args[0] + ".msbt"]
        labels, texts = read_labels(d), read_texts(d)
        for label in a.args[1:] or sorted(labels):
            print(f"{label} : {plain(texts[labels[label]], unit(d)) if label in labels else '(absent)'}")
    elif a.kind == "actor":
        folder, needle = romfs / a.args[0], a.args[1] if len(a.args) > 1 else ""
        for f in sorted(folder.glob("*.bcett.byml.zs")):
            for actor in read_byml(codec.decompress(f)).get("Actors", []):
                if needle in actor.get("Gyaml", "") or needle in str(actor.get("Dynamic", "")):
                    pos = [round(x, 1) for x in actor.get("Translate", [])]
                    print(f"{f.name} {actor['Gyaml']} hash={actor['Hash']} pos={pos} "
                          f"dyn={actor.get('Dynamic')} présence={actor.get('Presence')}")
    elif a.kind == "rsdb":
        table, row = a.args[0], a.args[1] if len(a.args) > 1 else None
        rows = read_byml(codec.decompress(next((romfs / "RSDB").glob(f"{table}.Product.*.rstbl.byml.zs"))))
        for r in rows:
            if row is None or r.get("__RowId") == row:
                print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
