"""Navi says what the other players send: "You received Hookshot from Bob!" (multiworld, docs/MULTIWORLD.md).

A balloon (NaviChat, as "You OK?" after a fall) does not stop the game. Asking for one is a single GameData write: an
Enum whose value is the balloon's number (GAME_KNOWLEDGE, "Navi's balloons"). The texts are in the mod: one balloon per
(sender, item) pair the player can receive (`incoming` in the player's data), plus one per sender ("a gift from Bob")
used when there are more pairs than free balloons.

Both sides compute the same table from the player's data (`layout`): the mod builder (`patch["mw_navi"]`,
`ModBuilder._write_navi_balloons`) and the bridge (`Announcer`). `mark` names a saved Int the mod adds, so that the
bridge never asks for balloons that the installed mod does not hold (older mod, other table).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterable

DATA = Path(__file__).parent / "data" / "items.json"

REQUEST = 0x34C5D5F7  # Enum (name unknown) = balloon asked for; the game sets it back to None once shown
# balloons without parameters in the game and that no script, AI or map asks for (files, 2026-11-25; e.g. 118 is asked
# for by a script): (first, last) ranges
_FREE = ((9, 9), (11, 11), (13, 14), (16, 17), (22, 24), (27, 28), (35, 35), (41, 43), (55, 61), (63, 66), (68, 74),
         (76, 76), (79, 79), (81, 81), (84, 88), (90, 90), (93, 93), (99, 99), (101, 101), (103, 103), (105, 107),
         (112, 115), (117, 117), (119, 120), (123, 123), (126, 126), (129, 129), (132, 133), (137, 138), (140, 140),
         (142, 146), (152, 159), (161, 163), (165, 168), (170, 171), (176, 179), (183, 184), (187, 194), (196, 196),
         (198, 198), (201, 201), (204, 211), (213, 213), (221, 221), (224, 224), (227, 227), (231, 231), (233, 238),
         (240, 240), (243, 243), (247, 247), (249, 253), (255, 258), (261, 268), (270, 283), (286, 293), (295, 296),
         (299, 300), (302, 303), (305, 311), (313, 321), (323, 329), (333, 333), (337, 344), (346, 350), (356, 357),
         (360, 360), (363, 365), (367, 368), (370, 370), (373, 375), (379, 379), (383, 383), (386, 386), (388, 388),
         (390, 392), (395, 396), (398, 398), (410, 411), (415, 415), (418, 418), (421, 421), (424, 425), (428, 431),
         (433, 435), (438, 438), (440, 440), (442, 442), (444, 444), (446, 448), (451, 453), (455, 455), (459, 460),
         (463, 464), (471, 471), (500, 511))
NUMBERS = tuple(n for first, last in reversed(_FREE) for n in range(last, first - 1, -1))
LINE = 36  # characters of one line (33 seen on screen; 63 run off it)
_FORBIDDEN = re.compile("[\x00-\x1f\x7f]")  # control characters (0x0e starts a text tag)
_MINOR = ("Rupee", "Bundle", "MagicJar", "Heart_Piece", "Token")  # first to lose their own balloon if there are too many


def raw_value(number: int) -> str:
    return f"type{number:03d}"


def played_flag(number: int) -> str:
    """Saved Bool set by the game when the balloon is shown; it is not shown again while it is true."""
    return f"HavePlayedNaviBalloonMessage.{raw_value(number)}"


def incoming(placements: Iterable[dict[str, tuple[int, str]]], slot: int) -> list[tuple[int, str]]:
    """(sender index, item) pairs that the player may receive, sorted, without the locations. An item of a progressive
    chain is given as the next step: every step of its chain is listed."""
    data = json.loads(DATA.read_text(encoding="utf-8"))
    steps: dict[str, tuple[str, ...]] = {i: tuple(chain) for chain in data["progressive"] for i in chain}
    ocarinas = ("Item_Ocarina_Fairy", "Item_Ocarina_Time")  # mw_items.ItemGiver.adjusted
    steps.update(dict.fromkeys(ocarinas, ocarinas))
    return sorted({(sender, step) for sender, places in enumerate(placements) if sender != slot
                   for owner, item in places.values() if owner == slot
                   for step in steps.get(item, (item,))})


def layout(pairs: Iterable[tuple[int, str]]) -> dict[int, tuple[int, str]]:
    """{balloon number: (sender, item)}; item "" = the sender's balloon for any item without its own."""
    pairs = sorted(set(pairs), key=lambda p: (any(word in p[1] for word in _MINOR), p))
    senders = [(s, "") for s in sorted({s for s, _ in pairs})]
    return dict(zip(NUMBERS, senders + pairs))


def mark(table: dict[int, tuple[int, str]], names: list[str]) -> str:
    """Saved Int added by a mod holding exactly these balloons."""
    blob = json.dumps([sorted((n, s, i) for n, (s, i) in table.items()), names])
    return f"OoTRR.MW.Navi.{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:8]}"


def text(sender: str, item: str, color_on: bytes = b"", color_off: bytes = b"") -> bytes:
    """The balloon's message (UTF-8; `item` as the game writes it, "" = not named): on one line when it fits."""
    sender = _FORBIDDEN.sub("", sender).strip() or "another player"
    item = _FORBIDDEN.sub("", item).strip() or "a gift"
    gap = " " if len(f"You received {item} from {sender}!") <= LINE else "\n"
    return b"You received " + color_on + item.encode() + color_off + f"{gap}from {sender}!".encode()


class Announcer:
    """Queue of balloons, one at a time (a request made while a balloon is shown replaces it). Driven by `step`, called
    when Link is in play; `game`: get_int / get_bool / set_bool / set_enum (a `Longshot`, or a fake)."""

    SHOWN = 4.0  # seconds before the next balloon
    RETRY = 8.0  # asked for and not shown (a fight, Navi away...): asked again
    TRIES = 8
    MAX_WAITING = 20  # a long absence: only the last ones are said (the log has them all)

    def __init__(self, game: Any, table: dict[int, tuple[int, str]], names: list[str],
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.game, self.clock = game, clock
        self.mark = mark(table, names)
        self.numbers = {pair: number for number, pair in table.items()}
        self.waiting: deque[int] = deque(maxlen=self.MAX_WAITING)
        self.current: int | None = None
        self.state = ""  # of the current balloon: "reset" (its flag) -> "asked" -> "shown"
        self.since = 0.0
        self.tries = 0
        self.enabled: bool | None = None  # does the installed mod hold these balloons? (read once)

    def add(self, sender: int, item: str) -> None:
        number = self.numbers.get((sender, item), self.numbers.get((sender, "")))
        if number is not None:
            self.waiting.append(number)

    def _ask(self) -> None:
        self.game.set_enum(REQUEST, raw_value(self.current))
        self._to("asked")

    def _to(self, state: str) -> None:
        self.state, self.since = state, self.clock()

    def step(self) -> None:
        if self.current is None:
            if not self.waiting:
                return
            if self.enabled is None:
                self.enabled = self.game.get_int(self.mark) is not None
            if not self.enabled:
                self.waiting.clear()
                return
            self.game.set_bool(played_flag(self.waiting[0]), False)
            self.current, self.tries = self.waiting.popleft(), 0
            self._to("reset")
        elif self.state == "reset":
            if self.game.get_bool(played_flag(self.current)) is False:  # the queued write is applied
                self._ask()
        elif self.state == "asked":
            if self.game.get_bool(played_flag(self.current)):
                self._to("shown")
            elif self.clock() - self.since > self.RETRY:
                self.tries += 1
                if self.tries < self.TRIES:
                    self._ask()
                else:
                    self.current = None
        elif self.clock() - self.since > self.SHOWN:
            self.current = None

    def reloaded(self) -> None:
        """After a loading: the balloon asked for may be lost (the Enum is not saved), ask for it again."""
        if self.current is not None and self.state != "shown":
            self.waiting.appendleft(self.current)
        self.current = None
