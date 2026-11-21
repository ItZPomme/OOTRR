"""Join a multiworld from the command line: room code -> your player's data file (never the other worlds).

    python -m ootrr.tools.mw_join CODE                 # the players' names
    python -m ootrr.tools.mw_join CODE --player Bob    # saves Bob's data: output/mw_<hash>_p<n>.json

Then: python -m ootrr.tools.mw_mod <that file> --romfs ... --mod-out <Longshot>/mods, and
python -m ootrr.tools.mw_longshot <that file> --server <host>:<port>. The desktop app's Multiworld window does all of
it (tools.mw_app).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..mw_code import CodeError, decode
from ..mw_session import SessionError, join, room_players


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ootrr.tools.mw_join", description=__doc__.splitlines()[0])
    ap.add_argument("code", help="room code given by the host")
    ap.add_argument("--player", help="your name (or number from 1)")
    ap.add_argument("--out", default="output", help="folder of the player data file (default output)")
    args = ap.parse_args(argv)
    try:
        room = decode(args.code)
        if not args.player:
            print("players:", ", ".join(f"{i + 1} {n}" for i, n in enumerate(room_players(room))))
            return 0
        room, data, path = join(args.code, args.player, Path(args.out))
    except (CodeError, SessionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"player {data.slot + 1} {data.names[data.slot]} of multiworld {data.room_hash}: {path}")
    print(f"server: {room.host}:{room.port}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
