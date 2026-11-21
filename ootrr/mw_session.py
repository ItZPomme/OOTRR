"""Hosting and joining a multiworld from a room code (docs/MULTIWORLD.md, "Joining"); used by the desktop app and
the commands `tools.mw_host` / `tools.mw_join`.

Host: the server runs in a background thread of the host's app; the port is opened on the router by UPnP when the
router allows it; the code holds the address the others reach (`mw_code`).
Join: with the code, ask the host's server for the players' names, then for one player's data (`GETSLOT`: that
player's world only, no spoiler of the others), saved as a player data file that `tools.mw_mod` and the bridge read.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import multiworld as mw
from . import mw_protocol as P
from .mw_code import RoomCode, decode, encode


LEASE = 6 * 3600  # seconds the router keeps the port open (UPnP)


class SessionError(RuntimeError):
    pass


# ---- joining -------------------------------------------------------------------------------------------------

def _ask(code: RoomCode, *fields: object, timeout: float = 10.0) -> list[list[str]]:
    """One request to the host's server; its answer lines (until the server closes)."""
    try:
        sock = socket.create_connection((code.host, code.port), timeout=timeout)
    except OSError as exc:
        raise SessionError(f"cannot reach the host ({code.host}:{code.port}): {exc}. Is the host's server running, "
                           f"and its port open?") from None
    lines: list[list[str]] = []
    with sock, sock.makefile("rb") as f:
        sock.sendall(P.encode(*fields))
        for raw in f:
            msg = P.decode(raw)
            if msg[0] == P.ERROR:
                raise SessionError(f"the host refused: {' '.join(msg[1:])}")
            lines.append(msg)
    return lines


def room_players(code: str | RoomCode) -> list[str]:
    code = decode(code) if isinstance(code, str) else code
    for msg in _ask(code, P.ROOM, P.PROTOCOL, code.room_hash):
        if msg[0] == P.PLAYERS:
            return msg[1:]
    raise SessionError("the host did not send the players")


def fetch_slot(code: str | RoomCode, slot: int) -> mw.SlotData:
    """Player `slot`'s data (from 1)."""
    code = decode(code) if isinstance(code, str) else code
    chunks: dict[int, str] = {}
    total = None
    for msg in _ask(code, P.GETSLOT, P.PROTOCOL, code.room_hash, slot, timeout=30):
        if msg[0] == P.DATA:
            chunks[int(msg[1])] = msg[3] if len(msg) > 3 else ""
            total = int(msg[2])
    if total is None or len(chunks) != total:
        raise SessionError("the player data arrived incomplete")
    data = mw.slot_from_json(P.unpack([chunks[i] for i in range(total)]))
    if data.room_hash != code.room_hash:
        raise SessionError("the host sent another multiworld")
    return data


def save_slot(data: mw.SlotData, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"mw_{data.room_hash}_p{data.slot + 1}.json"
    path.write_text(json.dumps(mw.slot_to_json(data), ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def join(code: str, player: str | int, folder: Path) -> tuple[RoomCode, mw.SlotData, Path]:
    """Code + player (name or number from 1) -> the player data file, saved in `folder`."""
    room = decode(code)
    names = room_players(room)
    if isinstance(player, int) or str(player).isdigit():
        slot = int(player)
    else:
        matches = [i + 1 for i, n in enumerate(names) if n.casefold() == str(player).strip().casefold()]
        if not matches:
            raise SessionError(f"no player named {player} (players: {', '.join(names)})")
        slot = matches[0]
    if not 1 <= slot <= len(names):
        raise SessionError(f"player 1 to {len(names)}")
    data = fetch_slot(room, slot)
    return room, data, save_slot(data, folder)


# ---- hosting -------------------------------------------------------------------------------------------------

@dataclass
class Host:
    """The server of a multiworld in a background thread, the port opened by UPnP when possible, and the code."""
    file: Path
    port: int = P.DEFAULT_PORT
    address: str | None = None  # address to put in the code (default: UPnP external address, else this PC's)
    use_upnp: bool = True
    log: Callable[[str], None] = print
    code: str | None = None
    local_code: str | None = None  # same room, this PC's local address: for players on the host's own network
    notes: list[str] = field(default_factory=list)  # what the host should know (UPnP result, address used)
    _thread: threading.Thread | None = None
    _loop: asyncio.AbstractEventLoop | None = None
    _gateway: object = None
    _mapped: bool = False

    def start(self, ready_timeout: float = 10.0) -> str:
        from .mw_log import Log, labeller
        from .tools.mw_server import Room, Server

        result = mw.load(self.file)
        room = Room(result, self.file.with_suffix(".state.json"), label=labeller())
        server = Server(room)
        server.log = Log(self.file.with_suffix(".log"), echo=self.log)
        started = threading.Event()
        failure: list[BaseException] = []

        def run() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                srv = self._loop.run_until_complete(
                    asyncio.start_server(server.handle, "0.0.0.0", self.port, limit=P.MAX_LINE))
            except OSError as exc:
                failure.append(exc)
                started.set()
                return
            server.log(f"multiworld {room.hash} hosted on port {self.port}; players: "
                       + ", ".join(f"{i + 1} {n}" for i, n in enumerate(room.names)))
            started.set()
            try:
                self._loop.run_forever()
            finally:
                srv.close()
                self._loop.run_until_complete(srv.wait_closed())
                self._loop.close()

        self._thread = threading.Thread(target=run, daemon=True, name="mw-server")
        self._thread.start()
        started.wait(ready_timeout)
        if failure:
            raise SessionError(f"cannot start the server on port {self.port}: {failure[0]}")
        address = self.address or self._open_port()
        self.code = encode(RoomCode(address, self.port, room.hash))
        # players on the host's own network cannot use the internet address (most routers refuse a connection from
        # inside to their own public address, "hairpinning", seen 2026-11-21): they get a code with the local one
        self.local_code = encode(RoomCode(_lan_ip(), self.port, room.hash))
        return self.code

    def _open_port(self) -> str:
        from . import upnp

        lan = None
        if self.use_upnp:
            gw = upnp.find_gateway()
            if gw is None:
                self.notes.append("UPnP: no router answered (UPnP off on the box?). Players outside your network need "
                                  f"port {self.port} (TCP) opened on your router, or a VPN such as Tailscale/ZeroTier.")
            else:
                lan = gw.local_ip
                try:
                    try:  # a lease: the port closes by itself if the app dies without closing it
                        gw.add_mapping(self.port, gw.local_ip, self.port, "OoTRR multiworld", lease=LEASE)
                    except upnp.UpnpError:  # some routers only accept permanent mappings (error 725)
                        gw.add_mapping(self.port, gw.local_ip, self.port, "OoTRR multiworld", lease=0)
                    self._gateway, self._mapped = gw, True
                    external = gw.external_ip()
                except upnp.UpnpError as exc:
                    self.notes.append(f"UPnP: the router refused to open the port ({exc}).")
                    external = ""
                if self._mapped and upnp.is_public(external):
                    self.notes.append(f"UPnP: port {self.port} opened on the router; the code uses your internet address.")
                    return external
                if self._mapped:
                    self.notes.append("UPnP: port opened, but the router's own address is not public (4G, "
                                      "carrier-grade NAT): players outside your network will not get through.")
        lan = lan or _lan_ip()
        self.notes.append(f"The code uses your local address ({lan}): it works on your own network only, unless you "
                          "give another address (your internet address with the port opened, or a VPN address).")
        return lan

    def stop(self) -> None:
        if self._mapped and self._gateway is not None:
            try:
                self._gateway.delete_mapping(self.port)
            except OSError:
                pass
            self._mapped = False
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(5)


def _lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET address: no packet is sent, only the route is picked
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
