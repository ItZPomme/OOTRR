"""Multiworld protocol: what the games and the server say to each other (see docs/MULTIWORLD.md).

TCP, one message per line, UTF-8, fields separated by a tab (location names hold spaces). The first field is the
command. Simple enough to be read by the native module (C++, no JSON) and by a PC bridge (Longshot).

Game -> server
    HELLO   <protocol> <room hash> <slot> [<name>]   first message; slot = player number, from 1
    CHECK   <location name>                          a location of this world was found
    SYNC    <count>                                  the game has applied <count> received items (saved in the game)
    GOAL                                             this player has beaten the game
    PING
Server -> game
    WELCOME <slot> <players> <name 1> ... <name N>  after HELLO
    ITEM    <index> <from slot> <item> <location>    received item number <index> (from 0), sent again after each
                                                     SYNC until the game counts it; the game ignores an index it
                                                     already applied
    SENT    <to slot> <item> <location>              the item found at our location went to that player
    INFO    <text>                                   a line to show (another player found something, finished...)
    ERROR   <code> <text>                            then the server closes the connection
    PONG

Joining (the desktop app, before any game; a room code gives the address and the room id, `ootrr.mw_code`: the
room hash, or the id of the waiting room the multiworld was generated from)
    ROOM    <protocol> <room id>                     -> HASH <room hash>, PLAYERS <name 1> ... <name N>
                                                        (waiting room: WAITING <name 1> ... <name N>, the players
                                                        joined so far, the host first)
    JOIN    <protocol> <room id> <name> <settings>   waiting room only: join with these settings (a settings string,
                                                     `ootrr.race`); the same name again replaces its settings
                                                     -> WAITING ...
    GETSLOT <protocol> <room id> <slot>              -> HASH <room hash>, DATA <i> <n> <chunk> (i = 0..n-1), then the
                                                        server closes: that player's data (`multiworld.slot_to_json`,
                                                        zlib, base64), never the other worlds
"""

from __future__ import annotations

PROTOCOL = 1
DEFAULT_PORT = 38300
MAX_LINE = 1024

HELLO, CHECK, SYNC, GOAL, PING = "HELLO", "CHECK", "SYNC", "GOAL", "PING"
ROOM, GETSLOT, PLAYERS, DATA = "ROOM", "GETSLOT", "PLAYERS", "DATA"
JOIN, WAITING, HASH = "JOIN", "WAITING", "HASH"
MAX_PLAYERS = 16  # players in a waiting room
CHUNK = 900  # base64 characters per DATA line
WELCOME, ITEM, SENT, INFO, ERROR, PONG = "WELCOME", "ITEM", "SENT", "INFO", "ERROR", "PONG"

# ERROR codes
E_PROTOCOL = "protocol"   # unknown protocol version or malformed message
E_ROOM = "room"           # the game's seed is not this multiworld (room hash)
E_SLOT = "slot"           # no such player
E_TAKEN = "taken"         # another game is already connected as this player
E_HELLO = "hello"         # a message before HELLO
E_WAITING = "waiting"     # the multiworld is not generated yet (waiting room)
E_STARTED = "started"     # the waiting room is closed: the multiworld is generated (or being generated)
E_SETTINGS = "settings"   # settings string not readable by the host's OoTRR
E_NAME = "name"           # empty or invalid player name, or the waiting room is full


def pack(obj) -> list[str]:
    """JSON -> zlib -> base64, cut into DATA chunks."""
    import base64
    import json
    import zlib
    text = base64.b64encode(zlib.compress(json.dumps(obj, ensure_ascii=False).encode("utf-8"), 9)).decode("ascii")
    return [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]


def unpack(chunks: list[str]):
    import base64
    import json
    import zlib
    return json.loads(zlib.decompress(base64.b64decode("".join(chunks))).decode("utf-8"))


class ProtocolError(ValueError):
    pass


def encode(*fields: object) -> bytes:
    parts = [str(f) for f in fields]
    for p in parts:
        if "\t" in p or "\n" in p or "\r" in p:
            raise ProtocolError(f"field with a tab or a line break: {p!r}")
    line = ("\t".join(parts) + "\n").encode("utf-8")
    if len(line) > MAX_LINE:
        raise ProtocolError("line too long")
    return line


def decode(line: bytes) -> list[str]:
    if len(line) > MAX_LINE:
        raise ProtocolError("line too long")
    text = line.decode("utf-8", errors="strict").rstrip("\r\n")
    if not text:
        raise ProtocolError("empty line")
    return text.split("\t")
