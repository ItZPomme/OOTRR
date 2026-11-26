"""Platform-specific paths and process helpers for the Longshot desktop tools."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


LONGSHOT_BINARIES = ("longshot.exe",) if os.name == "nt" else ("longshot",)
GAME_PROCESSES = {
    "longshot": {"longshot", "longshot.exe"},
    "eden": {"eden", "eden.exe", "fritchii", "fritchii.exe", "yuzu", "yuzu.exe", "suyu", "suyu.exe",
             "citron", "citron.exe", "sudachi", "sudachi.exe"},
}
CHANNEL_ORDER = ("stable", "", "rc")


def longshot_bases() -> tuple[Path, ...]:
    base = Path.home() / "Games" / "Longshot"
    return (base, Path("C:/Games/Longshot")) if os.name == "nt" else (base,)


def app_data_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def longshot_binary(folder: Path) -> Path | None:
    for name in LONGSHOT_BINARIES:
        path = folder / name
        if path.is_file() and (os.name == "nt" or os.access(path, os.X_OK)):
            return path
    return None


def _version_key(name: str) -> tuple:
    main, _, pre = name.lstrip("vV").partition("-")
    nums = tuple(int(x) if x.isdigit() else 0 for x in main.split("."))
    pre_nums = tuple(int(x) for x in re.findall(r"\d+", pre))
    return nums, (1,) if not pre else (0,) + pre_nums


def find_longshot(bases: tuple[Path, ...] | None = None) -> Path | None:
    """Find the newest Longshot version, preferring stable then the old layout then release candidates."""
    for base in bases if bases is not None else longshot_bases():
        if not base.is_dir():
            continue
        for channel in CHANNEL_ORDER:
            folder = base / channel if channel else base
            if not folder.is_dir():
                continue
            found = [path for path in folder.iterdir() if path.is_dir() and longshot_binary(path)]
            if found:
                return max(found, key=lambda path: _version_key(path.name))
        channels = sorted((path for path in base.iterdir() if path.is_dir() and path.name not in CHANNEL_ORDER),
                          key=lambda path: path.name)
        for channel in channels:
            found = [path for path in channel.iterdir() if path.is_dir() and longshot_binary(path)]
            if found:
                return max(found, key=lambda path: _version_key(path.name))
    return None


def saved_longshot(path: str | None) -> Path | None:
    """Keep the saved install if it still exists; otherwise find the current install."""
    if path and longshot_binary(Path(path)):
        return Path(path)
    return find_longshot()


def _process_names(pid_dir: Path) -> set[str]:
    names = set()
    try:
        names.add((pid_dir / "comm").read_text(encoding="utf-8").strip().lower())
    except OSError:
        pass
    try:
        names.add((pid_dir / "exe").resolve().name.lower())
    except OSError:
        pass
    try:
        command = (pid_dir / "cmdline").read_bytes().split(b"\0", 1)[0].decode(errors="replace")
        if command:
            names.add(Path(command).name.lower())
    except OSError:
        pass
    return names


def game_running(target: str = "longshot", proc_root: Path = Path("/proc")) -> bool:
    names = GAME_PROCESSES[target]
    if os.name == "nt":
        try:
            out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                                 creationflags=0x08000000).stdout.lower()
        except OSError:
            return False
        return any(line.split(",", 1)[0].strip('"') in names for line in out.splitlines())
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["pgrep", "-x", *sorted(names)], capture_output=True, text=True)
        except OSError:
            return False
        return out.returncode == 0
    try:
        pid_dirs = (path for path in proc_root.iterdir() if path.name.isdigit())
        return any(_process_names(path) & names for path in pid_dirs)
    except OSError:
        return False


def open_path(path: str | Path) -> None:
    path = str(path)
    if os.name == "nt":
        os.startfile(path)
    else:
        command = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([command, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)