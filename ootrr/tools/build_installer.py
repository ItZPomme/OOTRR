"""Builds the standalone Windows installer (output/OoTRR-installer.exe) with PyInstaller.

    python -m pip install pyinstaller
    python -m ootrr.tools.build_installer [--native native/exlaunch/deploy/subsdk9]

The exe contains Python, the libraries (zstandard, ainb), the randomizer data (ootrr/data) and the native
module (subsdk9): it must be built from the same code as that module. No game files are put in it.
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
    p.add_argument("--native", type=Path, default=NATIVE, help="native module to bundle (subsdk9)")
    p.add_argument("--out", type=Path, default=ROOT / "output")
    a = p.parse_args(argv)
    if not a.native.is_file():
        raise SystemExit(f"native module not found: {a.native}")
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
    print("written:", exe, f"({exe.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
