"""Multiworld server: relays the items between the games of a multiworld (protocol: `ootrr.mw_protocol`).

    python -m ootrr.multiworld --players 2 --names Alice,Bob --seed 1234 -o output/mw.json
    python -m ootrr.tools.mw_server output/mw.json [--host 0.0.0.0] [--port 38300]

One player runs it; the others connect to that PC (port open on the router, or a VPN such as Tailscale/ZeroTier).
The progress (found locations, items sent to each player) is saved next to the multiworld file
(`<file>.state.json`) after every change: the server can be stopped and started again, the games resume.
Every exchange is written to `<file>.log` ("Bot -> Pomme: Hookshot (GF Rupee Chest)", the items' names from the
game's texts, `ootrr.mw_log`) and sent to every game, whose bridge logs it too.

When a player beats the game (GOAL), the items of their world that other players still need are sent to them
("release", like Archipelago), unless `--no-release`.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .. import multiworld as mw
from .. import mw_protocol as P
from ..mw_log import Log, exchange, labeller, plain_label


@dataclass
class Event:
    """Something to tell the games after a change of the room."""
    items: list[tuple[int, int]] = field(default_factory=list)       # (receiver slot index, received index)
    sent: list[tuple[int, int, str, str]] = field(default_factory=list)  # (finder, receiver, item, location)
    info: list[str] = field(default_factory=list)


class Room:
    """State of a multiworld (no network here: `Server` relays it). Slots are indexes from 0 here, numbers from
    1 in the protocol."""

    def __init__(self, result: mw.MultiResult, state_path: Path | None = None, release: bool = True,
                 label=None) -> None:
        self.result = result
        self.label = label or plain_label  # item actor -> readable name (mw_log)
        self.hash = mw.room_hash(result)
        self.names = [p.name for p in result.players]
        self.state_path = state_path
        self.release = release
        n = len(self.names)
        self.checked: list[set[str]] = [set() for _ in range(n)]
        self.received: list[list[tuple[int, str, str]]] = [[] for _ in range(n)]  # (finder, item, location)
        self.goal = [False] * n
        if state_path and state_path.exists():
            self._load(state_path)

    # ---- persistence ----
    def _load(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("hash") != self.hash:
            raise ValueError(f"{path.name} belongs to another multiworld (hash {data.get('hash')}, not {self.hash})")
        self.checked = [set(c) for c in data["checked"]]
        self.received = [[(int(f), i, l) for f, i, l in r] for r in data["received"]]
        self.goal = [bool(g) for g in data["goal"]]

    def save(self) -> None:
        if not self.state_path:
            return
        data = {"hash": self.hash, "checked": [sorted(c) for c in self.checked],
                "received": [[list(r) for r in rs] for rs in self.received], "goal": self.goal}
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.state_path)  # never a half-written state if the server stops

    # ---- changes ----
    def check(self, slot: int, location: str, event: Event | None = None) -> Event:
        """A location of `slot`'s world was found. Unknown or already found: nothing happens."""
        event = event or Event()
        placed = self.result.placements[slot].get(location)
        if placed is None or location in self.checked[slot]:
            return event
        self.checked[slot].add(location)
        owner, item = placed
        if owner != slot:
            self.received[owner].append((slot, item, location))
            event.items.append((owner, len(self.received[owner]) - 1))
            event.sent.append((slot, owner, item, location))
            event.info.append(exchange(self.names[slot], self.names[owner], self.label(item), location))
        return event

    def finish(self, slot: int) -> Event:
        event = Event()
        if self.goal[slot]:
            return event
        self.goal[slot] = True
        event.info.append(f"{self.names[slot]} has beaten the game")
        if self.release:
            for location, (owner, _) in sorted(self.result.sent(slot).items()):
                if not self.goal[owner]:
                    self.check(slot, location, event)
        return event


class LobbyError(ValueError):
    def __init__(self, code: str, text: str) -> None:
        super().__init__(text)
        self.code = code


class Lobby:
    """Waiting room before the multiworld is generated (the desktop app's host): the players who joined so far,
    each with their own settings (sent as a settings string, `ootrr.race`), the host first. Joins come from the
    server's thread, the host's window reads it: hence the lock."""

    MAX_NAME = 24

    def __init__(self, room_id: str, host_name: str, host_settings: dict) -> None:
        self.id = room_id.upper()
        self.lock = threading.Lock()
        self.open = True
        self.players: dict[str, dict] = {}
        self.players[self.check_name(host_name)] = dict(host_settings)

    @classmethod
    def check_name(cls, name: str) -> str:
        name = " ".join(str(name).split())
        if not name or len(name) > cls.MAX_NAME or any(ord(c) < 32 for c in name):
            raise LobbyError(P.E_NAME, f"a player name has 1 to {cls.MAX_NAME} characters")
        return name

    def join(self, name: str, settings_string: str) -> list[str]:
        """Adds a player (or replaces the settings of the player who joined under that name); the names."""
        from .. import race
        name = self.check_name(name)
        try:
            settings, _ = race.decode(settings_string)
        except (race.SettingsStringError, ValueError) as exc:
            raise LobbyError(P.E_SETTINGS, f"settings not readable by the host's OoTRR ({exc})") from None
        with self.lock:
            if not self.open:
                raise LobbyError(P.E_STARTED, "the host has already started the multiworld")
            host = next(iter(self.players))
            same = next((n for n in self.players if n.casefold() == name.casefold()), None)
            if same == host:
                raise LobbyError(P.E_NAME, f"{host} is the host's name: pick another one")
            if same is None and len(self.players) >= P.MAX_PLAYERS:
                raise LobbyError(P.E_NAME, f"the waiting room is full ({P.MAX_PLAYERS} players)")
            self.players[same or name] = settings
            return list(self.players)

    def remove(self, name: str) -> None:
        with self.lock:
            if name != next(iter(self.players)):
                self.players.pop(name, None)

    def set_host_settings(self, settings: dict) -> None:
        with self.lock:
            self.players[next(iter(self.players))] = dict(settings)

    def names(self) -> list[str]:
        with self.lock:
            return list(self.players)

    def players_copy(self) -> list[tuple[str, dict]]:
        with self.lock:
            return [(n, dict(s)) for n, s in self.players.items()]

    def close(self) -> list[tuple[str, dict]]:
        """No more joins (the host generates): the players and their settings, in order."""
        with self.lock:
            self.open = False
        return self.players_copy()

    def reopen(self) -> None:
        """The generation failed: players may join again or change their settings."""
        with self.lock:
            self.open = True


class Server:
    def __init__(self, room: Room | None = None, lobby: Lobby | None = None) -> None:
        self.room = room
        self.lobby = lobby
        self.aliases: set[str] = set()  # other ids of this multiworld (the waiting room it was generated from)
        self.clients: dict[int, asyncio.StreamWriter] = {}

    def _knows(self, room_id: str) -> bool:
        room_id = room_id.upper()
        return ((self.room is not None and room_id == self.room.hash) or room_id in self.aliases
                or (self.lobby is not None and room_id == self.lobby.id))

    def log(self, text: str) -> None:
        print(text, flush=True)

    async def _send(self, slot: int, *fields: object) -> None:
        writer = self.clients.get(slot)
        if writer is None:
            return
        try:
            writer.write(P.encode(*fields))
            await writer.drain()
        except (ConnectionError, OSError):
            self.clients.pop(slot, None)

    async def _send_item(self, slot: int, index: int) -> None:
        finder, item, location = self.room.received[slot][index]
        await self._send(slot, P.ITEM, index, finder + 1, item, location)

    async def _publish(self, event: Event) -> None:
        if not (event.items or event.sent or event.info):
            return
        self.room.save()
        for owner, index in event.items:
            await self._send_item(owner, index)
        for finder, owner, item, location in event.sent:
            await self._send(finder, P.SENT, owner + 1, item, location)
        for text in event.info:
            self.log(text)
            for slot in list(self.clients):
                await self._send(slot, P.INFO, text)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        slot: int | None = None

        async def error(code: str, text: str) -> None:
            writer.write(P.encode(P.ERROR, code, text))
            with contextlib.suppress(ConnectionError, OSError):
                await writer.drain()

        try:
            while True:
                try:
                    line = await reader.readuntil(b"\n")
                except asyncio.LimitOverrunError:
                    await error(P.E_PROTOCOL, "line too long")
                    return
                except (asyncio.IncompleteReadError, ConnectionError, OSError):
                    return  # closed or reset by the game (Windows: WinError 64)
                try:
                    msg = P.decode(line)
                except (P.ProtocolError, UnicodeDecodeError) as exc:
                    await error(P.E_PROTOCOL, str(exc))
                    return
                cmd, args = msg[0], msg[1:]
                if slot is None:
                    if cmd in (P.ROOM, P.GETSLOT, P.JOIN):  # joining from the desktop app (no game yet)
                        await self._join(cmd, args, writer, error)
                        return
                    if cmd != P.HELLO:
                        await error(P.E_HELLO, "HELLO first")
                        return
                    if self.room is None:
                        await error(P.E_WAITING, "the multiworld is not generated yet")
                        return
                    slot = await self._hello(args, writer, error)
                    if slot is None:
                        return
                    continue
                if cmd == P.CHECK and len(args) == 1:
                    await self._publish(self.room.check(slot, args[0]))
                elif cmd == P.SYNC and len(args) == 1 and args[0].isdigit():
                    for index in range(int(args[0]), len(self.room.received[slot])):
                        await self._send_item(slot, index)
                elif cmd == P.GOAL and not args:
                    await self._publish(self.room.finish(slot))
                elif cmd == P.PING:
                    await self._send(slot, P.PONG)
                else:
                    await error(P.E_PROTOCOL, f"bad message {cmd}")
                    return
        finally:
            if slot is not None and self.clients.get(slot) is writer:
                del self.clients[slot]
                self.log(f"{self.room.names[slot]} disconnected")
            with contextlib.suppress(ConnectionError, OSError):
                writer.close()

    async def _join(self, cmd: str, args: list[str], writer: asyncio.StreamWriter, error) -> None:
        """ROOM: the players' names (or the waiting room's); JOIN: a player joins the waiting room with their
        settings; GETSLOT: one player's data (`multiworld.slot_data`), never the other worlds."""
        if len(args) < 2 or args[0] != str(P.PROTOCOL):
            await error(P.E_PROTOCOL, f"protocol {P.PROTOCOL} expected")
            return
        if not self._knows(args[1]):
            await error(P.E_ROOM, "this server runs another multiworld")
            return
        if cmd == P.JOIN:
            if len(args) != 4:
                await error(P.E_PROTOCOL, "JOIN <protocol> <room id> <name> <settings>")
                return
            if self.room is not None or self.lobby is None:
                await error(P.E_STARTED, "the host has already started the multiworld")
                return
            try:
                names = self.lobby.join(args[2], args[3])
            except LobbyError as exc:
                await error(exc.code, str(exc))
                return
            self.log(f"{Lobby.check_name(args[2])} joined the waiting room (players: {', '.join(names)})")
            writer.write(P.encode(P.WAITING, *names))
        elif self.room is None:
            if cmd == P.GETSLOT:
                await error(P.E_WAITING, "the multiworld is not generated yet")
                return
            writer.write(P.encode(P.WAITING, *self.lobby.names()))
        elif cmd == P.ROOM:
            writer.write(P.encode(P.HASH, self.room.hash))
            writer.write(P.encode(P.PLAYERS, *self.room.names))
        else:
            if len(args) != 3 or not args[2].isdigit() or not 1 <= int(args[2]) <= len(self.room.names):
                await error(P.E_SLOT, f"player 1 to {len(self.room.names)}")
                return
            slot = int(args[2]) - 1
            writer.write(P.encode(P.HASH, self.room.hash))
            chunks = P.pack(mw.slot_to_json(mw.slot_data(self.room.result, slot)))
            for i, chunk in enumerate(chunks):
                writer.write(P.encode(P.DATA, i, len(chunks), chunk))
            self.log(f"{self.room.names[slot]}'s data sent (joining)")
        with contextlib.suppress(ConnectionError, OSError):
            await writer.drain()

    async def _hello(self, args: list[str], writer: asyncio.StreamWriter, error) -> int | None:
        if len(args) < 3 or args[0] != str(P.PROTOCOL):
            await error(P.E_PROTOCOL, f"protocol {P.PROTOCOL} expected")
            return None
        if args[1] != self.room.hash:
            await error(P.E_ROOM, f"this server runs multiworld {self.room.hash}")
            return None
        if not args[2].isdigit() or not 1 <= int(args[2]) <= len(self.room.names):
            await error(P.E_SLOT, f"player 1 to {len(self.room.names)}")
            return None
        slot = int(args[2]) - 1
        old = self.clients.get(slot)
        if old is not None:  # the same game reconnecting (the old connection may be dead): the new one wins
            with contextlib.suppress(ConnectionError, OSError):
                old.close()
        self.clients[slot] = writer
        self.log(f"{self.room.names[slot]} connected")
        await self._send(slot, P.WELCOME, slot + 1, len(self.room.names), *self.room.names)
        return slot

    async def serve(self, host: str, port: int) -> None:
        server = await asyncio.start_server(self.handle, host, port, limit=P.MAX_LINE)
        names = ", ".join(f"{i + 1} {n}" for i, n in enumerate(self.room.names))
        self.log(f"multiworld {self.room.hash} on {host}:{port}; players: {names}")
        async with server:
            await server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ootrr.tools.mw_server", description=__doc__.splitlines()[0])
    ap.add_argument("file", help="multiworld file (python -m ootrr.multiworld)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=P.DEFAULT_PORT)
    ap.add_argument("--no-release", action="store_true", help="keep a finished player's items in their world")
    ap.add_argument("--log", help="log of every exchange (default: <file>.log, appended)")
    ap.add_argument("--romfs", help="RomFS for the items' names (default: Longshot's own, else actor names)")
    args = ap.parse_args(argv)
    path = Path(args.file)
    try:
        room = Room(mw.load(path), path.with_suffix(".state.json"), release=not args.no_release,
                    label=labeller(args.romfs))
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    server = Server(room)
    server.log = Log(args.log or path.with_suffix(".log"), echo=lambda line: print(line, flush=True))
    try:
        asyncio.run(server.serve(args.host, args.port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
