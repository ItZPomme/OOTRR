"""Mod de test : les 4 coffres de la maison de Mido (forêt Kokiri) contiennent
des objets reconnaissables au lieu de rubis.

    python -m ootrr.tools.testmod --romfs "D:\\...\\romfs" [--install]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from ..formats.byml import read_byml
from ..modbuild import ModBuilder, emulator_root, install

TESTS = {
    # test 1 : un objet quelconque dans un coffre (validé en jeu)
    "1": {
        10831981390482426294: "Item_Hookshot",    # Mido, rubis vert à l'origine
        4555665598794293658: "Item_HoverBoot",    # Mido, rubis bleu
        9725242744547055868: "Item_Range_Bow",    # Mido, rubis bleu
        12786193094758345086: "Item_Boomerang",   # Mido, rubis bleu
    },
    # test 2 : améliorations dans le désordre, chant, pierre ancestrale, coffre à événement
    "2": {
        10831981390482426294: "Item_Longshot",            # Mido, ouvrir en 1er
        4555665598794293658: "Item_Hookshot",             # Mido, ouvrir en 2e
        9725242744547055868: "Item_Gauntlet_Silver",      # Mido
        12786193094758345086: "Item_Melody_ZeldaLullaby", # Mido
        16757992849254467386: "Item_Stone_Fire",          # coffre de l'Épée Kokiri
    },
    # test 3 : capacité des sacs, ocarina + chant, coffre à événement sans son événement
    "3": {
        10831981390482426294: "Item_BombBag_Large",       # Mido, ouvrir en 1er
        4555665598794293658: "Item_BombBag_Small",        # Mido, ouvrir en 2e
        9725242744547055868: "Item_Ocarina_Fairy",        # Mido
        12786193094758345086: "Item_Melody_ZeldaLullaby", # Mido
        16757992849254467386: {"Drop__DropActor": "Item_Wallet_Large", "GetEventName": None},  # coffre de l'Épée
    },
    # test 4 : munitions. L'événement d'origine de l'objet le remplit-il ?
    "4": {
        10831981390482426294: {"Drop__DropActor": "Item_BombBag_Small",       # Mido, ouvrir en 1er
                               "GetEventName": "Get_StoneOfFire_GetBombBag"},
        4555665598794293658: "Item_BombBundle_Small",                          # Mido, ouvrir en 2e
        9725242744547055868: "Item_Range_SlingShot",                           # Mido, sans événement
        12786193094758345086: {"Drop__DropActor": "Item_Range_SlingShot",     # Mido, avec l'événement d'origine
                               "GetEventName": "InsideTheDekuTree_GetSlingShot"},
    },
    # test 5 : les bombes exigent-elles le Bracelet Goron ?
    "5": {
        10831981390482426294: "Item_BombBag_Small",       # Mido, ouvrir en 1er : essayer une bombe
        4555665598794293658: "Item_Gauntlet_Goron",       # Mido, ouvrir en 2e : réessayer
    },
    # test 6 : objets donnés par les événements (PNJ, boss)
    "6": {},
    # test 7 : cœurs posés au sol remplacés par des coffres
    "7": {
        17948245526767051747: {"Gyaml": "Obj_TBox_A_02_NoBake", "Drop__DropActor": "Item_Hookshot"},   # réceptacle de Gohma
        13389209437182306002: {"Gyaml": "Obj_TBox_A_01_NoBake", "Drop__DropActor": "Item_HoverBoot"},  # quart de cœur de Kakariko
        17926402522258180222: {"Gyaml": "Obj_TBox_A_01_NoBake", "Drop__DropActor": "Item_Range_Bow"},  # quart de cœur de Kakariko
    },
}

TESTS["8"] = {}

# modifications d'archives d'acteurs par test : {acteur: {fichier interne: {clé: valeur}}}
PACK_TESTS = {
    # test 8 : un cœur ramassé donne un autre objet (paramètre PouchActor, comme la bombe au sol)
    "8": {
        "Obj_Heart_Container": {"Component/PouchContentParam/HeartUtuwa.game__component__PouchContentParam.bgyml":
                                {"PouchActor": "Work/Actor/Item_Hookshot.engine__actor__ActorParam.gyml"}},
        "Obj_Heart_Piece": {"Component/PouchContentParam/HeartPiece.game__component__PouchContentParam.bgyml":
                            {"PouchActor": "Work/Actor/Item_HoverBoot.engine__actor__ActorParam.gyml"}},
    },
}

TESTS["9"] = {}

# test 10 : objets ramassables sur mesure (copies du réceptacle) à la place des quarts de cœur de Kakariko
TESTS["10"] = {
    13389209437182306002: {"Gyaml": "Obj_OoTRR_Pickup_000"},   # moulin
    17926402522258180222: {"Gyaml": "Obj_OoTRR_Pickup_001"},   # second quart de cœur au sol
}
TESTS["11"] = dict(TESTS["10"])
# test 12 : réceptacle de Gohma remplacé par un objet sur mesure + nouvelles catégories, à des quarts
# de cœur faciles à atteindre en enfant (plaine d'Hyrule, rivière Zora)
TESTS["12"] = {
    9814903750835309225: {"Gyaml": "Obj_OoTRR_Pickup_000"},    # plaine d'Hyrule, près des ruines de Lon Lon (enfant)
    4189391771527808272: {"Gyaml": "Obj_OoTRR_Pickup_001"},    # rivière Zora (1)
    11455676800795329345: {"Gyaml": "Obj_OoTRR_Pickup_003"},   # rivière Zora (2)
    17948245526767051747: {"Gyaml": "Obj_OoTRR_Pickup_002"},   # réceptacle de Gohma
    # de quoi faire sauter les rochers de la rivière Zora : sac de bombes + bracelet dans la maison de Mido
    10831981390482426294: {"Drop__DropActor": "Item_BombBag_Small"},
    4555665598794293658: {"Drop__DropActor": "Item_Gauntlet_Goron"},
}
PICKUP_TESTS = {
    "10": {"Obj_OoTRR_Pickup_000": "Item_Range_Bow", "Obj_OoTRR_Pickup_001": "Item_HoverBoot"},
    # test 11 : mêmes emplacements, objets d'enfant (visibles dans l'inventaire de Link enfant)
    "11": {"Obj_OoTRR_Pickup_000": "Item_Boomerang", "Obj_OoTRR_Pickup_001": "Item_Range_SlingShot"},
    # test 12 : Boot (équipement), KeyItem spécial (bracelet), Material (masse) dans la salle du boss
    "12": {"Obj_OoTRR_Pickup_000": "Item_HoverBoot", "Obj_OoTRR_Pickup_001": "Item_Melody_SunSong",
           "Obj_OoTRR_Pickup_002": "Item_Hammer", "Obj_OoTRR_Pickup_003": "Item_Scale_Silver"},
}

# modifications des tables RSDB par test : {table: {__RowId: {champ: valeur}}}
RSDB_TESTS = {
    # test 9 : le cœur ramassé porte le nom d'un autre objet (comme Obj_Bomb -> Item_Bomb)
    "9": {
        "ActorInfo": {
            "Obj_Heart_Container": {"ActorName": "Item_Hookshot"},
            "Obj_Heart_Piece": {"ActorName": "Item_HoverBoot"},
        },
        "PouchActorInfo": {
            "Obj_Heart_Container": {"__copy_from": "Item_Hookshot"},
            "Obj_Heart_Piece": {"__copy_from": "Item_HoverBoot"},
        },
    },
}

# modifications d'événements par test : {flux: {ancien objet: nouvel objet}}
EVENT_TESTS = {
    "6": {
        "Dm_Kokiri_0155": {"Item_Ocarina_Fairy": "Item_Boomerang"},     # Saria sur le pont
        "Dm_Kokiri_0130": {"Item_Stone_Forest": "Item_Stone_Water"},    # récompense de Gohma
        "Dm_Deku_BossOut": {"Obj_Heart_Container": "Item_Hookshot"},    # réceptacle de Gohma
    },
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--romfs", required=True)
    p.add_argument("--out", default="output/mod_test")
    p.add_argument("--test", default="2", choices=sorted(TESTS))
    p.add_argument("--install", action="store_true", help="copier dans le dossier de mods d'Eden")
    args = p.parse_args(argv)

    changes = {h: (v if isinstance(v, dict) else {"Drop__DropActor": v}) for h, v in TESTS[args.test].items()}
    MIDO_CHESTS = {h: c["Drop__DropActor"] for h, c in changes.items() if "Drop__DropActor" in c}
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    builder = ModBuilder(args.romfs)
    report = builder.build(changes, out / "romfs", event_changes=EVENT_TESTS.get(args.test),
                           pack_changes=PACK_TESTS.get(args.test), rsdb_changes=RSDB_TESTS.get(args.test),
                           pickups=PICKUP_TESTS.get(args.test))
    for line in report:
        print(line)

    # vérification : relire le mod produit
    for f in (out / "romfs" / "Banc").rglob("*.zs"):
        root = read_byml(builder.codec.decompress(f))
        got = {a["Hash"]: a["Dynamic"]["Drop__DropActor"] for a in root["Actors"] if a.get("Hash") in MIDO_CHESTS}
        assert all(MIDO_CHESTS[h] == v for h, v in got.items()), (f, got)
    print("Relecture du mod : OK")

    if args.install:
        target = install(out, emulator_root(), "OoTRR-test")
        print(f"Installé dans {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
