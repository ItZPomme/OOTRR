"""Dungeon small keys and boss keys (settings small_keys and boss_keys, data in data/keys.json).

How the game handles keys (read in the files, see docs/GAME_KNOWLEDGE.md "Dungeon keys"):

- each dungeon has saved GameData members `DungeonInfo.<game>.SmallKeyNum` (Int) and `.IsGetBossKey` (Bool);
- a chest gives a key with `Dm_SY_Treasurebox` (`EventGetDungeonSmallKey` / `EventGetDungeonBossKey`, no
  dungeon parameter): the key goes to the dungeon of the current map. A key of dungeon A found elsewhere is
  therefore given as `Obj_MiniGame_SmallKey` (the Treasure Chest Shop's "door key", not put in the pouch) and the
  chest's `GetEventName` runs a copy of the boss key chest event (`ForesetTemple_GetBossKey`: opening sequence,
  then Navi's line) where Navi's line is replaced by "DungeonInfo.A.SmallKeyNum + 1" or "IsGetBossKey = true".

The logic is prudent (the repository has no door layout): see `World` (`_key_rule`) and fill.py.
"""

from __future__ import annotations

import json
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

    @property
    def key_rooms(self) -> dict[int, int]:
        """{room: number of small key chests} (own_dungeon keeps these counts)."""
        out: dict[int, int] = {}
        for k in self.small:
            out[k["room"]] = out.get(k["room"], 0) + 1
        return out

    def small_location(self, i: int) -> str:
        return f"{self.name} Small Key Chest {i + 1}"

    @property
    def boss_location(self) -> str:
        return f"{self.name} Boss Key Chest"


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
            name=name, game=body["game"], regions=list(body["regions"]), region=body["region"], rule=body["rule"],
            small=list(body["small"]), freestanding=list(body.get("freestanding", [])),
            boss_key=body.get("boss_key"), boss=list(body.get("boss", [])),
            boss_events=list(body.get("boss_events", [])), events=dict(body.get("events", {})))
    return out


def load_rooms(data_dir: Path) -> dict[str, int]:
    with (data_dir / "keys.json").open(encoding="utf-8") as fh:
        return dict(json.load(fh)["rooms"])


def conjuncts(rule: str) -> set[str]:
    return {part.strip() for part in str(rule).split(" and ") if part.strip()}


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
