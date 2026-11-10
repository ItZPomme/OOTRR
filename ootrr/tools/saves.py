"""Sauvegarde et restauration des parties d'Eden, pour reprendre un test sans tout recommencer.

    python -m ootrr.tools.saves list
    python -m ootrr.tools.saves backup avant_gohma
    python -m ootrr.tools.saves restore avant_gohma

Les copies sont rangées dans le dossier « saves » du projet. Avant chaque
restauration, l'état actuel est d'abord copié dans « saves/_avant_restauration »,
pour pouvoir revenir en arrière. Eden doit être fermé.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from ..modbuild import TITLE_ID

BACKUP_DIR = Path(__file__).resolve().parents[2] / "saves"


def game_save_dir() -> Path:
    root = Path(os.environ["APPDATA"]) / "eden" / "nand" / "user" / "save"
    found = [p for p in root.rglob(TITLE_ID) if p.is_dir()]
    if not found:
        raise SystemExit(f"Aucune sauvegarde du jeu trouvée sous {root}")
    if len(found) > 1:
        found.sort(key=lambda p: max((f.stat().st_mtime for f in p.rglob("*") if f.is_file()), default=0))
    return found[-1]


def describe(folder: Path) -> str:
    slots = sorted(p.name for p in folder.iterdir() if p.is_dir() and p.name.startswith("slot_"))
    newest = max((f.stat().st_mtime for f in folder.rglob("*") if f.is_file()), default=0)
    return f"{len(slots)} emplacements, modifié le {datetime.fromtimestamp(newest):%Y-%m-%d %H:%M}"


def copy(src: Path, dst: Path) -> None:
    try:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    except PermissionError:
        raise SystemExit("Erreur : fichiers verrouillés. Ferme Eden puis relance la commande.")


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="ootrr.tools.saves")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="lister les copies")
    b = sub.add_parser("backup", help="copier les parties actuelles")
    b.add_argument("name", nargs="?", help="nom de la copie (défaut : date et heure)")
    r = sub.add_parser("restore", help="remettre une copie à la place des parties actuelles")
    r.add_argument("name")
    args = p.parse_args(argv)

    live = game_save_dir()
    if args.cmd == "list":
        print(f"Parties actuelles : {live}\n  {describe(live)}")
        if BACKUP_DIR.exists():
            for d in sorted(BACKUP_DIR.iterdir()):
                if d.is_dir():
                    print(f"  {d.name:<28} {describe(d)}")
        return 0
    if args.cmd == "backup":
        name = args.name or datetime.now().strftime("%Y-%m-%d_%Hh%M")
        copy(live, BACKUP_DIR / name)
        print(f"Copie « {name} » créée ({describe(BACKUP_DIR / name)})")
        return 0
    src = BACKUP_DIR / args.name
    if not src.is_dir():
        raise SystemExit(f"Copie introuvable : {args.name} (voir : python -m ootrr.tools.saves list)")
    copy(live, BACKUP_DIR / "_avant_restauration")
    copy(src, live)
    print(f"Copie « {args.name} » restaurée. L'état précédent est dans « _avant_restauration ».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
