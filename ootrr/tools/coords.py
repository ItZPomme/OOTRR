"""Player positions logged by the native module, and the actors nearest to them.

The in-game menu mod (native module) writes "OoTRR: position x y z" in the emulator log each time Link stands still
for one second somewhere new. Stand next to a chest (a scrub, a rock...), wait one second, then:

    python -m ootrr.tools.coords                                    # last logged positions
    python -m ootrr.tools.coords --follow                           # print them as they come
    python -m ootrr.tools.coords --romfs ROMFS --area Banc/HyruleField --filter Obj_TBox   # + nearest chests

With --area, each position is followed by the nearest actors of that area (maps `*.bcett.byml.zs`), their hash, and
the location name when an `ootrr/data` entry uses that hash. The emulator can stay open (the log is only read).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

LINE = re.compile(r"OoTRR: position (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)")
DATA = Path(__file__).resolve().parents[1] / "data"


def default_log() -> Path | None:
    appdata = Path(os.environ.get("APPDATA", ""))
    logs = [appdata / emu / "log" / name for emu in ("fritchii", "eden")
            for name in ("eden_log.busy.txt", "eden_log.txt")]
    logs = [p for p in logs if p.is_file()]
    return max(logs, key=lambda p: p.stat().st_mtime) if logs else None


def location_names() -> dict[int, str]:
    """Actor hash -> location name, from every data entry with a "hashes" list."""
    names: dict[int, str] = {}

    def walk(node, name=None):
        if isinstance(node, dict):
            for h in node.get("hashes", []) if isinstance(node.get("hashes"), list) else []:
                if isinstance(h, int) and name:
                    names.setdefault(h, name)
            for key, value in node.items():
                walk(value, key if isinstance(value, dict) else name)
        elif isinstance(node, list):
            for value in node:
                walk(value, name)

    for f in DATA.rglob("*.json"):
        walk(json.loads(f.read_text(encoding="utf-8")))
    return names


def load_actors(romfs: Path, area: str, needle: str) -> list[tuple[str, str, int, list[float]]]:
    from ..formats.byml import read_byml
    from ..formats.zs import ZsCodec
    codec = ZsCodec(romfs)
    seen, actors = set(), []
    for f in sorted((romfs / area).glob("*.bcett.byml.zs")):
        for actor in read_byml(codec.decompress(f)).get("Actors", []):
            name, pos = actor.get("Gyaml", ""), actor.get("Translate")
            if needle not in name or not pos or actor["Hash"] in seen:
                continue
            seen.add(actor["Hash"])
            actors.append((f.name.split(".")[0], name, actor["Hash"], [float(x) for x in pos]))
    return actors


def show(pos: list[float], actors, names: dict[int, str], count: int) -> None:
    print(f"position {pos[0]:.1f} {pos[1]:.1f} {pos[2]:.1f}")
    for dist, (file, name, h, apos) in sorted((math.dist(pos, a[3]), a) for a in actors)[:count]:
        where = f"  <- {names[h]}" if h in names else ""
        print(f"    {dist:6.1f}  {name}  hash={h}  pos=[{apos[0]:.1f}, {apos[1]:.1f}, {apos[2]:.1f}]  ({file}){where}")


def show_live(pos: list[float], actors, names: dict[int, str]) -> None:
    text = f"x {pos[0]:8.1f}   y {pos[1]:8.1f}   z {pos[2]:8.1f}"
    if actors:
        dist, (_, name, h, _) = min((math.dist(pos, a[3]), a) for a in actors)
        text += f"   nearest: {name} {dist:.1f}" + (f" ({names[h]})" if h in names else "")
    print("\r" + text[:150].ljust(150), end="", flush=True)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--log", help="emulator log (default: the latest of fritchii / eden in %%APPDATA%%)")
    p.add_argument("--romfs", help="RomFS, to name the nearest actors (with --area)")
    p.add_argument("--area", help="folder of the maps, e.g. Banc/HyruleField")
    p.add_argument("--filter", default="", help="only actors whose name contains this text (e.g. TBox)")
    p.add_argument("-n", "--count", type=int, default=3, help="nearest actors shown per position (default 3)")
    p.add_argument("--last", type=int, default=5, help="positions shown from the log (default 5)")
    p.add_argument("--follow", action="store_true", help="keep reading the log and show new positions")
    p.add_argument("--live", action="store_true",
                   help="like --follow, on one line updated in place (test mod built with menutest --live-coords)")
    a = p.parse_args(argv)
    a.follow = a.follow or a.live
    log = Path(a.log) if a.log else default_log()
    if not log or not log.is_file():
        raise SystemExit("emulator log not found: give it with --log")
    if a.area and not a.romfs:
        raise SystemExit("--area needs --romfs")
    actors = load_actors(Path(a.romfs), a.area, a.filter) if a.area else []
    names = location_names() if actors else {}
    print(f"log: {log}" + (f" ; {len(actors)} actors in {a.area}" if a.area else ""))

    with open(log, encoding="utf-8", errors="replace") as f:
        found = [[float(x) for x in m.groups()] for m in map(LINE.search, f) if m]
        for pos in [] if a.live else found[-a.last:]:
            show(pos, actors, names, a.count)
        if a.live and found:
            show_live(found[-1], actors, names)
        if not found:
            print("no position logged yet (is the OoTRR menu mod installed? stand still for one second)")
        while a.follow:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            m = LINE.search(line)
            if m:
                pos = [float(x) for x in m.groups()]
                show_live(pos, actors, names) if a.live else show(pos, actors, names, a.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
