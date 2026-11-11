"""Menu du randomizer dans le jeu : « Nouvelle partie » ouvre l'écran d'options du jeu, mais avec
nos réglages (voir native/README.md pour la partie code natif).

Côté fichiers (ce module) :
- GameData : structure `OoTRRMenu`, copie de `OptionData` (mêmes membres, mêmes types) dont les
  entrées ne sont pas sauvegardées. Pendant le menu, le module natif redirige la poignée
  `OptionData` vers `OoTRRMenu` : nos lignes lisent et écrivent nos valeurs, jamais les options du joueur.
- Table de lignes `UI/OptionSetTable/OoTRRMenu…bgyml` (dans le pack Bootup), chargée par le module natif.
- Textes `OoTRR_<type>_Title`, `OoTRR_<type>_Caption`, `OoTRR_<type>_<nn>` dans `LayoutMsg/SystemOption_00`
  (le module natif cherche d'abord l'étiquette préfixée).
- `Sequence/NormalTitle` : Nouvelle partie -> écran d'options -> confirmation -> partie, et un
  drapeau `OoTRR.IsRandomizerMenu` levé avant notre menu, baissé avant l'écran Options normal et au
  début de la partie (le module natif le voit passer, il n'existe pas dans GameData).

Chaque réglage emprunte un type d'option du jeu (le jeu ne connaît que les siens) : une liste à
choix pour un réglage à plusieurs valeurs, une bascule pour un oui / non.
"""

from __future__ import annotations

import copy
import uuid

from .formats.byml import U32, byml_version, read_byml, write_byml
from .formats.gamedata import flag_hash, index
from .formats.msbt import add_messages, read_labels

MENU_FLAG = "OoTRR.IsRandomizerMenu"
GENERATE_FLAG = "OoTRR.GenerateSeed"  # levé au début de la partie : le module natif génère la seed
SEED_ENTRY = "OoTRR.Seed"  # seed de la partie (entier, sauvegardé) : régénérée au chargement
STRUCT = "OoTRRMenu"
OPTION_STRUCT = "OptionData"
BOOTUP = "Pack/Bootup.Nin_Ounce_NVN2.pack.zs"
GAME_TABLE = "UI/OptionSetTable/OptionSetTable.game__ui__OptionSetTable.bgyml"
MENU_TABLE = "UI/OptionSetTable/OoTRRMenu.game__ui__OptionSetTable.bgyml"
MESSAGES = "LayoutMsg/SystemOption_00.msbt"
TITLE = "Sequence/NormalTitle.module.ainb"
COMMON_LAYOUTS = "UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.blarc.zs"
LAYOUT_CATEGORIES = "UI/LayoutArchiveCategory.Product.100.byml.zs"
GAME_LAYOUT = "SystemOption_00"
MENU_LAYOUT = "OoTRRMenu_00"  # copie de SystemOption_00 sans le modèle amiibo (aucune ligne amiibo)
# un modèle inutilisé reste affiché à sa place ; le séparateur sert (lignes SEPARATOR) : ne pas le cacher,
# ses copies le seraient aussi
HIDDEN_PANES = ("Pa_AmiiboBtn_00",)
SEPARATOR = "-"

# réglage -> (type d'option emprunté, valeurs du réglage dans l'ordre affiché) ; None = bascule oui / non.
# Ordre d'affichage ; SEPARATOR = ligne de séparation du jeu.
# Seed : bascule « seed manuelle » ; activée, le module natif ouvre le clavier virtuel au lancement
# de la partie (pavé numérique) pour la saisir. Pas un réglage : non sauvegardée.
SEED_MANUAL = "seed_manual"
SEED_ROW_NAMES = (SEED_MANUAL,)
# repère remplacé par le module natif (texte lu) par la seed aléatoire tirée à l'ouverture du menu
SEED_PLACEHOLDER = "######"
ROWS: list[tuple[str, str, list[str] | None]] = [
    (SEED_MANUAL, "VoiceSubtitle", None),
    (SEPARATOR, "", None),
    ("open_forest", "CameraRotateSpeed", ["closed", "closed_deku", "open"]),
    ("open_door_of_time", "IsCameraUpDownReverse", None),
    ("free_time_travel", "IsCameraRightLeftReverse", None),
    ("skip_child_zelda", "IsUseGyro", None),
    (SEPARATOR, "", None),
    ("bridge", "VoiceLanguage", ["open", "vanilla", "stones", "medallions", "dungeons", "hearts"]),
    ("shuffle_rewards", "LockOnType", ["vanilla", "shuffled"]),
    ("shuffle_hearts", "ControllerRumble", ["none", "freestanding", "all"]),
    # VoiceSubtitleSpeakerName est grisé tant que VoiceSubtitle (seed manuelle) est désactivé : IsDisplayTextRuby
    ("shuffle_scrubs", "IsDisplayTextRuby", None),
    ("maps_compasses", "DisplayMode", ["vanilla", "start_with", "removed"]),
    (SEPARATOR, "", None),
    ("logic_lens_required", "IsChangeJumpButton", None),
]
# réglages fixés pour la partie générée dans le jeu (pas de ligne dans le menu)
FIXED_SETTINGS = {"skip_cutscenes": "safe"}
# nombre requis pour le pont selon sa condition (le menu n'a pas de ligne pour bridge_count ;
# settings.build refuse un nombre au-delà du maximum de la condition)
BRIDGE_COUNTS = {"stones": 3, "medallions": 6, "dungeons": 9, "hearts": 10}
# base des fichiers du mod du menu : scènes passées, et Kokiri bloqueurs présents selon leur drapeau
# (comme open_forest = ask) pour que la forêt s'ouvre en jeu selon le réglage
STATIC_SETTINGS = {"skip_cutscenes": "safe", "open_forest": "ask"}
SETTING_ROWS = [r for r in ROWS if r[0] != SEPARATOR and r[0] not in SEED_ROW_NAMES]
SEED_ROWS = [r for r in ROWS if r[0] in SEED_ROW_NAMES]
SEPARATOR_BUTTON = flag_hash("Separator")

# textes : réglage -> (titre, description, {valeur: libellé}) ; anglais puis français
TEXTS_EN = {
    "open_forest": ("Kokiri Forest", "Closed: original game. Closed Deku: the exit to Hyrule Field is open.\nOpen: the Deku Tree is open too.",
                    {"closed": "Closed", "closed_deku": "Closed Deku", "open": "Open"}),
    "open_door_of_time": ("Open Door of Time", "The Door of Time is open from the start.", {}),
    "free_time_travel": ("Free Time Travel", "The Master Sword sends Link back to childhood at any time.", {}),
    "skip_child_zelda": ("Skip Child Zelda", "Start with Zelda's Letter and Zelda's Lullaby.", {}),
    "bridge": ("Rainbow Bridge", "Condition to open the rainbow bridge to Ganon's Castle.",
               {"open": "Open", "vanilla": "Vanilla", "stones": "Stones", "medallions": "Medallions",
                "dungeons": "Dungeons", "hearts": "Hearts"}),
    "shuffle_rewards": ("Dungeon Rewards", "Shuffle the Spiritual Stones and Medallions between the bosses\nand Link's Pocket.",
                        {"vanilla": "Vanilla", "shuffled": "Shuffled"}),
    "shuffle_scrubs": ("Deku Scrubs", "The 5 Deku Scrubs selling a unique item sell an item of the seed\ninstead, once, for 40 rupees.", {}),
    "shuffle_hearts": ("Heart Pieces", "Shuffle the freestanding Pieces of Heart (and the boss Heart Containers).",
                       {"none": "Vanilla", "freestanding": "Freestanding", "all": "All"}),
    "maps_compasses": ("Maps and Compasses", "Maps and compasses: in place, given at the start, or removed.",
                       {"vanilla": "Vanilla", "start_with": "Start With", "removed": "Removed"}),
    "skip_cutscenes": ("Skip Cutscenes", "Mark cutscenes that change nothing as already seen.",
                       {"none": "None", "safe": "Safe"}),
    "logic_lens_required": ("Lens Required", "The logic requires the Lens of Truth for invisible paths.", {}),
    "seed_manual": ("Manual Seed", f"Off: random seed {SEED_PLACEHOLDER}. On: a keyboard opens when the game\nstarts to type the seed.", {}),
}
TEXTS_FR = {
    "open_forest": ("Forêt Kokiri", "Fermée : jeu d'origine. Fermée (Mojo) : la sortie vers la plaine est ouverte.\nOuverte : l'Arbre Mojo aussi.",
                    {"closed": "Fermée", "closed_deku": "Fermée (Mojo)", "open": "Ouverte"}),
    "open_door_of_time": ("Porte du Temps ouverte", "La Porte du Temps est ouverte dès le départ.", {}),
    "free_time_travel": ("Voyage temporel libre", "L'Épée de Légende renvoie Link enfant à tout moment.", {}),
    "skip_child_zelda": ("Passer Zelda enfant", "Lettre de Zelda et Berceuse de Zelda dès le départ.", {}),
    "bridge": ("Pont arc-en-ciel", "Condition d'ouverture du pont vers le château de Ganon.",
               {"open": "Ouvert", "vanilla": "Original", "stones": "Pierres", "medallions": "Médaillons",
                "dungeons": "Donjons", "hearts": "Cœurs"}),
    "shuffle_rewards": ("Récompenses des boss", "Mélange les pierres et médaillons entre les boss\net la poche de Link.",
                        {"vanilla": "Original", "shuffled": "Mélangées"}),
    "shuffle_scrubs": ("Peste Mojo", "Les 5 Peste Mojo qui vendent un objet unique vendent un objet de la seed\nà la place, une fois, pour 40 rubis.", {}),
    "shuffle_hearts": ("Quarts de cœur", "Mélange les quarts de cœur au sol (et les réceptacles des boss).",
                       {"none": "Original", "freestanding": "Au sol", "all": "Tous"}),
    "maps_compasses": ("Cartes et boussoles", "Cartes et boussoles : à leur place, données au départ, ou retirées.",
                       {"vanilla": "Original", "start_with": "Au départ", "removed": "Retirées"}),
    "skip_cutscenes": ("Passer les cinématiques", "Les cinématiques sans effet sont marquées comme vues.",
                       {"none": "Aucune", "safe": "Sûres"}),
    "logic_lens_required": ("Monocle requis", "La logique exige le Monocle de Vérité pour les passages invisibles.", {}),
    "seed_manual": ("Seed manuelle", f"Désactivé : seed aléatoire {SEED_PLACEHOLDER}. Activé : un clavier s'ouvre\nau lancement de la partie pour saisir la seed.", {}),
}
FRENCH = ("EUfr", "USfr")


def gamedata_struct(root: dict, defaults: dict | None = None) -> list[str]:
    """Ajoute la structure OoTRRMenu (copie d'OptionData) à GameDataList.

    Les membres qui portent un réglage sont enregistrés dans la sauvegarde de la partie
    (progress.sav, SaveFileIndex 0) et échappent à la remise à zéro de « Nouvelle partie »
    (ResetTypeValue 0) ; les autres ne sont pas sauvegardés. Voir add_saved_entries pour les
    métadonnées de sauvegarde."""
    data = root["Data"]
    idx = index(root)
    src = next(e for e in data["Struct"] if e["Hash"] == flag_hash(OPTION_STRUCT))
    if any(e["Hash"] == flag_hash(STRUCT) for e in data["Struct"]):
        raise KeyError(f"GameData : structure {STRUCT} déjà présente")
    types = {flag_hash(t): t for _, t, _ in SETTING_ROWS + SEED_ROWS}
    by_type = {t: (s, values) for s, t, values in SETTING_ROWS}
    members = []
    report = []
    for m in src["DefaultValue"]:
        section, entry = idx[m["Value"]]
        name = types.get(m["Hash"], f"{m['Hash']:08x}")
        new = copy.deepcopy(entry)
        new["Hash"] = U32(flag_hash(f"{STRUCT}.{name}"))
        setting, values = by_type.get(name, (None, None))
        new["SaveFileIndex"] = PROGRESS_SAVE if setting else -1
        new["ResetTypeValue"] = 0
        if any(r[1] == name for r in SEED_ROWS):
            new["DefaultValue"] = False
            report.append(f"GameData {STRUCT}.{name} (seed)")
        if defaults is not None and setting in defaults:
            value = defaults[setting]
            if values is None and section == "Bool":
                new["DefaultValue"] = bool(value)
            elif values is not None and value in values and section == "Enum":
                new["DefaultValue"] = type(entry["DefaultValue"])(entry["Values"][values.index(value)])
        data[section].append(new)
        members.append({"Hash": m["Hash"], "Value": new["Hash"]})
        if setting:
            report.append(f"GameData {STRUCT}.{name} ({setting}) défaut={new['DefaultValue']}")
    data["Struct"].append({"DefaultValue": members, "Hash": U32(flag_hash(STRUCT)),
                           "ResetTypeValue": 0, "SaveFileIndex": -1})
    for name in (MENU_FLAG, GENERATE_FLAG):
        flag = copy.deepcopy(next(e for e in data["Bool"] if e.get("SaveFileIndex") == -1))
        flag.update({"Hash": U32(flag_hash(name)), "DefaultValue": False, "ResetTypeValue": 0})
        data["Bool"].append(flag)
        report.append(f"GameData : drapeau {name}")
    report.append(f"GameData : structure {STRUCT} ({len(members)} membres)")
    # drapeaux posés selon le menu et lus par des expressions (sauvegardés : ils doivent tenir au chargement)
    for name in EXTRA_SAVED_FLAGS:
        flag = copy.deepcopy(next(e for e in data["Bool"] if e.get("SaveFileIndex") == PROGRESS_SAVE))
        flag.update({"Hash": U32(flag_hash(name)), "DefaultValue": False, "ResetTypeValue": 0})
        data["Bool"].append(flag)
        report.append(f"GameData : drapeau {name} (sauvegardé)")
    seed = copy.deepcopy(next(e for e in data["Int"] if e.get("SaveFileIndex") == PROGRESS_SAVE))
    seed.update({"Hash": U32(flag_hash(SEED_ENTRY)), "DefaultValue": 0, "ResetTypeValue": 0})
    data["Int"].append(seed)
    report.append(f"GameData : entier {SEED_ENTRY} (sauvegardé)")
    saved = sum(1 for _ in SETTING_ROWS) + 1 + len(EXTRA_SAVED_FLAGS)
    report += add_saved_entries(root, PROGRESS_SAVE, saved)
    return report


PROGRESS_SAVE = 0  # SaveFileIndex de slot_%02d/progress.sav

# Voyage dans le temps libre : la condition de retour enfant (module du marché adulte,
# SageOfForest_IsCompleted_Exp) devient « drapeau du menu OU Temple de la Forêt fini »
FREE_TIME_FLAG = "OoTRR.FreeTimeTravel"
FREE_TIME_EXP = "OoTRR_FreeTimeTravel_Exp"
RETURN_MODULE = "Logic/Market_Adult_Prefab_89da.logic.module.ainb"
RETURN_CONDITION = "SageOfForest_IsCompleted_Exp"
MENU_BOOL_EXPS = {FREE_TIME_EXP: [("Bool", FREE_TIME_FLAG), ("Exp", RETURN_CONDITION), ("OR",)]}
# Pont arc-en-ciel : un drapeau sauvegardé par condition, posé par le menu. Module du pont : la scène
# GanonCastle_Adult_Field_Rainbow se déclenche si « Ready » ET NON « Step01 » (la scène fait passer la
# quête Defeat_Ganon à Step01) ; le pont existe une fois la scène vue. Seule « Ready » est remplacée,
# par « OU sur les conditions : drapeau ET condition » (original : l'expression de la quête).
BRIDGE_MODES = ("open", "vanilla", "stones", "medallions", "dungeons", "hearts")
BRIDGE_FLAGS = {mode: f"OoTRR.Bridge.{mode}" for mode in BRIDGE_MODES}
BRIDGE_MODULE_FILE = "Logic/GanonCastle_Level_Field_00_Prefab_14ba.logic.module.ainb"
BRIDGE_MENU_EXP = {"Defeat_Ganon_IsAfter_Ready_Exp": "OoTRR_MenuBridge_Ready_Exp"}


def bridge_menu_exps() -> dict[str, list[tuple]]:
    """Expressions du pont valables pour toutes les conditions du menu (nombres : BRIDGE_COUNTS)."""
    from .world import MAX_LIFE, MEDAL_FLAGS, STONE_FLAGS, _at_least

    exps: dict[str, list[tuple]] = {}
    conds: dict[str, list[tuple]] = {}
    for mode, flags, prefix in (("stones", STONE_FLAGS, "OoTRR_MenuBridgeS"),
                                ("medallions", MEDAL_FLAGS, "OoTRR_MenuBridgeM"),
                                ("dungeons", STONE_FLAGS + MEDAL_FLAGS, "OoTRR_MenuBridgeD")):
        sub = _at_least(flags, min(BRIDGE_COUNTS[mode], len(flags)), prefix)
        exps.update(sub)
        conds[mode] = [("Exp", next(iter(sub)))]
    values = list(range(4 * BRIDGE_COUNTS["hearts"], 81))  # MaxLife en quarts de cœur
    # « au moins N cœurs » = MaxLife vaut l'une des valeurs ; les expressions du jeu ont au plus 26
    # éléments : morceaux de 8 valeurs (23 éléments) réunis par une expression de tête
    top = []
    for i in range(0, len(values), 8):
        part = [("IntEq", MAX_LIFE, values[i])]
        for v in values[i + 1:i + 8]:
            part += [("IntEq", MAX_LIFE, v), ("OR",)]
        exps[f"OoTRR_MenuBridgeH_{i // 8}"] = part
        top += [("Exp", f"OoTRR_MenuBridgeH_{i // 8}")] + ([("OR",)] if top else [])
    exps["OoTRR_MenuBridgeH"] = top
    conds["hearts"] = [("Exp", "OoTRR_MenuBridgeH")]
    for original, name in BRIDGE_MENU_EXP.items():
        prog = [("Bool", BRIDGE_FLAGS["open"])]
        for mode, cond in (("vanilla", [("Exp", original)]), *conds.items()):
            prog += [("Bool", BRIDGE_FLAGS[mode])] + cond + [("AND",), ("OR",)]
        exps[name] = prog
    return exps


def bridge_module(raw: bytes) -> bytes:
    """Module du pont : les deux expressions de la quête Defeat_Ganon deviennent celles du menu."""
    import ainb

    script = ainb.AINB.from_binary(raw)
    found = set()
    for node in script.nodes:
        for p in node.params.string_inputs or []:
            if p.name == "GameDataNameBoolExp" and p.default_value in BRIDGE_MENU_EXP:
                found.add(p.default_value)
                p.default_value = BRIDGE_MENU_EXP[p.default_value]
    if found != set(BRIDGE_MENU_EXP):
        raise ValueError(f"{BRIDGE_MODULE_FILE} : expressions trouvées {sorted(found)}")
    return script.to_binary()


EXTRA_SAVED_FLAGS = (FREE_TIME_FLAG,) + tuple(BRIDGE_FLAGS.values())
# drapeaux de départ propres au menu : (réglage, valeur, drapeau, valeur du drapeau)
EXTRA_START_FLAGS = [("free_time_travel", True, FREE_TIME_FLAG, True)] + [
    ("bridge", mode, flag, True) for mode, flag in BRIDGE_FLAGS.items()]


def return_module(raw: bytes) -> bytes:
    """Module du retour enfant : l'expression lue devient FREE_TIME_EXP."""
    import ainb

    script = ainb.AINB.from_binary(raw)
    found = 0
    for node in script.nodes:
        for p in node.params.string_inputs or []:
            if p.name == "GameDataNameBoolExp" and p.default_value == RETURN_CONDITION:
                p.default_value = FREE_TIME_EXP
                found += 1
    if found != 1:
        raise ValueError(f"{RETURN_MODULE} : {found} conditions {RETURN_CONDITION}")
    return script.to_binary()


def add_saved_entries(root: dict, save_index: int, count: int) -> list[str]:
    """Met à jour les métadonnées de sauvegarde après l'ajout de `count` entrées scalaires
    (Bool, Int, Enum…) enregistrées dans le fichier `save_index`.

    progress.sav (relevé sur une sauvegarde) : en-tête 0x20 octets, puis pour chaque type un
    marqueur et une paire (hachage u32, valeur u32) par entrée, puis la zone des tableaux et chaînes,
    dont la position est SaveDataOffsetPos (aussi écrite dans l'en-tête). Une entrée scalaire ajoute
    8 octets à la table : la zone de données et la taille totale se décalent d'autant. Les
    sauvegardes sont indexées par hachage : une ancienne sauvegarde prend la valeur par défaut."""
    meta = root["MetaData"]
    grow = 8 * count
    old = (meta["SaveDataOffsetPos"][save_index], meta["SaveDataSize"][save_index])
    meta["SaveDataOffsetPos"][save_index] = type(old[0])(old[0] + grow)
    meta["SaveDataSize"][save_index] = type(old[1])(old[1] + grow)
    meta["AllDataSaveOffset"] = type(meta["AllDataSaveOffset"])(meta["AllDataSaveOffset"] + grow)
    meta["AllDataSaveSize"] = type(meta["AllDataSaveSize"])(meta["AllDataSaveSize"] + grow)
    return [f"GameData : {count} entrées sauvegardées dans {meta['SaveDirectory'][save_index]} "
            f"(données {old[0]} -> {meta['SaveDataOffsetPos'][save_index]}, "
            f"taille {old[1]} -> {meta['SaveDataSize'][save_index]})"]


def option_table(game_table: bytes, enum_values: dict[str, list[str]]) -> bytes:
    """Notre table de lignes, construite à partir des lignes du jeu (même forme, sans conditions)."""
    tree = read_byml(game_table)
    rows = {r.get("OptionType"): r for r in tree["OptionSetArray"]
            if "OptionType" in r and r.get("ButtonType") != SEPARATOR_BUTTON}
    separator = next(r for r in tree["OptionSetArray"] if r.get("ButtonType") == SEPARATOR_BUTTON)
    out = []
    for setting, option_type, values in ROWS:
        if setting == SEPARATOR:
            out.append(copy.deepcopy(separator))
            continue
        row = copy.deepcopy(rows[flag_hash(option_type)])
        row.pop("CheckGameData", None)
        row.pop("IsCheckDisplayGameData", None)
        if values is not None:
            names = enum_values[option_type][:len(values)]
            if len(names) < len(values):
                raise ValueError(f"{option_type} : {len(names)} valeurs pour {len(values)} choix")
            row["ChoiceType"] = [U32(flag_hash(n)) for n in names]
        out.append(row)
    tree["OptionSetArray"] = out
    return write_byml(tree, byml_version(game_table))


def messages(msbt: bytes, language: str) -> bytes:
    texts = TEXTS_FR if language in FRENCH else TEXTS_EN
    new = {}
    for setting, option_type, values in SETTING_ROWS + SEED_ROWS:
        title, caption, labels = texts[setting]
        new[f"OoTRR_{option_type}_Title"] = title.encode()
        new[f"OoTRR_{option_type}_Caption"] = caption.encode()
        for i, v in enumerate(values or []):
            new[f"OoTRR_{option_type}_{i:02d}"] = labels.get(v, v).encode()
    have = read_labels(msbt)
    clash = [k for k in new if k in have]
    if clash:
        raise KeyError(f"{MESSAGES} : étiquettes déjà présentes {clash[:3]}")
    return add_messages(msbt, new)


def menu_layout(buil: bytes) -> bytes:
    """Copie de la mise en page de l'écran d'options où les modèles inutilisés sont invisibles.

    Format .buil (BFFH / UIL) : table des noms d'éléments (pointeurs vers la réserve de chaînes),
    puis une fiche par élément contenant « u32 index du nom, u32 drapeaux » ; le bit 0 des drapeaux
    est « visible » (comme les volets ui2d). Sans ligne amiibo ni séparateur dans notre table, le jeu
    ne se sert pas de ces modèles et les laisse affichés à leur place."""
    import re
    import struct

    data = bytearray(buil)
    # les fiches numérotent les noms depuis le début de la réserve, qui commence par le nom de la mise
    # en page (« SystemOption_00 »), juste avant « RootPane » (vérifié en jeu : un cran de décalage
    # cache le bouton à choix modèle au lieu de l'amiibo)
    root = data.index(b"RootPane\0")
    pool = data.rindex(b"\0", 0, root - 1) + 1
    names = []
    off = pool
    while data[off] and len(names) < 64:
        end = data.index(b"\0", off)
        names.append(data[off:end].decode())
        off = end + 1
    for pane in HIDDEN_PANES:
        idx = names.index(pane)
        flags = rb"[\x00-\xff]{2}\x55\x02"  # drapeaux : 0x0255xxxx dans ce fichier
        hits = [m.start() for m in re.finditer(re.escape(struct.pack("<I", idx)) + flags, data)]
        if len(hits) != 1:
            raise ValueError(f"{pane} : fiche introuvable ou ambiguë ({len(hits)})")
        data[hits[0] + 4] &= 0xFE
    return bytes(data)


def start_flag_table() -> tuple[list[tuple[str, object, str, bool]], list[str]]:
    """Drapeaux à poser au début de la partie selon les réglages du menu : différence entre les
    drapeaux de départ de chaque valeur et ceux de la base (STATIC_SETTINGS). Renvoie
    ([(réglage, valeur, drapeau, valeur du drapeau)], [drapeaux non booléens ignorés])."""
    from .settings import build
    from .world import World

    base = World(build(dict(STATIC_SETTINGS))).start_flags()
    table, skipped = [], []
    for setting, _option_type, values in SETTING_ROWS:
        for value in (values if values is not None else [False, True]):
            if setting == "bridge":
                continue  # pas de drapeau de départ
            flags = World(build({**STATIC_SETTINGS, setting: value})).start_flags()
            for name, flag_value in flags.items():
                if base.get(name) == flag_value:
                    continue
                if not isinstance(flag_value, bool) or name.startswith("#"):
                    skipped.append(f"{setting}={value}: {name}={flag_value}")
                    continue
                table.append((setting, value, name, flag_value))
    table += EXTRA_START_FLAGS
    return table, skipped


MOAT_MODULE = "Logic/HyruleField_Child_Prefab_91f9.logic.module.ainb"


def moat_module(raw: bytes) -> bytes:
    """Ocarina des douves : le module le crée si l'étape de la quête DoorOfTime **est** Step04.
    Devient « après Step03 » (= Step04 ou plus) : porte fermée, comme le jeu d'origine (l'ocarina
    disparaît une fois obtenu) ; porte ouverte (Step06), il existe aussi, avec la condition de
    présence « 3 pierres ». Python, lui, remplaçait Step04 par Step06 (porte ouverte seulement)."""
    import ainb

    script = ainb.AINB.from_binary(raw)
    check = next(n for n in script.nodes if n.name == "HoldChallengeCurrentStepCheckOrder")
    step = next(p for p in check.params.string_inputs if p.name == "ChallengeStepName")
    if step.default_value != "Step04":
        raise ValueError(f"{MOAT_MODULE} : étape inattendue {step.default_value}")
    step.default_value = "Step03"
    outputs = [o.name for o in check.params.bool_outputs]
    ocarina = next(n for n in script.nodes if n.name == "ActorLogicOcarinaTime")
    create = next(p for p in ocarina.params.bool_inputs if p.name == "Logic_Create")
    if create.source.src_node_index != check.index or outputs[create.source.src_output_index] != "IsEqual":
        raise ValueError(f"{MOAT_MODULE} : branchement inattendu")
    create.source.src_output_index = outputs.index("IsAfter")
    return script.to_binary()


def title_sequence(raw: bytes) -> bytes:
    """NormalTitle : Nouvelle partie -> nouveau nœud Option.module -> ConfirmationNewGame -> partie,
    et le drapeau MENU_FLAG (vrai avant notre menu, faux avant l'écran Options et au début de la partie).

    Modifie directement l'objet de la bibliothèque `ainb` (son passage par dict/JSON casse la table
    des chaînes de cette version)."""
    import ainb
    from ainb.node import ChildPlug
    from ainb.transition import Transition

    script = ainb.AINB.from_binary(raw)
    nodes = script.nodes

    def new_guid() -> str:
        return str(uuid.UUID(int=(0x4F6F5452 << 96) | (0x4000 << 48) | (0x8000 << 32) | len(nodes)))

    confirm = next(n for n in nodes if n.name == "ConfirmationNewGame.module")
    option = next(n for n in nodes if n.name == "Option.module"
                  and any(t.node_index != 7 for t in n.transition_plugs))
    before = [p for n in nodes for p in (n.transition_plugs or []) if p.node_index == confirm.index]
    to_option = [n for n in nodes for p in (n.transition_plugs or []) if p.node_index == option.index]
    if len(before) != 1 or len(to_option) != 1:
        raise ValueError("NormalTitle : structure inattendue (transitions vers la confirmation / les options)")
    prepare_new_game = next(n for n in nodes for p in (n.transition_plugs or []) if p is before[0])
    yes = next(t for t in confirm.transition_plugs if t.transition.command_name == "Yes")
    start = nodes[yes.node_index]

    menu = copy.deepcopy(option)
    menu.index = len(nodes)
    menu.guid = new_guid()
    end = menu.transition_plugs[0]
    end.node_index = confirm.index
    end.transition = Transition(transition_type=end.transition.transition_type,
                                update_post_calc=end.transition.update_post_calc,
                                command_name=end.transition.command_name)
    nodes.append(menu)
    before[0].node_index = menu.index
    for m in script.modules:
        if m.path == "Option.module.ainb":
            m.instance_count += 1

    template = next(n for n in nodes if n.name == "SeqOneShotSetNonStructGameDataBool")

    def set_flag(value: bool, flag: str = MENU_FLAG):
        n = copy.deepcopy(template)
        n.index = len(nodes)
        n.guid = new_guid()
        for p in n.params.string_inputs:
            if p.name == "GameDataFullName":
                p.default_value = flag
        for p in n.params.bool_inputs:
            if p.name == "Value":
                p.default_value = value
        nodes.append(n)
        return n

    def child(n) -> ChildPlug:
        plug = ChildPlug()
        plug.node_index = n.index
        return plug

    # les nœuds de préparation (Element_Simultaneous) exécutent tous leurs enfants
    prepare_new_game.child_plugs.append(child(set_flag(True)))
    to_option[0].child_plugs.append(child(set_flag(False)))
    start.child_plugs.insert(0, child(set_flag(False)))
    # génération après la remise à zéro des données de la partie (SeqExecuteResetGameData, sinon les
    # drapeaux posés au départ seraient effacés) mais avant AfterLoadSaveData.module : le jeu y lit ses
    # données (ex. cartes des donjons) ; posés après, ils ne sont pas pris en compte (vérifié en jeu)
    after_load = next(n for n in nodes if n.name == "AfterLoadSaveData.module")
    holder = next(n for n in nodes if any(p.node_index == after_load.index for p in (n.child_plugs or [])))
    pos = next(i for i, p in enumerate(holder.child_plugs) if p.node_index == after_load.index)
    holder.child_plugs.insert(pos, child(set_flag(True, GENERATE_FLAG)))
    return script.to_binary()


def menu_header(root: dict) -> str:
    """En-tête C++ pour le module natif : comment lire chaque réglage du menu dans GameData
    (structure OoTRRMenu : numéro de membre, booléen ou énumération, valeurs du jeu -> valeurs du réglage)."""
    from .settings import SETTINGS

    idx = index(root)
    src = next(e for e in root["Data"]["Struct"] if e["Hash"] == flag_hash(OPTION_STRUCT))
    member = {m["Hash"]: i for i, m in enumerate(src["DefaultValue"])}
    names = list(SETTINGS)
    lines = ["// Généré par ootrr/ingame_menu.py (menu_header) : ne pas modifier à la main.", "#pragma once",
             "#include <cstdint>", "", "namespace ootrr::menu {", "",
             f"constexpr uint32_t kStructHash = 0x{flag_hash(STRUCT):08x};  // {STRUCT}",
             f"constexpr uint32_t kMenuFlagHash = 0x{flag_hash(MENU_FLAG):08x};  // {MENU_FLAG}",
             f"constexpr uint32_t kGenerateFlagHash = 0x{flag_hash(GENERATE_FLAG):08x};  // {GENERATE_FLAG}",
             f"constexpr uint32_t kSeedHash = 0x{flag_hash(SEED_ENTRY):08x};  // {SEED_ENTRY}",
             "// valeur lue -> valeur du réglage : bool = 0/1 ; énumération = index de la valeur du jeu",
             "// member = hachage du nom du membre (ex. CameraRotateSpeed) : les accesseurs GameData d'une",
             "// structure cherchent le membre par ce hachage dans la table de la poignée",
             "struct MenuSetting { int32_t setting; uint32_t member; bool is_bool; int32_t count;",
             "                     uint32_t game_values[8]; int32_t setting_values[8]; };"]
    rows = []
    for setting, option_type, values in SETTING_ROWS:
        section, entry = idx[src["DefaultValue"][member[flag_hash(option_type)]]["Value"]]
        m = f"0x{flag_hash(option_type):08x}"
        sid = names.index(setting)
        if values is None:
            rows.append(f"    {{{sid}, {m}, true, 0, {{}}, {{}}}},  // {setting} <- {option_type}")
            continue
        allowed = SETTINGS[setting][1]
        game = ", ".join(f"0x{flag_hash(v):08x}" for v in entry["RawValues"][:len(values)])
        ours = ", ".join(str(allowed.index(v)) for v in values)
        rows.append(f"    {{{sid}, {m}, false, {len(values)}, {{{game}}}, {{{ours}}}}},  // {setting} <- {option_type}")
    lines += [f"constexpr int kMenuSettingCount = {len(rows)};",
              "inline constexpr MenuSetting kMenuSettings[kMenuSettingCount] = {"] + rows + ["};", ""]
    by_name = {s: t for s, t, _ in SEED_ROWS}
    lines += ["// seed manuelle : bascule ; activée, le clavier virtuel s'ouvre au lancement de la partie",
              f"constexpr uint32_t kSeedManualMember = 0x{flag_hash(by_name[SEED_MANUAL]):08x};  // {by_name[SEED_MANUAL]}",
              "constexpr uint32_t kSeedMax = 999999;  // seeds aléatoires : 1-999999 (courtes à recopier)", ""]

    def value_index(setting, value):
        allowed = SETTINGS[setting][1]
        if allowed is bool:
            return int(bool(value))
        return allowed.index(value) if isinstance(allowed, tuple) else int(value)

    fixed = [f"    {{{names.index(k)}, {value_index(k, v)}}},  // {k} = {v}" for k, v in FIXED_SETTINGS.items()]
    lines += ["struct FixedSetting { int32_t setting; int32_t value; };",
              f"constexpr int kFixedSettingCount = {len(fixed)};",
              "inline constexpr FixedSetting kFixedSettings[kFixedSettingCount] = {"] + fixed + ["};", ""]
    bridge = SETTINGS["bridge"][1]
    counts = [f"    {{{bridge.index(k)}, {v}}},  // {k}" for k, v in BRIDGE_COUNTS.items()]
    lines += [f"constexpr int32_t kBridgeSetting = {names.index('bridge')};",
              f"constexpr int32_t kBridgeCountSetting = {names.index('bridge_count')};",
              "struct BridgeCount { int32_t bridge; int32_t count; };",
              f"constexpr int kBridgeCountCount = {len(counts)};",
              "inline constexpr BridgeCount kBridgeCounts[kBridgeCountCount] = {"] + counts + ["};", ""]
    table, skipped = start_flag_table()
    structs = {e["Hash"]: {m["Hash"]: m["Value"] for m in e["DefaultValue"]} for e in root["Data"]["Struct"]}

    def struct_member(name: str) -> tuple[int, int]:
        """(structure, membre) si le drapeau est un membre de structure (ex. DungeonInfo.X.IsGetMap), sinon (0, 0)."""
        if "." not in name:
            return 0, 0
        parent, member = name.rsplit(".", 1)
        members = structs.get(flag_hash(parent), {})
        if members.get(flag_hash(member)) == flag_hash(name):
            return flag_hash(parent), flag_hash(member)
        return 0, 0

    flags = []
    for s, v, f, fv in table:
        st, mb = struct_member(f)
        flags.append(f"    {{{names.index(s)}, {value_index(s, v)}, 0x{flag_hash(f):08x}, 0x{st:08x}, 0x{mb:08x}, "
                     f"{str(fv).lower()}}},  // {s}={v} : {f}")
    lines += ["// drapeaux posés au début de la partie : si réglage == valeur, drapeau = valeur du drapeau ;",
              "// membre de structure (structure != 0) : écrit via la poignée de la structure",
              "struct StartFlag { int32_t setting; int32_t value; uint32_t flag; uint32_t structure; uint32_t member;",
              "                   bool flag_value; };",
              f"constexpr int kStartFlagCount = {len(flags)};",
              "inline constexpr StartFlag kStartFlags[kStartFlagCount] = {"] + flags + ["};"]
    enums = []
    for entry in skipped:
        # "réglage=valeur: drapeau=valeur" ; drapeau "#hachage" ou nom, valeur = nom de la valeur d'énumération
        head, flag = entry.split(": ", 1)
        s, v = head.split("=", 1)
        name, value = flag.rsplit("=", 1)
        h = int(name[1:]) if name.startswith("#") else flag_hash(name)
        v = {"True": True, "False": False}.get(v, v)
        enums.append(f"    {{{names.index(s)}, {value_index(s, v)}, 0x{h:08x}, 0x{flag_hash(value):08x}}},  // {entry}")
    lines += ["// énumérations posées au début de la partie (valeur = hachage du nom de la valeur)",
              "struct StartEnum { int32_t setting; int32_t value; uint32_t flag; uint32_t enum_value; };",
              f"constexpr int kStartEnumCount = {len(enums)};",
              "inline constexpr StartEnum kStartEnums[kStartEnumCount] = {"] + (enums or ["    {-1, 0, 0, 0},"]) + ["};"]
    from .world import DOOR_OF_TIME_STEP
    lines += ["// Porte du Temps ouverte : la quête ne doit pas reculer sous Step06",
              f"constexpr uint32_t kDoorChallengeHash = 0x{flag_hash('DoorOfTime'):08x};  // DoorOfTime",
              f"constexpr uint32_t kDoorChallengePathHash = 0x{flag_hash('Work/Challenge/DoorOfTime.game__challenge__Challenge.gyml'):08x};",
              f"constexpr uint32_t kDoorOpenSteps[] = {{0x{flag_hash('Step06'):08x}, 0x{flag_hash('Complete'):08x}}};  // Step06, Complete",
              f"constexpr int32_t kOpenDoorSetting = {names.index('open_door_of_time')};"]
    lines += ["", "}  // namespace ootrr::menu", ""]
    return "\n".join(lines)
