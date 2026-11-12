"""Export de la logique pour le générateur natif (C++, dans le jeu).

    python -m ootrr.native_logic        # écrit native/exlaunch/source/program/rando/logic_data.hpp

Le générateur Python compile les règles avec les réglages figés. Ici, les réglages restent des
variables : le jeu les lit dans le menu. Les règles deviennent un code préfixé (entiers) évalué
par native/exlaunch/source/program/rando/generator.cpp, avec exactement la même résolution des
noms que ootrr/rules.py (helpers, puis réglages, puis objets / événements).

Code d'une règle (préfixe, chaque élément est un int32) :
  T_TRUE | T_FALSE | T_IS_CHILD | T_IS_ADULT
  T_HAS chose n                 chose = index d'inventaire (capacité logique ou événement)
  T_HELPER h                    règle nommée de helpers.json
  T_SET_BOOL r                  réglage booléen r
  T_SET_IS r v                  réglage r == v (index de valeur, ou entier)
  T_NOT x | T_AND n x1..xn | T_OR n x1..xn
  T_CMP op a b                  a et b sont des nombres :
     N_CONST v | N_COUNT n c1..cn | N_HEARTS | N_SETTING r
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from .settings import SETTINGS
from .world import (DATA_DIR, JUNK_REPLACEMENT, LINKS_POCKET, OCARINA_EVENTS, OCARINA_OF_TIME_LOCATION, SONG_OF_TIME_LOCATION,
                    OPEN_DOOR_START, SARIA_GIFT, SKIP_CHILD_ZELDA, World)
from .search import RETURN_TO_CHILD

OUT = Path(__file__).resolve().parents[1] / "native" / "exlaunch" / "source" / "program" / "rando" / "logic_data.hpp"

OPS = ["T_TRUE", "T_FALSE", "T_IS_CHILD", "T_IS_ADULT", "T_HAS", "T_HELPER", "T_SET_BOOL", "T_SET_IS",
       "T_NOT", "T_AND", "T_OR", "T_CMP", "N_CONST", "N_COUNT", "N_HEARTS", "N_SETTING"]
OP = {name: i for i, name in enumerate(OPS)}
CMPS = {ast.GtE: 0, ast.Gt: 1, ast.LtE: 2, ast.Lt: 3, ast.Eq: 4, ast.NotEq: 5}
KINDS = ("general", "song", "reward")


class ExportError(ValueError):
    pass


def _read(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


class Exporter:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        items_raw = _read(data_dir / "items.json")
        self.helper_src: dict[str, str] = _read(data_dir / "helpers.json")["helpers"]
        self.regions_raw: dict[str, dict] = {}
        self.extra_locations: dict[str, dict] = {}
        for path in sorted((data_dir / "world").glob("*.json")):
            content = _read(path)
            self.regions_raw.update(content.get("regions", {}))
            for name, body in content.get("locations", {}).items():
                if not name.startswith("_"):
                    self.extra_locations[name] = body
        from .starting import add_spawn_exits
        self.regions_raw = add_spawn_exits(self.regions_raw)  # même sorties de Root que world.World
        self.logic_items: dict[str, dict] = items_raw["logic"]
        self.actors: dict[str, dict] = items_raw["actors"]
        self.ground = set(items_raw.get("ground", []))
        self.ground_native = set(items_raw.get("ground_native", {}))
        events = []
        for body in self.regions_raw.values():
            events += [e for e in body.get("events", {}) if e not in events]
        # espace d'inventaire : capacités logiques puis événements (comme les clés de State.items)
        self.inventory = list(self.logic_items) + events
        self.inv = {n: i for i, n in enumerate(self.inventory)}
        self.event_names = set(events)
        self.settings = list(SETTINGS)
        self.set_index = {n: i for i, n in enumerate(self.settings)}
        self.usable = {n: b["use"] for n, b in self.logic_items.items() if b.get("use")}
        self.code: list[int] = []
        self.helpers: dict[str, int] = {}  # nom -> index
        self.helper_offsets: list[int] = []
        for name in self.helper_src:
            self.helpers[name] = len(self.helpers)
            self.helper_offsets.append(-1)
        for name, src in self.helper_src.items():
            self.helper_offsets[self.helpers[name]] = self.rule(src, f"helper {name}")

    # ------------------------------------------------------------- règles
    def rule(self, source, where: str) -> int:
        """Compile une règle, renvoie son décalage dans self.code."""
        start = len(self.code)
        if isinstance(source, bool):
            self.code.append(OP["T_TRUE" if source else "T_FALSE"])
            return start
        text = str(source).strip()
        if not text:
            self.code.append(OP["T_TRUE"])
            return start
        self._bool(ast.parse(text, mode="eval").body, where, text)
        return start

    def _err(self, where, src, msg):
        return ExportError(f"{where} : {msg} dans « {src} »")

    def _thing(self, node, where, src) -> int:
        if not isinstance(node, ast.Name) or node.id not in self.inv:
            raise self._err(where, src, "objet ou événement attendu")
        return self.inv[node.id]

    def _setting(self, node, where, src) -> int:
        if not isinstance(node, ast.Name) or node.id not in self.set_index:
            raise self._err(where, src, "réglage attendu")
        return self.set_index[node.id]

    def _name(self, name: str, where, src) -> None:
        c = self.code
        if name in ("true", "True"):
            c.append(OP["T_TRUE"])
        elif name in ("false", "False"):
            c.append(OP["T_FALSE"])
        elif name == "is_child":
            c.append(OP["T_IS_CHILD"])
        elif name == "is_adult":
            c.append(OP["T_IS_ADULT"])
        elif name in self.helpers:
            c += [OP["T_HELPER"], self.helpers[name]]
        elif name in self.set_index:
            if SETTINGS[name][1] is not bool:
                raise self._err(where, src, f"réglage non booléen « {name} »")
            c += [OP["T_SET_BOOL"], self.set_index[name]]
        elif name in self.inv:
            c += [OP["T_HAS"], self.inv[name], 1]
        else:
            raise self._err(where, src, f"nom inconnu « {name} »")

    def _call(self, node: ast.Call, where, src) -> None:
        c = self.code
        fname, args = node.func.id, node.args
        if fname == "has":
            c += [OP["T_HAS"], self._thing(args[0], where, src), args[1].value]
        elif fname == "can_use":
            item = args[0].id
            self._thing(args[0], where, src)
            info = self.usable.get(item, {})
            parts = []
            if info.get("age"):
                parts.append(("age", info["age"]))
            parts.append(("has", item))
            parts += [("name", n) for n in info.get("needs", [])]
            c += [OP["T_AND"], len(parts)]
            for kind, value in parts:
                if kind == "age":
                    c.append(OP["T_IS_ADULT" if value == "adult" else "T_IS_CHILD"])
                elif kind == "has":
                    c += [OP["T_HAS"], self.inv[value], 1]
                else:
                    self._name(value, where, src)
        elif fname == "can_play":
            c += [OP["T_AND"], 2, OP["T_HAS"], self.inv["Ocarina"], 1,
                  OP["T_HAS"], self._thing(args[0], where, src), 1]
        elif fname == "setting_is":
            r = self._setting(args[0], where, src)
            allowed = SETTINGS[self.settings[r]][1]
            value = args[1].value
            v = allowed.index(value) if isinstance(allowed, tuple) else int(value)
            c += [OP["T_SET_IS"], r, v]
        else:
            raise self._err(where, src, f"fonction inconnue « {fname} »")

    def _num(self, node, where, src) -> None:
        c = self.code
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            c += [OP["N_CONST"], node.value]
        elif isinstance(node, ast.Call) and node.func.id == "count":
            c += [OP["N_COUNT"], len(node.args)] + [self._thing(a, where, src) for a in node.args]
        elif isinstance(node, ast.Call) and node.func.id == "hearts":
            c.append(OP["N_HEARTS"])
        elif isinstance(node, ast.Call) and node.func.id == "setting_value":
            c += [OP["N_SETTING"], self._setting(node.args[0], where, src)]
        else:
            raise self._err(where, src, "valeur numérique attendue")

    def _bool(self, node, where, src) -> None:
        c = self.code
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            c.append(OP["T_TRUE" if node.value else "T_FALSE"])
        elif isinstance(node, ast.Name):
            self._name(node.id, where, src)
        elif isinstance(node, ast.Call):
            self._call(node, where, src)
        elif isinstance(node, ast.Compare):
            c += [OP["T_CMP"], CMPS[type(node.ops[0])]]
            self._num(node.left, where, src)
            self._num(node.comparators[0], where, src)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            c.append(OP["T_NOT"])
            self._bool(node.operand, where, src)
        elif isinstance(node, ast.BoolOp):
            c += [OP["T_AND" if isinstance(node.op, ast.And) else "T_OR"], len(node.values)]
            for v in node.values:
                self._bool(v, where, src)
        else:
            raise self._err(where, src, f"élément non supporté ({type(node).__name__})")

    # ------------------------------------------------------------- monde
    def world(self) -> dict:
        regions = list(self.regions_raw)
        rid = {n: i for i, n in enumerate(regions)}
        dungeons: list[str] = []
        exits, events, locations = [], [], []
        for rname, body in self.regions_raw.items():
            for target, src in body.get("exits", {}).items():
                exits.append((rid[rname], rid[target], self.rule(src, f"sortie {rname} -> {target}")))
            for ename, src in body.get("events", {}).items():
                events.append((self.inv[ename], rid[rname], self.rule(src, f"événement {ename}")))
            d = body.get("dungeon")
            if d and d not in dungeons:
                dungeons.append(d)
        actor_names = list(self.actors)
        aid = {n: i for i, n in enumerate(actor_names)}

        def add(lname, rname, lbody):
            if isinstance(lbody, str):
                lbody = {"rule": lbody}
            hashes = lbody.get("hashes", [])
            d = self.regions_raw[rname].get("dungeon")
            locations.append(dict(
                name=lname, region=rid[rname], kind=KINDS.index(lbody.get("kind", "general")),
                rule=self.rule(lbody.get("rule", "True"), f"lieu {lname}"),
                vanilla=aid[lbody["vanilla"]], dungeon=dungeons.index(d) if d else -1,
                shuffle=bool(lbody.get("shuffle", bool(hashes))),
                dungeon_item={"map": 1, "compass": 2}.get(lbody.get("dungeon_item"), 0),
                pickup={"freestanding": 1, "boss": 2}.get(lbody.get("pickup"), 0),
                no_progression=bool(lbody.get("no_progression", False)),
                event={"keep": 1, "drop": 2}.get(lbody.get("event"), 0),
                conditional=bool(lbody.get("conditional", False)), scrub=bool(lbody.get("scrub", False)),
                skulltula=bool(lbody.get("skulltula", False)), shop=int(lbody.get("shop", 0)),
                shop_actor=lbody.get("shop_actor") or "", price=int(lbody.get("price", 0)),
                slot=int(lbody.get("slot", -1)), ocarina=bool(lbody.get("ocarina", False)),
                hashes=[int(h) for h in hashes]))

        for rname, body in self.regions_raw.items():
            for lname, lbody in body.get("locations", {}).items():
                add(lname, rname, lbody)
        for lname, lbody in self.extra_locations.items():
            add(lname, lbody.get("region", ""), lbody)
        lid = {l["name"]: i for i, l in enumerate(locations)}
        heart_logic = {"Heart_Piece", "Heart_Container"}
        items = []
        for name, body in self.actors.items():
            logic = body.get("logic")
            items.append(dict(name=name, logic=self.inv[logic] if logic else -1, level=body.get("level") or 0,
                              heart=logic in heart_logic, ground=name in self.ground or name in self.ground_native))
        return dict(regions=regions, dungeons=dungeons, exits=exits, events=events, locations=locations,
                    items=items, rid=rid, lid=lid, aid=aid)

    # ------------------------------------------------------------- sortie C++
    def header(self) -> str:
        w = self.world()

        def cstr(s: str) -> str:
            return json.dumps(s, ensure_ascii=True)

        lines = [
            "// Généré par python -m ootrr.native_logic : ne pas modifier à la main.",
            "#pragma once",
            "#include <cstdint>",
            "",
            "namespace ootrr::logic {",
            "",
            "enum Op : int32_t { " + ", ".join(OPS) + " };",
            "",
        ]
        # réglages
        lines.append(f"constexpr int kSettingCount = {len(self.settings)};")
        lines.append("enum SettingKind : int32_t { S_BOOL, S_ENUM, S_INT };")
        lines.append("struct SettingInfo { const char* name; SettingKind kind; int32_t value_count; const char* const* values; int32_t def; };")
        for name in self.settings:
            allowed = SETTINGS[name][1]
            if isinstance(allowed, tuple):
                lines.append(f"inline constexpr const char* kValues_{name}[] = {{{', '.join(cstr(v) for v in allowed)}}};")
        rows = []
        for name in self.settings:
            default, allowed, _ = SETTINGS[name]
            if allowed is bool:
                rows.append(f"    {{{cstr(name)}, S_BOOL, 2, nullptr, {int(default)}}},")
            elif isinstance(allowed, tuple):
                rows.append(f"    {{{cstr(name)}, S_ENUM, {len(allowed)}, kValues_{name}, {allowed.index(default)}}},")
            else:
                rows.append(f"    {{{cstr(name)}, S_INT, 0, nullptr, {int(default)}}},")
        lines += ["inline constexpr SettingInfo kSettings[kSettingCount] = {"] + rows + ["};"]
        lines += [f"enum SettingId : int32_t {{ " + ", ".join(f"SET_{n}" for n in self.settings) + " };", ""]

        def enum_value(setting, value):
            return SETTINGS[setting][1].index(value)

        consts = {
            "kRoot": w["rid"][World.ROOT],
            "kTempleOfTime": w["rid"]["Temple of Time"],
            "kGoal": self.inv[World.GOAL_EVENT],
            "kReturnToChild": self.inv[RETURN_TO_CHILD],
            "kOcarina": self.inv["Ocarina"],
            "kHeartContainer": self.inv["Heart_Container"],
            "kHeartPiece": self.inv["Heart_Piece"],
            "kJunk": w["aid"][JUNK_REPLACEMENT],
            "kLinksPocket": w["lid"][LINKS_POCKET],
            "kSariaGift": w["lid"][SARIA_GIFT],
            "kOcarinaOfTimeLocation": w["lid"][OCARINA_OF_TIME_LOCATION],
            "kBridgeHearts": enum_value("bridge", "hearts"),
            "kMapsVanilla": enum_value("maps_compasses", "vanilla"),
            "kMapsShuffle": enum_value("maps_compasses", "shuffle"),
            "kHeartsAll": enum_value("shuffle_hearts", "all"),
            "kHeartsFreestanding": enum_value("shuffle_hearts", "freestanding"),
            "kSkulltulasOverworld": enum_value("shuffle_skulltulas", "overworld"),
            "kSkulltulasAll": enum_value("shuffle_skulltulas", "all"),
            "kShopPricesAffordable": enum_value("shop_prices", "affordable"),
            "kShopPricesRandom": enum_value("shop_prices", "random"),
            "kSkipSafe": enum_value("skip_cutscenes", "safe"),
            "kRewardsVanilla": enum_value("shuffle_rewards", "vanilla"),
            "kRewardsShuffled": enum_value("shuffle_rewards", "shuffled"),
            "kAccessibilityAll": enum_value("accessibility", "all"),
            "kKindReward": KINDS.index("reward"),
            "kKindSong": KINDS.index("song"),
            "kSongsShuffle": enum_value("shuffle_songs", "shuffle"),
            "kSongsRandom": enum_value("shuffle_songs", "random"),
            "kSongOfTimeLocation": w["lid"][SONG_OF_TIME_LOCATION],
        }
        lines += [f"constexpr int32_t {k} = {v};" for k, v in consts.items()]
        lines.append(f"inline constexpr int32_t kOpenDoorStart[] = {{{', '.join(str(w['lid'][n]) for n in OPEN_DOOR_START)}}};")
        lines.append(f"inline constexpr int32_t kSkipChildZelda[] = {{{', '.join(str(w['lid'][n]) for n in SKIP_CHILD_ZELDA)}}};")
        # départ : points d'apparition (data/spawns.json), âge de chacun (1 = adulte) ; résolu par ingame.cpp
        from .starting import adult_default, spawns
        sp = spawns()
        lines.append(f"constexpr int kSpawnCount = {len(sp)};")
        lines.append("inline constexpr int32_t kSpawnAdult[kSpawnCount] = {" + ", ".join("1" if s["age"] == "adult" else "0" for s in sp) + "};")
        lines.append(f"constexpr int32_t kAdultDefaultSpawn = {adult_default()};")
        lines.append(f"constexpr int32_t kAgeAdult = {enum_value('starting_age', 'adult')};")
        lines.append(f"constexpr int32_t kAgeRandom = {enum_value('starting_age', 'random')};")
        lines.append("")
        # inventaire, objets
        lines.append(f"constexpr int kInventoryCount = {len(self.inventory)};")
        lines.append("inline constexpr const char* kInventoryNames[kInventoryCount] = {" + ", ".join(cstr(n) for n in self.inventory) + "};")
        lines.append("struct ItemInfo { const char* name; int32_t logic; int32_t level; bool heart; bool ground; };")
        lines.append(f"constexpr int kItemCount = {len(w['items'])};")
        lines.append("inline constexpr ItemInfo kItems[kItemCount] = {")
        lines += [f"    {{{cstr(i['name'])}, {i['logic']}, {i['level']}, {str(i['heart']).lower()}, {str(i['ground']).lower()}}},"
                  for i in w["items"]]
        lines.append("};")
        # régions, sorties, événements
        lines.append(f"constexpr int kRegionCount = {len(w['regions'])};")
        lines.append("inline constexpr const char* kRegionNames[kRegionCount] = {" + ", ".join(cstr(n) for n in w["regions"]) + "};")
        lines.append("struct Exit { int32_t source, target, rule; };")
        lines.append(f"constexpr int kExitCount = {len(w['exits'])};")
        lines.append("inline constexpr Exit kExits[kExitCount] = {" + ", ".join(f"{{{a}, {b}, {r}}}" for a, b, r in w["exits"]) + "};")
        lines.append("struct Event { int32_t thing, region, rule; };")
        lines.append(f"constexpr int kEventCount = {len(w['events'])};")
        lines.append("inline constexpr Event kEvents[kEventCount] = {" + ", ".join(f"{{{a}, {b}, {r}}}" for a, b, r in w["events"]) + "};")
        # lieux
        lines.append("// event : 0 aucun, 1 keep, 2 drop (scène de l'objet d'origine, retirée si l'objet change)")
        lines.append("struct LocationInfo { const char* name; int32_t region, kind, rule, vanilla, dungeon; bool shuffle; int32_t dungeon_item, pickup; bool no_progression; int32_t event; bool conditional; bool scrub; bool skulltula; int32_t shop; const char* shop_actor; int32_t price; bool ocarina; };")
        lines.append(f"constexpr int kLocationCount = {len(w['locations'])};")
        lines.append("inline constexpr LocationInfo kLocations[kLocationCount] = {")
        for l in w["locations"]:
            lines.append(f"    {{{cstr(l['name'])}, {l['region']}, {l['kind']}, {l['rule']}, {l['vanilla']}, {l['dungeon']}, "
                         f"{str(l['shuffle']).lower()}, {l['dungeon_item']}, {l['pickup']}, {str(l['no_progression']).lower()}, "
                         f"{l['event']}, {str(l['conditional']).lower()}, {str(l['scrub']).lower()}, {str(l['skulltula']).lower()}, {l['shop']}, {cstr(l['shop_actor'])}, {l['price']}, {str(l['ocarina']).lower()}}},")
        lines.append("};")
        # Peste Mojo : entier GameData du prix (prix / 5), écrit par le module selon les réglages
        from .formats.gamedata import flag_hash
        scrubs = [(i, flag_hash(SCRUB_PRICE_ENTRY.format(token(i))), flag_hash(SCRUB_PRICE_UNITS.format(token(i))))
                  for i, l in enumerate(w["locations"]) if l["scrub"]]
        lines.append("// prix / 5 écrit en dizaines (tens) et unités (units) : une question du jeu ne gère que 16 cas")
        lines.append("struct ScrubPrice { int32_t location; uint32_t tens; uint32_t units; };")
        lines.append(f"constexpr int kScrubPriceCount = {len(scrubs)};")
        lines.append("inline constexpr ScrubPrice kScrubPrices[kScrubPriceCount] = {"
                     + ", ".join(f"{{{i}, 0x{h:08x}, 0x{u:08x}}}" for i, h, u in scrubs) + "};")
        # règles
        lines.append(f"constexpr int kHelperCount = {len(self.helper_offsets)};")
        lines.append("inline constexpr int32_t kHelpers[kHelperCount] = {" + ", ".join(map(str, self.helper_offsets)) + "};")
        lines.append(f"constexpr int kCodeSize = {len(self.code)};")
        lines.append("inline constexpr int32_t kCode[kCodeSize] = {")
        for i in range(0, len(self.code), 24):
            lines.append("    " + ", ".join(map(str, self.code[i:i + 24])) + ",")
        lines.append("};")
        lines += ["", "}  // namespace ootrr::logic", ""]
        return "\n".join(lines)


TOKEN_PREFIX = "OoTRR_L"


def token(location_index: int) -> str:
    """Jeton d'emplacement mis dans la carte à la place de l'objet (remplacé en jeu par le module natif)."""
    return f"{TOKEN_PREFIX}{location_index:04d}"


def chest_tokens() -> dict[int, str]:
    """{hash d'acteur: jeton} pour tous les coffres mélangeables (pas les cœurs au sol)."""
    w = Exporter().world()
    out = {}
    for i, l in enumerate(w["locations"]):
        if l["hashes"] and l["shuffle"] and not l["pickup"] and not l["scrub"] and not l["skulltula"] and not l["shop"]:
            for h in l["hashes"]:
                out[h] = token(i)
    return out


def shop_tokens() -> dict[int, tuple[str, int]]:
    """{hash d'article: (jeton, rang)} pour les articles de boutique mélangeables (ootrr.shops)."""
    w = Exporter().world()
    return {h: (token(i), l["shop"]) for i, l in enumerate(w["locations"]) if l["shop"] for h in l["hashes"]}


def shop_slots() -> dict[str, dict[int, tuple[str, int]]]:
    """{boutique: {index d'article: (jeton, rang)}} (listes des marchands, ootrr.shops)."""
    w = Exporter().world()
    out: dict[str, dict[int, tuple[str, int]]] = {}
    for i, l in enumerate(w["locations"]):
        if l["shop"]:
            out.setdefault(l["name"].rsplit(" Item ", 1)[0], {})[l["slot"]] = (token(i), l["shop"])
    return out


def skulltula_tokens() -> dict[int, str]:
    """{hash d'acteur: jeton} pour les Skulltulas d'or : elles lâchent le jeton (objet ramassable sur mesure),
    le module natif donne l'objet placé au ramassage (modèle, textes et ajout redirigés)."""
    w = Exporter().world()
    return {h: token(i) for i, l in enumerate(w["locations"]) if l["skulltula"] for h in l["hashes"]}


def song_tokens() -> dict[str, str]:
    """{chant d'origine: jeton de son emplacement} (dons de Dm_SY_Ocarina, menu natif)."""
    w = Exporter().world()
    names = [i["name"] for i in w["items"]]
    return {names[l["vanilla"]]: token(i) for i, l in enumerate(w["locations"]) if l["kind"] == KINDS.index("song")}


def ocarina_tokens() -> dict[str, tuple[str, str]]:
    """{scène: (ocarina d'origine, jeton)} : Saria et les douves donnent le jeton de leur lieu (action
    d'inventaire, affichage de l'objet obtenu) ; le module natif donne l'objet de la seed à la place
    (l'ocarina d'origine si shuffle_ocarinas est désactivé)."""
    w = Exporter().world()
    return {flow: (vanilla, token(w["lid"][name])) for name, (flow, vanilla) in OCARINA_EVENTS.items()}


SCRUB_PRICE_ENTRY = "OoTRR.Price.{}"  # entier GameData : dizaines de prix / 5 de la Peste Mojo (choisi par le module)
SCRUB_PRICE_UNITS = "OoTRR.PriceUnits.{}"  # ... et unités


def scrub_price_entries() -> dict[str, tuple[str, str]]:
    """{jeton: entier GameData} pour les Peste Mojo vendeuses : le script de vente choisit la vente au
    prix (5 x valeur) selon cet entier, écrit par le module natif selon les réglages de prix."""
    return {t: (SCRUB_PRICE_ENTRY.format(t), SCRUB_PRICE_UNITS.format(t)) for t, _ in scrub_tokens().values()}


def scrub_tokens() -> dict[str, tuple[str, list[int]]]:
    """{nom du lieu: (jeton, hashes des Peste Mojo)} pour les Peste Mojo vendeuses : le jeton est vendu,
    le module natif donne l'objet placé (ou l'objet d'origine si elles ne sont pas mélangées)."""
    w = Exporter().world()
    return {l["name"]: (token(i), list(l["hashes"])) for i, l in enumerate(w["locations"]) if l["scrub"]}


def heart_tokens() -> dict[int, tuple[str, str]]:
    """{hash d'acteur: (jeton, acteur d'origine)} pour tous les cœurs posés au sol (quarts de cœur et
    réceptacles des boss), mélangés ou non : le module natif donne l'objet de la seed au ramassage."""
    w = Exporter().world()
    out = {}
    for i, l in enumerate(w["locations"]):
        if l["hashes"] and l["pickup"]:
            for h in l["hashes"]:
                out[h] = (token(i), w["items"][l["vanilla"]]["name"])
    return out


def main() -> int:
    text = Exporter().header()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"écrit {OUT} ({len(text)} octets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
