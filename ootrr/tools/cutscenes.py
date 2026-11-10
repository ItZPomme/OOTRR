"""Classe les cinématiques (Event/EventFlow/Dm_*) en « sûres à passer » ou « à garder ».

    python -m ootrr.tools.cutscenes --romfs "D:\\...\\romfs"

Une cinématique est passable si elle a un drapeau HavePlayedEvent.<nom> (le jeu
retient qu'elle a été vue) ET si ni elle ni ses sous-flux ne :
  - modifient un drapeau de sauvegarde (EventTriggerSetGameData*, AddOrSubGameDataInt) ;
  - donnent ou retirent un objet (GetPouchContent*, AddOrRemovePouchContent, ou un nom d'objet cité) ;
  - changent l'heure, sauvegardent, ou changent de scène (titre, crédits…).
Résultat : ootrr/data/cutscenes.json (liste « skippable »), utilisé par le réglage skip_cutscenes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from ..formats.byml import read_byml
from ..formats.evfl import string_refs
from ..formats.gamedata import index, murmur3_32
from ..formats.zs import ZsCodec

STATE_ACTIONS = {
    "EventTriggerSetGameDataBool", "EventTriggerSetGameDataInt", "EventTriggerAddOrSubGameDataInt",
    "EventTriggerSetGameDataFloat", "EventTriggerSetGameDataString", "EventTriggerSetGameDataEnum",
    "GetPouchContent", "GetPouchContentByActorName", "EventTriggerAddOrRemovePouchContent", "PouchSystemActor",
    "EventTrigger_SetTime", "EventTriggerRequestAutoSave",
}
SCENE_RE = re.compile(r"Banc|ChangeScene|SceneChange|LoadScene|Stage(Change|Load)|GameOver|Ending|Credit|Title", re.I)
ITEM_PREFIX = ("Item_", "Obj_Heart", "Weapon_Sword", "Weapon_Shield", "Armor_")
ACTOR_PREFIX = ("Npc_", "Enemy_", "Obj_", "Item_", "Animal_", "Player", "Weapon_", "Armor_", "Land_", "Navi")
OUT = Path(__file__).resolve().parents[1] / "data" / "cutscenes.json"
# scènes que l'événement de démarrage joue sans condition (vérifiées : sans objet ni drapeau)
EVENT_SKIPS = {"OpeningEvent": ["Dm_Kokiri_0000", "Dm_Kokiri_0030"]}


def classify(romfs: Path) -> tuple[list[str], dict[str, list[str]]]:
    codec = ZsCodec(romfs)
    idx = index(read_byml(codec.decompress(next((romfs / "GameData").glob("GameDataList*.byml.zs")))))
    flows = {p.name.replace(".bfevfl.zs", ""): p for p in (romfs / "Event" / "EventFlow").glob("*.bfevfl.zs")}
    cache: dict[str, set[str]] = {}
    memo: dict[str, list[str]] = {}

    def refs_of(f: str) -> set[str]:
        if f not in cache:
            cache[f] = set(string_refs(codec.decompress(flows[f])))
        return cache[f]

    def reasons(f: str, stack: tuple = ()) -> list[str]:
        if f in memo:
            return memo[f]
        if f in stack:
            return []
        r = refs_of(f)
        why = sorted(r & STATE_ACTIONS)
        why += [f"scène:{s}" for s in sorted(r) if SCENE_RE.search(s)]
        why += [f"objet:{s}" for s in sorted(r) if s.startswith(ITEM_PREFIX)]
        for s in sorted(r):
            if s in flows and s != f and not s.startswith(ACTOR_PREFIX) and reasons(s, stack + (f,)):
                why.append(f"sous-flux:{s}")
        memo[f] = why
        return why

    safe, kept = [], {}
    for flow in sorted(f for f in flows if f.startswith("Dm_")):
        if murmur3_32(f"HavePlayedEvent.{flow}") not in idx:
            continue
        why = reasons(flow)
        if why:
            kept[flow] = why
        else:
            safe.append(flow)
    return safe, kept


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--romfs", required=True)
    args = p.parse_args(argv)
    safe, kept = classify(Path(args.romfs))
    OUT.write_text(json.dumps({
        "_doc": "Cinématiques sans effet sur la partie (ni objet, ni drapeau, ni changement de scène) : "
                "le réglage skip_cutscenes=safe les marque comme déjà vues dès la nouvelle partie. "
                "Généré par python -m ootrr.tools.cutscenes.",
        "skippable": safe,
        "_event_skips": "Scènes jouées sans vérifier le drapeau « déjà vue » : l'étape qui les joue est sautée "
                        "dans l'événement indiqué (ex. narration de la tapisserie et réveil par Navi au démarrage).",
        "event_skips": EVENT_SKIPS,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(safe)} cinématiques passables, {len(kept)} gardées -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
