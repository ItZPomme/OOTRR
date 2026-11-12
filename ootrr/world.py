"""Chargement et validation des données du monde (objets, régions, lieux)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rules import Rule, RuleCompiler, RuleError

DATA_DIR = Path(__file__).parent / "data"

LOCATION_KINDS = ("general", "song", "reward")

# nom de donjon dans la logique -> nom utilisé par le jeu (dossiers Banc, drapeaux DungeonInfo.*)
GAME_DUNGEONS = {
    "Deku Tree": "InsideTheDekuTree",
    "Dodongos Cavern": "DodongoCavern",
    "Jabu Jabus Belly": "InsideJabuJabuBelly",
    "Forest Temple": "ForestTemple",
    "Fire Temple": "FireTemple",
    "Water Temple": "WaterTemple",
    "Shadow Temple": "ShadowTemple",
    "Spirit Temple": "SpiritTemple",
    "Bottom of the Well": "BottomOfTheWell",
    "Ice Cavern": "IceCavern",
    "Gerudo Training Ground": "GerudoTrainingGround",
}
JUNK_REPLACEMENT = "TBox_Rupee_Green"
# réglage skip_child_zelda : ces lieux donnent leur objet dès la nouvelle partie
SKIP_CHILD_ZELDA = ("HC Zeldas Letter", "Song from Impa")
# scène de Rauru sautée : la récompense de la poche de Link est donnée au départ
LINKS_POCKET = "Links Pocket"
SKIP_RAURU_FLAGS = ("HavePlayedEvent.Dm_TimeTemple_0040",)  # 1re fois l'épée tirée -> salle des sages
# scènes qui donnent chaque récompense de boss (l'objet y est nommé en clair) ; .110 = version de la mise à jour
REWARD_EVENTS = {
    "Queen Gohma": ["Dm_Kokiri_0130"],
    "King Dodongo": ["Dm_DeathMtTrail_0025"],
    "Barinade": ["Dm_ZoraFountain_0030", "Dm_InsideJabu_Jabu_0030", "Dm_InsideJabu_Jabu_0030.110"],
    "Phantom Ganon": ["Dm_Awake_Forest_Get", "Dm_Awake_Forest_Get.110"],
    "Volvagia": ["Dm_Awake_Fire_Get", "Dm_Awake_Fire_Get.110"],
    "Morpha": ["Dm_Awake_Water_Get", "Dm_Awake_Water_Get.110"],
    "Bongo Bongo": ["Dm_Awake_Shadow_Get", "Dm_Awake_Shadow_Get.110"],
    "Twinrova": ["Dm_Awake_Spirit_Get", "Dm_Awake_Spirit_Get.110"],
}
# réglage open_door_of_time : la quête « DoorOfTime » démarre à l'étape Step06 (porte ouverte),
# donc Zelda et Impa ne sont plus là : leurs objets sont donnés au départ. L'Ocarina du Temps
# reste dans les douves (module modifié pour l'étape Step06), ramassable avec les 3 pierres.
OPEN_DOOR_START = SKIP_CHILD_ZELDA
DOOR_OF_TIME_STEP = ("Enum", 931730378, "Step06")  # état de la quête (enum GameData sans nom connu)
# Rencontrer Zelda (Goto_HyruleCastle:Goto_HyruleCastle_MeetZelda) fait passer la quête Goto_HyruleCastle à
# Complete et DoorOfTime à Step01 ; c'est ce qui lance le cycle jour / nuit. Avec skip_child_zelda (ou la
# porte ouverte), ces états sont posés au départ. Enum de Goto_HyruleCastle : hash relevé dans l'expression
# Goto_HyruleCastle_IsCompleted_Exp.
MEET_ZELDA_QUEST = ("Enum", 3683238313, "Complete")
# départ adulte : drapeau de l'époque (vrai = enfance), épée donnée (elle sert à redevenir enfant)
ADULT_FLAG = "Sequence_IsChildhood"
ADULT_START_ITEMS = ("Weapon_Sword_Master",)
# start_with_consumables : premier sac plein (10 bâtons, 20 noix). L'ajout à l'inventaire crée l'objet mais
# laisse son stock à 0 (constaté en jeu) : le stock est l'entier PouchData.<objet>.StockNum
START_CONSUMABLES = (("Item_DekuStick", 10), ("Item_DekuNut", 20))
# ... après le petit sac de chaque objet : sans lui le maximum est 0 et le stock reste à 0 (constaté)
START_CONSUMABLE_BAGS = ("Item_StickBag_Small", "Item_NutBag_Small")
MEET_ZELDA_DOOR_STEP = ("Enum", 931730378, "Step01")
# l'Ocarina du Temps n'apparaît dans les douves qu'à l'étape Step04 de la quête : Step06 avec la porte ouverte
OPEN_DOOR_OCARINA = {"HyruleField_Child_Prefab_91f9": {"Step04": "Step06"}}
# ... et seulement quand Link a les 3 pierres : nouvelle expression booléenne + condition de présence
HAS_ALL_STONES_EXP = "OoTRR_HasAllStones_Exp"
BOOL_EXPS = {HAS_ALL_STONES_EXP: [("Bool", "IsGet.Item_Stone_Forest"), ("Bool", "IsGet.Item_Stone_Fire"), ("AND",),
                                  ("Bool", "IsGet.Item_Stone_Water"), ("AND",)]}
OCARINA_OF_TIME_ACTOR = 2802436684568022035  # Obj_Ocarina_Time_A_01, douves (HyruleField_Child_Static)
# La scène de Zelda dans les douves ne se déclenche pas avec la porte ouverte, et un ocarina
# ramassé au sol n'est pas jouable (seuls les « dons » des scènes et des coffres le sont).
# -> l'ocarina des douves est retiré et remplacé par un coffre au bord, près du pont-levis :
# il contient l'Ocarina du Temps et joue à l'ouverture le script des douves (qui donne aussi
# le Chant du Temps). Le coffre est une copie d'un coffre de la même carte.
MOAT_CHEST_SOURCE = 5755485285664292988  # Obj_TBox_A_01_NoBake de HyruleField_Child_Static
MOAT_CHEST = 0x007A7253_0000_0002        # nouvel acteur (hash libre dans la carte)
MOAT_LAND_POS = [-2.5, 150.4, 55.5]      # sol, sortie du pont-levis, à côté du point d'arrivée StartPos_DoorOfTime (-0.08, 150.4, 54.2)
MOAT_CHEST_EVENT = "HyruleField_DoorOfTime_GetOcarinaOfTime"
# skip_cutscenes=safe : scènes de Kaepora Gaebora mises de côté par le tri automatique (elles posent
# des drapeaux) mais sans objet, et la découverte de la forêt à la sortie de la maison (Dm_Kokiri_0045 : caméra, nom du lieu ;
# écartée par le tri car elle replace Link devant sa porte)
EXTRA_SKIPPED = ("Dm_HrlField_0005", "Dm_HrlField_0010", "Dm_HrlField_0080",
                 "Dm_LakeHrl_0003", "Dm_LakeHrl_0005", "Dm_LakeHrl_0010", "Dm_Kokiri_0045")
# Cycle jour / nuit de la plaine : en quittant la forêt (Goto_HyruleCastle:KokiriForest_ArriveLostWood, étape
# 182), le jeu pose HyruleField_ChangeENV = vrai ; la plaine enfant prend alors la palette
# MainField_Bluesky_First (WorldParam HyruleField_Child, ConditionEnvTimePalette), qui force la lumière du
# soleil (IsForceMainLight, soleil fixe). Seule la scène du hibou à l'entrée de la plaine
# (Goto_HyruleCastle_Kaepora_00, étape 181) le remet à faux. Elle n'est demandée (module
# HyruleField_Child_Prefab_de5f) que si Dm_HrlField_0010 n'est pas vue et la quête Goto_HyruleCastle est à
# Step01 : avec ses scènes marquées vues (EXTRA_SKIPPED) ou Zelda passée (quête Complete), la lumière restait
# figée. L'étape qui pose le drapeau est sautée (la palette « First » n'est qu'un éclairage de première arrivée).
FIELD_FIRST_PALETTE_STEP = ("Goto_HyruleCastle", "#182")
# Le temps ne s'écoule qu'après l'arrivée à l'entrée de la plaine : 0x345c020 (« heure figée ? », appelé par
# l'avance de l'heure 0x3cdf70) répond « libre » si la quête Meet_DekuTree est à Ready, ou si
# HyruleField_ArriveEntrance est vrai et HrlField_HasEnteredFirstTime_Adult faux ; sinon l'heure ne bouge plus et
# les demandes d'heure (Chant du Soleil) sont effacées sans être appliquées (trace native en jeu, 2026-11-12 :
# 6 h 00 pendant toute la partie, demandes 0 h et 20 h ignorées). HyruleField_ArriveEntrance n'est posé que par la
# scène du hibou (Goto_HyruleCastle_Kaepora_00, étape 132), jamais jouée avec les scènes passées ou Zelda passée.
TIME_FLOW_FLAG = "HyruleField_ArriveEntrance"
# La scène de Saria au pont (Dm_Kokiri_0155) n'est plus passée : Saria donne son objet au pont (l'Ocarina
# des fées, ou l'objet de la seed avec shuffle_ocarinas), comme dans le jeu d'origine.
SARIA_GIFT = "LW Gift from Saria"
OCARINA_OF_TIME_LOCATION = "HF Ocarina of Time Item"
SONG_OF_TIME_LOCATION = "Song from Ocarina of Time"  # aussi donné directement aux douves (moat_items)
# jamais de bombes à ces deux lieux (sans sac, un coffre de bombes donne le sac de bombes, constaté en jeu ;
# le même risque n'a pas pu être écarté pour une scène) ; même règle dans generator.cpp (CanPlace)
OCARINA_FORBIDDEN_PREFIX = "Item_BombBundle"
# shuffle_ocarinas : scènes qui donnent les ocarinas (action d'inventaire + affichage nommant l'objet)
OCARINA_EVENTS = {SARIA_GIFT: ("Dm_Kokiri_0155", "Item_Ocarina_Fairy"),
                  OCARINA_OF_TIME_LOCATION: ("Dm_MelodyGet_Time", "Item_Ocarina_Time")}
# lieux dont la première découverte est faite par la scène d'arrivée (RSDB Location,
# IsShowLocationUIFirstTimeInDemo = vrai) ; relevé dans la version 2.0.0
LOCATIONS_SHOWN_IN_DEMO = (
    "BottomOfTheWell", "DeathMountainCrater", "DeathMountainTrail", "DesertColossus", "DodongoCavern",
    "DreamWorld", "FireTemple", "ForestTemple", "GanonCastle", "GerudoFortress", "GerudoTrainingGround",
    "GerudoValley", "GoronCity", "Graveyard", "HyruleCastle", "HyruleField", "IceCavern", "IngoRanch",
    "InsideJabuJabuBelly", "InsideTheDekuTree", "KakarikoVillage", "KokiriForest", "LakeHylia",
    "LonLonRanch", "Market", "SacredForestMeadow", "ShadowTemple", "SpiritTemple", "TimeTemple",
    "WaterTemple", "ZoraDomain", "ZoraFountain", "ZoraRiver",
)
# skip_cutscenes=safe : drapeaux « déjà fait » pour des interruptions sans objet
SKIP_FLAGS = (
    # forêt Kokiri déjà découverte : pas de carte « Forêt Kokiri » à la sortie de la maison (sa scène
    # Dm_Kokiri_0045 est passée, le jeu montrerait la carte à la première entrée)
    "IsVisitLocation.KokiriForest",
    # porte de la maison de Link ouverte dès le départ : sinon elle joue Dm_Kokiri_0045 en s'ouvrant
    # (OpenEventName de l'acteur, sans tenir compte du drapeau « déjà vue ») ; la scène pose ce drapeau
    "KokiriForest_LinkHouseDoor_Open",
    # la Kokiri sur le toit de la boutique qui appelle Link au premier passage
    "KokiriForest_Kokiri_011_StopInFrontOfShop_00",
    "HaveTalked_Special.Npc_Kokiri_011_Child_BefoerStopInFrontOfShop_Talk_Event111",
    # la Kokiri de la boutique qui fait essayer le bouclier
    "Npc_Kokiri_010_Child_Teach",
    "HaveTalked_Special.Npc_Kokiri_010_Child_FocusOnAttentionRock_ShieldDeku_Event94",
)
# Les demandes d'événement qui font arrêter Link par ces Kokiri sont rendues absentes (condition de
# présence : scène d'introduction pas encore vue, donc toujours faux une fois la partie commencée)
# Talon devant le château (HyruleCastle_Static) : comme Impa, il disparaît une fois Zelda rencontrée
# (DoorOfTime >= Step01), donc avec « Zelda enfant passée » ou la porte ouverte il n'est plus là
TALON_CASTLE = 5439531180495276262
TALON_GONE = {"FlagName": "DoorOfTime_IsAfter_Step01_Exp", "IsCheckLazy": False, "IsNegation": True}
KOKIRI_INTERRUPTIONS = (
    15690126774393333419,  # KokiriForest_Kokiri_011_StopInFrontOfShop_00 (toit de la boutique)
    18383848770792576395,  # SubEvent_Kokiri_011_FocusOnNPC
    362318883433329390,    # Npc_Kokiri_010_FocusOnAttentionRock_ShieldDeku (essai du bouclier)
    9786449099218098875,   # FocusOnAttentionRock_ShieldDeku_Short
)
NEVER_AFTER_INTRO = {"FlagName": "HavePlayedEvent.Dm_Kokiri_0030", "IsCheckLazy": False, "IsNegation": True}
# … et « déjà obtenu » pour les consommables ramassés (pas d'animation la première fois)
CONSUMABLES = (
    "Obj_Rupee_Green", "Obj_Rupee_Blue", "Obj_Rupee_Red", "Obj_Rupee_Purple", "Obj_Rupee_Gold",
    "Obj_Heart", "Obj_MagicJar_Small", "Obj_MagicJar_Large", "Obj_DekuSeed",
    "Obj_ArrowBundle_Small", "Obj_ArrowBundle_Medium", "Obj_ArrowBundle_Large",
    "Item_BombBundle_Small", "Item_DekuStickBundle_Small", "Item_BombchuBundle_Small",
    "Item_BombchuBundle_Medium", "Item_BombchuBundle_Large", "TBox_DekuNutBundle", "TBox_DekuSeedBundle",
)

# Pont arc-en-ciel : le module GanonCastle_Level_Field_00_Prefab_14ba déclenche la scène du pont
# (GanonCastle_Adult_Field_Rainbow) selon deux expressions de la quête « Defeat_Ganon ». Elles sont
# remplacées (noms de même longueur) par des expressions qui décrivent la condition choisie.
# La scène se déclenche si « Ready » ET NON « Step01 » (elle fait passer la quête à Step01) et le pont
# existe une fois la scène vue : seule « Ready » est remplacée (remplacer les deux empêchait la scène,
# constaté en jeu avec le menu natif, 2026-11-10).
BRIDGE_EXP = {"Defeat_Ganon_IsAfter_Ready_Exp": "OoTRR_Bridge_Condition_Exp_A00"}
BRIDGE_MODULE = {"GanonCastle_Level_Field_00_Prefab_14ba": dict(BRIDGE_EXP)}
STONE_FLAGS = [f"IsGet.Item_Stone_{x}" for x in ("Forest", "Fire", "Water")]
MEDAL_FLAGS = [f"IsGet.Item_Medal_{x}" for x in ("Forest", "Fire", "Water", "Spirit", "Shadow", "Light")]
MAX_LIFE = "PlayerStatus.MaxLife"  # en quarts de cœur (12 = 3 cœurs)


def _at_least(flags: list[str], n: int, prefix: str) -> dict[str, list[tuple]]:
    """Expressions « au moins n drapeaux parmi flags » (seuil en sous-expressions nommées).

    E(i, k) = au moins k drapeaux parmi flags[i:] = (flags[i] ET E(i+1, k-1)) OU E(i+1, k)."""
    exps: dict[str, list[tuple]] = {}

    def name(i: int, k: int) -> str:
        return f"{prefix}_{i}_{k}"

    def build(i: int, k: int) -> list[tuple]:
        rest = len(flags) - i
        if k == 1 and rest == 1:
            return [("Bool", flags[i])]
        if k == rest:  # tous les restants
            prog = [("Bool", flags[i])]
            for f in flags[i + 1:]:
                prog += [("Bool", f), ("AND",)]
            return prog
        take = [("Bool", flags[i])] + ([("Exp", name(i + 1, k - 1))] + [("AND",)] if k > 1 else [])
        return take + [("Exp", name(i + 1, k)), ("OR",)]

    for i in range(len(flags) - 1, -1, -1):
        for k in range(1, len(flags) - i + 1):
            exps[name(i, k)] = build(i, k)
    return {name(0, n): exps[name(0, n)], **exps}


def bridge_exps(mode: str, count: int) -> dict[str, list[tuple]]:
    """Expressions booléennes de la condition du pont (les deux noms de BRIDGE_EXP valent la condition)."""
    if mode == "vanilla":
        return {}
    exps: dict[str, list[tuple]] = {}
    if mode == "open" or count <= 0:
        cond = [("Bool", "IsGet.Item_Stone_Forest"), ("Bool", "IsGet.Item_Stone_Forest"), ("NOT",), ("OR",)]
    elif mode == "hearts":
        # au moins count cœurs : MaxLife (quarts) vaut l'une des valeurs de 4*count à 80
        values = list(range(4 * count, 81))
        cond = [("IntEq", MAX_LIFE, values[0])]
        for v in values[1:]:
            cond += [("IntEq", MAX_LIFE, v), ("OR",)]
    else:
        flags = {"stones": STONE_FLAGS, "medallions": MEDAL_FLAGS, "dungeons": STONE_FLAGS + MEDAL_FLAGS}[mode]
        sub = _at_least(flags, min(count, len(flags)), "OoTRR_Bridge")
        exps.update(sub)
        cond = [("Exp", next(iter(sub)))]
    for name in BRIDGE_EXP.values():
        exps[name] = list(cond)
    return exps
# réglage free_time_travel : l'épée de légende renvoie enfant sans attendre le Temple de la Forêt
# (condition remplacée par une expression toujours vraie une fois la porte ouverte, même longueur)
FREE_TIME_TRAVEL = {"Market_Adult_Prefab_89da": {"SageOfForest_IsCompleted_Exp": "DoorOfTime_IsAfter_Ready_Exp"}}
# Peste Mojo vendeuses mélangées : prix unique (les quarts de cœur coûtent 100 dans le jeu, plus que la
# bourse d'enfant) ; le script commun vend l'objet une fois (SimpleShopSub_Scrub_Business_OneTime)
SCRUB_PRICE = 40
SCRUB_SECRET_LOCATION = "HF Deku Scrub Heart Piece"  # script à part : vente directe (entrée « Secret »)
FOREST_FLAGS = {"exit": "KokiriForest_Npc_Kokiri_007_Child_Blocker_00", "deku": "KokiriForest_Npc_Kokiri_Mido_Child_Blocker"}
# réglage open_forest : PNJ « bloqueurs » retirés de KokiriForest_Child_Static
OPEN_FOREST_REMOVALS = {
    "exit": [6882168009719929077],  # Npc_Kokiri_007_Child, devant la sortie vers le pont
    # Mido devant le chemin de l'Arbre Mojo, et la scène où il parle après la pierre (elle le cherche)
    "deku": [15309024097747311596, 13618365260078545106],
}


class DataError(ValueError):
    """Erreur dans les fichiers de données."""



def shop_count(settings) -> int:
    """Nombre d'articles mélangés par boutique (réglage shuffle_shops : off, 1 à 4)."""
    value = settings.get("shuffle_shops", "off")
    return 0 if value == "off" else int(value)


SHOP_AFFORDABLE = 10
SHOP_MAX_PRICE = 99  # sans bourse dans la logique : jamais plus que la bourse d'enfant


def shop_price(settings, seed: int, location_index: int, vanilla_price: int) -> int:
    """Prix d'un article mélangé (même calcul que le module natif, ShopPrice)."""
    mode = settings.get("shop_prices", "vanilla")
    if mode == "affordable":
        return SHOP_AFFORDABLE
    if mode == "random":
        h = (seed * 0x9E3779B97F4A7C15 + (location_index + 1) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        h ^= h >> 31
        h = (h * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        h ^= h >> 29
        return (h % 20) * 5
    return min(vanilla_price, SHOP_MAX_PRICE)

@dataclass
class Item:
    """Un objet réel du jeu (nom d'acteur) et la capacité logique qu'il donne."""
    name: str
    logic: str | None
    level: int | None

    @property
    def progression(self) -> bool:
        return self.logic is not None


@dataclass
class Location:
    name: str
    region: str
    kind: str
    rule: Rule
    rule_src: str
    vanilla: str
    dungeon: str | None
    hashes: list[int] = field(default_factory=list)
    shuffle: bool = False
    event: str | None = None  # "keep" | "drop" | None
    dungeon_item: str | None = None  # "map" | "compass" | None
    conditional: bool = False  # coffre A_06 à contenu conditionnel
    pickup: str | None = None  # "freestanding" | "boss" : cœur posé au sol ; "item" : autre objet au sol (shuffle_gifts)
    actor: str | None = None  # pickup "item" : type de l'acteur posé au sol (ex. Obj_Arrow_Fire)
    no_progression: bool = False  # emplacement incertain : jamais d'objet nécessaire pour finir
    scrub: bool = False  # Peste Mojo vendeuse : hashes = l'acteur Enemy_Scrub_Business (enfant / adulte)
    skulltula: bool = False  # Skulltula d'or : hashes = l'acteur Enemy_Skulltula_Gold, l'objet remplace le jeton
    shop: int = 0  # article de boutique : rang (mélangé si rang <= shuffle_shops), hashes = l'acteur Shop_*
    shop_actor: str | None = None  # article d'origine (Shop_*)
    price: int = 0  # prix d'origine de l'article
    ocarina: bool = False  # ocarina donné par une scène (Saria, douves) : mélangé avec shuffle_ocarinas
    gift: bool = False  # cadeau donné par une scène ou un PNJ (data/gifts.json) : mélangé avec shuffle_gifts

    @property
    def is_chest(self) -> bool:
        return bool(self.hashes) and not self.pickup and not self.scrub and not self.skulltula and not self.shop


@dataclass
class Event:
    name: str
    region: str
    rule: Rule
    rule_src: str


@dataclass
class Exit:
    source: str
    target: str
    rule: Rule
    rule_src: str


@dataclass
class Region:
    name: str
    dungeon: str | None
    exits: list[Exit] = field(default_factory=list)
    locations: list[Location] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise DataError(f"{path.name} : JSON invalide ligne {exc.lineno} ({exc.msg})") from None


class World:
    """Le graphe du jeu, compilé pour un jeu de réglages donné."""

    ROOT = "Root"
    GOAL_EVENT = "Triforce"

    def __init__(self, settings: dict, data_dir: Path | str = DATA_DIR) -> None:
        self.settings = settings
        data_dir = Path(data_dir)

        items_raw = _read_json(data_dir / "items.json")
        helpers_raw = _read_json(data_dir / "helpers.json")["helpers"]
        regions_raw: dict[str, dict] = {}
        extra_locations: dict[str, dict] = {}
        for path in sorted((data_dir / "world").glob("*.json")):
            content = _read_json(path)
            for name, body in content.get("regions", {}).items():
                if name in regions_raw:
                    raise DataError(f"{path.name} : région « {name} » définie deux fois")
                regions_raw[name] = body
            for name, body in content.get("locations", {}).items():
                if name.startswith("_"):
                    continue  # commentaire
                if name in extra_locations:
                    raise DataError(f"{path.name} : lieu « {name} » défini deux fois")
                extra_locations[name] = body

        self.gift_edits: dict[str, list[tuple[str, int, str, str]]] = {
            name: [tuple(e) for e in edits]
            for name, edits in _read_json(data_dir / "gifts.json")["gifts"].items()}

        # --- capacités logiques et objets réels
        self.logic_items: dict[str, dict] = items_raw["logic"]
        self.items: dict[str, Item] = {}
        for name, body in items_raw["actors"].items():
            logic = body.get("logic")
            if logic is not None and logic not in self.logic_items:
                raise DataError(f"items.json : {name} donne « {logic} », absent de la section logic")
            if logic in ("Heart_Piece", "Heart_Container") and settings.get("bridge") != "hearts":
                logic = None  # les cœurs ne comptent pour la logique qu'avec le pont « hearts »
            self.items[name] = Item(name, logic, body.get("level"))
        self.ground: set[str] = set(items_raw.get("ground", []))
        self.ground_native: dict[str, str] = dict(items_raw.get("ground_native", {}))
        for name in self.ground | set(self.ground_native):
            if name not in self.items:
                raise DataError(f"items.json : objet au sol inconnu « {name} »")

        # --- événements (déclarés dans les régions)
        event_names = set()
        for rname, body in regions_raw.items():
            for ename in body.get("events", {}):
                if ename in self.logic_items:
                    raise DataError(f"région {rname} : l'événement « {ename} » porte le nom d'un objet")
                event_names.add(ename)
        if self.GOAL_EVENT not in event_names:
            raise DataError(f"aucun événement « {self.GOAL_EVENT} » (condition de victoire)")

        usable = {n: b["use"] for n, b in self.logic_items.items() if b.get("use")}
        from .starting import add_spawn_exits
        regions_raw = add_spawn_exits(regions_raw)  # Root -> point d'apparition (spawn_point)
        self.compiler = RuleCompiler(self.logic_items, event_names, helpers_raw, settings, usable)
        try:
            self.compiler.compile_all_helpers()
            self._build_regions(regions_raw, extra_locations)
        except RuleError as exc:
            raise DataError(str(exc)) from None
        self._validate()

    # ------------------------------------------------------------------
    def _add_location(self, lname: str, rname: str, lbody: dict | str) -> None:
        if lname in self.locations:
            raise DataError(f"lieu « {lname} » défini deux fois")
        if isinstance(lbody, str):
            lbody = {"rule": lbody}
        if rname not in self.regions:
            raise DataError(f"lieu {lname} : région inconnue « {rname} »")
        kind = lbody.get("kind", "general")
        if kind not in LOCATION_KINDS:
            raise DataError(f"lieu {lname} : type inconnu « {kind} »")
        hashes = [int(h) for h in lbody.get("hashes", [])]
        event = lbody.get("event")
        if event not in (None, "keep", "drop"):
            raise DataError(f"lieu {lname} : event doit valoir keep ou drop")
        src = lbody.get("rule", "True")
        if lname in self._start_location_names():
            # objet donné dès la nouvelle partie : le lieu est atteint d'office
            rname, src = self.ROOT, "True"
        region = self.regions[rname]
        loc = Location(
            name=lname,
            region=rname,
            kind=kind,
            rule=self.compiler.compile(src, f"lieu {lname}"),
            rule_src=str(src),
            vanilla=lbody.get("vanilla"),
            dungeon=region.dungeon,
            hashes=hashes,
            shuffle=bool(lbody.get("shuffle", bool(hashes))),
            event=event,
            dungeon_item=lbody.get("dungeon_item"),
            conditional=bool(lbody.get("conditional", False)),
            pickup=lbody.get("pickup"),
            actor=lbody.get("actor"),
            no_progression=bool(lbody.get("no_progression", False)),
            scrub=bool(lbody.get("scrub", False)),
            skulltula=bool(lbody.get("skulltula", False)),
            shop=int(lbody.get("shop", 0)),
            shop_actor=lbody.get("shop_actor"),
            price=int(lbody.get("price", 0)),
            ocarina=bool(lbody.get("ocarina", False)),
            gift=bool(lbody.get("gift", False)),
        )
        if loc.dungeon_item and self.settings.get("maps_compasses", "vanilla") == "vanilla":
            loc.shuffle = False
        if loc.pickup:
            mode = self.settings.get("shuffle_hearts", "none")
            loc.shuffle = mode == "all" or (mode == "freestanding" and loc.pickup == "freestanding")
            if loc.pickup == "item":  # objet unique posé au sol (Flèche de feu) : comme les cadeaux
                loc.shuffle = bool(self.settings.get("shuffle_gifts"))
        if loc.scrub:
            loc.shuffle = bool(self.settings.get("shuffle_scrubs"))
        if loc.skulltula:
            mode = self.settings.get("shuffle_skulltulas", "off")
            loc.shuffle = mode == "all" or (mode == "overworld" and loc.dungeon is None)
        if loc.shop:
            loc.shuffle = loc.shop <= shop_count(self.settings)
        if loc.ocarina:
            loc.shuffle = bool(self.settings.get("shuffle_ocarinas"))
        if loc.kind == "song":
            loc.shuffle = self.settings.get("shuffle_songs", "vanilla") == "random"
        if loc.gift:
            loc.shuffle = bool(self.settings.get("shuffle_gifts"))
        region.locations.append(loc)
        self.locations[lname] = loc

    def _build_regions(self, regions_raw: dict[str, dict], extra_locations: dict[str, dict]) -> None:
        self.regions: dict[str, Region] = {}
        self.locations: dict[str, Location] = {}
        self.events: list[Event] = []
        c = self.compiler

        for rname, body in regions_raw.items():
            region = Region(rname, body.get("dungeon"))
            for target, src in body.get("exits", {}).items():
                region.exits.append(Exit(rname, target, c.compile(src, f"sortie {rname} -> {target}"), str(src)))
            for ename, src in body.get("events", {}).items():
                ev = Event(ename, rname, c.compile(src, f"événement {ename}"), str(src))
                region.events.append(ev)
                self.events.append(ev)
            self.regions[rname] = region
        for rname, body in regions_raw.items():
            for lname, lbody in body.get("locations", {}).items():
                self._add_location(lname, rname, lbody)
        for lname, lbody in extra_locations.items():
            self._add_location(lname, lbody.get("region", ""), lbody)

    def _validate(self) -> None:
        if self.ROOT not in self.regions:
            raise DataError(f"région de départ « {self.ROOT} » absente")
        for region in self.regions.values():
            for ex in region.exits:
                if ex.target not in self.regions:
                    raise DataError(f"sortie {region.name} -> {ex.target} : région cible inconnue")
        seen_hashes: dict[int, str] = {}
        for loc in self.locations.values():
            if loc.vanilla is None:
                raise DataError(f"lieu {loc.name} : objet vanilla manquant")
            if loc.vanilla not in self.items:
                raise DataError(f"lieu {loc.name} : objet inconnu « {loc.vanilla} » (absent de items.json)")
            if loc.shuffle and not loc.hashes and not loc.ocarina and loc.kind != "song" and not loc.gift:
                raise DataError(f"lieu {loc.name} : seuls les coffres (avec hashes) peuvent être mélangés")
            for h in loc.hashes:
                if h in seen_hashes:
                    raise DataError(f"hash {h} utilisé par {seen_hashes[h]} et {loc.name}")
                seen_hashes[h] = loc.name
            if loc.pickup:
                if loc.pickup not in ("freestanding", "boss", "item"):
                    raise DataError(f"lieu {loc.name} : pickup doit valoir freestanding, boss ou item")
                if loc.pickup == "item":
                    if not loc.actor or not loc.hashes:
                        raise DataError(f"lieu {loc.name} : un objet au sol doit avoir un hash et son acteur (actor)")
                elif loc.vanilla not in self.ground_native or not loc.hashes:
                    raise DataError(f"lieu {loc.name} : un cœur au sol doit avoir un hash et un objet d'origine au sol")
            if loc.gift and loc.name not in self.gift_edits:
                raise DataError(f"lieu {loc.name} : cadeau absent de gifts.json")
            if loc.dungeon_item:
                if loc.dungeon_item not in ("map", "compass"):
                    raise DataError(f"lieu {loc.name} : dungeon_item doit valoir map ou compass")
                if loc.dungeon not in GAME_DUNGEONS:
                    raise DataError(f"lieu {loc.name} : carte/boussole hors d'un donjon connu")

    # ------------------------------------------------------------------
    def shuffled_locations(self) -> list[Location]:
        return [l for l in self.locations.values() if l.shuffle]

    def fixed_locations(self) -> list[Location]:
        return [l for l in self.locations.values() if not l.shuffle]

    def pool(self) -> list[tuple[str, str | None]]:
        """Objets à répartir dans les coffres mélangés : (objet, donjon imposé ou None).

        Cartes et boussoles : « shuffle » = dans un coffre de leur propre donjon
        (le jeu les attribue au donjon où le coffre est ouvert) ; « removed » et
        « start_with » = remplacées par un rubis vert."""
        mode = self.settings.get("maps_compasses", "vanilla")
        out: list[tuple[str, str | None]] = []
        for loc in self.shuffled_locations():
            if loc.dungeon_item and mode == "shuffle":
                out.append((loc.vanilla, loc.dungeon))
            elif loc.dungeon_item:
                out.append((JUNK_REPLACEMENT, None))
            else:
                out.append((loc.vanilla, None))
        return out

    def start_flags(self) -> dict[str, bool]:
        """Drapeaux de sauvegarde à activer dès la nouvelle partie."""
        flags: dict[str, bool] = {}
        # cycle jour / nuit : voir TIME_FLOW_FLAG (toujours, quels que soient les réglages)
        flags[TIME_FLOW_FLAG] = True
        if self.settings.get("maps_compasses") == "start_with":
            for loc in self.locations.values():
                if loc.dungeon_item:
                    field_name = "IsGetMap" if loc.dungeon_item == "map" else "IsGetCompass"
                    flags[f"DungeonInfo.{GAME_DUNGEONS[loc.dungeon]}.{field_name}"] = True
        # forêt ouverte : ces drapeaux font apparaître les murs invisibles devant les passages
        forest = self.settings.get("open_forest", "closed")
        if forest in ("closed_deku", "open"):
            flags["KokiriForest_Npc_Kokiri_007_Child_Blocker_00"] = False
        if forest == "open":
            flags["KokiriForest_Npc_Kokiri_Mido_Child_Blocker"] = False
        if self.skip_rauru():
            for name in SKIP_RAURU_FLAGS:
                flags[name] = True
        if self.settings.get("skip_child_zelda") or self.settings.get("open_door_of_time"):
            # Zelda déjà rencontrée : quête du château finie (le temps passe), Porte du Temps à Step01
            flags[f"#{MEET_ZELDA_QUEST[1]}"] = MEET_ZELDA_QUEST[2]
            if not self.settings.get("open_door_of_time"):
                flags[f"#{MEET_ZELDA_DOOR_STEP[1]}"] = MEET_ZELDA_DOOR_STEP[2]
        if self.settings.get("start_with_consumables"):
            for name, count in START_CONSUMABLES:
                flags[f"PouchData.{name}.StockNum"] = count
        if self.settings.get("starting_age") == "adult":
            # comme Market_Child_Field_ChildToAdult (l'âge suit ce drapeau et la carte d'arrivée)
            flags[ADULT_FLAG] = False
        if self.settings.get("open_door_of_time"):
            # posés par le jeu quand la porte s'ouvre (événement DoorOfTime_OpenDoor)
            flags["Market_Child_TimeTempleDoor_Opened"] = True
            flags["HavePlayedEvent.Dm_TimeTemple_0010"] = True
            # la porte s'ouvre selon l'étape de la quête « DoorOfTime » (module Market_Common_f252)
            flags[f"#{DOOR_OF_TIME_STEP[1]}"] = DOOR_OF_TIME_STEP[2]
        if self.settings.get("skip_cutscenes") == "safe":
            path = DATA_DIR / "cutscenes.json"
            if not path.exists():
                raise DataError("data/cutscenes.json absent : lance python -m ootrr.tools.cutscenes --romfs ...")
            for name in SKIP_FLAGS + tuple(f"IsGet.{item}" for item in CONSUMABLES):
                flags[name] = True
            for name in list(_read_json(path)["skippable"]) + list(EXTRA_SKIPPED):
                flags[f"HavePlayedEvent.{name}"] = True
        return flags

    def removed_actors(self) -> list[int]:
        """Acteurs retirés des cartes (hash), ex. les Kokiri qui bloquent la forêt."""
        mode = self.settings.get("open_forest", "closed")
        out: list[int] = []
        if mode in ("closed_deku", "open"):
            out += OPEN_FOREST_REMOVALS["exit"]
        if mode == "open":
            out += OPEN_FOREST_REMOVALS["deku"]
        return out

    def skip_rauru(self) -> bool:
        return self.settings.get("skip_cutscenes") == "safe" or self.settings.get("shuffle_rewards") != "vanilla"

    def _start_location_names(self) -> tuple[str, ...]:
        names: tuple[str, ...] = ()
        if self.settings.get("open_door_of_time"):
            names = OPEN_DOOR_START
        elif self.settings.get("skip_child_zelda"):
            names = SKIP_CHILD_ZELDA
        if self.skip_rauru():
            names += (LINKS_POCKET,)
        return names

    def start_location_names(self) -> tuple[str, ...]:
        return self._start_location_names()

    def reward_locations(self) -> list[Location]:
        return [l for l in self.locations.values() if l.kind == "reward"]

    def song_locations(self) -> list[Location]:
        return [l for l in self.locations.values() if l.kind == "song"]

    def song_gives(self, placements: dict[str, str]) -> dict[str, str]:
        """{chant d'origine: objet donné à sa place} pour les dons de Dm_SY_Ocarina (un don par chant,
        choisi selon la mélodie de la scène) ; vide si les chants sont à leur place."""
        return {l.vanilla: placements.get(l.name, l.vanilla) for l in self.song_locations()
                if placements.get(l.name, l.vanilla) != l.vanilla}

    def reward_event_changes(self, placements: dict[str, str]) -> dict[str, dict[str, str]]:
        """{scène: {récompense d'origine: nouvelle récompense}} pour les boss dont la récompense change."""
        out: dict[str, dict[str, str]] = {}
        for name, flows in REWARD_EVENTS.items():
            loc = self.locations[name]
            if placements[name] != loc.vanilla:
                for flow in flows:
                    out.setdefault(flow, {})[loc.vanilla] = placements[name]
        return out

    def ocarina_event_changes(self, placements: dict[str, str]) -> dict[str, dict[str, str]]:
        """shuffle_ocarinas (mod sans menu) : {scène: {ocarina d'origine: objet placé}} pour Saria et les
        douves (action d'inventaire, affichage de l'objet obtenu)."""
        out: dict[str, dict[str, str]] = {}
        for name, (flow, vanilla) in OCARINA_EVENTS.items():
            item = placements.get(name, vanilla)
            if self.locations[name].shuffle and item != vanilla:
                out.setdefault(flow, {})[vanilla] = item
        return out

    def gift_event_changes(self, placements: dict[str, str]) -> dict[str, list[tuple[int, str, str, str]]]:
        """shuffle_gifts (mod sans menu) : {scène: [(événement, paramètre, texte d'origine, objet placé)]}.
        Avec le menu natif, ootrr.native_logic.gift_tokens donne le jeton du lieu à la place de l'objet."""
        out: dict[str, list[tuple[int, str, str, str]]] = {}
        for name, edits in self.gift_edits.items():
            if not self.locations[name].shuffle:
                continue
            item = placements.get(name)
            for flow, event, param, old in edits:
                if item and item != old:
                    out.setdefault(flow, []).append((event, param, old, item))
        return out

    def moat_items(self, placements: dict[str, str]) -> tuple[str, ...]:
        """Objets donnés directement aux douves (porte ouverte) : l'objet du lieu de l'Ocarina du Temps
        et le Chant du Temps."""
        return (placements.get(OCARINA_OF_TIME_LOCATION, "Item_Ocarina_Time"),
                placements.get(SONG_OF_TIME_LOCATION, "Item_Melody_TimeSong"))

    def logic_patches(self) -> dict[str, dict[str, str]]:
        """Chaînes à remplacer dans les modules de logique (Logic/<module>.logic.module.ainb)."""
        out: dict[str, dict[str, str]] = {}
        if self.settings.get("free_time_travel"):
            out.update(FREE_TIME_TRAVEL)
        if self.settings.get("open_door_of_time"):
            out.update(OPEN_DOOR_OCARINA)  # l'ocarina des douves apparaît à l'étape Step06
        if self.settings.get("bridge", "vanilla") != "vanilla":
            out.update(BRIDGE_MODULE)
        return out

    def ingame_questions(self) -> list[str]:
        """Réglages décidés par une question au début de la nouvelle partie."""
        return ["open_forest"] if self.settings.get("open_forest") == "ask" else []

    def bool_exps(self) -> dict[str, list[tuple]]:
        """Expressions booléennes ajoutées aux données de sauvegarde (non sauvegardées)."""
        out = dict(BOOL_EXPS) if self.settings.get("open_door_of_time") else {}
        out.update(bridge_exps(self.settings.get("bridge", "vanilla"), self.settings.get("bridge_count", 0)))
        return out

    def actor_changes(self) -> dict[int, dict]:
        """Modifications d'acteurs liées aux réglages (hors contenu des coffres)."""
        out: dict[int, dict] = {}
        if self.settings.get("open_forest") == "ask":
            # forêt ouverte selon la réponse en jeu : les Kokiri bloqueurs n'existent que tant que
            # leurs drapeaux « bloqueur » sont vrais (la réponse « oui » les met à faux)
            for h in OPEN_FOREST_REMOVALS["exit"]:
                out[h] = {"Presence": {"FlagName": FOREST_FLAGS["exit"], "IsCheckLazy": False, "IsNegation": False}}
            for h in OPEN_FOREST_REMOVALS["deku"]:
                out[h] = {"Presence": {"FlagName": FOREST_FLAGS["deku"], "IsCheckLazy": False, "IsNegation": False}}
        out[TALON_CASTLE] = {"Presence": dict(TALON_GONE)}
        if self.settings.get("skip_cutscenes") == "safe":
            for h in KOKIRI_INTERRUPTIONS:
                out[h] = {"Presence": dict(NEVER_AFTER_INTRO)}

        if self.settings.get("open_door_of_time"):
            presence = {"FlagName": HAS_ALL_STONES_EXP, "IsCheckLazy": False, "IsNegation": False}
            out[OCARINA_OF_TIME_ACTOR] = {"Presence": presence}
        return out

    def pack_changes(self, romfs: Path | None = None, codec=None) -> dict[str, dict[str, dict]]:
        """Paramètres modifiés dans des archives d'acteurs : {acteur: {fichier: {clé: valeur}}}."""
        return {}

    def extra_pickups(self) -> dict[str, str]:
        return {}

    def free_return_to_child(self) -> bool:
        return bool(self.settings.get("free_time_travel"))

    def start_items(self, placements: dict[str, str] | None = None) -> list[str]:
        """Objets ajoutés à l'inventaire dès la nouvelle partie (action insérée dans l'intro)."""
        items = [(placements or {}).get(name, self.locations[name].vanilla) for name in self._start_location_names()]
        if self.settings.get("starting_age") == "adult":
            items += list(ADULT_START_ITEMS)
        if self.settings.get("start_with_consumables"):
            items += list(START_CONSUMABLE_BAGS) + [name for name, _ in START_CONSUMABLES]
        return items

    def rsdb_changes(self, romfs_locations: list[str] | None = None) -> dict[str, dict[str, dict]]:
        """Lignes des tables RSDB à modifier : {table: {__RowId: {champ: valeur}}}.

        skip_cutscenes=safe : la première découverte d'un lieu (nom, carte et mini-carte) est faite
        par sa scène d'arrivée (EventTriggerOpenLocationUI) quand IsShowLocationUIFirstTimeInDemo est
        vrai ; la scène étant marquée vue, le lieu resterait « ??? ». Champ mis à faux : le jeu le
        découvre à la première entrée (validé en jeu : sans ce champ, carte de l'Arbre Mojo absente)."""
        if self.settings.get("skip_cutscenes") != "safe":
            return {}
        rows = romfs_locations if romfs_locations is not None else LOCATIONS_SHOWN_IN_DEMO
        return {"Location": {f"Work/Location/{name}.game__location__Location.gyml":
                             {"IsShowLocationUIFirstTimeInDemo": False} for name in rows}}

    def event_skips(self) -> dict[str, list[str]]:
        """Étapes d'événements à sauter : scènes jouées sans condition (ex. l'introduction), et
        avec la porte du temps ouverte, toute progression de la quête « DoorOfTime » (sinon la
        scène de l'Ocarina du Temps la ferait reculer et la porte se refermerait)."""
        skips: dict[str, list[str]] = {}
        if self.settings.get("skip_cutscenes") == "safe":
            skips.update(_read_json(DATA_DIR / "cutscenes.json").get("event_skips", {}))
        if self.settings.get("open_door_of_time"):
            skips.setdefault("DoorOfTime", []).append("DoorOfTime")
        if self.settings.get("skip_cutscenes") == "safe":
            # après l'achat du bouclier Mojo, la vendeuse lance le tutoriel du bouclier d'une autre Kokiri
            skips.setdefault("Npc_Kokiri_001_Shop_Child", []).append("DekuShield_TutorialTalk")
        # cycle jour / nuit (tous réglages) : voir FIELD_FIRST_PALETTE_STEP
        skips.setdefault(FIELD_FIRST_PALETTE_STEP[0], []).append(FIELD_FIRST_PALETTE_STEP[1])
        return skips

    def can_place(self, item: str, loc: Location) -> bool:
        """Contraintes d'emplacement : objets au sol limités, emplacements incertains sans progression."""
        if loc.pickup and item not in self.ground and item not in self.ground_native:
            return False
        if loc.skulltula and item not in self.ground and item not in self.ground_native:
            return False  # lâché par la Skulltula : objet ramassable (objet sur mesure ou version au sol)
        if loc.shop and item not in self.ground and item not in self.ground_native:
            return False  # article de boutique : objet donné par le jeton (le module natif ajoute les rubis)
        if loc.scrub and (item not in self.ground and item not in self.ground_native
                          or item.startswith("TBox_Rupee_")):
            return False  # vendu par une Peste Mojo : objets « au sol » (un rubis vendu n'irait pas dans la bourse)
        if loc.ocarina and item.startswith(OCARINA_FORBIDDEN_PREFIX):
            return False  # bombes données par la scène de Saria / des douves : le jeu pourrait donner le sac
        if loc.gift and (item.startswith(OCARINA_FORBIDDEN_PREFIX) or item.startswith("TBox_Rupee_")):
            return False  # bombes (le jeu pourrait donner le sac) et rubis (pas d'inventaire) : pas donnés par une scène
        if loc.no_progression and self.is_progression(item):
            return False
        return True

    def is_progression(self, item: str) -> bool:
        info = self.items.get(item)
        return bool(info and info.progression)

    def collect(self, inventory: Counter, item: str) -> None:
        """Ajoute un objet à un inventaire de capacités logiques.

        Objet à niveau (level) : on garde le maximum, car le jeu ne rétrograde
        jamais (le Grappin obtenu après le Super Grappin ne change rien).
        Événement ou objet sans niveau : +1."""
        info = self.items.get(item)
        if info is None:
            inventory[item] += 1  # événement
        elif info.logic is None:
            return
        elif info.level is None:
            inventory[info.logic] += 1
        else:
            inventory[info.logic] = max(inventory[info.logic], info.level)
