"""Giving a received multiworld item (Longshot bridge, `ootrr.tools.mw_longshot`).

Longshot cannot call game code directly. Most received items are written through the game's GameData write queues
(`longshot_control.Longshot.set_int` / `set_bool`, saved like the game's own writes); Gauntlets and ocarinas instead
use a game-side EventFlow dispatcher to call the native pouch-add action:

- `IsGet.<pouch name>` = true and `PouchData.<pouch name>.StockNum` (1, or +1 for bottles and tokens). Seen in
  game (Longshot, 2026-11-17): a Hookshot given this way is shown, equipped, fires and is saved.
- The adjustments of the native module (`ingame::AdjustItem`): progressive chains (the step after the highest one
  owned, read from `IsGet.*`), ocarinas (Fairy, then Time), bombs and bombchus without a bomb bag -> 5 rupees.
- What the game does on its own when it adds an item, as seen in the GameData changes of a chest giving the
  Medium Bomb Bag (2026-11-17): the bag's ammunition is filled (`PouchData.Item_Bomb.StockNum` = 30).
- Rupees: `PlayerStatus.CurrentRupee` + value, up to the wallet's limit. Strength: `PlayerStatus.LiftGrade`. Magic:
  `PlayerStatus.MPMax` / `MP`. Heart Container: `PlayerStatus.MaxLife` + 4 quarters and full life
  (as `ingame::AddMaxLife`). Piece of Heart: the pieces counter, a container every 4 [hypothesis].

Validated in game (Longshot, 2026-11-20, kept after save + reload): Hookshot, progressive bomb bag + bombs, Bow +
quiver + arrows, rupees. **Heart Containers do not work**: the game rewrites PlayerStatus.MaxLife from Link's data
every frame (the sound plays, the heart goes away). Pieces of Heart, bottles, seeds, songs, swords, shields and
magic: written from the files and the native module, **to validate in game** (the giver logs every write). No
get-item window: the bridge prints the item. Magic jars (a refill) give nothing.

Bottles have no StockNum. The game's own pouch function (decompiled, main 0x110d570) takes the first of the five
slots `PlayerStatus.AssignableItem.BottleInfo.Bottle<A-E>` whose `IsValid` is false, sets it and writes the content
in its Enum `BottleItem`; `_bottle` does the same.

`gd` is any object with get_int / get_bool / set_int(name, value, add=False) / set_bool / set_enum(name, raw value)
(a `Longshot`, or a fake in the tests).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Protocol

DATA = Path(__file__).parent / "data" / "items.json"

RUPEES = {"Green": 1, "Blue": 5, "Red": 20, "Purple": 50, "Gold": 200}
BOMB_RUPEES = 5  # bombs without a bag: the native module gives 5 rupees (the game would give the bag)
# ammunition held in the bomb bag: bombchus too (RSDB PouchActorInfo Item_Bombchu: SmallBagActor Item_BombBag_Small,
# MaxNumGameData Bomb, as Item_Bomb). Without a bag their maximum is 0, but a written StockNum showed 5 bombchus in
# the menu (multiworld, 2026-11-25)
BAG_AMMO = ("Item_Bomb", "Item_Bombchu")

# flags meaning "this chain step is owned" (native kChains; the bow and slingshot have no IsGet.Item_Range_* flag)
STEP_FLAGS = {
    "Item_Range_Bow": ("IsGet.Weapon_Range_Bow", "IsGet.Item_Quiver_Small"),
    "Item_Range_SlingShot": ("IsGet.Weapon_Range_SlingShot", "IsGet.Item_BulletBag_Small"),
    "Item_Gauntlet_Goron": ("IsGet.Armor_Child_Gauntlet_Goron",),
    "Item_Gauntlet_Silver": ("IsGet.Armor_Adult_Gauntlet_Silver",),
    "Item_Gauntlet_Gold": ("IsGet.Armor_Adult_Gauntlet_Gold",),
}
# pouch names of chain steps that differ from the item (items.json progressive_pouch gives the others)
POUCH_NAMES = {"Item_Gauntlet_Silver": "Armor_Adult_Gauntlet_Silver", "Item_Gauntlet_Gold": "Armor_Adult_Gauntlet_Gold",
               "Obj_Token_Gold": "Item_Token_Gold"}
# bag -> (ammunition, capacity): filled when the bag is given (seen for Item_BombBag_Medium -> 30 bombs)
BAGS = {
    "Item_BombBag_Small": ("Item_Bomb", 20), "Item_BombBag_Medium": ("Item_Bomb", 30),
    "Item_BombBag_Large": ("Item_Bomb", 40),
    "Item_Range_Bow": ("Item_Arrow_Normal", 30), "Item_Quiver_Medium": ("Item_Arrow_Normal", 40),
    "Item_Quiver_Large": ("Item_Arrow_Normal", 50),
    # capacities: PouchActorInfo AfterExpansionMaxNum (IsItemStockMaxIfGet: the game fills them too)
    "Item_Range_SlingShot": ("Item_DekuSeed", 30), "Item_BulletBag_Medium": ("Item_DekuSeed", 40),
    "Item_BulletBag_Large": ("Item_DekuSeed", 50),
    "Item_NutBag_Medium": ("Item_DekuNut", 30), "Item_NutBag_Large": ("Item_DekuNut", 40),
    "Item_StickBag_Medium": ("Item_DekuStick", 20), "Item_StickBag_Large": ("Item_DekuStick", 30),
}
# extra items that come with a step (the bow comes with its small quiver; memory: a bow without one is unusable)
WITH = {"Item_Range_Bow": ("Item_Quiver_Small",), "Item_Range_SlingShot": ("Item_BulletBag_Small",)}
# ammunition bundles -> (ammunition, amount)
BUNDLES = {  # counts from the game's names ("Three Deku Nuts", "Five Arrows", "10 Arrows"...)
    "Item_BombBundle_Small": ("Item_Bomb", 5), "Item_BombchuBundle_Small": ("Item_Bombchu", 5),
    "TBox_ArrowBundle_Medium": ("Item_Arrow_Normal", 5), "TBox_ArrowBundle_Large": ("Item_Arrow_Normal", 10),
    "TBox_DekuNutBundle": ("Item_DekuNut", 3), "Item_DekuStickBundle_Small": ("Item_DekuStick", 3),
}
COUNTED = ("Item_Token_Gold",)  # several copies: the count grows
# bottle -> content (raw value of the Enum BottleItem; RSDB PouchActorInfo.BottleItem)
BOTTLES = {"Item_Bottle": "Empty", "Item_Bottle_Milk": "MaxMilk", "Item_Bottle_Letter": "Letter"}
BOTTLE_SLOTS = tuple(f"PlayerStatus.AssignableItem.BottleInfo.Bottle{s}" for s in "ABCDE")
# flag set with an item by the game's get scene, which does not run here: the quest reads it
# (Get_StoneOfWater:StoneOfWater_GetRutoletter; reading the letter then moves the quest on, StoneOfWater_UseRutoletter)
QUEST_FLAGS = {"Item_Bottle_Letter": "Get_StoneOfWater_GetRutoLetter"}
# This anonymous Enum is the Get_StoneOfWater challenge state. The bottle's quest Bool alone does not advance it;
# the original pickup event also moves the challenge to Step05_01 so King Zora and Jabu-Jabu use the right state.
LETTER_QUEST_ENUM = "#1539965606"
LETTER_QUEST_STEP = "Step05_01"
LETTER_READ_FLAG = "Get_StoneOfWater_ReadRutoLetter"
JABU_FED_FLAG = "GaveFishToJabJab"
# what the game computes when it adds an item, and keeps as its own value (PlayerStatus, found in the files):
# strength, read to lift things (received bracelet that lifted nothing, 2026-11-24) and magic (MPMax 24 / 48 in
# PouchActorInfo, x10 in PlayerStatus: 240 in a save with the single magic)
LIFT_GRADE, MP_MAX, MP = "PlayerStatus.LiftGrade", "PlayerStatus.MPMax", "PlayerStatus.MP"
LIFT_GRADES = {"Item_Gauntlet_Goron": "Low", "Item_Gauntlet_Silver": "Middle", "Item_Gauntlet_Gold": "High"}
POUCH_ACTION_ITEMS = ("Item_Gauntlet_Goron", "Item_Gauntlet_Silver", "Item_Gauntlet_Gold",
                      "Item_Ocarina_Fairy", "Item_Ocarina_Time")
POUCH_ACTION_CODES = {item: code for code, item in enumerate(POUCH_ACTION_ITEMS, 1)}
POUCH_ACTION_REQUEST = "OoTRR.MW.PouchActionRequest"
POUCH_ACTION_ACK = "OoTRR.MW.PouchActionAck"
MAGIC = {"Item_FairyBless_MP": 240, "Item_FairyBless_MPDouble": 480}
MAGIC.update(dict.fromkeys(("Item_DinFire", "Item_FaroreWind", "Item_NayruLove", "Item_GlassTruth", "Item_Arrow_Fire",
                            "Item_Arrow_Ice", "Item_Arrow_Light"), 240))  # they bring the first magic too
DOUBLE_DEFENSE = "#1455153276"  # unnamed PlayerStatus Bool set by PouchAdd for the special deal of the double defense
# rupees: the wallet's limit (PouchActorInfo AfterExpansionMaxNum); beyond it the counter showed more than the maximum
WALLETS = (("Item_Wallet_Large", 1000), ("Item_Wallet_Medium", 500))
WALLET_SMALL = 200
APPLY_TRIES = 20  # reads of a queued write before giving up on seeing it applied
MAX_LIFE, LIFE, RUPEE = "PlayerStatus.MaxLife", "PlayerStatus.Life", "PlayerStatus.CurrentRupee"
HEART_PIECES = "PouchData.Obj_Heart_Piece.StockNum"


class GameData(Protocol):
    def get_int(self, name: str) -> int | None: ...
    def get_bool(self, name: str) -> bool | None: ...
    def set_int(self, name: str, value: int, add: bool = False) -> None: ...
    def set_bool(self, name: str, value: bool) -> None: ...
    def set_enum(self, name: str, value: str) -> None: ...


def _stock(name: str) -> str:
    return f"PouchData.{name}.StockNum"


class ItemGiver:
    def __init__(self, gd: GameData, data_path: Path = DATA, fixed: Iterable[str] = ()) -> None:
        """fixed: first steps of the chains given as placed (`multiworld.fixed_chains`)."""
        self.gd = gd
        self.fixed = set(fixed)
        data = json.loads(data_path.read_text(encoding="utf-8"))
        self.chains: list[list[str]] = data["progressive"]
        self.kept = set(data.get("progressive_kept", ()))
        self.pouch = dict(data.get("progressive_pouch", {}))
        self.pouch.update(POUCH_NAMES)
        self.log: list[str] = []

    # ---- reading ----
    def _owns_step(self, step: str) -> bool:
        flags = STEP_FLAGS.get(step, (f"IsGet.{self.pouch.get(step, step)}",))
        return any(self.gd.get_bool(f) for f in flags)

    def adjusted(self, item: str) -> str:
        """The item really given (progressive chains, ocarinas), as `ingame::AdjustItem`."""
        if item in ("Item_Ocarina_Fairy", "Item_Ocarina_Time"):
            owned = self.gd.get_bool("IsGet.Item_Ocarina_Fairy") or self.gd.get_bool("IsGet.Item_Ocarina_Time")
            return "Item_Ocarina_Time" if owned else "Item_Ocarina_Fairy"
        for chain in self.chains:
            if item in chain:
                owned = 0
                for i, step in enumerate(chain):
                    if self._owns_step(step):
                        owned = i + 1
                if chain[0] in self.fixed:  # as placed, never below what Link owns
                    return chain[max(chain.index(item), owned - 1)]
                if chain[0] in self.kept and not self._owns_step(chain[0]):
                    return chain[0]  # a quiver taken on the ground is no bow
                return chain[min(owned, len(chain) - 1)]
        return item

    # ---- writing ----
    def _int(self, name: str, value: int, add: bool = False) -> None:
        """Always an absolute write (`add`: current + value, read once): a write repeated by the bridge stays
        right."""
        if add:
            value += self.gd.get_int(name) or 0
        self.gd.set_int(name, value)
        self.log.append(f"{name} = {value}")

    def _bool(self, name: str) -> None:
        self.gd.set_bool(name, True)
        self.log.append(f"{name} = true")

    def _rupees(self, value: int) -> None:
        limit = next((n for wallet, n in WALLETS if self.gd.get_bool(f"IsGet.{wallet}")), WALLET_SMALL)
        current = self.gd.get_int(RUPEE) or 0
        self._int(RUPEE, max(current, min(current + value, limit)))

    def _status(self, item: str) -> None:
        """The values the game derives from an item it adds itself (strength, magic, defense)."""
        grade = LIFT_GRADES.get(item)
        if grade:
            self.gd.set_enum(LIFT_GRADE, grade)
            self.log.append(f"{LIFT_GRADE} = {grade}")
        magic = MAGIC.get(item)
        if magic and (self.gd.get_int(MP_MAX) or 0) < magic:
            self._int(MP_MAX, magic)
            self._int(MP, magic)
        if item == "Item_FairyBless_DefenseDouble" and self.gd.get_bool(DOUBLE_DEFENSE) is False:
            self._bool(DOUBLE_DEFENSE)

    def _ammo_flag(self, ammo: str) -> None:
        """The ammunition's own IsGet flag: without IsGet.Item_Bomb the menu shows no bombs, whatever their count
        (Longshot, 2026-11-20: 20 bombs written with the bag stayed invisible until the flag was set; a real bomb bag
        chest sets it too)."""
        if self.gd.get_bool(f"IsGet.{ammo}") is False:
            self._bool(f"IsGet.{ammo}")

    def _pouch_item(self, name: str) -> bool:
        """IsGet + StockNum of a pouch item; False if the game has no counter of that name."""
        current = self.gd.get_int(_stock(name))
        if current is None:
            return False
        if self.gd.get_bool(f"IsGet.{name}") is not None:
            self._bool(f"IsGet.{name}")
        if name in COUNTED:
            self._int(_stock(name), 1, add=True)
        elif current < 1:
            self._int(_stock(name), 1)
        return True

    def _bottle(self, item: str) -> None:
        slot = next((s for s in BOTTLE_SLOTS if self.gd.get_bool(f"{s}.IsValid") is False), None)
        if slot is None:
            self.log.append(f"{item}: no free bottle slot, nothing given")
            return
        if BOTTLES[item] != "Empty":  # a free slot is already Empty; content first: never a full bottle seen empty
            self.gd.set_enum(f"{slot}.BottleItem", BOTTLES[item])
            self.log.append(f"{slot}.BottleItem = {BOTTLES[item]}")
        self._bool(f"{slot}.IsValid")
        # queued write: wait until it is applied, or a second bottle given right after would take the same slot
        for _ in range(APPLY_TRIES):
            if self.gd.get_bool(f"{slot}.IsValid"):
                break
        for flag in (f"IsGet.{item}", QUEST_FLAGS.get(item)):
            if flag and self.gd.get_bool(flag) is not None:
                self._bool(flag)
        if item == "Item_Bottle_Letter":
            if (self.gd.get_bool(LETTER_READ_FLAG) is False
                    and self.gd.get_bool(JABU_FED_FLAG) is False):
                self.gd.set_enum(LETTER_QUEST_ENUM, LETTER_QUEST_STEP)
                self.log.append(f"{LETTER_QUEST_ENUM} = {LETTER_QUEST_STEP}")

    def give(self, item: str, defer_pouch_action: bool = False) -> list[str]:
        """Writes `item`, or leaves a selected pouch action to the game-side dispatcher; returns the log."""
        self.log = []
        rest = item.removeprefix("Obj_Rupee_").removeprefix("TBox_Rupee_")
        if rest != item and rest in RUPEES:
            self._rupees(RUPEES[rest])
            return self.log
        if item == "Obj_Heart_Container":
            life = (self.gd.get_int(MAX_LIFE) or 0) + 4
            self._int(MAX_LIFE, life)
            self._int(LIFE, life)
            return self.log
        if item == "Obj_Heart_Piece":
            pieces = (self.gd.get_int(HEART_PIECES) or 0) + 1
            if pieces >= 4:  # [hypothesis] four pieces make a container
                life = (self.gd.get_int(MAX_LIFE) or 0) + 4
                self._int(MAX_LIFE, life)
                self._int(LIFE, life)
                pieces -= 4
            self._int(HEART_PIECES, pieces)
            return self.log
        if item in BUNDLES:
            ammo, amount = BUNDLES[item]
            if ammo in BAG_AMMO and not any(self.gd.get_bool(f"IsGet.{b}") for b in
                                               ("Item_BombBag_Small", "Item_BombBag_Medium", "Item_BombBag_Large")):
                self._rupees(BOMB_RUPEES)
                return self.log
            if self.gd.get_int(_stock(ammo)) is not None:
                self._int(_stock(ammo), amount, add=True)
                self._ammo_flag(ammo)
            else:
                self.log.append(f"{item}: no counter {_stock(ammo)}, nothing given")
            return self.log
        if item in BOTTLES:
            self._bottle(item)
            return self.log
        if item.startswith("Item_Melody_"):  # songs have no counter: the game reads IsGet only
            if self.gd.get_bool(f"IsGet.{item}") is None:
                self.log.append(f"{item}: no flag IsGet.{item}, nothing given")
            else:
                self._bool(f"IsGet.{item}")
            return self.log
        real = self.adjusted(item)
        if real != item:
            self.log.append(f"{item} -> {real}")
        if defer_pouch_action and real in POUCH_ACTION_CODES:
            self.log.append(f"{real}: waiting for the game's pouch action")
            return self.log
        name = self.pouch.get(real, real)
        # the pouch name may be another actor's: Weapon_Range_Bow, Armor_GlassTruth (Lens of Truth: given as nothing
        # without this one, 2026-11-21), Armor_Adult_Gauntlet_Silver...
        # (TBox_Shield_Deku: Weapon_Shield_Deku, given as nothing without it, 2026-11-24)
        candidates = [name, real, real.replace("TBox_", "Item_", 1), real.replace("TBox_", "Weapon_", 1), real.replace("Item_", "Weapon_", 1),
                      real.replace("Item_", "Armor_", 1), real.replace("Item_", "Armor_Adult_", 1),
                      real.replace("Item_", "Armor_Child_", 1)]
        if not any(self._pouch_item(n) for n in dict.fromkeys(candidates)):
            self.log.append(f"{real}: no pouch counter found ({', '.join(dict.fromkeys(candidates))}), nothing given")
            return self.log
        self._status(real)
        for extra in WITH.get(real, ()):
            if not self._owns_step(extra):
                self._pouch_item(extra)
        if real in BAGS:
            ammo, capacity = BAGS[real]
            current = self.gd.get_int(_stock(ammo))
            if current is not None:
                self._int(_stock(ammo), max(current, capacity))
                self._ammo_flag(ammo)
        return self.log
