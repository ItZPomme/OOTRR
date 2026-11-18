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
"""

from __future__ import annotations

PROTOCOL = 1
DEFAULT_PORT = 38300
MAX_LINE = 1024

HELLO, CHECK, SYNC, GOAL, PING = "HELLO", "CHECK", "SYNC", "GOAL", "PING"
WELCOME, ITEM, SENT, INFO, ERROR, PONG = "WELCOME", "ITEM", "SENT", "INFO", "ERROR", "PONG"

# ERROR codes
E_PROTOCOL = "protocol"   # unknown protocol version or malformed message
E_ROOM = "room"           # the game's seed is not this multiworld (room hash)
E_SLOT = "slot"           # no such player
E_TAKEN = "taken"         # another game is already connected as this player
E_HELLO = "hello"         # a message before HELLO


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
