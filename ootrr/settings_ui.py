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
               "bridge", "bridge_count"]),
    ("Shuffle", ["shuffle_rewards", "shuffle_songs", "shuffle_ocarinas", "shuffle_scrubs", "scrub_prices",
                 "shuffle_skulltulas", "maps_compasses", "adult_trade_sequence"]),
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
    "accessibility": ("Accessibility", "All: every location can be reached. Beatable: only Ganon has to be "
                      "reachable, some items may be locked away.", {"all": "All", "beatable": "Beatable"}),
}
# app-only labels where the menu's are too long for the app's value cell
VALUE_OVERRIDES: dict[str, dict[str, str]] = {
    "maps_compasses": {"shuffle": "Shuffle"},
    "open_forest": {"ask": "Ask"},
}

SHOWN = [name for _, names in PAGES for name in names]
BRIDGE_MAX = {"stones": 3, "medallions": 6, "dungeons": 9, "hearts": 20}


def int_range(name: str, values: dict[str, Any]) -> tuple[int, int]:
    """(lowest, highest) value the app offers for an integer setting."""
    if name == "bridge_count":
        return 1, BRIDGE_MAX.get(values["bridge"], 9)
    return settings_mod.INT_RANGES[name]


def enabled(name: str, values: dict[str, Any]) -> bool:
    """False when the setting has no effect with the other values (row greyed out)."""
    if name == "bridge_count":
        return values["bridge"] in BRIDGE_MAX
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
