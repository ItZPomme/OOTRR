"""Multiworld log: who sent what to whom, with the items' names as the game writes them (docs/MULTIWORLD.md).

The server writes every exchange to its log and sends it to every game as an `INFO` line
(`Bot -> Pomme: Hookshot (GF Rupee Chest)`); each bridge writes those lines to its own log, plus a line when an
item has really been given in its game. Item names come from the game's texts (`ActorMsg/PouchContent`, label
`<actor>_Name`, read from a RomFS: the one given, else Longshot's own), else from the actor name
(`Item_Gauntlet_Silver` -> "Gauntlet Silver").
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Callable

# other actors that may carry the name of an item (pouch names of progressive steps, ground versions...)
_RELATED = (("TBox_", "Obj_"), ("TBox_", "Item_"), ("TBox_", "Weapon_"), ("Item_", "Weapon_"), ("Item_", "Armor_Adult_"),
            ("Item_", "Armor_Child_"), ("Item_", "Armor_"), ("Item_", "Obj_"))
_ALIASES = {"Goron_Tunic": "Armor_Adult_Goron", "Zora_Tunic": "Armor_Adult_Zora"}  # logic items, no real actor
_CODES = re.compile(r"\[\d+:\d+:[0-9a-fA-F]*\]")
_PREFIXES = ("Item_", "TBox_", "Obj_", "Weapon_", "Armor_Adult_", "Armor_Child_", "Armor_")


def plain_label(item: str) -> str:
    """Readable name without the game's texts: prefix removed, underscores as spaces."""
    name = item
    for prefix in _PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.replace("_", " ")


def game_item_names(romfs: Path | str | None, lang: str = "USen") -> dict[str, str]:
    """{actor: name} from the game's item texts; empty if the RomFS or the file is missing."""
    if not romfs:
        return {}
    try:
        from .formats.msbt import plain, read_labels, read_texts, unit
        from .formats.sarc import read_sarc
        from .formats.zs import ZsCodec

        romfs = Path(romfs)
        codec = ZsCodec(romfs)
        files = read_sarc(codec.decompress(next((romfs / "Mals").glob(f"{lang}.*.sarc.zs"))))
        d = files["ActorMsg/PouchContent.msbt"]
        labels, texts, u = read_labels(d), read_texts(d), unit(d)
        out = {}
        for label, i in labels.items():
            if label.endswith("_Name"):
                text = _CODES.sub("", plain(texts[i], u)).strip()
                if text:
                    out[label[:-len("_Name")]] = text
        return out
    except (OSError, StopIteration, KeyError, ValueError):
        return {}


def default_romfs() -> Path | None:
    """Longshot's own RomFS when Longshot is installed (the same texts as the update the mods are built from)."""
    try:
        from .tools.longshot_app import find_longshot
    except ImportError:
        return None
    found = find_longshot()
    return found / "romfs" if found and (found / "romfs").is_dir() else None


def labeller(romfs: Path | str | None = None, lang: str = "USen") -> Callable[[str], str]:
    """item actor -> readable name (game texts when found, else plain_label)."""
    from .mw_items import POUCH_NAMES
    import json
    from .world import DATA_DIR

    names = game_item_names(romfs or default_romfs(), lang)
    try:
        pouch = dict(json.loads((DATA_DIR / "items.json").read_text(encoding="utf-8")).get("progressive_pouch", {}))
    except (OSError, ValueError):
        pouch = {}
    pouch.update(POUCH_NAMES)

    def label(item: str) -> str:
        item = _ALIASES.get(item, item)
        if item.startswith("Tbox_"):  # Tbox_MagicJar_Large: the game's own spelling
            item = "TBox_" + item[5:]
        candidates = [item, pouch.get(item, item)]
        candidates += [item.replace(a, b, 1) for a, b in _RELATED if item.startswith(a)]
        for c in candidates:
            if c in names:
                return names[c]
        return plain_label(item)

    return label


def exchange(finder: str, owner: str, item_label: str, location: str) -> str:
    """The line of one exchange (server INFO and logs)."""
    return f"{finder} -> {owner}: {item_label} ({location})"


class Log:
    """Timestamped lines, printed and appended to a file (if any)."""

    def __init__(self, path: Path | str | None, echo: Callable[[str], None] = print) -> None:
        self.path = Path(path) if path else None
        self.echo = echo
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, text: str) -> None:
        line = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
        if self.echo:
            self.echo(line)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
