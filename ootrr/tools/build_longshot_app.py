"""Builds the standalone desktop apps with PyInstaller: the seed installer for Longshot and Eden
(output/OoTRR-App.exe) and the plandomizer (output/OoTRR-Plando.exe).

    python -m pip install pyinstaller
    python -m ootrr.tools.build_longshot_app              # OoTRR-App.exe
    python -m ootrr.tools.build_longshot_app --plando     # OoTRR-Plando.exe
    python -m ootrr.tools.build_longshot_app --all        # both

Each is one windowed exe (no console) with the logo as its icon, Python, the libraries (zstandard, ainb) and the
randomizer data. No game files are put in it: the apps read the game's RomFS at run time.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICON = ROOT / "ootrr" / "assets" / "longshot.ico"
APPS = {  # exe name -> module whose main() runs the window
    "OoTRR-App": "ootrr.tools.longshot_app",
    "OoTRR-Plando": "ootrr.tools.plando_app",
}


def build(name: str, module: str, out: Path) -> Path:
    sep = ";" if sys.platform == "win32" else ":"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        launcher = tmp / f"{name}.py"
        launcher.write_text(f"from {module} import main\nraise SystemExit(main())\n", encoding="utf-8")
        cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--windowed", "--noconfirm",
               "--name", name, "--icon", str(ICON), "--distpath", str(out), "--workpath", str(tmp / "build"),
               "--specpath", str(tmp), "--paths", str(ROOT),
               "--add-data", f"{ROOT / 'ootrr' / 'data'}{sep}ootrr/data",
               "--add-data", f"{ROOT / 'ootrr' / 'assets'}{sep}ootrr/assets",
               "--collect-submodules", "ootrr", "--collect-all", "ainb", "--hidden-import", "zstandard",
               str(launcher)]
        subprocess.run(cmd, check=True)
    exe = out / f"{name}.exe"
    print("written:", exe, f"({exe.stat().st_size // 1024} KB)")
    return exe


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=ROOT / "output")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--plando", action="store_true", help="build OoTRR-Plando.exe instead of OoTRR-App.exe")
    group.add_argument("--all", action="store_true", help="build both")
    a = p.parse_args(argv)
    if not ICON.is_file():
        from .make_icon import main as make_icon
        make_icon()
    names = list(APPS) if a.all else ["OoTRR-Plando"] if a.plando else ["OoTRR-App"]
    for name in names:
        build(name, APPS[name], a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
