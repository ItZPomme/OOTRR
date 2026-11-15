"""Seed installer for Longshot (the PC recompilation of the game) and the Eden emulator, styled after the remake's
own Options menu.

    python -m ootrr.tools.longshot_app

Pick a target, a seed and settings, press "Install Seed": the generator builds the OoTRR mod on the PC and writes it
- for Longshot, from Longshot's own RomFS, to `<Longshot>/mods/OoTRR/romfs` (loaded at the next start);
- for Eden (or a fork), from the extracted update RomFS, to `<emulator data>/load/<TitleID>/OoTRR` (`--install`).
Close the game first. Settings come from `ootrr.settings_ui` (same texts as the native in-game menu); the
settings only the native module can apply (shops) are not offered.

For races, "Copy Settings" / "Copy with Seed" put a short settings string (`ootrr.race`) on the clipboard and
"Paste Settings" applies one (the three buttons are under "Install Seed"); after an install, the 5 hash symbols
of the seed are drawn in the forge box (the spoiler log names them), so racers can check they play the same seed.
Once the host has installed the seed, "Copy with Seed" also adds the seed hash to the string; a racer who pastes it
is told after the install whether they got the host's seed (a different hash = another OoTRR version).

Everything is drawn on a single tkinter canvas (no extra dependency): bronze leather rows, amber selectors on dark
tracks, a white focus halo, ornamental dividers and a paged list with a "Next Page" button, like the in-game menu.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from .. import race
from .. import settings as settings_mod
from .. import settings_ui
from . import seed_icons
from ..modbuild import TITLE_ID, emulator_root

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "OoTRR"
CONFIG = APP_DIR / "longshot_app.json"
SEEDS_DIR = APP_DIR / "seeds"
MOD_NAME = "OoTRR"
TARGETS = {"longshot": "Longshot", "eden": "Eden"}
# exact image names: our own "OoTRR-App.exe" must not count as the game
GAME_PROCESSES = {"longshot": ("longshot.exe",),
                  "eden": ("eden.exe", "fritchii.exe", "yuzu.exe", "suyu.exe", "citron.exe", "sudachi.exe")}

# ---- palette: the remake's menu (bronze leather, amber selectors, cream text) ---------------------------------
BG_TOP, BG_BOTTOM = (36, 38, 29), (17, 16, 12)
BANNER, BANNER_LO, BANNER_EDGE = "#6a4a25", "#4a3318", "#241709"
PANEL, PANEL_EDGE, PANEL_SIDE = "#3b2a1a", "#5b4226", "#2e2114"
CELL, CELL_HI, CELL_EDGE = "#6b5230", "#7c6038", "#8f7545"
TRACK, TRACK_EDGE = "#1d1b15", "#6b5230"
AMBER, AMBER_HI, AMBER_LO = "#e3a02c", "#f2bb55", "#b57a17"
CREAM, DIM, FAINT = "#f6ecd8", "#8c7f66", "#4c4638"
BOX, BOX_EDGE = "#4a3320", "#6c4f2d"
ORANGE, RED = "#f0793a", "#e0644f"
ORNAMENT = "#6e5532"

W, H = 1180, 724

PAGES = settings_ui.PAGES
BRIDGE_MAX = settings_ui.BRIDGE_MAX

PRESETS = {
    "Standard": {},
    "Quick": {"open_forest": "open", "open_door_of_time": True, "skip_cutscenes": "safe",
              "skip_child_zelda": True, "start_with_consumables": True},
    "Chaos": {"shuffle_scrubs": True, "shuffle_skulltulas": "all",
              "shuffle_songs": "random", "shuffle_ocarinas": True,
              "shuffle_rewards": "shuffled", "maps_compasses": "shuffle", "starting_age": "random",
              "skip_cutscenes": "safe"},
}
PRESET_HINTS = {
    "Standard": "The default rules: gifts and Pieces of Heart are always in the item pool.",
    "Quick": "Forest and Door of Time open, cutscenes skipped, Zelda's items and consumables at the start.",
    "Chaos": "Almost everything shuffled: songs, scrubs, skulltulas, rewards, ocarinas, maps and compasses.",
}
DEFAULT_HINT = "Left-click a row to change it, right-click to go back. Hover a row to read what it does."


def pretty(name, value) -> str:
    return settings_ui.value_label(name, value)


def find_longshot() -> Path | None:
    """Newest `Games/Longshot/v*` folder that holds longshot.exe."""
    for base in (Path.home() / "Games" / "Longshot", Path("C:/Games/Longshot")):
        if base.is_dir():
            found = sorted((p for p in base.iterdir() if (p / "longshot.exe").is_file()), reverse=True)
            if found:
                return found[0]
    return None


def valid_romfs(path: Path) -> bool:
    return (path / "GameData").is_dir() and (path / "Pack").is_dir()


def game_running(target: str = "longshot") -> bool:
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                             creationflags=0x08000000).stdout.lower()
    except OSError:
        return False
    names = tuple(f'"{n}"' for n in GAME_PROCESSES[target])
    return any(line.startswith(names) for line in out.splitlines())


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def hexc(c) -> str:
    return "#%02x%02x%02x" % c


class QueueWriter:
    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, text):
        if text:
            self.q.put(("log", text))
        return len(text or "")

    def flush(self):
        pass


class App:
    def __init__(self):
        with contextlib.suppress(Exception):
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        self.root = tk.Tk()
        self.root.title("OoTRR · Longshot")
        with contextlib.suppress(Exception):  # window / taskbar icon (the logo is bundled in the exe)
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
            self._icon = tk.PhotoImage(file=str(base / "ootrr" / "assets" / "longshot.png"))
            self.root.iconphoto(True, self._icon)
        self.S = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        self.root.configure(bg=hexc(BG_TOP))
        self.root.geometry(f"{int(W * self.S)}x{int(H * self.S)}")
        self.root.resizable(False, False)
        self.c = tk.Canvas(self.root, width=int(W * self.S), height=int(H * self.S), highlightthickness=0,
                           bg=hexc(BG_TOP))
        self.c.pack()

        self.cfg = self._load_cfg()
        self.values = settings_mod.defaults()
        shown = set(settings_ui.SHOWN)  # hidden settings always use the generator's defaults
        for k, v in (self.cfg.get("settings") or {}).items():
            if k in shown:
                with contextlib.suppress(Exception):
                    self.values[k] = settings_mod._coerce(k, v)
        self.preset = self.cfg.get("preset", "Standard")
        self.longshot = Path(self.cfg["longshot"]) if self.cfg.get("longshot") else find_longshot()
        self.romfs_override = Path(self.cfg["romfs"]) if self.cfg.get("romfs") else None
        self.target = self.cfg.get("target") if self.cfg.get("target") in TARGETS else "longshot"
        self.emu_dir = Path(self.cfg["emu_dir"]) if self.cfg.get("emu_dir") else emulator_root()
        self.eden_romfs = Path(self.cfg["eden_romfs"]) if self.cfg.get("eden_romfs") else None

        self.page = 0
        self.regions: list[dict] = []
        self.hover: str | None = None
        self.hint = DEFAULT_HINT
        self.busy = False
        self.done_at = 0.0
        self.status = ("Ready", CREAM)
        self.result: dict = {}
        # (string of the pasted settings and seed, host's seed hash): checked after an install of that very seed
        self.expected: tuple[str, str] | None = None
        self.q: queue.Queue = queue.Queue()
        self.t = 0.0
        self.running = game_running(self.target)
        self._poll_running = 0

        self.f_title = tkfont.Font(family="Georgia", size=17, weight="bold")
        self.f_row = tkfont.Font(family="Segoe UI", size=12)
        self.f_small = tkfont.Font(family="Segoe UI", size=10)
        self.f_big = tkfont.Font(family="Georgia", size=21, weight="bold")
        self.f_cap = tkfont.Font(family="Georgia", size=15, weight="bold")
        self.f_footer = tkfont.Font(family="Segoe UI", size=12)

        self._draw_background()
        self._make_widgets()
        self.draw()

        self.c.bind("<Button-1>", lambda e: self._click(e, "l"))
        self.c.bind("<Button-3>", lambda e: self._click(e, "r"))
        self.c.bind("<Motion>", self._motion)
        self.c.bind("<Leave>", lambda e: self._set_hover(None))
        self.root.bind("<Return>", lambda e: self.install())
        self.root.bind("<Escape>", lambda e: self._close())
        self.root.bind("<Key>", self._key)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(33, self._tick)

    # ---- config ---------------------------------------------------------------------------------------------
    def _load_cfg(self) -> dict:
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_cfg(self):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps({
                "longshot": str(self.longshot) if self.longshot else None,
                "romfs": str(self.romfs_override) if self.romfs_override else None,
                "target": self.target, "emu_dir": str(self.emu_dir) if self.emu_dir else None,
                "eden_romfs": str(self.eden_romfs) if self.eden_romfs else None,
                "preset": self.preset, "seed": self.seed_var.get(),
                "settings": {k: v for k, v in self.values.items() if k != "spawn_point"}}, indent=2),
                encoding="utf-8")
        except OSError:
            pass

    def _close(self):
        self._save_cfg()
        self.root.destroy()

    def _key(self, e):
        if self.root.focus_get() is self.entry:
            return
        k = e.keysym.lower()
        if k == "y":
            self.apply_preset("Standard")
        elif k == "x":
            self.open_spoiler()
        elif k == "b":
            self._close()
            return
        else:
            return
        self.draw()

    # ---- drawing primitives (design units -> pixels) --------------------------------------------------------
    def p(self, *v):
        return [x * self.S for x in v]

    def rect(self, x0, y0, x1, y1, fill="", outline="", w=1, tags="dyn"):
        return self.c.create_rectangle(*self.p(x0, y0, x1, y1), fill=fill, outline=outline,
                                       width=max(1, int(w * self.S)) if outline else 0, tags=tags)

    def text(self, x, y, s, font, fill, anchor="w", width=None, tags="dyn"):
        kw = {"width": int(width * self.S)} if width else {}
        return self.c.create_text(*self.p(x, y), text=s, font=font, fill=fill, anchor=anchor, tags=tags, **kw)

    def line(self, *pts, fill=ORNAMENT, w=1, tags="dyn", **kw):
        return self.c.create_line(*self.p(*pts), fill=fill, width=max(1, int(w * self.S)), tags=tags, **kw)

    def poly(self, *pts, fill="", outline="", tags="dyn"):
        return self.c.create_polygon(*self.p(*pts), fill=fill, outline=outline, tags=tags)

    def oval(self, x0, y0, x1, y1, tags="dyn", **kw):
        return self.c.create_oval(*self.p(x0, y0, x1, y1), tags=tags, **kw)

    def add_region(self, box, rid, left=None, right=None, hint=None):
        self.regions.append({"box": box, "id": rid, "l": left, "r": right, "hint": hint})

    def width_of(self, font, s) -> float:
        return font.measure(s) / self.S

    def smallcaps(self, x, y, s, fill=CREAM):
        """'Next Page' in small capitals: big first letter of every word, small caps after."""
        cx, new_word = x, True
        for ch in s:
            if ch == " ":
                cx += 9
                new_word = True
                continue
            font = self.f_big if new_word else self.f_cap
            self.text(cx, y, ch.upper(), font, fill, anchor="sw")
            cx += self.width_of(font, ch.upper()) + 1
            new_word = False

    def focus_ring(self, x0, y0, x1, y1):
        """White glow with a black inner line, the menu's cursor."""
        self.rect(x0 - 3, y0 - 3, x1 + 3, y1 + 3, outline="#fdfdf6", w=2)
        self.rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1, outline="#000000", w=2)

    def swirl(self, cx, cy, half=250):
        self.line(cx - half, cy, cx - 44, cy, fill="#54401f")
        self.line(cx + 44, cy, cx + half, cy, fill="#54401f")
        self.line(cx - 40, cy + 2, cx - 28, cy - 6, cx - 16, cy + 3, cx - 6, cy - 3, cx, cy, cx + 6, cy - 3,
                  cx + 16, cy + 3, cx + 28, cy - 6, cx + 40, cy + 2, fill=ORNAMENT, w=2, smooth=True)
        for dx in (-half, half):
            self.oval(cx + dx - 2, cy - 2, cx + dx + 2, cy + 2, fill="#54401f", outline="")

    def crest(self, x, y):
        self.rect(x, y, x + 36, y + 36, outline=CREAM, w=2)
        for ox, oy in ((18, 7), (11, 19), (25, 19)):
            self.poly(x + ox, y + oy, x + ox - 6, y + oy + 11, x + ox + 6, y + oy + 11, fill=CREAM)

    # ---- static background ----------------------------------------------------------------------------------
    def _draw_background(self):
        steps = 80
        for i in range(steps):
            col = hexc(mix(BG_TOP, BG_BOTTOM, i / (steps - 1)))
            self.c.create_rectangle(0, i * H * self.S / steps, W * self.S, (i + 1) * H * self.S / steps + 1,
                                    fill=col, outline="", tags="bg")
        # a dim, out-of-focus valley behind the menu (soft overlapping shapes, no detail)
        for x0, y0, x1, y1, col in ((650, 330, 1300, 800, "#252a1d"), (900, 150, 1500, 520, "#2b2e22"),
                                     (-200, 420, 700, 900, "#1e2217"), (560, 560, 1200, 900, "#2d3022"),
                                     (760, 40, 1250, 260, "#30332a")):
            self.oval(x0, y0, x1, y1, fill=col, outline="", tags="bg")
        self.oval(0, 0, 0, 0, tags="bg", outline="")

    # ---- widgets (entry, log) -------------------------------------------------------------------------------
    def _make_widgets(self):
        self.seed_var = tk.StringVar(value=str(self.cfg.get("seed", "")))
        self.entry = tk.Entry(self.root, textvariable=self.seed_var, bg=TRACK, fg=CREAM, insertbackground=AMBER,
                              relief="flat", font=("Segoe UI", 13), highlightthickness=0, bd=0,
                              selectbackground=AMBER_LO, selectforeground="#ffffff")
        self.c.create_window(*self.p(312, 105), window=self.entry, anchor="w", width=int(252 * self.S),
                             height=int(28 * self.S))
        self.entry.bind("<FocusIn>", lambda e: self.draw())
        self.entry.bind("<FocusOut>", lambda e: self.draw())

        self.log = tk.Text(self.root, bg="#1a130b", fg="#d8c9aa", relief="flat", bd=0, highlightthickness=0,
                           font=("Consolas", 10), wrap="word", state="disabled", padx=10, pady=8,
                           selectbackground=AMBER_LO, cursor="arrow")
        self.c.create_window(*self.p(700, 430), window=self.log, anchor="nw", width=int(430 * self.S),
                             height=int(120 * self.S))
        self.log_line("The seed is waiting. Choose your options and press Install Seed.\n")

    def log_line(self, s: str):
        self.log.configure(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---- screen ---------------------------------------------------------------------------------------------
    def draw(self):
        self.c.delete("dyn")
        self.regions = []
        self._banner()
        self._left_panel()
        self._right_column()
        self._race_buttons()
        self._footer()

    def _banner(self):
        self.rect(0, 0, W, 62, fill=BANNER)
        self.rect(0, 40, W, 62, fill=BANNER_LO)
        self.rect(0, 58, W, 62, fill=BANNER_EDGE)
        for x in range(30, W, 120):  # faint embossed knots, like the carved banner
            self.oval(x, 8, x + 70, 44, outline="#7b5a30")
            self.oval(x + 20, 14, x + 50, 38, outline="#73532d")
        self.rect(0, 0, W, 62, outline="")
        self.text(W / 2 + 1, 33, "Ocarina of Time Randomizer", self.f_title, "#2b1c0a", anchor="center")
        self.text(W / 2, 31, "Ocarina of Time Randomizer", self.f_title, "#fff3d6", anchor="center")
        self.text(28, 31, TARGETS[self.target], self.f_small, "#e7cfa0", anchor="w")
        self.text(W - 28, 31, f"{PAGES[self.page][0]}  ·  {self.page + 1} / {len(PAGES)}", self.f_small, "#e7cfa0",
                  anchor="e")

    def _cell_row(self, y, label, rid, h=40, x0=70, x1=620, split=300):
        """Bronze label cell + value cell frame. Returns the value cell box."""
        self.rect(x0, y, split, y + h, fill=CELL, outline=CELL_EDGE)
        self.rect(split, y, x1, y + h, fill=TRACK, outline=TRACK_EDGE)
        self.text(x0 + 24, y + h / 2, label, self.f_row, CREAM)
        return (split, y, x1, y + h)

    def _left_panel(self):
        self.rect(40, 62, 650, 690, fill=PANEL, outline="")
        self.rect(40, 62, 50, 690, fill=PANEL_SIDE)
        self.rect(640, 62, 650, 690, fill=PANEL_SIDE)
        self.rect(40, 62, 650, 690, outline=PANEL_EDGE)

        # seed row: entry on a dark track, dice at the end
        focus = self.root.focus_get() is self.entry
        y = 84
        cell = self._cell_row(y, "Seed", "seed")
        if focus:
            self.focus_ring(*cell)
        self.rect(cell[0], cell[1], cell[2], cell[3], outline=TRACK_EDGE if not focus else "")
        hot = self.hover == "dice"
        dx0 = cell[2] - 46
        self.rect(dx0, y + 4, cell[2] - 4, y + 36, fill=AMBER_HI if hot else AMBER, outline=AMBER_LO)
        for ox, oy in ((-6, -6), (6, 6), (0, 0), (-6, 6), (6, -6)):
            self.oval(dx0 + 21 + ox - 2, y + 20 + oy - 2, dx0 + 21 + ox + 2, y + 20 + oy + 2, fill="#fff7e2", outline="")
        self.add_region((dx0, y + 4, cell[2] - 4, y + 36), "dice", self.roll, None,
                        "Roll a random seed. Leave the field empty for a random one; any number or word works.")

        # preset row: three segments
        y = 134
        cell = self._cell_row(y, "Preset", "preset")
        names = list(PRESETS)
        seg = (cell[2] - cell[0] - 8) / 3
        for i, name in enumerate(names):
            sx0 = cell[0] + 4 + i * seg
            on = self.preset == name
            rid = f"preset:{name}"
            if on:
                self.rect(sx0 + 1, y + 4, sx0 + seg - 1, y + 36, fill=AMBER, outline=AMBER_LO)
                self.line(sx0 + 2, y + 5, sx0 + seg - 2, y + 5, fill=AMBER_HI)
            self.text(sx0 + seg / 2, y + 20, name, self.f_row, "#ffffff" if on else FAINT, anchor="center")
            self.add_region((sx0, y, sx0 + seg, y + 40), rid, lambda n=name: self.apply_preset(n), None,
                            PRESET_HINTS[name])
            if self.hover == rid:
                self.focus_ring(sx0 + 1, y + 4, sx0 + seg - 1, y + 36)

        self.swirl(345, 198)

        # the current page of runes
        defaults = settings_mod.defaults()
        for i, name in enumerate(PAGES[self.page][1]):
            self._rune_row(206 + i * 44, name, defaults)

        self.swirl(345, 566)

        # Next Page, like the menu's own
        y = 580
        hot = self.hover == "next"
        self.rect(70, y, 300, y + 62, fill=CELL_HI if hot else CELL, outline=CELL_EDGE)
        self.crest(84, y + 13)
        self.smallcaps(132, y + 43, "Next Page")
        self.rect(300, y, 620, y + 62, fill=TRACK, outline=TRACK_EDGE)
        self.text(460, y + 31, "Press A", self.f_row, ORANGE, anchor="center")
        if hot:
            self.focus_ring(70, y, 620, y + 62)
        self.add_region((70, y, 620, y + 62), "next", self.next_page, lambda: self.next_page(-1),
                        "Show the next page of options.")

    def _rune_row(self, y, name, defaults):
        label = settings_ui.title(name)
        disabled = not settings_ui.enabled(name, self.values)
        rid = f"rune:{name}"
        hot = self.hover == rid and not disabled
        cell = self._cell_row(y, label, rid)
        hint = settings_ui.caption(name)
        if self.values[name] != defaults[name] and not disabled:  # lit diamond = differs from the default
            self.poly(78, y + 20, 83, y + 15, 88, y + 20, 83, y + 25, fill=AMBER, outline="")
        if disabled:
            self.text(460, y + 20, "—", self.f_row, FAINT, anchor="center")
            self.text(79, y + 20, "", self.f_row, FAINT)
            return
        x0, _, x1, _ = cell
        val = self.values[name]
        default, allowed, _ = settings_mod.SETTINGS[name]
        if allowed is bool:
            mid = (x0 + x1) / 2
            for on_side, sx0, sx1, lab in ((True, x0 + 4, mid, "On"), (False, mid, x1 - 4, "Off")):
                active = val is on_side
                if active:
                    self.rect(sx0, y + 4, sx1, y + 36, fill=AMBER, outline=AMBER_LO)
                    self.line(sx0 + 1, y + 5, sx1 - 1, y + 5, fill=AMBER_HI)
                self.text((sx0 + sx1) / 2, y + 20, lab, self.f_row, "#ffffff" if active else FAINT, anchor="center")
            self.add_region((70, y, x1, y + 40), rid, lambda n=name: self.step(n, 1), lambda n=name: self.step(n, -1), hint)
        else:
            if allowed is int:
                lo, hi = settings_ui.int_range(name, self.values)
                first, last = val <= lo, val >= hi
            else:
                idx = allowed.index(val)
                first, last = idx == 0, idx == len(allowed) - 1
            self.rect(x0 + 4, y + 4, x1 - 4, y + 36, fill=AMBER, outline=AMBER_LO)
            self.line(x0 + 5, y + 5, x1 - 5, y + 5, fill=AMBER_HI)
            self.text((x0 + x1) / 2, y + 20, pretty(name, val), self.f_row, "#ffffff", anchor="center")
            if not last:
                self.poly(x1 - 18, y + 13, x1 - 18, y + 27, x1 - 11, y + 20, fill="#fff7e2")
            if not first:
                self.poly(x0 + 18, y + 13, x0 + 18, y + 27, x0 + 11, y + 20, fill="#fff7e2")
            mid = (x0 + x1) / 2
            self.add_region((70, y, mid, y + 40), rid, lambda n=name: self.step(n, -1), lambda n=name: self.step(n, 1), hint)
            self.add_region((mid, y, x1, y + 40), rid, lambda n=name: self.step(n, 1), lambda n=name: self.step(n, -1), hint)
        if hot:
            self.focus_ring(x0 + 4, y + 4, x1 - 4, y + 36)

    def _box(self, x0, y0, x1, y1):
        self.rect(x0, y0, x1, y1, fill=BOX, outline=BOX_EDGE)

    def _right_column(self):
        # target card: Longshot / Eden selector, game and RomFS folders
        self._box(690, 84, 1140, 202)
        self.text(708, 102, "Target", self.f_small, DIM)
        seg_x0, seg_x1 = 776, 1124
        seg = (seg_x1 - seg_x0) / len(TARGETS)
        for i, (key, name) in enumerate(TARGETS.items()):
            sx0 = seg_x0 + i * seg
            on = self.target == key
            rid = f"target:{key}"
            self.rect(sx0 + 1, 90, sx0 + seg - 1, 114, fill=AMBER if on else TRACK,
                      outline=AMBER_LO if on else TRACK_EDGE)
            self.text(sx0 + seg / 2, 102, name, self.f_small, "#ffffff" if on else DIM, anchor="center")
            if self.hover == rid:
                self.focus_ring(sx0 + 1, 90, sx0 + seg - 1, 114)
            hint = ("Build the mod from Longshot's own RomFS and write it to Longshot's mods folder."
                    if key == "longshot" else
                    "Build the mod from the extracted update RomFS and install it in the emulator "
                    f"(load/{TITLE_ID}/{MOD_NAME}). Disable any other OoTRR mod there (e.g. OoTRR-menu).")
            self.add_region((sx0, 88, sx0 + seg, 116), rid, lambda k=key: self.set_target(k), None, hint)
        ok = self._game_ok()
        romfs = self._romfs()
        rom_ok = romfs is not None and valid_romfs(romfs)
        game_dir = self.longshot if self.target == "longshot" else self.emu_dir
        y = 128
        for label, path, good in (("Game" if self.target == "longshot" else "Emulator", game_dir, ok),
                                  ("RomFS", romfs, rom_ok)):
            self.text(708, y, label, self.f_small, DIM)
            self.oval(770, y - 4, 778, y + 4, fill=AMBER if good else RED, outline="")
            shown = "not found" if path is None else str(path).replace(str(Path.home()), "~")
            if label == "Game" and ok:
                version = self._version()
                shown = self._short(shown, 36 - len(version)) + f"  ({version})"
            else:
                shown = self._short(shown, 38)
            self.text(786, y, shown, self.f_small, CREAM if good else RED)
            y += 20
        bw = 134
        if self.target == "longshot":
            buttons = (("Game Folder", "pick_game", self.pick_game, True,
                        "Choose the Longshot version folder (the one with longshot.exe)."),
                       ("RomFS", "pick_romfs", self.pick_romfs, True,
                        "RomFS used to build the mod. Defaults to Longshot's own romfs folder."),
                       ("Mods Folder", "modsdir", self.open_mods, ok, "Open Longshot's mods folder."))
        else:
            buttons = (("Emulator Folder", "pick_game", self.pick_game, True,
                        "Choose the emulator's data folder, the one with load/ (e.g. %APPDATA%\\eden or "
                        "%APPDATA%\\fritchii)."),
                       ("RomFS", "pick_romfs", self.pick_romfs, True,
                        "RomFS of the extracted update (.../updates/<version>/romfs), used to build the mod."),
                       ("Mods Folder", "modsdir", self.open_mods, ok,
                        f"Open the emulator's mods folder for the game (load/{TITLE_ID})."))
        for i, (lab, rid, fn, en, hint) in enumerate(buttons):
            bx = 706 + i * (bw + 8)
            self._small_button((bx, 168, bx + bw, 194), lab, rid, fn, en, hint)

        # Hint box
        self._box(690, 214, 1140, 330)
        self.text(710, 228, self.hint, self.f_row, CREAM, anchor="nw", width=410)

        # Forge box
        self._box(690, 344, 1140, 560)
        s, col = self.status
        self.oval(708, 360, 716, 368, fill=col, outline="")
        self.text(724, 364, self._short(s, 44), self.f_small, col)
        self._hash_row(378)
        self.rect(698, 424, 1132, 552, fill="#1a130b", outline="#33250f")

        # Install Seed row
        y = 580
        ready = self._ready() and not self.busy
        hot = self.hover == "install" and ready
        self.rect(690, y, 975, y + 62, fill=CELL_HI if hot else CELL, outline=CELL_EDGE)
        self.crest(704, y + 13)
        self.smallcaps(752, y + 43, "Install Seed", CREAM if self._ready() else DIM)
        self.rect(975, y, 1140, y + 62, fill=TRACK, outline=TRACK_EDGE)
        if self.busy:  # amber light sweeping through the track while forging
            sx = 981 + (self.t * 240) % 170
            self.rect(max(981, sx - 60), y + 50, min(1134, sx), y + 56, fill=AMBER)
            self.text(1057, y + 28, "Forging…", self.f_row, AMBER_HI, anchor="center")
        elif self.done_at and self.t - self.done_at < 4 and self.result.get("ok"):
            self.text(1057, y + 31, "Installed ✓", self.f_row, AMBER_HI, anchor="center")
        else:
            self.text(1057, y + 31, "Press Enter" if ready else "Not ready", self.f_row,
                      ORANGE if ready else FAINT, anchor="center")
        if hot:
            self.focus_ring(690, y, 1140, y + 62)
        if ready:
            self.add_region((690, y, 1140, y + 62), "install", self.install, None,
                            f"Build the mod and install it for {TARGETS[self.target]}.")

    def _hash_row(self, y):
        """The seed's 5 hash symbols (empty slots until a seed is built)."""
        seed_hash = self.result.get("hash")
        names = race.hash_symbols(seed_hash) if seed_hash else [None] * race.HASH_SYMBOLS
        if seed_hash:
            self.text(1124, 364, f"Hash {seed_hash}", self.f_small, DIM, anchor="e")
        step, size = 74, 38
        x = 915 - step * (len(names) - 1) / 2
        for i, name in enumerate(names):
            x0 = x + i * step - size / 2 - 3
            self.rect(x0, y, x0 + size + 6, y + size + 6, fill=TRACK, outline=TRACK_EDGE)
            if name:
                seed_icons.draw(self, name, x0 + 3, y + 3, size)
                hint = (f"Hash symbol {i + 1}: {name}. Racers with the same 5 symbols, in the same order, "
                        "play the same seed.")
            else:
                self.text(x0 + size / 2 + 3, y + size / 2 + 3, "?", self.f_row, FAINT, anchor="center")
                hint = "The seed's 5 hash symbols appear here once it is installed."
            self.add_region((x0, y, x0 + size + 6, y + size + 6), f"hash:{i}", None, None, hint)

    def _small_button(self, box, label, rid, fn, enabled, hint):
        x0, y0, x1, y1 = box
        hot = self.hover == rid and enabled
        self.rect(x0, y0, x1, y1, fill=CELL_HI if hot else CELL, outline=CELL_EDGE)
        self.text((x0 + x1) / 2, (y0 + y1) / 2, label, self.f_small, CREAM if enabled else DIM, anchor="center")
        if hot:
            self.focus_ring(x0, y0, x1, y1)
        if enabled:
            self.add_region(box, rid, fn, None, hint)

    def _race_buttons(self):
        """Copy / paste a settings string, under Install Seed."""
        for i, (lab, rid, fn, hint) in enumerate((
                ("Copy Settings", "copy", lambda: self.copy_settings(False),
                 "Copy a short string of these settings to the clipboard, to share them for a race."),
                ("Copy with Seed", "copyseed", lambda: self.copy_settings(True),
                 "Copy these settings and the seed: everyone who pastes it builds exactly the same seed "
                 "(same OoTRR version needed). Install first: the string then carries the seed hash."),
                ("Paste Settings", "paste", self.paste_settings,
                 "Apply a settings string from the clipboard (and its seed, if it has one). If it has the host's "
                 "seed hash, the app says after the install whether you got the same seed."))):
            bx = 690 + i * 153
            self._small_button((bx, 652, bx + 144, 678), lab, rid, fn, not self.busy, hint)

    def _footer(self):
        items = [("Spoiler", "X", "spoiler", self.open_spoiler, bool(self.result.get("spoiler"))),
                 ("Default Settings", "Y", "defaults", lambda: self.apply_preset("Standard"), True),
                 ("Back", "B", "close", self._close, True)]
        x = W - 28
        for label, letter, rid, fn, en in reversed(items):
            hot = self.hover == rid and en
            col = "#ffffff" if en else FAINT
            circle_x = x - 11
            self.oval(circle_x - 11, 690, circle_x + 11, 712, fill="#fdfdf6" if en else FAINT, outline="")
            self.text(circle_x, 701, letter, self.f_small, "#222222", anchor="center")
            tx = circle_x - 18
            self.text(tx, 701, label, self.f_footer, col, anchor="e")
            w = self.width_of(self.f_footer, label) + 56
            if hot:
                self.rect(x - w, 686, x + 4, 716, outline="#fdfdf6")
            if en:
                self.add_region((x - w, 686, x + 4, 716), rid, fn, None, None)
            x -= w + 14

    # ---- state helpers --------------------------------------------------------------------------------------
    def _romfs(self) -> Path | None:
        if self.target == "eden":
            return self.eden_romfs
        if self.romfs_override:
            return self.romfs_override
        return self.longshot / "romfs" if self.longshot else None

    def _game_ok(self) -> bool:
        if self.target == "eden":
            return self.emu_dir is not None and self.emu_dir.is_dir()
        return self.longshot is not None and self.longshot.is_dir()

    def _mods_dir(self) -> Path:
        """Folder the mod folder is written into."""
        if self.target == "eden":
            return self.emu_dir / "load" / TITLE_ID
        return self.longshot / "mods"

    def _version(self) -> str:
        try:
            for line in (self.longshot / "longshot_version.txt").read_text(encoding="utf-8").splitlines():
                if line.startswith("version="):
                    return line.split("=", 1)[1]
        except OSError:
            pass
        return self.longshot.name

    @staticmethod
    def _short(s: str, n: int) -> str:
        return s if len(s) <= n else "…" + s[-(n - 1):]

    def _ready(self) -> bool:
        r = self._romfs()
        return bool(self._game_ok() and r and valid_romfs(r))

    # ---- interaction ----------------------------------------------------------------------------------------
    def _hit(self, e):
        x, y = e.x / self.S, e.y / self.S
        for r in reversed(self.regions):
            x0, y0, x1, y1 = r["box"]
            if x0 <= x <= x1 and y0 <= y <= y1:
                return r
        return None

    def _motion(self, e):
        r = self._hit(e)
        self._set_hover(r["id"] if r else None, (r["hint"] or DEFAULT_HINT) if r else DEFAULT_HINT)

    def _set_hover(self, rid, hint=DEFAULT_HINT):
        if rid != self.hover or hint != self.hint:
            self.hover, self.hint = rid, hint
            self.c.configure(cursor="hand2" if rid else "")
            if not self.busy:
                self.draw()

    def _click(self, e, side):
        self.c.focus_set()
        r = self._hit(e)
        if r and r[side]:
            r[side]()
        if not self.busy:
            self.draw()

    def step(self, name, d):
        default, allowed, _ = settings_mod.SETTINGS[name]
        cur = self.values[name]
        if allowed is bool:
            self.values[name] = not cur
        elif allowed is int:
            lo, hi = settings_ui.int_range(name, self.values)
            self.values[name] = min(hi, max(lo, cur + d))
        else:  # stops at both ends, like the menu's arrows
            self.values[name] = allowed[min(len(allowed) - 1, max(0, allowed.index(cur) + d))]
        if name == "bridge" and self.values["bridge"] in BRIDGE_MAX:
            self.values["bridge_count"] = min(self.values["bridge_count"], BRIDGE_MAX[self.values["bridge"]])
        self.preset = "Custom"

    def next_page(self, d=1):
        self.page = (self.page + d) % len(PAGES)

    def apply_preset(self, name):
        self.values = settings_mod.defaults()
        self.values.update(PRESETS[name])
        self.preset = name

    def copy_settings(self, with_seed: bool):
        if with_seed and not self.seed_var.get().strip():
            self.roll()
        seed = self.seed_var.get().strip() if with_seed else None
        try:
            s = race.encode(self.values, seed)
            # the hash of the installed seed, if it was built from these very settings and seed
            if with_seed and self.result.get("ok") and self.result.get("hash") and self.result.get("code") == s:
                s = race.encode(self.values, seed, self.result["hash"])
        except (race.SettingsStringError, settings_mod.SettingsError) as exc:
            self.status = ("These settings cannot be copied", RED)
            self.log_line(f"{exc}\n")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(s)
        self.status = ("Settings and seed copied" if with_seed else "Settings copied", AMBER_HI)
        self.log_line(f"Copied to the clipboard: {s}\n")

    def paste_settings(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""
        try:
            values, seed, seed_hash = race.decode_full(text)
        except race.SettingsStringError as exc:
            self.status = ("Not a valid settings string", RED)
            self.log_line(f"Paste Settings: {exc}.\n")
            return
        self.values = values
        self.preset = next((n for n, over in PRESETS.items() if {**settings_mod.defaults(), **over} == values),
                           "Custom")
        if seed is not None:
            self.seed_var.set(seed)
        self.result = {}
        self.expected = (race.encode(values, seed), seed_hash) if seed_hash else None
        self.status = ("Settings and seed pasted" if seed is not None else "Settings pasted", AMBER_HI)
        self.log_line(f"Pasted {''.join(text.split()).upper()}" + (f" (seed {seed})" if seed else "") + ".\n")
        if seed_hash:
            self.log_line("Press Install Seed: the app will check that you get the host's seed.\n")
        self._save_cfg()

    def roll(self):
        self.seed_var.set(str(secrets.randbelow(10 ** 9)))

    def set_target(self, key):
        if key != self.target and not self.busy:
            self.target = key
            self.running = game_running(key)
            self.status = ("Ready", CREAM)
            self.result = {}
            self._save_cfg()

    def pick_game(self):
        from tkinter import filedialog
        if self.target == "eden":
            d = filedialog.askdirectory(title="Emulator data folder (the one with load/)",
                                        initialdir=str(self.emu_dir or Path.home()))
            if d and (Path(d) / "load").is_dir():
                self.emu_dir = Path(d)
                self._save_cfg()
            elif d:
                self.status = ("No load folder in that folder", RED)
            return
        d = filedialog.askdirectory(title="Longshot version folder", initialdir=str(self.longshot or Path.home()))
        if d and (Path(d) / "longshot.exe").is_file():
            self.longshot, self.romfs_override = Path(d), None
            self._save_cfg()
        elif d:
            self.status = ("longshot.exe not found in that folder", RED)

    def pick_romfs(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="RomFS folder", initialdir=str(self._romfs() or Path.home()))
        if d and self.target == "eden":
            self.eden_romfs = Path(d)
            self._save_cfg()
        elif d:
            self.romfs_override = Path(d)
            self._save_cfg()
        if d and not valid_romfs(Path(d)):
            self.status = ("Not a RomFS folder (no GameData / Pack)", RED)

    def open_spoiler(self):
        if self.result.get("spoiler"):
            os.startfile(self.result["spoiler"])

    def open_mods(self):
        mods = self._mods_dir()
        mods.mkdir(parents=True, exist_ok=True)
        os.startfile(mods)

    # ---- install --------------------------------------------------------------------------------------------
    def install(self):
        if self.busy or not self._ready():
            return
        name = TARGETS[self.target]
        if game_running(self.target):
            self.status = (f"Close {name} first", RED)
            self.log_line(f"{name} is running: its mod files are locked. Close it and try again.\n")
            self.draw()
            return
        if not self.seed_var.get().strip():
            self.roll()
        seed = self.seed_var.get().strip()
        mods = self._mods_dir()
        argv = ["--seed", seed, "--romfs", str(self._romfs()), "--out", str(SEEDS_DIR), "--mod-name", MOD_NAME]
        if self.target == "eden":
            os.environ["OOTRR_EMU_DIR"] = str(self.emu_dir)  # read by modbuild.emulator_root() for --install
            argv.append("--install")
        else:
            argv += ["--mod-out", str(mods)]
        for k, v in self.values.items():
            if k != "spawn_point" and v != settings_mod.defaults()[k]:
                argv += ["--set", f"{k}={v}"]
        try:  # what the seed is built from, to add its hash to "Copy with Seed"
            code = race.encode(self.values, seed)
        except (race.SettingsStringError, settings_mod.SettingsError):
            code = None
        self.busy, self.result = True, {}
        self.status = ("Forging the seed…", AMBER_HI)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.log_line(f"Seed {seed}\n")
        self._save_cfg()
        mods.mkdir(parents=True, exist_ok=True)
        SEEDS_DIR.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._work, args=(argv, code), daemon=True).start()

    def _work(self, argv, code):
        from ..__main__ import main as cli
        w = QueueWriter(self.q)
        code, err = 1, None
        try:
            with contextlib.redirect_stdout(w), contextlib.redirect_stderr(w):
                code = cli(argv)
        except SystemExit as exc:
            err = exc.code if isinstance(exc.code, str) else None
            code = exc.code if isinstance(exc.code, int) else 1
        except Exception as exc:  # shown in the log
            err, code = f"{type(exc).__name__}: {exc}", 1
        spoilers = sorted(SEEDS_DIR.glob("*_spoiler.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        ok = code == 0 and bool(spoilers)
        # OoTRR_<seed>_<hash>_spoiler.txt (the app's seeds are numbers, see __main__.seed_to_int)
        seed_hash = spoilers[0].name.split("_")[2] if ok else None
        self.q.put(("done", {"ok": code == 0, "err": err, "spoiler": str(spoilers[0]) if ok else None,
                             "hash": seed_hash, "code": code}))

    def _tick(self):
        self.t += 0.033
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "log":
                    self.log_line(data)
                else:
                    self.busy = False
                    self.result = data
                    self.done_at = self.t
                    if data["err"]:
                        self.log_line(f"\n{data['err']}\n")
                    if data["ok"]:
                        name = TARGETS[self.target]
                        self.status = (f"Installed. Start {name} to play.", AMBER_HI)
                        self.log_line(f"\nDone. The mod is in {name}'s mods folder; start the game to play.\n")
                        self._check_host_hash(data)
                        others = self._other_ootrr_mods()
                        if others:
                            self.log_line(f"Other OoTRR mods are installed ({', '.join(others)}): disable them in "
                                          "the emulator (right-click the game > Configure > Add-Ons), only one "
                                          "OoTRR mod may be active.\n")
                    else:
                        self.status = ("Something went wrong", RED)
                    self.draw()
        except queue.Empty:
            pass
        if self.busy:
            self.draw()
        elif self.done_at and self.t - self.done_at < 4.1 and int(self.t * 30) % 4 == 0:
            self.draw()
        self._poll_running += 1
        if self._poll_running % 90 == 0 and not self.busy:
            running = game_running(self.target)
            if running != self.running:
                self.running = running
                self.status = ((f"{TARGETS[self.target]} is running: close it to install", AMBER_HI) if running
                               else ("Ready", CREAM))
                self.draw()
        self.root.after(33, self._tick)

    def _check_host_hash(self, data: dict):
        """After an install of a pasted seed: compare its hash with the host's (if the string had it)."""
        if not self.expected or data.get("code") != self.expected[0]:
            return
        expected = self.expected[1]
        if data.get("hash") == expected:
            self.status = ("Installed: same seed as the host \u2713", AMBER_HI)
            self.log_line(f"Same seed as the host (hash {expected}).\n")
        else:
            self.status = ("Not the host's seed: check the OoTRR version", RED)
            self.log_line(f"Your seed hash is {data.get('hash')}, the host's is {expected}: same settings and seed, "
                          "but another placement. You and the host must use the same OoTRR version.\n")

    def _other_ootrr_mods(self) -> list[str]:
        if self.target != "eden":
            return []
        with contextlib.suppress(OSError):
            return sorted(p.name for p in self._mods_dir().iterdir()
                          if p.is_dir() and p.name.lower().startswith("ootrr") and p.name != MOD_NAME)
        return []

    def run(self):
        self.root.mainloop()


def main() -> int:
    App().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
