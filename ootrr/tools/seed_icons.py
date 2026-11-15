"""The 32 hash symbols (`ootrr.race.SYMBOLS`) drawn with canvas shapes, for the desktop app.

No game file is used: every icon is a handful of polygons, ovals and lines in a 40 x 40 box, coloured like the
item in the game, so two racers can compare their 5 symbols at a glance. `draw(app, name, x, y, size)` uses the
app's primitives (`poly`, `oval`, `line`, `rect`, in design units).
"""

from __future__ import annotations

INK = "#1a120a"


class _Pen:
    """Maps the 40 x 40 icon box onto the app's canvas (top-left x, y, side `size`)."""

    def __init__(self, app, x, y, size):
        self.app, self.x, self.y, self.k = app, x, y, size / 40.0

    def _pts(self, pts):
        out = []
        for i in range(0, len(pts), 2):
            out += [self.x + pts[i] * self.k, self.y + pts[i + 1] * self.k]
        return out

    def poly(self, *pts, fill, outline=INK):
        self.app.poly(*self._pts(pts), fill=fill, outline=outline)

    def oval(self, x0, y0, x1, y1, fill, outline=INK, w=1):
        p = self._pts((x0, y0, x1, y1))
        self.app.oval(*p, fill=fill, outline=outline, width=max(1, int(w * self.app.S)))

    def line(self, *pts, fill, w=2, **kw):
        self.app.line(*self._pts(pts), fill=fill, w=w * self.k, **kw)


def _arrow(p, tip):
    p.line(6, 34, 30, 10, fill="#c9a46a", w=3)
    p.poly(34, 6, 24, 10, 30, 16, fill=tip)
    p.poly(6, 34, 6, 27, 10, 30, fill="#e8e0d0")
    p.poly(6, 34, 13, 34, 10, 30, fill="#e8e0d0")


def _sword(p, blade, hilt, long):
    tip = 3 if long else 9
    p.poly(20, tip, 23, tip + 4, 23, 27, 17, 27, 17, tip + 4, fill=blade)
    p.poly(9, 27, 31, 27, 31, 30, 9, 30, fill=hilt)
    p.poly(18, 30, 22, 30, 22, 36, 18, 36, fill="#6b4a2a")
    p.oval(17, 35, 23, 39, fill=hilt)


def _boot(p, colour, sole):
    p.poly(12, 5, 24, 5, 24, 24, 34, 28, 34, 33, 10, 33, 10, 24, fill=colour)
    p.poly(10, 33, 34, 33, 34, 36, 10, 36, fill=sole)


def _key(p, colour, big):
    if big:
        p.oval(5, 5, 21, 21, fill=colour)
        p.oval(10, 10, 16, 16, fill="#d23b2b")
        p.poly(18, 16, 34, 32, 31, 35, 15, 19, fill=colour)
        p.poly(26, 30, 30, 26, 34, 30, 30, 34, fill=colour)
        p.poly(22, 26, 26, 22, 29, 25, 25, 29, fill=colour)
    else:
        p.oval(13, 3, 27, 17, fill=colour)
        p.oval(17, 7, 23, 13, fill="#2a2a2a", outline="")
        p.poly(18, 16, 22, 16, 22, 37, 18, 37, fill=colour)
        p.poly(22, 27, 28, 27, 28, 30, 22, 30, fill=colour)
        p.poly(22, 32, 27, 32, 27, 35, 22, 35, fill=colour)


def _shield(p, face, rim, mark):
    p.poly(6, 6, 34, 6, 34, 20, 20, 37, 6, 20, fill=rim)
    p.poly(9, 9, 31, 9, 31, 19, 20, 33, 9, 19, fill=face)
    p.poly(20, 12, 26, 22, 14, 22, fill=mark)


def _draw_symbol(p: _Pen, name: str):
    if name == "Deku Stick":
        p.line(9, 34, 31, 6, fill="#8a5a2b", w=5)
        p.oval(27, 3, 35, 11, fill="#e9d7a8")
    elif name == "Deku Nut":
        p.oval(8, 8, 32, 32, fill="#a8743a")
        p.oval(14, 12, 26, 20, fill="#d9b57a", outline="")
        p.line(20, 8, 20, 4, fill="#5a3a1a", w=3)
    elif name == "Bomb":
        p.oval(6, 11, 34, 39, fill="#2c3f8f")
        p.oval(12, 16, 19, 23, fill="#8fa3e8", outline="")
        p.poly(17, 9, 23, 9, 23, 13, 17, 13, fill="#9a9a9a")
        p.line(20, 9, 26, 3, fill="#c9a46a", w=2)
        p.oval(25, 0, 31, 6, fill="#ffd34d", outline="#f07a2a")
    elif name == "Fairy Bow":
        p.line(10, 4, 26, 12, 26, 28, 10, 36, fill="#8a5a2b", w=4, smooth=True)
        p.line(10, 4, 10, 36, fill="#f0ead8", w=1)
        p.poly(23, 17, 29, 17, 29, 23, 23, 23, fill="#d9a83a")
    elif name == "Fire Arrow":
        _arrow(p, "#f05a2a")
    elif name == "Ice Arrow":
        _arrow(p, "#7fd8f5")
    elif name == "Light Arrow":
        _arrow(p, "#ffe866")
    elif name == "Slingshot":
        p.line(20, 37, 20, 20, fill="#8a5a2b", w=4)
        p.line(20, 21, 9, 6, fill="#8a5a2b", w=4)
        p.line(20, 21, 31, 6, fill="#8a5a2b", w=4)
        p.line(9, 6, 20, 15, 31, 6, fill="#d9c9a0", w=2)
    elif name == "Ocarina":
        p.oval(5, 10, 35, 32, fill="#3d74d6")
        p.poly(30, 14, 39, 10, 38, 15, 33, 20, fill="#3d74d6")
        p.oval(11, 15, 21, 21, fill="#9cc2ff", outline="")
        for x, y in ((13, 25), (19, 26), (25, 24)):
            p.oval(x, y, x + 3, y + 3, fill=INK, outline="")
    elif name == "Hookshot":
        p.poly(6, 22, 22, 22, 22, 30, 6, 30, fill="#8e939c")
        p.poly(10, 30, 16, 30, 14, 37, 9, 37, fill="#6b4a2a")
        p.line(22, 26, 30, 18, fill="#c9ccd2", w=2)
        p.poly(28, 13, 38, 3, 34, 17, fill="#d23b2b")
    elif name == "Boomerang":
        p.poly(4, 32, 20, 6, 36, 32, 29, 35, 20, 18, 11, 35, fill="#3a5ec9")
        p.poly(20, 6, 24, 13, 20, 19, 16, 13, fill="#e9c24a")
    elif name == "Lens of Truth":
        p.line(28, 28, 36, 37, fill="#6b4a2a", w=5)
        p.oval(4, 4, 30, 30, fill="#d9a83a")
        p.oval(8, 8, 26, 26, fill="#b7a6ff")
        p.oval(14, 14, 20, 20, fill="#d23b2b", outline="")
    elif name == "Magic Bean":
        p.oval(8, 12, 32, 30, fill="#b5452e")
        p.oval(13, 15, 22, 21, fill="#e08a64", outline="")
        p.line(20, 12, 24, 4, fill="#4fae3c", w=3)
        p.poly(24, 4, 32, 2, 28, 9, fill="#4fae3c")
    elif name == "Megaton Hammer":
        p.line(14, 37, 24, 16, fill="#8a5a2b", w=4)
        p.poly(10, 4, 36, 14, 31, 27, 5, 17, fill="#8e939c")
        p.poly(10, 4, 16, 6, 11, 19, 5, 17, fill="#c9ccd2")
    elif name == "Bottle":
        p.poly(15, 3, 25, 3, 25, 8, 15, 8, fill="#a8743a")
        p.poly(16, 8, 24, 8, 24, 14, 32, 22, 32, 37, 8, 37, 8, 22, 16, 14, fill="#cfe9f2")
        p.poly(11, 26, 29, 26, 29, 34, 11, 34, fill="#e45a7a", outline="")
    elif name == "Kokiri Sword":
        _sword(p, "#d9dde3", "#4f8f3a", long=False)
    elif name == "Master Sword":
        _sword(p, "#eef2f8", "#6a4ec9", long=True)
    elif name == "Deku Shield":
        p.oval(4, 4, 36, 36, fill="#8a5a2b")
        p.oval(9, 9, 31, 31, fill="#b8814a")
        p.poly(20, 11, 28, 26, 12, 26, fill="#d23b2b")
    elif name == "Hylian Shield":
        _shield(p, "#2f57b8", "#c9ccd2", "#d23b2b")
    elif name == "Iron Boots":
        _boot(p, "#7d838c", "#4a4e55")
    elif name == "Hover Boots":
        _boot(p, "#9a6a3a", "#5a3a1a")
        p.poly(10, 14, 1, 8, 3, 16, fill="#f4efe2")
        p.poly(10, 20, 0, 18, 4, 24, fill="#f4efe2")
    elif name == "Goron Bracelet":
        p.oval(4, 10, 36, 32, fill="#d23b2b")
        p.oval(10, 15, 30, 27, fill="#2a1a10")
        p.oval(16, 7, 24, 15, fill="#ffd34d")
    elif name == "Silver Scale":
        p.poly(20, 3, 34, 16, 20, 37, 6, 16, fill="#c9d6e3")
        p.line(20, 8, 20, 32, fill="#7f97b0", w=2)
        p.line(12, 17, 20, 25, 28, 17, fill="#7f97b0", w=1)
    elif name == "Heart Container":
        p.poly(20, 36, 4, 18, 4, 10, 10, 5, 16, 5, 20, 10, 24, 5, 30, 5, 36, 10, 36, 18, fill="#e8322e")
        p.oval(9, 9, 15, 15, fill="#ff9a8a", outline="")
    elif name == "Rupee":
        p.poly(20, 2, 30, 12, 30, 28, 20, 38, 10, 28, 10, 12, fill="#2fb84a")
        p.poly(20, 8, 25, 14, 25, 26, 20, 32, 15, 26, 15, 14, fill="#7ae38c", outline="")
    elif name == "Gold Skulltula":
        for y in (12, 20, 28):
            p.line(4, y - 4, 13, y, fill="#b98a1c", w=2)
            p.line(36, y - 4, 27, y, fill="#b98a1c", w=2)
        p.oval(11, 8, 29, 34, fill="#f2c230")
        p.oval(14, 14, 19, 19, fill=INK, outline="")
        p.oval(21, 14, 26, 19, fill=INK, outline="")
    elif name == "Triforce":
        gold = "#f2c230"
        p.poly(20, 3, 28, 18, 12, 18, fill=gold)
        p.poly(12, 18, 20, 33, 4, 33, fill=gold)
        p.poly(28, 18, 36, 33, 20, 33, fill=gold)
    elif name == "Compass":
        p.oval(4, 4, 36, 36, fill="#d9a83a")
        p.oval(8, 8, 32, 32, fill="#f4efe2")
        p.poly(20, 9, 24, 20, 16, 20, fill="#d23b2b", outline="")
        p.poly(20, 31, 24, 20, 16, 20, fill="#5a6270", outline="")
    elif name == "Small Key":
        _key(p, "#a7adb6", big=False)
    elif name == "Boss Key":
        _key(p, "#e9b83a", big=True)
    elif name == "Din's Fire":
        p.poly(20, 2, 31, 18, 32, 28, 26, 37, 14, 37, 8, 28, 9, 18, 14, 22, fill="#f05a2a")
        p.poly(20, 14, 26, 25, 24, 34, 16, 34, 14, 25, fill="#ffd34d", outline="")
    elif name == "Fairy":
        p.oval(1, 6, 18, 20, fill="#ffd2ef", outline="#e98ac9")
        p.oval(22, 6, 39, 20, fill="#ffd2ef", outline="#e98ac9")
        p.oval(4, 20, 17, 31, fill="#ffd2ef", outline="#e98ac9")
        p.oval(23, 20, 36, 31, fill="#ffd2ef", outline="#e98ac9")
        p.oval(13, 11, 27, 29, fill="#fff6c8", outline="#ffe07a")
    else:
        raise KeyError(name)


def draw(app, name: str, x: float, y: float, size: float = 40) -> None:
    """Draws symbol `name` in the box (x, y)-(x + size, y + size), design units."""
    _draw_symbol(_Pen(app, x, y, size), name)

