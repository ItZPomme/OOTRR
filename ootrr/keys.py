"""Dungeon small keys and boss keys (settings small_keys and boss_keys, data in data/keys.json).

How the game handles keys (read in the files, see docs/GAME_KNOWLEDGE.md "Dungeon keys"):

- each dungeon has saved GameData members `DungeonInfo.<game>.SmallKeyNum` (Int) and `.IsGetBossKey` (Bool);
- a chest gives a key with `Dm_SY_Treasurebox` (`EventGetDungeonSmallKey` / `EventGetDungeonBossKey`, no
  dungeon parameter): the key goes to the dungeon of the current map. A key of dungeon A found elsewhere is
  therefore given as `Obj_MiniGame_SmallKey` (the Treasure Chest Shop's "door key", not put in the pouch) and the
  chest's `GetEventName` runs a copy of the boss key chest event (`ForesetTemple_GetBossKey`: opening sequence,
  then Navi's line) where Navi's line is replaced by "DungeonInfo.A.SmallKeyNum + 1" or "IsGetBossKey = true".

The logic is prudent (the repository has no door layout): see `World` (`_key_rule`) and fill.py. With shuffled small
keys, a location of the dungeon needs all of its small keys, unless its rule asks for a number itself
(`has(Small_Key_Forest_Temple, 2)`). A key chest may have its own `rule` in keys.json (default: the dungeon's).
A dungeon marked `"layout": true` in keys.json has all its key counts written: its rules are used as they are, and
small_keys=own_dungeon places its keys anywhere in the dungeon by the logic (otherwise in their vanilla rooms).

Vanilla keys are not items: each one is an event, collected in its vanilla place (`vanilla_events`), and the key
terms of the rules count these events. Removed keys: the key terms are true.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SMALL, BOSS = "small", "boss"
SETTING = {SMALL: "small_keys", BOSS: "boss_keys"}
SHUFFLED = ("own_dungeon", "any_dungeon", "random")  # modes where the key items are placed by the fill

ITEM_PREFIX = {SMALL: "OoTRR_SmallKey_", BOSS: "OoTRR_BossKey_"}  # + game dungeon name: one item per dungeon
GAME_ITEM = {SMALL: "Item_Dungeon_SmallKey", BOSS: "Item_Dungeon_BossKey"}  # given in the key's own dungeon
FOREIGN_ACTOR = "Obj_MiniGame_SmallKey"  # given elsewhere ("You got a door key!", NotPushToPouch)
COUNTER = {SMALL: "DungeonInfo.{game}.SmallKeyNum", BOSS: "DungeonInfo.{game}.IsGetBossKey"}
# chest event copied for a key given outside its dungeon: EventSetting / GameAnalyzedEventInfo row, its script and
# the entry point (EventTransition Dm_SY_Treasurebox, then Navi's line at TEMPLATE_STEP, replaced)
TEMPLATE_EVENT = "ForesetTemple_GetBossKey"
TEMPLATE_FLOW = "ForestTemple_Gimmick"
TEMPLATE_ENTRY = "TreasureBoxDM_NaviChat_ForestTemple_BossKey"
TEMPLATE_STEP = 101
# templates of the inserted actions: GameDataActor.EventTriggerAddOrSubGameDataInt (Value 1, step 33) and
# GameDataActor.EventTriggerSetGameDataBool (Value True, step 195)
ACTION_TEMPLATE_FLOW = "MiniGame_SequentialChoiceTreasure"
ACTION_TEMPLATE_STEP = {SMALL: 33, BOSS: 195}
ACTION = {SMALL: "EventTriggerAddOrSubGameDataInt", BOSS: "EventTriggerSetGameDataBool"}


@dataclass
class KeyDungeon:
    name: str  # logic name (e.g. "Forest Temple")
    game: str  # DungeonInfo / Banc name (e.g. "ForestTemple")
    regions: list[str]
    region: str  # region of the key chests
    rule: str  # prudent rule of every key chest
    small: list[dict]
    freestanding: list[dict]
    boss_key: dict | None
    boss: list[str]
    boss_events: list[str]
    events: dict[str, dict[str, str]] = field(default_factory=dict)  # {region: {event: rule}} added to the world
    # the data describes the doors: every rule of the dungeon that needs small keys says how many (worst case), a
    # rule without a key count needs none; own_dungeon then places the keys anywhere in the dungeon by the logic
    layout: bool = False
    # small keys the player owns from the start (GameData counter), counted in the rules' key numbers: a rule's
    # has(Small_Key_<Dungeon>, n) counts the game's keys, the logic needs n - start_keys of the item pool
    start_keys: int = 0
    # chain-locked doors unlocked from the start (keys.json unlocked_doors): their saved Bool is set at the new game,
    # so the door loads as already unlocked and needs no key
    unlocked_doors: list[dict] = field(default_factory=list)
    # vanilla keys only: {location or key chest: {written key count: keys asked}}. The counts are the worst case for
    # keys that may be anywhere; some cannot be met with the keys in their vanilla places (see keys.json)
    vanilla_counts: dict[str, dict[int, int]] = field(default_factory=dict)

    @property
    def key_rooms(self) -> dict[int, int]:
        """{room: number of small key chests} (own_dungeon keeps these counts)."""
        out: dict[int, int] = {}
        for k in self.small:
            out[k["room"]] = out.get(k["room"], 0) + 1
        return out

    def small_location(self, i: int) -> str:
        """Location name of a small key chest: its "name" in keys.json, else "<Dungeon> Small Key Chest <n>"."""
        return self.small[i].get("name") or f"{self.name} Small Key Chest {i + 1}"

    @property
    def boss_location(self) -> str:
        """Location name of the boss key chest: its "name" in keys.json, else "<Dungeon> Boss Key Chest"."""
        return (self.boss_key or {}).get("name") or f"{self.name} Boss Key Chest"


def active(settings: dict[str, Any]) -> bool:
    return any(settings.get(s, "vanilla") != "vanilla" for s in SETTING.values())


def mode(settings: dict[str, Any], kind: str) -> str:
    return settings.get(SETTING[kind], "vanilla")


def item_name(kind: str, game: str) -> str:
    return ITEM_PREFIX[kind] + game


def logic_name(kind: str, dungeon: str) -> str:
    return ("Small_Key_" if kind == SMALL else "Boss_Key_") + dungeon.replace(" ", "_")


def parse_item(item: str) -> tuple[str, str] | None:
    """(kind, game dungeon) of a key item, or None."""
    for kind, prefix in ITEM_PREFIX.items():
        if item.startswith(prefix):
            return kind, item[len(prefix):]
    return None


def event_name(kind: str, game: str) -> str:
    """Chest event (RSDB EventSetting row) that gives this key outside its dungeon."""
    return f"OoTRR_Get{'SmallKey' if kind == SMALL else 'BossKey'}_{game}"


def flow_name(kind: str, game: str) -> str:
    return f"OoTRR_{'SmallKey' if kind == SMALL else 'BossKey'}_{game}"


def load(data_dir: Path) -> dict[str, KeyDungeon]:
    with (data_dir / "keys.json").open(encoding="utf-8") as fh:
        raw = json.load(fh)
    out = {}
    for name, body in raw["dungeons"].items():
        out[name] = KeyDungeon(
            name=name, game=body["game"], regions=list(body["regions"]), region=body["region"],
            rule=body.get("rule") or _chests_rule(body),
            small=list(body["small"]), freestanding=list(body.get("freestanding", [])),
            boss_key=body.get("boss_key"), boss=list(body.get("boss", [])),
            boss_events=list(body.get("boss_events", [])), events=dict(body.get("events", {})),
            layout=bool(body.get("layout", False)), start_keys=int(body.get("start_keys", 0)),
            unlocked_doors=list(body.get("unlocked_doors", [])),
            vanilla_counts={name: {int(n): int(v) for n, v in counts.items()}
                            for name, counts in body.get("vanilla_counts", {}).items()})
    return out


def _chests_rule(body: dict) -> str:
    """Dungeon rule when keys.json gives none: everything its key chests ask for (key terms left out), i.e.
    what collecting all of its keys needs."""
    parts: list[str] = []
    for chest in body["small"] + ([body["boss_key"]] if body.get("boss_key") else []):
        if "rule" not in chest:
            raise ValueError(f"keys.json: {body['game']}: a key chest without rule needs the dungeon's rule")
        for part in sorted(conjuncts(without_key_terms(chest["rule"]))):
            part = f"({part})" if " or " in part else part  # a whole "a or b" rule stays one requirement
            if part not in parts:
                parts.append(part)
    return " and ".join(parts) or "True"


def load_rooms(data_dir: Path) -> dict[str, int]:
    with (data_dir / "keys.json").open(encoding="utf-8") as fh:
        return dict(json.load(fh)["rooms"])


def conjuncts(rule: str) -> set[str]:
    """Parts of an "a and b and c" rule, split at the top level only (an "and" inside parentheses stays in its
    part, e.g. "x and (y and z or w)" -> {"x", "(y and z or w)"}). A rule with a top-level "or" is one part.
    "True" parts are dropped: they ask nothing."""
    text = _unwrap(str(rule))
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 0 and text.startswith(" or ", i):
            return {text} if _unwrap(text) != "True" else set()
        elif depth == 0 and text.startswith(" and ", i):
            parts.append(text[start:i])
            i += len(" and ")
            start = i
            continue
        i += 1
    parts.append(text[start:])
    return {p for p in (_unwrap(part) for part in parts) if p and p != "True"}


def _unwrap(part: str) -> str:
    """The part without parentheses around the whole of it: "(a or b)" -> "a or b", "(a) or (b)" kept."""
    part = part.strip()
    while part.startswith("(") and part.endswith(")"):
        depth = 0
        for i, c in enumerate(part):
            depth += c == "("
            depth -= c == ")"
            if depth == 0 and i < len(part) - 1:
                return part  # the first parenthesis closes before the end
        part = part[1:-1].strip()
    return part


# a key term of a rule: has(Small_Key_<Dungeon>, n), or a bare Small_Key_<Dungeon> / Boss_Key_<Dungeon>
KEY_TERM = re.compile(r"has\(\s*(Small|Boss)_Key_(\w+)\s*,\s*\d+\s*\)|\b(Small|Boss)_Key_(\w+)\b")


def _term_kind(match: re.Match) -> str:
    return SMALL if (match.group(1) or match.group(3)) == "Small" else BOSS


def without_key_terms(rule: str, kinds: tuple[str, ...] = (SMALL, BOSS)) -> str:
    """The rule with its key terms of these kinds replaced by True (keys that are not items of the world: vanilla
    or removed keys, or the native generator, which never shuffles keys)."""
    return KEY_TERM.sub(lambda m: "True" if _term_kind(m) in kinds else m.group(0), str(rule))


def clamp_counts(rule: str, dungeon: str, limit: int, owned: int = 0) -> str:
    """has(Small_Key_<dungeon>, n) counts the game's keys: the `owned` start keys are taken off (none left to find:
    True), and n above the keys the logic knows asks for all of them instead."""
    name = logic_name(SMALL, dungeon)

    def count(m: re.Match) -> str:
        n = min(int(m.group(1)) - owned, limit)
        return f"has({name}, {n})" if n > 0 else "True"
    return re.sub(rf"has\(\s*{name}\s*,\s*(\d+)\s*\)", count, str(rule))


# ---------------------------------------------------------------------- vanilla keys in the logic
# With vanilla keys the key chests are not locations: each key (chest or ground) is an event of its region, collected
# when its rule is met, and the key terms of the rules count these events (Python and native generators).

VANILLA_EVENT = "Vanilla_"  # prefix of the events that stand for the keys in their vanilla places


def _vanilla_places(kd: KeyDungeon) -> list[dict]:
    return kd.small + kd.freestanding


def vanilla_small_events(kd: KeyDungeon) -> list[str]:
    base = VANILLA_EVENT + logic_name(SMALL, kd.name)
    return [f"{base}_{i + 1}" for i in range(len(_vanilla_places(kd)))]


def vanilla_boss_event(kd: KeyDungeon) -> str:
    return VANILLA_EVENT + logic_name(BOSS, kd.name)


def vanilla_terms(rule: Any, dungeons: dict[str, KeyDungeon], kinds: tuple[str, ...], where: str = "") -> str:
    """The rule of `where` (location or key chest) with its key terms of these kinds (vanilla keys) counted on the
    vanilla key events."""
    src = str(rule)
    for kd in dungeons.values():
        small, boss = logic_name(SMALL, kd.name), logic_name(BOSS, kd.name)
        if SMALL in kinds and small in src:
            events = vanilla_small_events(kd)
            counts = kd.vanilla_counts.get(where, {})

            def count(m: re.Match) -> str:
                n = int(m.group(1) or 1)
                n = min(counts.get(n, n) - kd.start_keys, len(events))
                return f"(count({', '.join(events)}) >= {n})" if n > 0 else "True"
            src = re.sub(rf"has\(\s*{small}\s*,\s*(\d+)\s*\)|(?<!\w){small}(?!\w)", count, src)
        if BOSS in kinds and kd.boss_key:
            src = re.sub(rf"has\(\s*{boss}\s*,\s*1\s*\)|(?<!\w){boss}(?!\w)", vanilla_boss_event(kd), src)
    return src


def vanilla_events(dungeons: dict[str, KeyDungeon], kinds: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """{region: {event: rule}} of the keys in their vanilla places (written rules, small key terms of the key chests
    already counted on the events)."""
    out: dict[str, dict[str, str]] = {}
    for kd in dungeons.values():
        if SMALL in kinds:
            for i, (event, place) in enumerate(zip(vanilla_small_events(kd), _vanilla_places(kd))):
                where = kd.small_location(i) if i < len(kd.small) else place.get("name", "")
                out.setdefault(place.get("region", kd.region), {})[event] = vanilla_terms(
                    place.get("rule", kd.rule), dungeons, kinds, where)
        if BOSS in kinds and kd.boss_key:
            out.setdefault(kd.boss_key.get("region", kd.region), {})[vanilla_boss_event(kd)] = str(
                kd.boss_key.get("rule", kd.rule))
    return out


def vanilla_boss_rule(src: Any, name: str, dungeons: dict[str, KeyDungeon]) -> str:
    """Rule of the location or event `name`: behind a boss door it also asks for the boss key."""
    for kd in dungeons.values():
        if kd.boss_key and name in kd.boss + kd.boss_events and not mentions(str(src), BOSS, kd.name):
            return f"({src}) and {logic_name(BOSS, kd.name)}"
    return str(src)


def start_keys(data_dir: Path) -> dict[str, int]:
    """{game dungeon: small keys owned from the start} (keys.json start_keys), whatever the key settings."""
    with (data_dir / "keys.json").open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {body["game"]: int(body["start_keys"]) for body in raw["dungeons"].values() if body.get("start_keys")}


def door_flags(data_dir: Path) -> dict[str, bool]:
    """{saved Bool: True} of the doors unlocked from the start (keys.json unlocked_doors), whatever the key settings."""
    with (data_dir / "keys.json").open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {door["flag"]: True for body in raw["dungeons"].values() for door in body.get("unlocked_doors", [])}


def mentions(rule: str, kind: str, dungeon: str) -> bool:
    """Does the rule ask for this dungeon's keys itself (e.g. has(Small_Key_Forest_Temple, 2))?"""
    name = logic_name(kind, dungeon)
    return any(_term_kind(m) == kind and f"{(m.group(1) or m.group(3))}_Key_{m.group(2) or m.group(4)}" == name
               for m in KEY_TERM.finditer(str(rule)))


def chest_change(item: str, location_game: str | None) -> dict[str, Any] | None:
    """Chest fields for a key item, or None if the item is not a key. location_game = game dungeon of the chest."""
    key = parse_item(item)
    if key is None:
        return None
    kind, game = key
    if location_game == game:
        return {"Drop__DropActor": GAME_ITEM[kind]}
    return {"Drop__DropActor": FOREIGN_ACTOR, "GetEventName": event_name(kind, game)}


def foreign_events(chests: list[dict]) -> dict[str, tuple[str, str]]:
    """{chest event: (kind, game)} for the keys given outside their dungeon (patch["chests"] entries)."""
    out: dict[str, tuple[str, str]] = {}
    for chest in chests:
        if chest["item"] == chest["vanilla"]:
            continue
        key = parse_item(chest["item"])
        if key and chest.get("key_dungeon") != key[1]:
            out[event_name(*key)] = key
    return dict(sorted(out.items()))


def rsdb_rows(events: dict[str, tuple[str, str]]) -> dict[str, dict[str, dict]]:
    """New RSDB rows of these chest events: copies of the boss key chest event, script changed."""
    if not events:
        return {}
    setting, analyzed = {}, {}
    for event, (kind, game) in events.items():
        setting[event] = {"__new": True, "__copy_from": TEMPLATE_EVENT,
                          "FlowchartFileName": f"Work/Event/EventFlow/{flow_name(kind, game)}.evfc"}
        analyzed[event] = {"__new": True, "__copy_from": TEMPLATE_EVENT}
    return {"EventSetting": setting, "GameAnalyzedEventInfo": analyzed}
