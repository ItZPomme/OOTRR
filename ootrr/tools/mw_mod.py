"""Builds one player's mod of a multiworld (PC-built mod, for Longshot or Eden; docs/MULTIWORLD.md).

    python -m ootrr.tools.mw_mod output/mw.json --slot 2 --romfs ROMFS --mod-out "<Longshot>/mods"
    python -m ootrr.tools.mw_mod output/mw.json --slot 2 --romfs ROMFS --install          # Eden

Own items as in a solo seed; a chest holding another player's item gives a placeholder and raises a saved Int
that the bridge watches (`multiworld.slot_patch`). Close the game first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import multiworld as mw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ootrr.tools.mw_mod", description=__doc__.splitlines()[0])
    ap.add_argument("file", help="multiworld file (python -m ootrr.multiworld), or a player's data file (joining)")
    ap.add_argument("--slot", type=int, help="player number (from 1); not needed with a player's data file")
    ap.add_argument("--romfs", required=True, help="RomFS used to build the mod (Longshot's own romfs folder works)")
    ap.add_argument("--mod-name", default="OoTRR")
    ap.add_argument("--mod-out", help="copy the mod into this mods folder (Longshot: <Longshot>/mods)")
    ap.add_argument("--install", action="store_true", help="install into Eden")
    ap.add_argument("--out", default="output", help="where to write the patch (default output)")
    args = ap.parse_args(argv)
    from ..__main__ import build_mod

    try:
        data = mw.load_slot(args.file, args.slot)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.slot = data.slot + 1
    patch = mw.slot_patch(data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    patch_path = out / f"mw_{patch['multiworld']['hash']}_p{args.slot}_patch.json"
    patch_path.write_text(json.dumps(patch, ensure_ascii=False, indent=1), encoding="utf-8")
    info = patch["multiworld"]
    print(f"multiworld {info['hash']}, player {args.slot} {info['players'][args.slot - 1]}: "
          f"{len(info['locations'])} chests hold other players' items; patch {patch_path}")
    build_mod(patch, Path(args.romfs), args.mod_name, args.install, Path(args.mod_out) if args.mod_out else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
