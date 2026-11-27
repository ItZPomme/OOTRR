"""Live view of a running Longshot game through its control socket (HOS_CONTROL, see docs/MULTIWORLD.md).

    python -m ootrr.tools.checkwatch                                   # GameData changes, map, event, position
    python -m ootrr.tools.checkwatch --romfs ROMFS --area Banc/HyruleField --filter Obj_   # + nearest actors

The socket is found by itself: the one the OoTRR app gave Longshot (`$XDG_RUNTIME_DIR/ootrr-*/control.sock`);
`--pipe` gives another endpoint (`HOS_CONTROL` value). Changed values are shown by name when the name appears in
this repository, else by hash (`#hash` works in `ootrr.tools.lookup` and in the data files).
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import re
import sys
from pathlib import Path

from ..formats.gamedata import flag_hash
from ..longshot_control import ControlError, Longshot

ROOT = Path(__file__).resolve().parents[2]
WORD = re.compile(r"[A-Za-z_][\w.]{3,}")


def find_endpoint() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    found = sorted(glob.glob(os.path.join(runtime, "ootrr-*", "control.sock")), key=os.path.getmtime)
    return found[-1] if found else "1"


def known_names() -> dict[int, str]:
    names: dict[int, str] = {}
    for path in list((ROOT / "ootrr").rglob("*.py")) + list((ROOT / "ootrr" / "data").rglob("*.json")):
        for word in WORD.findall(path.read_text(encoding="utf-8", errors="replace")):
            names.setdefault(flag_hash(word), word)
    return names


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pipe", help="Longshot's HOS_CONTROL value (default: the OoTRR app's socket)")
    p.add_argument("--romfs", help="RomFS, to name the nearest actors (with --area)")
    p.add_argument("--area", help="folder of the maps, e.g. Banc/HyruleField")
    p.add_argument("--filter", default="", help="only actors whose name contains this text")
    p.add_argument("-n", "--count", type=int, default=3, help="nearest actors shown (default 3)")
    p.add_argument("--every", type=int, default=30, help="frames between two looks (default 30)")
    a = p.parse_args(argv)
    if a.area and not a.romfs:
        raise SystemExit("--area needs --romfs")
    actors = []
    if a.area:
        from .coords import load_actors
        actors = load_actors(Path(a.romfs), a.area, a.filter)
    names = known_names()
    endpoint = a.pipe or find_endpoint()
    try:
        game = Longshot(endpoint, timeout=5)
    except ControlError as exc:
        raise SystemExit(f"{exc}\nStart Longshot with HOS_CONTROL=<socket path> and HOS_CONTROL_MEM=ro or rw "
                         "(the OoTRR app does it).")
    print(f"connected to {endpoint}; Ctrl+C to stop")
    game.call("subscribe", events=["oot"], every=a.every, changes=True)
    last = None
    first = True  # the first line lists every value
    with game:
        try:
            for msg in game.events():
                if msg.get("event") != "oot":
                    continue
                g = msg.get("game") or {}
                for h, value in ({} if first else g.get("changed") or {}).items():
                    print(f"  {names.get(int(h, 16), '#' + str(int(h, 16)))} = {value}", flush=True)
                first = False
                pos = g.get("pos")
                state = (g.get("map"), g.get("event"))
                if state != last:
                    print(f"map {state[0]}  event {state[1]}  age {g.get('age')}", flush=True)
                    last = state
                if actors and pos and not g.get("loading"):
                    near = sorted((math.dist(pos, act[3]), act) for act in actors)[:a.count]
                    print("  nearest: " + "; ".join(f"{act[1]} {d:.1f} hash={act[2]}" for d, act in near), flush=True)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
