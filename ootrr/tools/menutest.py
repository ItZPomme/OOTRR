"""Mod de test du menu du randomizer dans le jeu (voir ootrr/ingame_menu.py et native/README.md).

    python -m ootrr.tools.menutest --romfs ROMFS [--install]

Contenu : GameData (structure OoTRRMenu + drapeau), table de lignes dans le pack Bootup, textes
(LayoutMsg/SystemOption_00, toutes les langues), Sequence/NormalTitle, table RESTBL, et le module
natif (native/exlaunch/deploy/subsdk9, à compiler avant) dans exefs/.
Installe sous `OoTRR-menu` : désactiver les autres mods OoTRR (OoTRR, OoTRR-essai, OoTRR-options,
OoTRR-native) pendant le test.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import zstandard

from .. import ingame_menu as menu
from ..formats.byml import byml_version, read_byml, write_byml
from ..formats.sarc import Sarc
from ..modbuild import ModBuilder, emulator_root, install
from ..settings import defaults

NATIVE = Path(__file__).resolve().parents[2] / "native" / "exlaunch" / "deploy" / "subsdk9"


def build(romfs: Path, out: Path) -> list[str]:
    mb = ModBuilder(romfs)
    report = []

    # GameData : structure OoTRRMenu et drapeau du menu
    path = next((romfs / "GameData").glob("GameDataList*.byml.zs"))
    raw = mb.codec.decompress(path)
    root = read_byml(raw)
    report += menu.gamedata_struct(root, defaults())
    enum_values = {}
    from ..formats.gamedata import flag_hash, index
    idx = index(root)
    st = next(e for e in root["Data"]["Struct"] if e["Hash"] == flag_hash(menu.OPTION_STRUCT))
    names = {flag_hash(t): t for _, t, _ in menu.SETTING_ROWS}
    for m in st["DefaultValue"]:
        if m["Hash"] in names:
            section, entry = idx[m["Value"]]
            if section == "Enum":
                enum_values[names[m["Hash"]]] = entry["RawValues"]
    new = write_byml(root, byml_version(raw))
    rel = path.relative_to(romfs).as_posix()
    mb.restbl.resize_like(rel[:-3], len(raw), len(new))
    (out / rel).parent.mkdir(parents=True, exist_ok=True)
    (out / rel).write_bytes(mb.codec.compress(path.name, new))

    # pack Bootup : notre table de lignes à côté de celle du jeu
    path = romfs / menu.BOOTUP
    raw = mb.codec.decompress(path)
    sarc = Sarc(raw)
    game_table = sarc.files[menu.GAME_TABLE]
    table = menu.option_table(game_table, enum_values)
    sarc.files[menu.MENU_TABLE] = table
    margin = mb.restbl.get(menu.GAME_TABLE) - len(game_table)
    mb.restbl.set(menu.MENU_TABLE, len(table) + margin)
    new = sarc.to_bytes()
    mb.restbl.resize_like(menu.BOOTUP[:-3], len(raw), len(new))
    (out / menu.BOOTUP).parent.mkdir(parents=True, exist_ok=True)
    (out / menu.BOOTUP).write_bytes(mb.codec.compress(path.name, new))
    report.append(f"{menu.MENU_TABLE}: {len(menu.ROWS)} lignes")

    # mise en page : copie de l'écran d'options sans les modèles inutilisés
    path = romfs / menu.COMMON_LAYOUTS
    raw = mb.codec.decompress(path)
    sarc = Sarc(raw)
    sarc.files[f"{menu.MENU_LAYOUT}.buil"] = menu.menu_layout(sarc.files[f"{menu.GAME_LAYOUT}.buil"])
    new = sarc.to_bytes()
    mb.restbl.resize_like(menu.COMMON_LAYOUTS[:-3], len(raw), len(new))
    (out / menu.COMMON_LAYOUTS).parent.mkdir(parents=True, exist_ok=True)
    (out / menu.COMMON_LAYOUTS).write_bytes(mb.codec.compress(path.name, new))
    path = romfs / menu.LAYOUT_CATEGORIES
    raw = mb.codec.decompress(path)
    tree = read_byml(raw)
    tree["Common"].append(menu.MENU_LAYOUT)
    new = write_byml(tree, byml_version(raw))
    mb.restbl.resize_like(menu.LAYOUT_CATEGORIES[:-3], len(raw), len(new))
    (out / menu.LAYOUT_CATEGORIES).write_bytes(mb.codec.compress(path.name, new))
    report.append(f"mise en page {menu.MENU_LAYOUT} (sans {', '.join(menu.HIDDEN_PANES)})")

    # textes, toutes les langues
    for path in sorted((romfs / "Mals").glob("*.sarc.zs")):
        raw = mb.codec.decompress(path)
        sarc = Sarc(raw)
        old = sarc.files[menu.MESSAGES]
        sarc.files[menu.MESSAGES] = menu.messages(old, path.name[:4])
        if mb.restbl.has(menu.MESSAGES):
            mb.restbl.resize_like(menu.MESSAGES, len(old), len(sarc.files[menu.MESSAGES]))
        new = sarc.to_bytes()
        rel = path.relative_to(romfs).as_posix()
        mb.restbl.resize_like(rel[:-3], len(raw), len(new))
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(mb.codec.compress(path.name, new))
    report.append(f"{menu.MESSAGES}: textes OoTRR_* ajoutés")

    # écran titre
    raw = (romfs / menu.TITLE).read_bytes()
    new = menu.title_sequence(raw)
    mb.restbl.resize_like(menu.TITLE, len(raw), len(new))
    (out / menu.TITLE).parent.mkdir(parents=True, exist_ok=True)
    (out / menu.TITLE).write_bytes(new)
    report.append(f"{menu.TITLE}: menu après Nouvelle partie + drapeau {menu.MENU_FLAG}")

    rel = mb.restbl_path.relative_to(romfs)
    (out / rel).parent.mkdir(parents=True, exist_ok=True)
    (out / rel).write_bytes(zstandard.ZstdCompressor(level=16).compress(mb.restbl.to_bytes()))
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--romfs", required=True, type=Path)
    p.add_argument("--install", action="store_true")
    a = p.parse_args(argv)
    if not NATIVE.is_file():
        raise SystemExit(f"module natif absent : {NATIVE} (compiler native/exlaunch, voir native/README.md)")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for line in build(a.romfs, root / "romfs"):
            print(line)
        (root / "exefs").mkdir()
        shutil.copy2(NATIVE, root / "exefs" / "subsdk9")
        if a.install:
            print("installé :", install(root, emulator_root(), "OoTRR-menu"))
        else:
            dest = Path("output") / "OoTRR-menu"
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(root, dest)
            print("écrit dans", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
