"""Multiworld bridge for Longshot: Longshot's control pipe <-> the multiworld server (docs/MULTIWORLD.md).

    python -m ootrr.tools.mw_mod output/mw.json --slot 2 --romfs ROMFS --mod-out "<Longshot>/mods"   # once
    (start Longshot with HOS_CONTROL=1 and HOS_CONTROL_MEM=rw, load the save)
    python -m ootrr.tools.mw_longshot output/mw.json --slot 2 --server 192.168.1.10:38300

- Found locations: a chest holding another player's item adds 1 to its saved Int (`multiworld.location_counter`);
  the `oot` events of Longshot list it among the changed values -> `CHECK`. At connection and after each loading
  every watched Int is read again (locations found while the bridge was off, an older save reloaded).
- Received items: `ITEM <index>` are given in order by `ItemGiver` (queued GameData writes) when Link is in play,
  not in a scene or a loading; the saved Int `OoTRR.MW.Received` counts the applied ones (`SYNC`). Reloading an
  older save lowers it: the server sends the missing items again.
- No GOAL yet: the game's end is not watched (no release when a Longshot player finishes).
"""

from __future__ import annotations

import argparse
import queue
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .. import multiworld as mw
from .. import mw_protocol as P
from ..formats.gamedata import flag_hash
from ..mw_items import ItemGiver


class BridgeError(RuntimeError):
    pass


class Bridge:
    """The bridge's decisions, without I/O: `game` is a `Longshot` (or a fake), `send(*fields)` sends a message to
    the server. Feed it server messages (`on_server`) and Longshot `oot` events (`on_game`)."""

    def __init__(self, game: Any, watch: dict[str, str], room_hash: str, slot: int, names: list[str],
                 send: Callable[..., None], say: Callable[[str], None] = print) -> None:
        self.game, self.send, self.say = game, send, say
        self.watch = watch  # saved Int -> location
        self.by_hash = {flag_hash(name): loc for name, loc in watch.items()}
        self.room_hash, self.slot, self.names = room_hash, slot, names
        self.giver = ItemGiver(game)
        self.pending: dict[int, tuple[int, str, str]] = {}  # received index -> (from slot, item, location)
        self.sent: set[str] = set()
        self.ready = False  # WELCOME received
        # last count written: a queued write is applied at the game's next frame, a read before that is stale
        self.written: int | None = None

    # ---- connection ----
    def hello(self) -> None:
        self.send(P.HELLO, P.PROTOCOL, self.room_hash, self.slot)

    def received_count(self) -> int:
        value = self.game.get_int(mw.RECEIVED_COUNTER)
        if value is None:
            raise BridgeError(f"no {mw.RECEIVED_COUNTER} in the game: it does not run this player's multiworld mod")
        return value

    def scan(self) -> None:
        """Reads every watched Int (bridge started late, save reloaded): CHECK for the found ones."""
        for name, loc in self.watch.items():
            if (self.game.get_int(name) or 0) > 0:
                self._check(loc)

    def _check(self, loc: str) -> None:
        if loc not in self.sent:
            self.sent.add(loc)
            self.send(P.CHECK, loc)

    # ---- messages ----
    def on_server(self, msg: list[str]) -> None:
        cmd, args = msg[0], msg[1:]
        if cmd == P.WELCOME:
            self.ready = True
            self.say(f"connected as {self.names[self.slot - 1]} (player {self.slot})")
            self.send(P.SYNC, self.received_count())
            self.scan()
        elif cmd == P.ITEM:
            index, finder, item, loc = int(args[0]), int(args[1]), args[2], args[3]
            self.pending[index] = (finder, item, loc)
        elif cmd == P.SENT:
            self.say(f"sent {args[1]} to {self.names[int(args[0]) - 1]} ({args[2]})")
        elif cmd == P.INFO:
            self.say(args[0])
        elif cmd == P.ERROR:
            raise BridgeError(f"server: {' '.join(args)}")

    def on_game(self, game: dict[str, Any]) -> None:
        """One `oot` event (its "game" object): found locations, then received items if Link is free."""
        for h, value in (game.get("changed") or {}).items():
            loc = self.by_hash.get(int(h, 16))
            if loc is not None and isinstance(value, int) and value > 0:
                self._check(loc)
        if self.ready and not game.get("event") and not game.get("loading"):
            self.apply()

    def apply(self) -> int:
        """Gives the received items the game does not count yet, in order; returns how many."""
        count = self.received_count()
        if self.written is not None:
            count = max(count, self.written)
        given = 0
        while count in self.pending:
            finder, item, loc = self.pending.pop(count)
            writes = self.giver.give(item)
            self.game.set_int(mw.RECEIVED_COUNTER, count + 1)
            count += 1
            self.written = count
            given += 1
            self.say(f"received {item} from {self.names[finder - 1]} ({loc}): {'; '.join(writes)}")
        if given:
            self.send(P.SYNC, count)
        for index in [i for i in self.pending if i < count]:
            del self.pending[index]  # already applied (an older copy sent again)
        return given

    def reloaded(self) -> None:
        """After a loading: the save may be another one, read everything again."""
        self.sent.clear()
        self.written = None
        if self.ready:
            self.send(P.SYNC, self.received_count())
            self.scan()


class ServerLink:
    """TCP connection to the server in a thread: received lines go to `inbox`."""

    def __init__(self, host: str, port: int, inbox: queue.Queue) -> None:
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(None)
        self.inbox = inbox
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def send(self, *fields: object) -> None:
        with self.lock:
            self.sock.sendall(P.encode(*fields))

    def _read(self) -> None:
        buf = b""
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self.inbox.put(P.decode(line + b"\n"))
        except (OSError, P.ProtocolError):
            pass
        self.inbox.put(None)  # connection lost


def run(args) -> int:
    from ..longshot_control import ControlError, Longshot

    result = mw.load(args.file)
    slot = args.slot
    if not 1 <= slot <= len(result.players):
        print(f"error: player 1 to {len(result.players)}", file=sys.stderr)
        return 1
    watch = mw.remote_watch(result, slot - 1)
    host, _, port = args.server.rpartition(":")
    inbox: queue.Queue = queue.Queue()
    try:
        game = Longshot(args.pipe)
    except ControlError as exc:
        print(f"error: {exc}\nStart Longshot with HOS_CONTROL={args.pipe} and HOS_CONTROL_MEM=rw.", file=sys.stderr)
        return 1
    if game.call("status").get("protocol") != 1:
        print("warning: Longshot's control protocol is not 1: this bridge may not understand it")
    link = ServerLink(host or "127.0.0.1", int(port or P.DEFAULT_PORT), inbox)
    bridge = Bridge(game, watch, mw.room_hash(result), slot, [p.name for p in result.players], link.send)
    print(f"multiworld {bridge.room_hash}, player {slot} {bridge.names[slot - 1]}: {len(watch)} locations watched")
    bridge.hello()
    game.call("subscribe", events=["oot", "state"], every=args.every, changes=True)
    loading = False
    for ev in game.events():
        while not inbox.empty():
            msg = inbox.get()
            if msg is None:
                raise BridgeError("connection to the server lost")
            bridge.on_server(msg)
        if ev.get("event") == "oot":
            g = ev.get("game") or {}
            if loading and not g.get("loading"):
                bridge.reloaded()
            loading = bool(g.get("loading"))
            bridge.on_game(g)
        elif ev.get("event") == "state" and ev.get("state") != "play":
            loading = True
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ootrr.tools.mw_longshot", description=__doc__.splitlines()[0])
    ap.add_argument("file", help="multiworld file")
    ap.add_argument("--slot", type=int, required=True, help="your player number (from 1)")
    ap.add_argument("--server", default=f"127.0.0.1:{P.DEFAULT_PORT}", help="host:port of the multiworld server")
    ap.add_argument("--pipe", default="1", help="Longshot's HOS_CONTROL value (default 1)")
    ap.add_argument("--every", type=int, default=10, help="frames between two looks at the game (default 10)")
    args = ap.parse_args(argv)
    while True:
        try:
            return run(args)
        except BridgeError as exc:
            print(f"bridge: {exc}", file=sys.stderr)
            if "server:" in str(exc) or "does not run" in str(exc):
                return 1
        except (OSError, ConnectionError) as exc:
            print(f"bridge: {exc}", file=sys.stderr)
        print("retrying in 5 s...")
        time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
