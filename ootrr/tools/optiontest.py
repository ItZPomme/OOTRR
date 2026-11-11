"""Mod de test de l'écran d'options : le jeu accepte-t-il une table de lignes et des textes modifiés ?

    python -m ootrr.tools.optiontest --romfs ROMFS [--install]

- Table `UI/OptionSetTable` (pack Bootup) : la ligne « Vitesse de la caméra » passe en premier et
  la ligne du carnet de Zelda est retirée.
- Messages `LayoutMsg/SystemOption_00` (toutes les langues) : titre et valeurs de cette ligne
  remplacés par des textes « OoTRR ».
- `--menu` : « Nouvelle partie » ouvre l'écran d'options (nouveau nœud `Option.module` dans
  `Sequence/NormalTitle`, réécrit avec la bibliothèque `ainb`) ; en le fermant, la confirmation
  « Commencer ? » apparaît, puis la partie commence.
Installe sous `OoTRR-options` : désactiver les autres mods OoTRR de la RomFS (ils écrivent aussi
la table RESTBL).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import zstandard

from ..formats.byml import byml_version, read_byml, write_byml
from ..formats.msbt import read_labels, replace_texts
from ..formats.sarc import Sarc
from ..modbuild import ModBuilder, emulator_root, install

BOOTUP = "Pack/Bootup.Nin_Ounce_NVN2.pack.zs"
TABLE = "UI/OptionSetTable/OptionSetTable.game__ui__OptionSetTable.bgyml"
MESSAGES = "LayoutMsg/SystemOption_00.msbt"
CAMERA_SPEED = 183082848      # OptionType de la ligne à 5 choix (CameraRotateSpeed)
ZELDA_NOTES = 916121729       # ligne conditionnelle du carnet de Zelda
TEXTS = {
    "CameraRotateSpeed_Title": "OoTRR - Open Forest",
    "CameraRotateSpeed_Caption": "OoTRR test: this line was renamed by the randomizer.",
    "CameraRotateSpeed_00": "Closed",
    "CameraRotateSpeed_01": "Closed Deku",
    "CameraRotateSpeed_02": "Open",
    "CameraRotateSpeed_03": "Ask",
    "CameraRotateSpeed_04": "Random",
}


def add_menu_after_new_game(raw: bytes) -> bytes:
    """NormalTitle : Nouvelle partie -> nouveau nœud Option.module -> ConfirmationNewGame -> partie.

    Le nœud qui préparait la confirmation (il cache l'écran titre, comme celui du bouton Options)
    mène au nouveau nœud ; sa sortie « End » mène à la confirmation, dont « Oui » lance la partie
    comme avant et « Non » revient au titre. Modifie directement l'objet de la bibliothèque `ainb`
    (son passage par dict/JSON casse la table des chaînes de cette version)."""
    import copy
    import uuid

    import ainb
    from ainb.transition import Transition

    script = ainb.AINB.from_binary(raw)
    nodes = script.nodes
    confirm = next(n for n in nodes if n.name == "ConfirmationNewGame.module")
    option = next(n for n in nodes if n.name == "Option.module"
                  and any(t.node_index != 7 for t in n.transition_plugs))
    before = [p for n in nodes for p in (n.transition_plugs or []) if p.node_index == confirm.index]
    if len(before) != 1:
        raise ValueError(f"NormalTitle : {len(before)} transitions vers la confirmation (1 attendue)")
    new = copy.deepcopy(option)
    new.index = len(nodes)
    new.guid = str(uuid.UUID(int=(0x4F6F5452 << 96) | (0x4000 << 48) | (0x8000 << 32) | len(nodes)))
    end = new.transition_plugs[0]
    end.node_index = confirm.index
    end.transition = Transition(transition_type=end.transition.transition_type,
                                update_post_calc=end.transition.update_post_calc,
                                command_name=end.transition.command_name)
    nodes.append(new)
    before[0].node_index = new.index
    for m in script.modules:
        if m.path == "Option.module.ainb":
            m.instance_count += 1
    return script.to_binary()


def build(romfs: Path, out: Path, menu: bool = False) -> list[str]:
    mb = ModBuilder(romfs)
    report = []

    path = romfs / BOOTUP
    raw = mb.codec.decompress(path)
    sarc = Sarc(raw)
    data = sarc.files[TABLE]
    tree = read_byml(data)
    rows = tree["OptionSetArray"]
    first = [r for r in rows if r.get("OptionType") == CAMERA_SPEED]
    rest = [r for r in rows if r.get("OptionType") not in (CAMERA_SPEED, ZELDA_NOTES)]
    tree["OptionSetArray"] = first + rest
    sarc.files[TABLE] = write_byml(tree, byml_version(data))
    new = sarc.to_bytes()
    mb.restbl.resize_like(BOOTUP[:-3], len(raw), len(new))
    dest = out / BOOTUP
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(mb.codec.compress(path.name, new))
    report.append(f"{TABLE}: {len(rows)} -> {len(tree['OptionSetArray'])} lignes")

    for path in sorted((romfs / "Mals").glob("*.sarc.zs")):
        raw = mb.codec.decompress(path)
        sarc = Sarc(raw)
        msg = sarc.files[MESSAGES]
        labels = read_labels(msg)
        changes = {k: v.encode() for k, v in TEXTS.items() if k in labels}
        sarc.files[MESSAGES] = replace_texts(msg, changes)
        data = sarc.to_bytes()
        rel = path.relative_to(romfs).as_posix()
        mb.restbl.resize_like(rel[:-3], len(raw), len(data))
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(mb.codec.compress(path.name, data))
        report.append(f"{rel}: {len(changes)} messages")

    if menu:
        rel = "Sequence/NormalTitle.module.ainb"
        raw = (romfs / rel).read_bytes()
        data = add_menu_after_new_game(raw)
        mb.restbl.resize_like(rel, len(raw), len(data))
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        report.append(f"{rel}: écran d'options inséré entre Nouvelle partie et la confirmation")

    rel = mb.restbl_path.relative_to(romfs)
    dest = out / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(zstandard.ZstdCompressor(level=16).compress(mb.restbl.to_bytes()))
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--romfs", required=True, type=Path)
    p.add_argument("--install", action="store_true")
    p.add_argument("--menu", action="store_true", help="Nouvelle partie ouvre l'écran d'options")
    p.add_argument("--eden", type=Path, default=None, help="dossier de l'émulateur (défaut : détecté)")
    a = p.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "romfs"
        for line in build(a.romfs, out, a.menu):
            print(line)
        if a.install:
            print("installé :", install(Path(tmp), a.eden or emulator_root(), "OoTRR-options"))
        else:
            dest = Path("output") / "OoTRR-options"
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(Path(tmp), dest)
            print("écrit dans", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
