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
- Log: every exchange of the multiworld (the server's INFO lines: "Bot -> Pomme: Hookshot (GF Rupee Chest)") and
  each item given in this game, in `<file>_p<slot>.log` (`--log`), with the items' names from the game's texts.
- Navi says each given item in a balloon (`mw_navi.Announcer`), one at a time.
- No GOAL yet: the game's end is not watched (no release when a Longshot player finishes).
"""

from __future__ import annotations

import argparse
import contextlib
import queue
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .. import multiworld as mw
from .. import mw_protocol as P
from ..formats.gamedata import flag_hash
from ..longshot_control import ControlError
from ..mw_items import (POUCH_ACTION_ACK, POUCH_ACTION_CODES, POUCH_ACTION_REQUEST, ItemGiver)
from ..mw_log import Log, labeller, plain_label
from ..mw_navi import Announcer, layout


class BridgeError(RuntimeError):
    pass


@dataclass
class _PendingPouchAction:
    index: int
    finder: int
    item: str
    location: str
    received_item: str
    code: int
    writes: list[str]
    phase: str = "clear"


class Bridge:
    """The bridge's decisions, without I/O: `game` is a `Longshot` (or a fake), `send(*fields)` sends a message to
    the server. Feed it server messages (`on_server`) and Longshot `oot` events (`on_game`)."""

    def __init__(self, game: Any, watch: dict[str, str], room_hash: str, slot: int, names: list[str],
                 send: Callable[..., None], say: Callable[[str], None] = print,
                 label: Callable[[str], str] | None = None, fixed: Iterable[str] = (),
                 incoming: Iterable[tuple[int, str]] = ()) -> None:
        self.game, self.send, self.say = game, send, say
        self.watch = watch  # saved Int -> location
        self.by_hash = {flag_hash(name): loc for name, loc in watch.items()}
        self.room_hash, self.slot, self.names = room_hash, slot, names
        self.giver = ItemGiver(game, fixed=fixed)  # fixed: multiworld.fixed_chains
        self.label = label or plain_label
        self.navi = Announcer(game, layout(incoming), names)  # incoming: multiworld.SlotData.incoming
        self.navi_error = self.apply_error = ""  # last one said
        self.pending: dict[int, tuple[int, str, str]] = {}  # received index -> (from slot, item, location)
        self.pouch_action: _PendingPouchAction | None = None
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
            pass  # the server's INFO line for the same exchange is logged
        elif cmd == P.INFO:
            self.say(args[0])  # every exchange of the multiworld (mw_log.exchange), and the players' goals
        elif cmd == P.ERROR:
            raise BridgeError(f"server: {' '.join(args)}")

    def on_game(self, game: dict[str, Any]) -> None:
        """One `oot` event (its "game" object): found locations, then received items if Link is free."""
        for h, value in (game.get("changed") or {}).items():
            loc = self.by_hash.get(int(h, 16))
            if loc is not None and isinstance(value, int) and value > 0:
                self._check(loc)
        if self.ready and not game.get("event") and not game.get("loading"):
            # write queue busy: the next look at the game tries again (not a reconnection: seen 2026-11-25, the
            # bridge reconnected every 12 s for minutes and the item never came)
            try:
                self.apply()
            except ControlError as exc:
                if str(exc) != self.apply_error:
                    self.apply_error = str(exc)
                    self.say(f"  item not given yet, retrying: {exc}")
                return
            self.apply_error = ""
            try:
                self.navi.step()
            except ControlError as exc:
                if str(exc) != self.navi_error:
                    self.navi_error = str(exc)
                    self.say(f"  Navi: {exc}")

    def apply(self) -> int:
        """Gives the received items the game does not count yet, in order (GameData writes, `ItemGiver`);
        returns how many."""
        count = self.received_count()
        if self.written is not None:
            count = max(count, self.written)
        given = 0
        if self.pouch_action is not None:
            action = self.pouch_action
            ack = self.game.get_int(POUCH_ACTION_ACK)
            if ack is None:
                raise BridgeError(f"no {POUCH_ACTION_ACK} in the game: it does not run this player's multiworld mod")
            if action.phase == "clear":
                if ack != 0:
                    self.game.set_int(POUCH_ACTION_ACK, 0)
                    return 0
                self.game.set_int(POUCH_ACTION_REQUEST, action.code)
                action.phase = "await"
                return 0
            if ack != action.code:
                return 0
            self._counted(action.index)
            del self.pending[action.index]
            count = action.index + 1
            given += 1
            self.navi.add(action.finder - 1, action.received_item)
            self.say(f"  given in game: {self.label(action.item)} (from {self.names[action.finder - 1]}, "
                     f"{action.location}; {'; '.join(action.writes)})")
            self.pouch_action = None
        while count in self.pending:
            finder, item, loc = self.pending[count]
            received = self.giver.adjusted(item)
            action_code = POUCH_ACTION_CODES.get(received)
            if action_code is not None:
                writes = self.giver.give(item, defer_pouch_action=True)
                self.pouch_action = _PendingPouchAction(count, finder, item, loc, received, action_code, writes)
                self.say(f"  waiting for the game's pouch action: {self.label(received)}")
                break
            # a failed write (ControlError) keeps the item pending: given again in full later (absolute writes)
            writes = self.giver.give(item)
            self._counted(count)
            del self.pending[count]
            count += 1
            given += 1
            self.navi.add(finder - 1, received)
            self.say(f"  given in game: {self.label(item)} (from {self.names[finder - 1]}, {loc}; {'; '.join(writes)})")
        if given:
            self.send(P.SYNC, count)
        for index in [i for i in self.pending if i < count]:
            del self.pending[index]  # already applied (an older copy sent again)
        return given

    def _counted(self, index: int) -> int:
        self.game.set_int(mw.RECEIVED_COUNTER, index + 1)
        self.written = index + 1
        return index + 1

    def reloaded(self) -> None:
        """After a loading: the save may be another one, read everything again."""
        self.sent.clear()
        self.written = None
        self.navi.reloaded()
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


class Retry(Exception):
    """Not ready yet (Longshot not started, server not reachable): try again a bit later."""


def run(args, echo: Callable[[str], None] = print, stop: threading.Event | None = None) -> int:
    """The bridge until Longshot or the server goes away (BridgeError / Retry / OSError), or `stop` is set."""
    from ..longshot_control import Longshot

    data = mw.load_slot(args.file, args.slot)
    slot = data.slot + 1
    watch = mw.remote_watch(data)
    host, _, port = args.server.rpartition(":")
    inbox: queue.Queue = queue.Queue()
    try:
        game = Longshot(args.pipe, timeout=2)
    except ControlError:
        raise Retry(f"waiting for Longshot (started with HOS_CONTROL={args.pipe}, HOS_CONTROL_MEM=rw)") from None
    if game.call("status").get("protocol") != 1:
        echo("warning: Longshot's control protocol is not 1: this bridge may not understand it")
    try:
        link = ServerLink(host or "127.0.0.1", int(port or P.DEFAULT_PORT), inbox)
    except OSError as exc:
        game.close()
        raise Retry(f"cannot reach the server {args.server}: {exc}") from None
    path = Path(args.file)
    log = Log(args.log or path.with_name(f"{path.stem}_p{slot}.log"), echo=echo)
    bridge = Bridge(game, watch, data.room_hash, slot, data.names, link.send, say=log, label=labeller(args.romfs),
                    fixed=mw.fixed_chains(data), incoming=data.incoming)
    echo(f"multiworld {bridge.room_hash}, player {slot} {bridge.names[slot - 1]}: {len(watch)} locations watched")
    bridge.hello()
    game.call("subscribe", events=["oot", "state"], every=args.every, changes=True)
    loading = False
    try:
        for ev in game.events():
            if stop is not None and stop.is_set():
                return 0
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
    finally:
        game.close()
        with contextlib.suppress(OSError):
            link.sock.close()
    return 0


def run_until_stopped(file: str | Path, server: str, stop: threading.Event, echo: Callable[[str], None] = print,
                      pipe: str = "1", every: int = 10, log: str | None = None, romfs: str | None = None) -> None:
    """The bridge again and again (Longshot restarted, connection lost...) until `stop` is set; for the app."""
    args = argparse.Namespace(file=str(file), slot=None, server=server, pipe=pipe, every=every, log=log, romfs=romfs)
    waiting = None
    while not stop.is_set():
        try:
            run(args, echo, stop)
        except Retry as exc:
            if str(exc) != waiting:  # say it once, not every 5 s
                echo(str(exc))
                waiting = str(exc)
        except BridgeError as exc:
            echo(f"bridge: {exc}")
            waiting = None
            if "server:" in str(exc) or "does not run" in str(exc):
                return
        except (OSError, ConnectionError, ValueError) as exc:
            echo(f"bridge: {exc}")
            waiting = None
        stop.wait(5)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ootrr.tools.mw_longshot", description=__doc__.splitlines()[0])
    ap.add_argument("file", help="multiworld file, or your player's data file (joining)")
    ap.add_argument("--slot", type=int, help="your player number (from 1); not needed with a player's data file")
    ap.add_argument("--server", default=f"127.0.0.1:{P.DEFAULT_PORT}", help="host:port of the multiworld server")
    ap.add_argument("--pipe", default="1", help="Longshot's HOS_CONTROL value (default 1)")
    ap.add_argument("--every", type=int, default=10, help="frames between two looks at the game (default 10)")
    ap.add_argument("--log", help="log of the exchanges (default: <file>_p<slot>.log next to the file, appended)")
    ap.add_argument("--romfs", help="RomFS for the items' names (default: Longshot's own, else actor names)")
    args = ap.parse_args(argv)
    try:
        mw.load_slot(args.file, args.slot)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    while True:
        try:
            return run(args, lambda line: print(line, flush=True))
        except Retry as exc:
            print(exc, file=sys.stderr)
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
