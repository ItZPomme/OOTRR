"""Compare le générateur natif (C++, compilé pour le PC) au générateur Python, seed par seed.

    python -m ootrr.tools.native_check [--seeds 200] [--gxx CHEMIN\\g++.exe]

Régénère native/exlaunch/source/program/rando/logic_data.hpp, compile native/host/gen_main.cpp,
puis, pour chaque préréglage et chaque seed, vérifie que les deux générateurs placent exactement
les mêmes objets aux mêmes lieux (ou échouent tous les deux).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from .. import native_logic
from ..fill import FillError, generate
from ..settings import build as build_settings
from ..world import World

ROOT = Path(__file__).resolve().parents[2]
HOST = ROOT / "native" / "host"
DEFAULT_GXX = Path.home() / "Tools" / "w64devkit" / "bin" / "g++.exe"

PRESETS = {
    "défaut": {},
    "ouvert": {"open_forest": "open", "open_door_of_time": True, "skip_cutscenes": "safe"},
    "récompenses": {"shuffle_rewards": "shuffled", "skip_cutscenes": "safe", "maps_compasses": "shuffle"},
    "cœurs": {"bridge": "hearts", "bridge_count": 10, "shuffle_hearts": "all", "maps_compasses": "removed"},
    "mojo": {"shuffle_scrubs": True, "shuffle_hearts": "freestanding", "open_forest": "open"},
    "boutiques": {"shuffle_shops": "4", "shuffle_scrubs": True, "shuffle_skulltulas": "overworld"},
    "skulltulas": {"shuffle_skulltulas": "all", "shuffle_scrubs": True, "maps_compasses": "shuffle"},
    "pont": {"bridge": "medallions", "bridge_count": 6, "shuffle_rewards": "shuffled",
             "skip_child_zelda": True, "free_time_travel": False, "accessibility": "beatable"},
    "ocarinas": {"shuffle_ocarinas": True, "skip_cutscenes": "safe", "shuffle_hearts": "all"},
    "adulte": {"starting_age": "adult", "open_door_of_time": True, "spawn_point": 22, "start_with_consumables": True},
    "apparition": {"spawn_point": 9, "random_spawn": True, "shuffle_scrubs": True},
    "adulte loin": {"starting_age": "adult", "open_door_of_time": True, "spawn_point": 33, "shuffle_rewards": "shuffled"},
}


def build(gxx: Path) -> Path:
    native_logic.main()
    exe = HOST / "gen_main.exe"
    cmd = [str(gxx), "-O2", "-std=gnu++23", "-Wall", "-o", str(exe), str(HOST / "gen_main.cpp"),
           str(ROOT / "native" / "exlaunch" / "source" / "program" / "rando" / "generator.cpp")]
    env = dict(os.environ, PATH=str(gxx.parent) + os.pathsep + os.environ.get("PATH", ""))
    subprocess.run(cmd, check=True, env=env)
    return exe


def native(exe: Path, seed: int, overrides: dict) -> dict[str, str] | None:
    args = [str(exe), str(seed)] + [f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in overrides.items()]
    out = subprocess.run(args, check=True, capture_output=True, text=True).stdout.splitlines()
    if not out or out[0] == "ECHEC":
        return None
    return dict(line.split("=", 1) for line in out[1:])


def python(seed: int, overrides: dict) -> dict[str, str] | None:
    try:
        return generate(World(build_settings(overrides)), seed).placements
    except FillError:
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seeds", type=int, default=200)
    p.add_argument("--gxx", type=Path, default=DEFAULT_GXX)
    a = p.parse_args(argv)
    exe = build(a.gxx)
    bad = 0
    for name, overrides in PRESETS.items():
        t_py = t_cpp = 0.0
        diffs = 0
        for seed in range(a.seeds):
            t0 = time.perf_counter()
            expected = python(seed, overrides)
            t1 = time.perf_counter()
            got = native(exe, seed, overrides)
            t2 = time.perf_counter()
            t_py += t1 - t0
            t_cpp += t2 - t1
            if expected is None or got is None:
                same = expected is None and got is None
            else:
                same = {k: v for k, v in expected.items()} == {k: v for k, v in got.items() if v != "-"}
            if not same:
                diffs += 1
                if diffs <= 3:
                    print(f"  {name} seed {seed} : DIFFÉRENT")
                    if expected and got:
                        for k in sorted(set(expected) | set(got)):
                            if expected.get(k) != got.get(k):
                                print(f"    {k}: python={expected.get(k)} natif={got.get(k)}")
                                break
        bad += diffs
        print(f"{name:12} {a.seeds - diffs}/{a.seeds} identiques  (python {t_py:.1f} s, natif {t_cpp:.1f} s avec lancement)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
