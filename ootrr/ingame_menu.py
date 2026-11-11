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
ROWS: list[tuple[str, str, list[str] | None]] = [
    ("open_forest", "CameraRotateSpeed", ["closed", "closed_deku", "open"]),
    ("open_door_of_time", "IsCameraUpDownReverse", None),
    ("free_time_travel", "IsCameraRightLeftReverse", None),
    ("skip_child_zelda", "IsUseGyro", None),
    (SEPARATOR, "", None),
    ("bridge", "VoiceLanguage", ["open", "vanilla", "stones", "medallions", "dungeons", "hearts"]),
    ("shuffle_rewards", "LockOnType", ["vanilla", "shuffled"]),
    ("shuffle_hearts", "ControllerRumble", ["none", "freestanding", "all"]),
    ("maps_compasses", "DisplayMode", ["vanilla", "start_with", "removed"]),
    (SEPARATOR, "", None),
    ("skip_cutscenes", "OcarinaKeyAssign", ["none", "safe"]),
    ("logic_lens_required", "IsChangeJumpButton", None),
]
SETTING_ROWS = [r for r in ROWS if r[0] != SEPARATOR]
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
    "shuffle_hearts": ("Heart Pieces", "Shuffle the freestanding Pieces of Heart (and the boss Heart Containers).",
                       {"none": "Vanilla", "freestanding": "Freestanding", "all": "All"}),
    "maps_compasses": ("Maps and Compasses", "Maps and compasses: in place, given at the start, or removed.",
                       {"vanilla": "Vanilla", "start_with": "Start With", "removed": "Removed"}),
    "skip_cutscenes": ("Skip Cutscenes", "Mark cutscenes that change nothing as already seen.",
                       {"none": "None", "safe": "Safe"}),
    "logic_lens_required": ("Lens Required", "The logic requires the Lens of Truth for invisible paths.", {}),
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
    "shuffle_hearts": ("Quarts de cœur", "Mélange les quarts de cœur au sol (et les réceptacles des boss).",
                       {"none": "Original", "freestanding": "Au sol", "all": "Tous"}),
    "maps_compasses": ("Cartes et boussoles", "Cartes et boussoles : à leur place, données au départ, ou retirées.",
                       {"vanilla": "Original", "start_with": "Au départ", "removed": "Retirées"}),
    "skip_cutscenes": ("Passer les cinématiques", "Les cinématiques sans effet sont marquées comme vues.",
                       {"none": "Aucune", "safe": "Sûres"}),
    "logic_lens_required": ("Monocle requis", "La logique exige le Monocle de Vérité pour les passages invisibles.", {}),
}
FRENCH = ("EUfr", "USfr")


def gamedata_struct(root: dict, defaults: dict | None = None) -> list[str]:
    """Ajoute la structure OoTRRMenu (copie d'OptionData, non sauvegardée) à GameDataList."""
    data = root["Data"]
    idx = index(root)
    src = next(e for e in data["Struct"] if e["Hash"] == flag_hash(OPTION_STRUCT))
    if any(e["Hash"] == flag_hash(STRUCT) for e in data["Struct"]):
        raise KeyError(f"GameData : structure {STRUCT} déjà présente")
    types = {flag_hash(t): t for _, t, _ in SETTING_ROWS}
    by_type = {t: (s, values) for s, t, values in SETTING_ROWS}
    members = []
    report = []
    for m in src["DefaultValue"]:
        section, entry = idx[m["Value"]]
        name = types.get(m["Hash"], f"{m['Hash']:08x}")
        new = copy.deepcopy(entry)
        new["Hash"] = U32(flag_hash(f"{STRUCT}.{name}"))
        new["SaveFileIndex"] = -1
        new["ResetTypeValue"] = 0
        setting, values = by_type.get(name, (None, None))
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
    flag = copy.deepcopy(next(e for e in data["Bool"] if e.get("SaveFileIndex") == -1))
    flag.update({"Hash": U32(flag_hash(MENU_FLAG)), "DefaultValue": False, "ResetTypeValue": 0})
    data["Bool"].append(flag)
    report.append(f"GameData : drapeau {MENU_FLAG}")
    report.append(f"GameData : structure {STRUCT} ({len(members)} membres)")
    return report


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
    for setting, option_type, values in SETTING_ROWS:
        title, caption, labels = texts[setting]
        new[f"OoTRR_{option_type}_Title"] = title.encode()
        new[f"OoTRR_{option_type}_Caption"] = caption.encode()
        for i, v in enumerate(values or []):
            new[f"OoTRR_{option_type}_{i:02d}"] = labels[v].encode()
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
    pool = data.index(b"RootPane\0")
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

    def set_flag(value: bool):
        n = copy.deepcopy(template)
        n.index = len(nodes)
        n.guid = new_guid()
        for p in n.params.string_inputs:
            if p.name == "GameDataFullName":
                p.default_value = MENU_FLAG
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
    return script.to_binary()
