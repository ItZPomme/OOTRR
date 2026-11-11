"""Boutiques : listes d'articles des marchands (ShopParam) et marchand des Missiles.

Chaque marchand porte dans son archive (Pack/Actor/Npc_*_Shop*.pack.zs) un ou plusieurs fichiers
`Component/ShopParam/…` dont `GoodsList` liste ses 8 articles dans l'ordre de `ShopItemIndex` :
`Actor` (article affiché), `Release` (condition d'apparition : « Coming Soon » tant que la donnée
GameData est fausse, ou « épuisé » avec IsCheckSoldOutGameData), `StockNum` (-1 = illimité).
Un article absent de la liste n'est pas affiché : un jeton doit y prendre la place de l'article.
"""

from __future__ import annotations

from pathlib import Path

from .formats.byml import read_byml
from .formats.sarc import Sarc

# archive du marchand -> boutique (les deux variantes d'un même marchand partagent la liste)
SHOPKEEPERS = {
    "Npc_Kokiri_001_Shop_Child": "KF Shop",
    "Npc_Kokiri_001_Shop_Child_ShortStock": "KF Shop",  # avant l'Arbre Mojo
    "Npc_Kokiri_001_Shop_Adult": "KF Shop",
    "Npc_Hylia_018_Shop_Child": "Market Bazaar",
    "Npc_Hylia_018_Shop_Adult": "Kak Bazaar",
    "Npc_Hylia_020_Shop_Child": "Market Potion Shop",
    "Npc_Hylia_020_Shop_Adult": "Kak Potion Shop",
    "Npc_Hylia_021_Shop_Child": "Market Bombchu Shop",
    "Npc_Goron_011_Shop_Child": "GC Shop",
    "Npc_Goron_011_Shop_Adult": "GC Shop",
    "Npc_Zora_011_Shop_Child": "ZD Shop",
    "Npc_Zora_011_Shop_Adult": "ZD Shop",
}
SHOP_PARAM_DIR = "Component/ShopParam/"
NO_RELEASE = {"IsCheckReleaseGameData": False, "ReleaseGameData": ""}
# le marchand des Missiles n'apparaît qu'après la pierre du feu (Get_StoneOfFire_IsCompleted_Exp) :
# présence retirée (Market_Child_Static)
BOMBCHU_KEEPER = "Npc_Hylia_021_Shop_Child"


def actor_path(actor: str) -> str:
    return f"Work/Actor/{actor}.engine__actor__ActorParam.gyml"


MAX_RANK = 4  # articles mélangeables par boutique (réglage shuffle_shops : off, 1 à 4)
SHOP_FLAG = "OoTRR.Shop{}"  # vrai si shuffle_shops >= N : le jeton de rang N remplace l'article


def shop_flags() -> list[str]:
    return [SHOP_FLAG.format(k) for k in range(1, MAX_RANK + 1)]


def variant_name(name: str, count: int) -> str:
    """Component/ShopParam/X.game__…bgyml -> X_C<count> (liste quand <count> articles sont mélangés)."""
    head, dot, tail = name.partition(".")
    return f"{head}_C{count}{dot}{tail}"


def shopkeeper_changes(romfs: Path, codec, slots: dict[str, dict[int, tuple[str, int]]]) -> dict[str, dict[str, dict]]:
    """pack_changes pour ModBuilder : listes des marchands, tous les articles débloqués (plus de
    « Coming Soon » ni d'article épuisé). La liste d'origine garde les articles d'origine ; une variante
    X_C<n> par nombre n d'articles mélangés (1 à 4) met les jetons de rang <= n (`slots` :
    {boutique: {index: (jeton, rang)}}). Le module natif choisit la variante selon les réglages."""
    changes: dict[str, dict[str, dict]] = {}
    for keeper, shop in SHOPKEEPERS.items():
        sarc = Sarc(codec.decompress(romfs / "Pack" / "Actor" / f"{keeper}.pack.zs"))
        for name, data in sarc.files.items():
            if not name.startswith(SHOP_PARAM_DIR):
                continue
            goods = read_byml(data).get("GoodsList")
            if not goods:
                continue  # hérite de la liste d'un autre fichier
            if len(goods) != 8:
                raise ValueError(f"{keeper} {name} : {len(goods)} articles")
            for count in range(0, MAX_RANK + 1):
                new = []
                for i, g in enumerate(goods):
                    g = dict(g)
                    g["Release"] = dict(NO_RELEASE)
                    token, rank = slots.get(shop, {}).get(i, (None, 0))
                    if token and rank <= count:
                        g["Actor"] = actor_path(token)
                    new.append(g)
                fields = {"GoodsList": new}
                if count:
                    fields["__copy_from"] = name
                changes.setdefault(keeper, {})[variant_name(name, count) if count else name] = fields
    return changes


def presence(flag: str, negation: bool) -> dict:
    return {"FlagName": flag, "IsCheckLazy": False, "IsNegation": negation}


KF_GATE = "Meet_DekuTree_IsAfter_Step02_Exp"


def kokiri_gate_changes(romfs: Path, codec) -> tuple[dict[int, dict], set[int]]:
    """Boutique Kokiri : deux jeux d'articles (et de marchands) selon l'Arbre Mojo. Tout étant débloqué,
    le jeu « avant » est retiré et le jeu « après » toujours présent. Renvoie (changements, retirés)."""
    changes: dict[int, dict] = {}
    removed: set[int] = set()
    for path in sorted((romfs / "Banc" / "KokiriForest").glob("*.bcett.byml.zs")):
        for a in read_byml(codec.decompress(path)).get("Actors", []):
            p = a.get("Presence") or {}
            g = a["Gyaml"]
            if p.get("FlagName") != KF_GATE or not (g.startswith("Shop_") or g.startswith("Npc_Kokiri_001_Shop")):
                continue
            if p.get("IsNegation"):
                changes[a["Hash"]] = {"__delete": True}
                removed.add(a["Hash"])
            else:
                changes[a["Hash"]] = {"Presence": None}
    return changes, removed


def dual_actor_changes(romfs: Path, codec, tokens: dict[int, tuple[str, int]]) -> dict[int, dict]:
    """Articles mélangeables : l'article d'origine reste, présent tant que OoTRR.Shop<rang> est faux ;
    une copie (jeton) à la même place, présente quand il est vrai. Les étiquettes de quantité liées à
    l'article (lien Reference -> Shop_Board_*) suivent l'article d'origine.
    tokens : {hash d'article: (jeton, rang)}. Renvoie les changements d'acteurs (à fusionner)."""
    changes: dict[int, dict] = {}
    for path in sorted((romfs / "Banc").rglob("*Static.bcett.byml.zs")):
        actors = read_byml(codec.decompress(path)).get("Actors", [])
        # le marchand désigne ses articles par des liens (ForSale, Reference) : la copie en reçoit aussi
        links_to: dict[int, list[tuple[int, dict]]] = {}
        for npc in actors:
            for link in npc.get("Links", []):
                links_to.setdefault(link["Dst"], []).append((npc["Hash"], link))
        for a in actors:
            if a["Hash"] not in tokens:
                continue
            token, rank = tokens[a["Hash"]]
            flag = SHOP_FLAG.format(rank)
            clone_hash = (a["Hash"] * 0x9E3779B1 + rank) & 0xFFFFFFFFFFFFFFFF
            changes[a["Hash"]] = {"Presence": presence(flag, True),
                                  "__clone": [{"Hash": clone_hash, "Gyaml": token, "Presence": presence(flag, False)}]}
            for npc_hash, link in links_to.get(a["Hash"], []):
                new = dict(link)
                new["Dst"] = type(link["Dst"])(clone_hash)
                changes.setdefault(npc_hash, {}).setdefault("__add_links", []).append(new)
            for link in a.get("Links", []):
                if link.get("Name") == "Reference":
                    changes[link["Dst"]] = {"Presence": presence(flag, True)}
    return changes


def gated_board_hashes(romfs: Path, codec) -> list[int]:
    """Panneaux « épuisé » posés devant les articles tant qu'une condition n'est pas remplie (boutique
    Kokiri avant l'Arbre Mojo) : retirés, les articles étant débloqués. Les panneaux sans condition
    (marché) servent à marquer un article épuisé et restent."""
    out = []
    for path in sorted((romfs / "Banc").rglob("*.bcett.byml.zs")):
        if "Kokiri" not in path.name:
            continue
        for a in read_byml(codec.decompress(path)).get("Actors", []):
            if a["Gyaml"] == "Shop_Board_SoldOut" and a.get("Presence"):
                out.append(a["Hash"])
    return out


def bombchu_keeper_hashes(romfs: Path, codec) -> list[int]:
    data = read_byml(codec.decompress(romfs / "Banc" / "Market" / "Market_Child_Static.bcett.byml.zs"))
    return [a["Hash"] for a in data["Actors"] if a["Gyaml"] == BOMBCHU_KEEPER]
