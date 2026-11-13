"""Randomizer menu installer for players (standalone Windows program, no Python to install).

    OoTRR-installer.exe                 # asks for the romfs folder in a window
    OoTRR-installer.exe "PATH\\romfs"    # or as an argument

Builds the `OoTRR-menu` mod from the player's update RomFS (no game files are provided) and installs it into the
emulator (Fritchii or Eden), with the bundled native module (subsdk9 of the same version). Built by
`python -m ootrr.tools.build_installer` (PyInstaller).
From the sources: `python -m ootrr.tools.installer` uses native/exlaunch/deploy/subsdk9.
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
    messagebox.showinfo("OoTRR", "Choose the \"romfs\" folder of the game's UPDATE (version 131072),\n"
                                 "the one that contains Banc, Event, GameData, Pack…")
    folder = filedialog.askdirectory(title="Update romfs folder")
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
        print("Cancelled.")
        return 1
    if not (romfs / "GameData").is_dir() or not (romfs / "Pack").is_dir():
        print(f"This folder is not a RomFS of the game (GameData and Pack missing): {romfs}")
        return 1
    emulator = running_emulator()
    if emulator:
        print(f"The emulator is open ({emulator}): close it, then run the installer again.")
        return 1
    native = bundled_native()
    if not native.is_file():
        print(f"Native module not found: {native}")
        return 1
    print("Building the mod from", romfs, "(a few minutes)…")
    return build(["--romfs", str(romfs), "--native", str(native), "--install", "--quiet"])


def run() -> None:
    """Entry point of the exe: readable messages and a pause before closing the window."""
    code = 1
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if not isinstance(exc.code, int) and exc.code:
            print(exc.code)
    except Exception as exc:  # readable message for the player
        print("Error:", exc)
    if code == 0:
        print("\nInstalled: in the emulator, game Properties -> Add-Ons -> tick OoTRR-menu (and only that one).")
    if getattr(sys, "frozen", False):
        input("\nPress Enter to close.")
    sys.exit(code)


if __name__ == "__main__":
    run()
