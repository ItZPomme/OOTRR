"""Host a multiworld from the command line: server + port opened by UPnP when possible + the room code to share.

    python -m ootrr.tools.mw_host output/mw.json [--port 38300] [--address A.B.C.D] [--no-upnp]

The desktop app does the same from its Multiworld window (tools.mw_app). Ctrl+C stops the server (and closes the
port on the router).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .. import mw_protocol as P
from ..mw_session import Host, SessionError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ootrr.tools.mw_host", description=__doc__.splitlines()[0])
    ap.add_argument("file", help="multiworld file (python -m ootrr.multiworld)")
    ap.add_argument("--port", type=int, default=P.DEFAULT_PORT)
    ap.add_argument("--address", help="address to put in the code (default: the router's internet address by UPnP, "
                                      "else this PC's local address)")
    ap.add_argument("--no-upnp", action="store_true", help="do not ask the router to open the port")
    args = ap.parse_args(argv)
    host = Host(Path(args.file), port=args.port, address=args.address, use_upnp=not args.no_upnp,
                log=lambda line: print(line, flush=True))
    try:
        code = host.start()
    except (SessionError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for note in host.notes:
        print(note)
    print(f"\nRoom code: {code}\n(the others: Multiworld > Join in the app, or python -m ootrr.tools.mw_join {code})")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        host.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
