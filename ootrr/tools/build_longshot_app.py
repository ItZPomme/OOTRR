"""Builds the standalone Longshot seed installer (output/OoTRR-Longshot.exe) with PyInstaller.

    python -m pip install pyinstaller
    python -m ootrr.tools.build_longshot_app

One windowed exe (no console) with the logo as its icon, Python, the libraries (zstandard, ainb) and the
randomizer data. No game files are put in it: the app reads Longshot's own RomFS at run time.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICON = ROOT / "ootrr" / "assets" / "longshot.ico"
LAUNCHER = "from ootrr.tools.longshot_app import main\nraise SystemExit(main())\n"
NAME = "OoTRR-Longshot"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=ROOT / "output")
    a = p.parse_args(argv)
    if not ICON.is_file():
        from .make_icon import main as make_icon
        make_icon()
    sep = ";" if sys.platform == "win32" else ":"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        launcher = tmp / f"{NAME}.py"
        launcher.write_text(LAUNCHER, encoding="utf-8")
        cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--windowed", "--noconfirm",
               "--name", NAME, "--icon", str(ICON), "--distpath", str(a.out), "--workpath", str(tmp / "build"),
               "--specpath", str(tmp), "--paths", str(ROOT),
               "--add-data", f"{ROOT / 'ootrr' / 'data'}{sep}ootrr/data",
               "--add-data", f"{ROOT / 'ootrr' / 'assets'}{sep}ootrr/assets",
               "--collect-submodules", "ootrr", "--collect-all", "ainb", "--hidden-import", "zstandard",
               str(launcher)]
        subprocess.run(cmd, check=True)
    exe = a.out / f"{NAME}.exe"
    print("written:", exe, f"({exe.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
