"""Giving a received multiworld item by GameData writes (Longshot bridge, `ootrr.tools.mw_longshot`).

In Longshot no code of ours runs in the game, so a received item cannot go through the game's own "add to pouch"
(the native module's `PouchAdd`). The bridge writes what that would have changed, through the game's GameData write
queues (`longshot_control.Longshot.set_int` / `set_bool`, saved like the game's own writes):

- `IsGet.<pouch name>` = true and `PouchData.<pouch name>.StockNum` (1, or +1 for bottles and tokens). Seen in
  game (Longshot, 2026-11-17): a Hookshot given this way is shown, equipped, fires and is saved.
- The adjustments of the native module (`ingame::AdjustItem`): progressive chains (the step after the highest one
  owned, read from `IsGet.*`), ocarinas (Fairy, then Time), bombs without a bomb bag -> 5 rupees.
- What the game does on its own when it adds an item, as seen in the GameData changes of a chest giving the
  Medium Bomb Bag (2026-11-17): the bag's ammunition is filled (`PouchData.Item_Bomb.StockNum` = 30).
- Rupees: `PlayerStatus.CurrentRupee` + value. Heart Container: `PlayerStatus.MaxLife` + 4 quarters and full life
  (as `ingame::AddMaxLife`). Piece of Heart: the pieces counter, a container every 4 [hypothesis].

Validated in game (Longshot, 2026-11-20, kept after save + reload): Hookshot, progressive bomb bag + bombs, Bow +
quiver + arrows, rupees. **Heart Containers do not work**: the game rewrites PlayerStatus.MaxLife from Link's data
every frame (the sound plays, the heart goes away). Pieces of Heart, bottles (no PouchData.Item_Bottle.StockNum),
seeds, songs, swords, shields and magic: written from the files and the native module, **to validate in game**
(the giver logs every write). No get-item window: the bridge prints the item.

`gd` is any object with get_int / get_bool / set_int(name, value, add=False) / set_bool (a `Longshot`, or a fake
in the tests).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

DATA = Path(__file__).parent / "data" / "items.json"

RUPEES = {"Green": 1, "Blue": 5, "Red": 20, "Purple": 50, "Gold": 200}
BOMB_RUPEES = 5  # bombs without a bag: the native module gives 5 rupees (the game would give the bag)

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
}
# extra items that come with a step (the bow comes with its small quiver; memory: a bow without one is unusable)
WITH = {"Item_Range_Bow": ("Item_Quiver_Small",), "Item_Range_SlingShot": ("Item_BulletBag_Small",)}
# ammunition bundles -> (ammunition, amount)
BUNDLES = {  # counts from the game's names ("Three Deku Nuts", "Five Arrows", "10 Arrows"...)
    "Item_BombBundle_Small": ("Item_Bomb", 5), "Item_BombchuBundle_Small": ("Item_Bombchu", 5),
    "TBox_ArrowBundle_Medium": ("Item_Arrow_Normal", 5), "TBox_ArrowBundle_Large": ("Item_Arrow_Normal", 10),
    "TBox_DekuNutBundle": ("Item_DekuNut", 3), "Item_DekuStickBundle_Small": ("Item_DekuStick", 3),
}
COUNTED = ("Item_Bottle", "Item_Token_Gold")  # several copies: the count grows
MAX_LIFE, LIFE, RUPEE = "PlayerStatus.MaxLife", "PlayerStatus.Life", "PlayerStatus.CurrentRupee"
HEART_PIECES = "PouchData.Obj_Heart_Piece.StockNum"


class GameData(Protocol):
    def get_int(self, name: str) -> int | None: ...
    def get_bool(self, name: str) -> bool | None: ...
    def set_int(self, name: str, value: int, add: bool = False) -> None: ...
    def set_bool(self, name: str, value: bool) -> None: ...


def _stock(name: str) -> str:
    return f"PouchData.{name}.StockNum"


class ItemGiver:
    def __init__(self, gd: GameData, data_path: Path = DATA) -> None:
        self.gd = gd
        data = json.loads(data_path.read_text(encoding="utf-8"))
        self.chains: list[list[str]] = data["progressive"]
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

    def give(self, item: str) -> list[str]:
        """Writes `item` into the game; returns the writes (also kept in `log`)."""
        self.log = []
        rest = item.removeprefix("Obj_Rupee_").removeprefix("TBox_Rupee_")
        if rest != item and rest in RUPEES:
            self._int(RUPEE, RUPEES[rest], add=True)
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
            if ammo == "Item_Bomb" and not any(self.gd.get_bool(f"IsGet.{b}") for b in
                                               ("Item_BombBag_Small", "Item_BombBag_Medium", "Item_BombBag_Large")):
                self._int(RUPEE, BOMB_RUPEES, add=True)
                return self.log
            if self.gd.get_int(_stock(ammo)) is not None:
                self._int(_stock(ammo), amount, add=True)
                self._ammo_flag(ammo)
            else:
                self.log.append(f"{item}: no counter {_stock(ammo)}, nothing given")
            return self.log
        real = self.adjusted(item)
        if real != item:
            self.log.append(f"{item} -> {real}")
        name = self.pouch.get(real, real)
        # the pouch name may be another actor's: Weapon_Range_Bow, Armor_GlassTruth (Lens of Truth: given as nothing
        # without this one, 2026-11-21), Armor_Adult_Gauntlet_Silver...
        candidates = [name, real, real.replace("TBox_", "Item_", 1), real.replace("Item_", "Weapon_", 1),
                      real.replace("Item_", "Armor_", 1), real.replace("Item_", "Armor_Adult_", 1),
                      real.replace("Item_", "Armor_Child_", 1)]
        if not any(self._pouch_item(n) for n in dict.fromkeys(candidates)):
            self.log.append(f"{real}: no pouch counter found ({', '.join(dict.fromkeys(candidates))}), nothing given")
            return self.log
        for extra in WITH.get(real, ()):
            self._pouch_item(extra)
        if real in BAGS:
            ammo, capacity = BAGS[real]
            if self.gd.get_int(_stock(ammo)) is not None:
                self._int(_stock(ammo), capacity)
                self._ammo_flag(ammo)
        return self.log
