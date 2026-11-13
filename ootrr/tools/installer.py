"""Installateur du menu du randomizer pour les joueurs (programme Windows autonome, sans Python à installer).

    OoTRR-installer.exe                 # demande le dossier romfs dans une fenêtre
    OoTRR-installer.exe "CHEMIN\\romfs"  # ou en argument

Construit le mod `OoTRR-menu` à partir de la RomFS de la mise à jour du joueur (aucun fichier du jeu n'est
fourni) et l'installe dans l'émulateur (Fritchii ou Eden), avec le module natif embarqué (subsdk9 de la même
version). Fabriqué par `python -m ootrr.tools.build_installer` (PyInstaller).
Depuis les sources : `python -m ootrr.tools.installer` utilise native/exlaunch/deploy/subsdk9.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EMULATORS = ("fritchii.exe", "eden.exe", "yuzu.exe", "citron.exe", "suyu.exe")


def bundled_native() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2] / "native" / "exlaunch" / "deploy"))
    return base / "subsdk9"


def ask_romfs() -> Path | None:
    import tkinter
    from tkinter import filedialog, messagebox

    root = tkinter.Tk()
    root.withdraw()
    messagebox.showinfo("OoTRR", "Choisis le dossier « romfs » de la MISE À JOUR du jeu (version 131072),\n"
                                 "celui qui contient Banc, Event, GameData, Pack…")
    folder = filedialog.askdirectory(title="Dossier romfs de la mise à jour")
    root.destroy()
    return Path(folder) if folder else None


def running_emulator() -> str | None:
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
    except OSError:
        return None
    return next((e for e in EMULATORS if e in out), None)


def main(argv=None) -> int:
    from .menutest import main as build

    args = list(sys.argv[1:] if argv is None else argv)
    romfs = Path(args[0]) if args else ask_romfs()
    if romfs is None:
        print("Annulé.")
        return 1
    if not (romfs / "GameData").is_dir() or not (romfs / "Pack").is_dir():
        print(f"Ce dossier n'est pas une RomFS du jeu (GameData et Pack manquants) : {romfs}")
        return 1
    emulator = running_emulator()
    if emulator:
        print(f"L'émulateur est ouvert ({emulator}) : ferme-le, puis relance l'installateur.")
        return 1
    native = bundled_native()
    if not native.is_file():
        print(f"Module natif introuvable : {native}")
        return 1
    print("Construction du mod à partir de", romfs, "(quelques minutes)…")
    return build(["--romfs", str(romfs), "--native", str(native), "--install"])


def run() -> None:
    """Point d'entrée de l'exe : messages lisibles et pause avant de fermer la fenêtre."""
    code = 1
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if not isinstance(exc.code, int) and exc.code:
            print(exc.code)
    except Exception as exc:  # message lisible pour le joueur
        print("Erreur :", exc)
    if code == 0:
        print("\nInstallé : dans l'émulateur, Propriétés du jeu -> Add-Ons -> coche OoTRR-menu (et seulement lui).")
    if getattr(sys, "frozen", False):
        input("\nAppuie sur Entrée pour fermer.")
    sys.exit(code)


if __name__ == "__main__":
    run()
