"""Settings as the desktop app shows them: pages, titles, captions and value labels.

One table for both front-ends: titles, captions and value labels come from the in-game menu texts
(`ingame_menu.TEXTS_EN`), so a setting reads the same in the app and in the native menu. This module only adds
the app's page layout, the texts of the settings the native menu has no row for, and which settings a PC-built mod
cannot apply (`NATIVE_ONLY`). `tests/test_settings_ui.py` checks that every setting has exactly one place here.
"""

from __future__ import annotations

from typing import Any

from . import ingame_menu
from . import settings as settings_mod

# (page title, settings shown on that page, in order); at most 8 rows per page
PAGES: list[tuple[str, list[str]]] = [
    ("World", ["starting_age", "open_forest", "open_door_of_time", "free_time_travel",
               "bridge", "bridge_count", "skip_trials", "gerudo_fortress"]),
    ("Shuffle", ["shuffle_rewards", "shuffle_songs", "shuffle_ocarinas", "shuffle_scrubs", "scrub_prices",
                 "shuffle_skulltulas", "adult_trade_sequence", "gerudo_card"]),
    ("Dungeons", ["maps_compasses", "small_keys", "boss_keys", "key_locations", "ganon_boss_key",
                  "ganon_boss_key_count", "skip_tower_collapse"]),
    ("Comfort", ["skip_cutscenes", "skip_child_zelda", "start_with_consumables", "cucco_count", "big_poe_count",
                 "complete_mask_quest", "fast_bunny_hood", "blue_fire_arrows"]),
    ("Logic", ["logic", "logic_lens_required", "accessibility"]),
]
MAX_ROWS = 8

# settings that only the native module can apply (the generator refuses them for a PC-built mod): not shown
NATIVE_ONLY: dict[str, str] = {
    "shuffle_shops": "shops are applied by the native module in game (token items and the PouchAdd hook)",
    "shop_prices": "only used with shuffle_shops",
}
# settings the app does not show: they always keep the generator's default
HIDDEN: dict[str, str] = {
    "shuffle_gifts": "always on (gifts are always in the item pool)",
    "shuffle_hearts": "always all (Pieces of Heart and Heart Containers are always in the item pool)",
    "open_kakariko": "not supported by the patcher (settings.GAME_LOCKED)",
    "spawn_point": "internal, set by the adult start",
}

# texts of the settings without a row in the native menu, in the menu's format (title, caption, {value: label})
APP_TEXTS: dict[str, tuple[str, str, dict[str, str]]] = {
    "bridge_count": ("Bridge Count", "Number of stones, medallions, rewards or hearts needed to open the rainbow "
                     "bridge.", {}),
    # PC-only: the PC-built mod patches the count in the game files; the native menu has no row (its mod is
    # built once, so the counts would need a runtime hook) and always plays the vanilla counts
    "cucco_count": ("Anju's Cuccos", "Number of cuccos Anju needs in her pen before she gives her reward. "
                    "Original game: 7.", {}),
    "big_poe_count": ("Big Poes", "Number of Big Poes the Poe buyer in the adult market needs before he gives "
                      "his reward. Original game: 5 (500 points).", {}),
    # PC-only: a start flag (quest Enum at Complete), which the native menu's mod (built once) does not set
    "complete_mask_quest": ("Mask Quest Done", "The Happy Mask Shop quest is completed from the start: nothing "
                            "to sell or pay, the shop lends every mask, Mask of Truth included.", {}),
    # PC-only: nodes added to Link's walk module (the native menu's mod is built once and has no row)
    "fast_bunny_hood": ("Fast Bunny Hood", "As in Majora's Mask: Link runs 1.5 times faster while he wears the "
                        "Bunny Hood.", {}),
    # PC-only: nodes added to the arrow and red ice AIs (the native menu's mod is built once and has no row)
    "blue_fire_arrows": ("Blue Fire Arrows", "Ice Arrows act as Blue Fire: shoot one at red ice to melt it (Ice "
                         "Cavern, King Zora). The logic accepts them instead of a bottle.", {}),
    # PC-only: key chests, start counters and chest events in the game files (the native menu's mod is built
    # once and its generator has no key logic)
    "small_keys": ("Small Keys", "Vanilla: in their chests. Own Dungeon: shuffled in their dungeon (a key only "
                   "moves to a chest of the same room). Any Dungeon: in any dungeon. Removed: none in the chests, "
                   "every dungeon starts with all its keys. Random: anywhere.", {}),
    "boss_keys": ("Boss Keys", "Vanilla: in their chest. Own Dungeon: anywhere in their dungeon. Any Dungeon: in "
                  "any dungeon. Removed: owned from the start. Random: anywhere, Ganon's Castle included.", {}),
    # PC-only: ground items given as dungeon keys (see small_keys)
    "key_locations": ("Key Locations", "Chests: shuffled small keys only go to chests. Ground: also to ground "
                      "items (Heart Containers, Pieces of Heart, Gold Skulltula drops) inside their own dungeon; "
                      "vanilla ground-key spots become checks too. "
                      "Boss keys stay in chests.", {"chests": "Chests", "ground": "Chests + Ground"}),
    # PC-only: the native menu's generator always shuffles the card with the gifts (no row)
    "gerudo_card": ("Gerudo Card", "Random: the Gerudo Membership Card is in the item pool and the Gerudo who gives "
                    "it gives a seed item. Vanilla: she gives the card, as in the original game.",
                    {"random": "Random", "vanilla": "Vanilla"}),
    # PC-only: start flags (the native menu's mod is built once and has no row)
    "gerudo_fortress": ("Carpenters", "Gerudo Fortress. Normal: free the 4 carpenters to get the Gerudo Membership "
                        "Card check. Fast: the first carpenter you free is enough.",
                        {"normal": "Normal", "fast": "Fast"}),
    # PC-only: a logic module of Ganon's Castle and its key chest (the native menu's mod is built once)
    "ganon_boss_key": ("Ganon's Boss Key", "Same as Boss Keys, or on its own. Vanilla: in its chest. Removed: owned "
                       "from the start. Random: anywhere. Stones, Medallions, Dungeons, Hearts: given in the main room "
                       "of Ganon's Castle once you own enough of them.", {"boss_keys": "Same"}),
    "ganon_boss_key_count": ("Boss Key Count", "Number of stones, medallions, rewards or hearts that give Ganon's "
                             "Castle boss key.", {}),
    # PC-only: start flags (the native menu's mod is built once and has no row)
    "skip_trials": ("Skip Trials", "Ganon's Castle: the six trials are completed from the start, the barrier around "
                    "the tower is down. The trial rooms can still be visited for their chests.", {}),
    # PC-only: a script of the mod (the native menu's mod is built once and has no row)
    "skip_tower_collapse": ("Skip Tower Collapse", "No escape from the collapsing tower: after Ganondorf, Link goes "
                            "straight to Ganon's arena. No pots to refill between the two fights.", {}),
    "accessibility": ("Accessibility", "All: every location can be reached. Beatable: only Ganon has to be "
                      "reachable, some items may be locked away.", {"all": "All", "beatable": "Beatable"}),
}
# app-only labels where the menu's are too long for the app's value cell
VALUE_OVERRIDES: dict[str, dict[str, str]] = {
    "maps_compasses": {"shuffle": "Shuffle"},
    "open_forest": {"ask": "Ask"},
}

SHOWN = [name for _, names in PAGES for name in names]
BRIDGE_MAX = settings_mod.COUNT_LIMITS  # highest count per condition (bridge and ganon_boss_key)
CONDITION_OF = {count: name for name, count in settings_mod.COUNT_SETTINGS.items()}


def int_range(name: str, values: dict[str, Any]) -> tuple[int, int]:
    """(lowest, highest) value the app offers for an integer setting."""
    if name in CONDITION_OF:
        return 1, BRIDGE_MAX.get(values[CONDITION_OF[name]], 9)
    return settings_mod.INT_RANGES[name]


def enabled(name: str, values: dict[str, Any]) -> bool:
    """False when the setting has no effect with the other values (row greyed out)."""
    if name in CONDITION_OF:
        return values[CONDITION_OF[name]] in BRIDGE_MAX
    if name == "scrub_prices":
        return bool(values["shuffle_scrubs"])
    return True


def _texts(name: str) -> tuple[str, str, dict[str, str]]:
    if name in APP_TEXTS:
        return APP_TEXTS[name]
    return ingame_menu.TEXTS_EN[name]


def title(name: str) -> str:
    return _texts(name)[0]


def caption(name: str) -> str:
    """One-paragraph description (the menu's line breaks are for its narrow text box)."""
    return " ".join(_texts(name)[1].replace("\n", " ").split())


def choices(name: str) -> list[Any]:
    """Values offered by the app, in order."""
    _, allowed, _ = settings_mod.SETTINGS[name]
    if allowed is bool:
        return [True, False]
    if allowed is int:
        raise ValueError(f"{name}: integer setting, no fixed list")
    return list(allowed)


def value_label(name: str, value: Any) -> str:
    if value is True:
        return "On"
    if value is False:
        return "Off"
    text = VALUE_OVERRIDES.get(name, {}).get(str(value)) or _texts(name)[2].get(str(value))
    return text or str(value).replace("_", " ").title()
