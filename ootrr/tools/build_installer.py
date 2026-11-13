"""Fabrique l'installateur Windows autonome (output/OoTRR-installer.exe) avec PyInstaller.

    python -m pip install pyinstaller
    python -m ootrr.tools.build_installer [--native native/exlaunch/deploy/subsdk9]

L'exe contient Python, les bibliothèques (zstandard, ainb), les données du randomizer (ootrr/data) et le module
natif (subsdk9) : il doit être fabriqué depuis le même code que ce module. Aucun fichier du jeu n'y est mis.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native" / "exlaunch" / "deploy" / "subsdk9"
LAUNCHER = "from ootrr.tools.installer import run\nrun()\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--native", type=Path, default=NATIVE, help="module natif à embarquer (subsdk9)")
    p.add_argument("--out", type=Path, default=ROOT / "output")
    a = p.parse_args(argv)
    if not a.native.is_file():
        raise SystemExit(f"module natif absent : {a.native}")
    sep = ";" if sys.platform == "win32" else ":"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        launcher = tmp / "OoTRR-installer.py"
        launcher.write_text(LAUNCHER, encoding="utf-8")
        cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--console", "--noconfirm",
               "--name", "OoTRR-installer", "--distpath", str(a.out), "--workpath", str(tmp / "build"),
               "--specpath", str(tmp), "--paths", str(ROOT),
               "--add-data", f"{ROOT / 'ootrr' / 'data'}{sep}ootrr/data",
               "--add-binary", f"{a.native}{sep}.",
               "--collect-submodules", "ootrr", "--collect-all", "ainb", "--hidden-import", "zstandard",
               str(launcher)]
        subprocess.run(cmd, check=True)
    exe = a.out / "OoTRR-installer.exe"
    print("écrit :", exe, f"({exe.stat().st_size // 1024} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
