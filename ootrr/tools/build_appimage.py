"""Build the Linux AppImage for the Longshot desktop app.

    python -m pip install pyinstaller
    python -m ootrr.tools.build_appimage

Requires the project requirements, Tkinter development/runtime libraries and appimagetool on PATH (or set
APPIMAGETOOL to its path). The AppImage contains OoTRR, not game files.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .build_longshot_app import ROOT, build

APP = "OoTRR-App"
MODULE = "ootrr.tools.longshot_app"
ICON = ROOT / "ootrr" / "assets" / "longshot.png"
APP_RUN = '''#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/OoTRR-App" "$@"
'''
DESKTOP = '''[Desktop Entry]
Type=Application
Name=OoTRR Longshot Randomizer
Comment=Generate and install Ocarina of Time randomizer seeds for Longshot
Exec=OoTRR-App
Icon=ootrr
Categories=Game;Utility;
Terminal=false
'''


def build_appimage(out: Path, appimagetool: str) -> Path:
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not ICON.is_file():
        from .make_icon import main as make_icon
        make_icon()

    with tempfile.TemporaryDirectory(prefix="ootrr-appimage-") as temp:
        temp = Path(temp)
        executable = build(APP, MODULE, temp / "dist")
        appdir = temp / "OoTRR.AppDir"
        (appdir / "usr" / "bin").mkdir(parents=True)
        applications = appdir / "usr" / "share" / "applications"
        applications.mkdir(parents=True)
        icons = appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
        icons.mkdir(parents=True)
        shutil.copy2(executable, appdir / "usr" / "bin" / APP)
        shutil.copy2(ICON, appdir / "ootrr.png")
        shutil.copy2(ICON, icons / "ootrr.png")
        desktop_path = appdir / f"{APP}.desktop"
        desktop_path.write_text(DESKTOP, encoding="utf-8")
        shutil.copy2(desktop_path, applications / desktop_path.name)
        app_run = appdir / "AppRun"
        app_run.write_text(APP_RUN, encoding="utf-8")
        app_run.chmod(0o755)
        subprocess.run([appimagetool, "--no-appstream", str(appdir), str(out)], check=True)
    print("written:", out, f"({out.stat().st_size // 1024} KB)")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "output" / "OoTRR-App-x86_64.AppImage")
    parser.add_argument("--appimagetool", default=os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool"),
                        help="appimagetool executable (default: APPIMAGETOOL or PATH)")
    args = parser.parse_args(argv)
    if sys.platform != "linux":
        parser.error("AppImage builds must run on Linux")
    if importlib.util.find_spec("PyInstaller") is None:
        parser.error("PyInstaller not found; install requirements.txt and pyinstaller in this Python environment")
    try:
        import tkinter
    except ImportError as exc:
        parser.error(f"Tkinter is unavailable ({exc}); install your distribution's Python Tk package")
    if not args.appimagetool:
        parser.error("appimagetool not found; install it or set APPIMAGETOOL to its executable path")
    build_appimage(args.out, args.appimagetool)
    return 0


if __name__ == "__main__":
    sys.exit(main())