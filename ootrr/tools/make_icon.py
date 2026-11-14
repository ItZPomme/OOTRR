"""Draws the app logo (blue ocarina with a golden Triforce on a bronze plate) without any image library.

    python -m ootrr.tools.make_icon        # writes ootrr/assets/longshot.png and longshot.ico

Pure Python: signed-distance shapes, 3x3 supersampling, PNG written with zlib. The result is committed, so this only
needs to run again when the design changes.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SIZE = 256
SS = 3  # samples per pixel side


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def rrect(x, y, cx, cy, hw, hh, r):
    dx, dy = abs(x - cx) - (hw - r), abs(y - cy) - (hh - r)
    return math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0) - r


def ellipse(x, y, cx, cy, rx, ry, ang=0.0):
    c, s = math.cos(ang), math.sin(ang)
    px, py = x - cx, y - cy
    qx, qy = px * c + py * s, -px * s + py * c
    return (math.hypot(qx / rx, qy / ry) - 1) * min(rx, ry)


def capsule(x, y, ax, ay, bx, by, r):
    px, py, dx, dy = x - ax, y - ay, bx - ax, by - ay
    t = max(0.0, min(1.0, (px * dx + py * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - dx * t, py - dy * t) - r


def triangle(x, y, p0, p1, p2):
    """Signed distance (negative inside) of a convex triangle, as the max over its edges."""
    d = -1e9
    for (ax, ay), (bx, by) in ((p0, p1), (p1, p2), (p2, p0)):
        ex, ey = bx - ax, by - ay
        n = math.hypot(ex, ey)
        d = max(d, ((x - ax) * ey - (y - ay) * ex) / n)
    return d


# winding of the triangle points is fixed so that "inside" comes out negative
def tri(x, y, p0, p1, p2):
    return triangle(x, y, p0, p1, p2) if (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0]) > 0 \
        else triangle(x, y, p0, p2, p1)


PLATE_TOP, PLATE_BOT = hexrgb("#8a6330"), hexrgb("#3a2712")
RING, EDGE_DARK = hexrgb("#d9b46a"), hexrgb("#24170a")
BLUE_LIGHT, BLUE_DEEP, NAVY = hexrgb("#6fa8ff"), hexrgb("#1f46a0"), hexrgb("#0d1f52")
GOLD_LIGHT, GOLD_DEEP, GOLD_EDGE = hexrgb("#ffe58a"), hexrgb("#d8901f"), hexrgb("#7a4a0b")

ANG = -math.radians(28)  # the ocarina rises to the right
BODY = (112.0, 148.0, 86.0, 70.0)
MOUTH = ((172.0, 112.0), (196.0, 86.0), 19.0)
TRI_TOP = (108.0, 100.0)
TRI_H = 84.0


def sample(x, y):
    """RGBA (0..255, alpha 0..1) of the logo at a point."""
    plate = rrect(x, y, 128, 128, 120, 120, 56)
    if plate > 0:
        return None
    if plate > -5:
        col = EDGE_DARK
    elif plate > -9:
        col = lerp(RING, hexrgb("#9a7438"), (plate + 9) / -4 * 0 + (y / 256))
    else:
        col = lerp(PLATE_TOP, PLATE_BOT, y / 256)
        col = lerp(col, hexrgb("#b88a45"), max(0.0, 1 - math.hypot(x - 110, y - 100) / 150) * 0.45)

    bx, by, rx, ry = BODY
    # soft shadow under the ocarina
    sh = ellipse(x, y, bx + 5, by + 10, rx + 3, ry + 3, ANG)
    if sh < 0:
        col = lerp(col, (10, 6, 2), 0.35)
    # mouthpiece
    m = capsule(x, y, *MOUTH[0], *MOUTH[1], MOUTH[2])
    if m <= 0:
        col = NAVY if m > -4 else lerp(BLUE_LIGHT, BLUE_DEEP, 0.35 + (y - 60) / 120)
    # body
    b = ellipse(x, y, bx, by, rx, ry, ANG)
    if b <= 0:
        if b > -4.5:
            col = NAVY
        else:
            col = lerp(BLUE_LIGHT, BLUE_DEEP, ((x - bx) * 0.5 + (y - by) * 1.0) / 110 + 0.45)
            hl = ellipse(x, y, bx - 22, by - 24, 46, 17, ANG)
            if hl < 0:
                col = lerp(col, (225, 240, 255), 0.30 * min(1.0, -hl / 6))
        # finger holes (two staggered pairs along the long axis)
        c, s = math.cos(ANG), math.sin(ANG)
        for t, off in ((62, -8), (62, 12)):
            hx, hy = bx + t * c - off * s, by + t * s + off * c
            d = math.hypot(x - hx, y - hy)
            if d < 6.5:
                col = NAVY if d > 4.5 else (14, 24, 64)
    # Triforce
    cx, top = TRI_TOP
    h = TRI_H
    w = h * 1.1547 / 2 * 0.9
    gap = 3.5
    parts = [((cx, top), (cx - w / 2 + gap, top + h / 2 - gap), (cx + w / 2 - gap, top + h / 2 - gap)),
             ((cx - w / 2, top + h / 2 + gap), (cx - w, top + h), (cx, top + h)),
             ((cx + w / 2, top + h / 2 + gap), (cx, top + h), (cx + w, top + h))]
    for p in parts:
        d = tri(x, y, *p)
        if d <= 0:
            col = GOLD_EDGE if d > -2.5 else lerp(GOLD_LIGHT, GOLD_DEEP, (y - top) / h)
    return col


def render():
    rows = []
    for py in range(SIZE):
        row = bytearray()
        for px in range(SIZE):
            r = g = b = a = 0.0
            for sy in range(SS):
                for sx in range(SS):
                    c = sample(px + (sx + 0.5) / SS, py + (sy + 0.5) / SS)
                    if c is not None:
                        r += c[0]; g += c[1]; b += c[2]; a += 1
            n = SS * SS
            if a:
                row += bytes((int(r / a), int(g / a), int(b / a), int(255 * a / n)))
            else:
                row += bytes(4)
        rows.append(bytes(row))
    return rows


def downscale(rows, size):
    """Box filter on premultiplied RGBA."""
    k = SIZE // size if SIZE % size == 0 else None
    out = []
    for oy in range(size):
        row = bytearray()
        for ox in range(size):
            r = g = b = a = 0.0
            x0, x1 = ox * SIZE / size, (ox + 1) * SIZE / size
            y0, y1 = oy * SIZE / size, (oy + 1) * SIZE / size
            wsum = 0.0
            for yy in range(int(y0), min(SIZE, math.ceil(y1))):
                wy = min(yy + 1, y1) - max(yy, y0)
                for xx in range(int(x0), min(SIZE, math.ceil(x1))):
                    w = wy * (min(xx + 1, x1) - max(xx, x0))
                    p = rows[yy][xx * 4:xx * 4 + 4]
                    al = p[3] / 255 * w
                    r += p[0] * al; g += p[1] * al; b += p[2] * al; a += al
                    wsum += w
            if a > 0:
                row += bytes((int(r / a), int(g / a), int(b / a), int(255 * a / wsum)))
            else:
                row += bytes(4)
        out.append(bytes(row))
    return out


def png(rows) -> bytes:
    h, w = len(rows), len(rows[0]) // 4

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(images: list[tuple[int, bytes]]) -> bytes:
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    return head + entries + blobs


def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    full = render()
    (ASSETS / "longshot.png").write_bytes(png(full))
    images = [(s, png(full if s == SIZE else downscale(full, s))) for s in (16, 24, 32, 48, 64, 128, 256)]
    (ASSETS / "longshot.ico").write_bytes(ico(images))
    print("written:", ASSETS / "longshot.png", ASSETS / "longshot.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
