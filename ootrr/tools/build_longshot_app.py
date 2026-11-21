"""Builds the standalone desktop apps with PyInstaller: the seed installer for Longshot and Eden
(output/OoTRR-App.exe), the plandomizer (output/OoTRR-Plando.exe) and the live coordinates overlay
(output/OoTRR-Overlay.exe).

    python -m pip install pyinstaller
    python -m ootrr.tools.build_longshot_app              # OoTRR-App.exe
    python -m ootrr.tools.build_longshot_app --plando     # OoTRR-Plando.exe
    python -m ootrr.tools.build_longshot_app --overlay    # OoTRR-Overlay.exe
    python -m ootrr.tools.build_longshot_app --all        # all three

The app and the plandomizer are windowed exes (no console) with the logo as their icon, Python, the libraries
(zstandard, ainb) and the randomizer data. The overlay only uses the standard library and keeps a console: the
overlay itself is click-through, so closing the console is how it stops. No game files are put in any of them.
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
    "OoTRR-Overlay": "ootrr.tools.coords_overlay",
}
LIGHT = {"OoTRR-Overlay"}  # standard library only: console kept, no data or extra libraries
# When double-clicked, a console exe closes at once on an error: keep it open so the message can be read.
PAUSE = """
import sys
from {module} import main
try:
    code = main()
except SystemExit as exc:
    code = exc.code
if code and sys.stdin and sys.stdin.isatty():
    input("Press Enter to close.")
raise SystemExit(code)
"""


def build(name: str, module: str, out: Path) -> Path:
    sep = ";" if sys.platform == "win32" else ":"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        launcher = tmp / f"{name}.py"
        light = name in LIGHT
        launcher.write_text(PAUSE.format(module=module) if light
                            else f"from {module} import main\nraise SystemExit(main())\n", encoding="utf-8")
        cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--noconfirm",
               "--name", name, "--icon", str(ICON), "--distpath", str(out), "--workpath", str(tmp / "build"),
               "--specpath", str(tmp), "--paths", str(ROOT)]
        if not light:  # windowed app with the randomizer data and libraries
            cmd += ["--windowed",
                    "--add-data", f"{ROOT / 'ootrr' / 'data'}{sep}ootrr/data",
                    "--add-data", f"{ROOT / 'ootrr' / 'assets'}{sep}ootrr/assets",
                    "--collect-submodules", "ootrr", "--collect-all", "ainb", "--hidden-import", "zstandard"]
        cmd.append(str(launcher))
        subprocess.run(cmd, check=True)
    exe = out / f"{name}.exe"
    print("written:", exe, f"({exe.stat().st_size // 1024} KB)")
    return exe


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=ROOT / "output")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--plando", action="store_true", help="build OoTRR-Plando.exe instead of OoTRR-App.exe")
    group.add_argument("--overlay", action="store_true", help="build OoTRR-Overlay.exe instead of OoTRR-App.exe")
    group.add_argument("--all", action="store_true", help="build all three")
    a = p.parse_args(argv)
    if not ICON.is_file():
        from .make_icon import main as make_icon
        make_icon()
    names = (list(APPS) if a.all else ["OoTRR-Plando"] if a.plando else ["OoTRR-Overlay"] if a.overlay
             else ["OoTRR-App"])
    for name in names:
        build(name, APPS[name], a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
