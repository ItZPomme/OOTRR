"""Plandomizer window: choose where items are, Link's starting age and start point, and the settings.

    python -m ootrr.tools.plando_app [FILE.json]

Pick a location in the list, then an item on the right ("Random" gives it back to the generator). The other
locations are filled by the normal generator with the logic, so the seed stays finishable: "Check" generates the
seed and writes its spoiler, "Install" also builds the PC mod `OoTRR` for Longshot or Eden (game closed), like the
desktop app: it replaces the seed installed by the app. The game, emulator and RomFS folders are shared with the
desktop app (%APPDATA%/OoTRR/longshot_app.json). Plandos are saved as JSON (format in ootrr/plando.py) and can be
generated from the command line too: `python -m ootrr --plando FILE --romfs ROMFS --install`. The in-game menu
(native module) generates its own seeds and does not read plandos.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import plando as plando_mod
from .. import settings as settings_mod
from .. import settings_ui, starting
from ..modbuild import emulator_root
from ..world import DataError, World
from .longshot_app import CONFIG, QueueWriter, TARGETS, game_running, saved_longshot, valid_romfs
from .longshot_support import longshot_binary

APP_DIR = CONFIG.parent
OUT = APP_DIR / "plando"
MOD_NAME = "OoTRR"  # same mod as the desktop app: a plando replaces the installed seed (one OoTRR mod at a time)
RANDOM = "(Random)"
KIND_LABEL = {"pool": "", "reward": "boss reward: stones and medallions only", "song": "song location: songs only"}


class PlandoApp:
    def __init__(self, path: str | None = None):
        with contextlib.suppress(Exception):
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        self.root = tk.Tk()
        self.root.title("OoTRR Plandomizer")
        with contextlib.suppress(Exception):  # window / taskbar icon (the logo is bundled in the exe)
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
            self._icon = tk.PhotoImage(file=str(base / "ootrr" / "assets" / "longshot.png"))
            self.root.iconphoto(True, self._icon)
        self.root.geometry("1180x760")
        self.root.minsize(900, 560)
        self.cfg = self._load_cfg()
        self.path: Path | None = None
        self.settings: dict = {k: v for k, v in settings_mod.defaults().items() if k != "spawn_point"}
        self.placements: dict[str, str] = {}
        self.starting_items: list[str] = []
        self.world: World | None = None
        self.kinds: dict[str, str] = {}
        self.log_queue: queue.Queue = queue.Queue()
        self.running = False

        self.seed_var = tk.StringVar(value="")
        self.age_var = tk.StringVar(value="child")
        self.spawn_var = tk.StringVar(value="")
        self.search_var = tk.StringVar(value="")
        self.item_search_var = tk.StringVar(value="")
        self.target_var = tk.StringVar(value=self.cfg.get("target") if self.cfg.get("target") in TARGETS
                                       else "longshot")
        found = saved_longshot(self.cfg.get("longshot"))
        longshot = str(found) if found else ""
        emu = self.cfg.get("emu_dir") or (str(emulator_root()) if emulator_root() else "")
        self.dirs = {"longshot": longshot, "eden": emu}
        romfs = self.cfg.get("romfs") or ""
        if romfs and not valid_romfs(Path(romfs)):  # inside a Longshot version deleted since
            romfs = ""
        self.romfs_dirs = {"longshot": romfs, "eden": self.cfg.get("eden_romfs") or ""}
        self.game_var = tk.StringVar()
        self.romfs_var = tk.StringVar()
        self.only_set_var = tk.BooleanVar(value=False)
        self._build()
        self._update_start_items_button()
        if path:
            self.open_file(Path(path))
        else:
            self.rebuild_world()
        self.root.after(100, self._drain_log)

    # ------------------------------------------------------------------ config
    def _load_cfg(self) -> dict:
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}

    def _save_cfg(self):
        """Writes the folders back into the desktop app's config (its other keys are kept)."""
        self._store_target_fields()
        cfg = self._load_cfg()
        cfg.update({"target": self.target_var.get(), "longshot": self.dirs["longshot"] or None,
                    "emu_dir": self.dirs["eden"] or None, "romfs": self.romfs_dirs["longshot"] or None,
                    "eden_romfs": self.romfs_dirs["eden"] or None})
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def _store_target_fields(self):
        target = getattr(self, "_shown_target", None)
        if target:
            self.dirs[target] = self.game_var.get().strip()
            self.romfs_dirs[target] = self.romfs_var.get().strip()

    def _show_target(self):
        self._store_target_fields()
        target = self.target_var.get()
        self._shown_target = target
        self.game_var.set(self.dirs[target])
        self.romfs_var.set(self.romfs_dirs[target])
        self.game_label.configure(text="Longshot folder" if target == "longshot" else "Emulator folder")

    def romfs(self) -> Path | None:
        """RomFS to read: the one picked, or Longshot's own."""
        text = self.romfs_var.get().strip()
        if text:
            return Path(text)
        if self.target_var.get() == "longshot" and self.game_var.get().strip():
            return Path(self.game_var.get().strip()) / "romfs"
        return None

    # ------------------------------------------------------------------ layout
    def _build(self):
        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Seed").pack(side="left")
        ttk.Entry(top, textvariable=self.seed_var, width=14).pack(side="left", padx=(4, 14))
        ttk.Label(top, text="Starting age").pack(side="left")
        age = ttk.Combobox(top, textvariable=self.age_var, values=["child", "adult"], state="readonly", width=7)
        age.pack(side="left", padx=(4, 14))
        age.bind("<<ComboboxSelected>>", lambda e: self._age_changed())
        ttk.Label(top, text="Start point").pack(side="left")
        self.spawn_box = ttk.Combobox(top, textvariable=self.spawn_var, state="readonly", width=34)
        self.spawn_box.pack(side="left", padx=(4, 14))
        self.spawn_box.bind("<<ComboboxSelected>>", lambda e: self.rebuild_world())
        ttk.Button(top, text="Settings…", command=self.open_settings).pack(side="left")
        ttk.Button(top, text="Open…", command=self.open_dialog).pack(side="right")
        ttk.Button(top, text="Save as…", command=lambda: self.save_dialog(True)).pack(side="right", padx=4)
        ttk.Button(top, text="Save", command=lambda: self.save_dialog(False)).pack(side="right")
        ttk.Button(top, text="New", command=self.new_plando).pack(side="right", padx=4)

        start_bar = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        start_bar.pack(fill="x")
        self.start_items_button = ttk.Button(start_bar, text="Choose starting items…",
                                             command=self.open_start_items)
        self.start_items_button.pack(side="left")
        ttk.Label(start_bar, text="Select items Link receives at the start.").pack(side="left", padx=8)

        body = ttk.PanedWindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10)

        left = ttk.Frame(body)
        body.add(left, weight=3)
        bar = ttk.Frame(left)
        bar.pack(fill="x", pady=(0, 4))
        ttk.Label(bar, text="Search").pack(side="left")
        e = ttk.Entry(bar, textvariable=self.search_var)
        e.pack(side="left", fill="x", expand=True, padx=4)
        self.search_var.trace_add("write", lambda *a: self.fill_tree())
        ttk.Checkbutton(bar, text="Only chosen", variable=self.only_set_var,
                        command=self.fill_tree).pack(side="left")
        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=("vanilla", "chosen"), selectmode="browse")
        self.tree.heading("#0", text="Region / location")
        self.tree.heading("vanilla", text="Original item")
        self.tree.heading("chosen", text="Chosen item")
        self.tree.column("#0", width=330)
        self.tree.column("vanilla", width=190)
        self.tree.column("chosen", width=190)
        self.tree.tag_configure("set", foreground="#1a5fb4")
        self.tree.tag_configure("bad", foreground="#c01c28")
        self.tree.tag_configure("region", font=("Segoe UI", 9, "bold"))
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_location())

        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(right, weight=2)
        self.loc_title = ttk.Label(right, text="Pick a location", font=("Segoe UI", 11, "bold"), wraplength=380)
        self.loc_title.pack(anchor="w")
        self.loc_info = ttk.Label(right, text="", wraplength=380, foreground="#555")
        self.loc_info.pack(anchor="w", pady=(2, 8))
        bar2 = ttk.Frame(right)
        bar2.pack(fill="x")
        ttk.Label(bar2, text="Item").pack(side="left")
        ttk.Entry(bar2, textvariable=self.item_search_var).pack(side="left", fill="x", expand=True, padx=4)
        self.item_search_var.trace_add("write", lambda *a: self.fill_items())
        items_frame = ttk.Frame(right)
        items_frame.pack(fill="both", expand=True, pady=4)
        self.items = tk.Listbox(items_frame, activestyle="dotbox", exportselection=False)
        sb2 = ttk.Scrollbar(items_frame, orient="vertical", command=self.items.yview)
        self.items.configure(yscrollcommand=sb2.set)
        self.items.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        self.items.bind("<Double-Button-1>", lambda e: self.set_item())
        self.items.bind("<Return>", lambda e: self.set_item())
        buttons = ttk.Frame(right)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Place this item", command=self.set_item).pack(side="left")
        ttk.Button(buttons, text="Back to random", command=self.clear_item).pack(side="left", padx=4)
        self.count_label = ttk.Label(buttons, text="")
        self.count_label.pack(side="right")

        bottom = ttk.Frame(self.root, padding=(10, 6))
        bottom.pack(fill="x")
        for key, label in TARGETS.items():
            ttk.Radiobutton(bottom, text=label, value=key, variable=self.target_var,
                            command=self._show_target).pack(side="left")
        self.game_label = ttk.Label(bottom, text="", width=15, anchor="e")
        self.game_label.pack(side="left")
        ttk.Entry(bottom, textvariable=self.game_var, width=34).pack(side="left", padx=4)
        ttk.Button(bottom, text="…", width=3, command=self.pick_game).pack(side="left")
        ttk.Label(bottom, text="RomFS").pack(side="left", padx=(10, 0))
        ttk.Entry(bottom, textvariable=self.romfs_var, width=30).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(bottom, text="…", width=3, command=self.pick_romfs).pack(side="left")
        self.install_btn = ttk.Button(bottom, text="Install", command=lambda: self.generate(True))
        self.install_btn.pack(side="right")
        self.check_btn = ttk.Button(bottom, text="Check (spoiler only)", command=lambda: self.generate(False))
        self.check_btn.pack(side="right", padx=6)
        self._show_target()
        self.log = tk.Text(self.root, height=8, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="x", padx=10, pady=(0, 10))

    # ------------------------------------------------------------------ world
    def full_settings(self) -> dict:
        """Settings as the generator will see them (age and start point resolved)."""
        raw = dict(self.settings, starting_age=self.age_var.get())
        resolved = settings_mod.build(starting.resolve(settings_mod.build(raw), 0))
        return plando_mod.apply_start(resolved, self.spawn())

    def spawn(self) -> dict | None:
        label = self.spawn_var.get()
        for sp in plando_mod.spawn_choices(self.age_var.get()):
            if self._spawn_label(sp) == label:
                return {"age": sp["age"], "region": sp["region"], "pos": sp["pos"]}
        return None

    @staticmethod
    def _spawn_label(sp: dict) -> str:
        return f"{sp['region']}  ({sp['pos']})"

    def _default_spawn_label(self) -> str:
        return "Default (Temple of Time)" if self.age_var.get() == "adult" else "Default (Link's house)"

    def _age_changed(self):
        self.fill_spawns(None)
        self.rebuild_world()

    def fill_spawns(self, spawn: dict | None):
        labels = [self._default_spawn_label()] + [self._spawn_label(sp)
                                                  for sp in plando_mod.spawn_choices(self.age_var.get())]
        self.spawn_box.configure(values=labels)
        chosen = self._default_spawn_label()
        for sp in plando_mod.spawn_choices(self.age_var.get()):
            if spawn and sp["region"] == spawn.get("region") and (not spawn.get("pos") or sp["pos"] == spawn["pos"]):
                chosen = self._spawn_label(sp)
        self.spawn_var.set(chosen)

    def rebuild_world(self):
        if not self.spawn_box.cget("values"):
            self.fill_spawns(None)
        try:
            self.world = World(self.full_settings())
        except (settings_mod.SettingsError, plando_mod.PlandoError, DataError) as exc:
            messagebox.showerror("Settings", str(exc))
            return
        self.kinds = plando_mod.placeable(self.world)
        self.fill_tree()
        self.show_location()

    # ------------------------------------------------------------------ tree
    def fill_tree(self):
        if not self.world:
            return
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        needle = self.search_var.get().lower().strip()
        regions: dict[str, list] = {}
        for loc in self.world.locations.values():
            if loc.name not in self.kinds and loc.name not in self.placements:
                continue
            if self.only_set_var.get() and loc.name not in self.placements:
                continue
            chosen = self.placements.get(loc.name, "")
            if needle and needle not in f"{loc.name} {loc.region} {loc.vanilla} {chosen}".lower():
                continue
            regions.setdefault(loc.region, []).append(loc)
        bad = set(self.problems())
        for region in sorted(regions):
            n = sum(l.name in self.placements for l in regions[region])
            rid = self.tree.insert("", "end", iid=f"region::{region}", text=f"{region}" + (f"   [{n}]" if n else ""),
                                   open=bool(needle) or self.only_set_var.get(), tags=("region",))
            for loc in sorted(regions[region], key=lambda l: l.name):
                chosen = self.placements.get(loc.name, "")
                tags = ("bad",) if loc.name in bad else ("set",) if chosen else ()
                self.tree.insert(rid, "end", iid=loc.name, text=loc.name,
                                 values=(loc.vanilla, chosen or RANDOM), tags=tags)
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.see(iid)
                self.tree.selection_set(iid)
        self.count_label.configure(text=f"{len(self.placements)} chosen, {len(self.kinds)} locations")

    def problems(self) -> dict[str, str]:
        """location -> problem, for the chosen placements (settings changed, wrong kind...)."""
        if not self.world:
            return {}
        out = {}
        for text in plando_mod.validate(self.world, self.placements):
            name = text.split(":", 1)[0]
            out[name if name in self.placements else text] = text
        return out

    def current(self):
        sel = self.tree.selection()
        if not sel or sel[0].startswith("region::") or not self.world:
            return None
        return self.world.locations.get(sel[0])

    def show_location(self):
        loc = self.current()
        if loc is None:
            self.loc_title.configure(text="Pick a location")
            self.loc_info.configure(text="Locations shuffled with these settings, by region. Double-click an item "
                                         "to place it.")
            self.items.delete(0, "end")
            return
        kind = self.kinds.get(loc.name)
        lines = [f"Region: {loc.region}", f"Original item: {loc.vanilla}", f"Rule: {loc.rule_src}"]
        if kind and KIND_LABEL[kind]:
            lines.append(KIND_LABEL[kind])
        problem = self.problems().get(loc.name)
        if problem:
            lines.append(f"Problem: {problem}")
        self.loc_title.configure(text=loc.name)
        self.loc_info.configure(text="\n".join(lines))
        self.fill_items()

    def allowed_items(self, loc) -> list[str]:
        kind = self.kinds.get(loc.name)
        if kind == "reward":
            return sorted({l.vanilla for l in self.world.reward_locations()})
        if kind == "song":
            return sorted({l.vanilla for l in self.world.song_locations()})
        if kind is None:
            return []
        return sorted(name for name in self.world.items if self.world.can_place(name, loc))

    def fill_items(self):
        loc = self.current()
        self.items.delete(0, "end")
        if loc is None:
            return
        needle = self.item_search_var.get().lower().strip()
        chosen = self.placements.get(loc.name)
        entries = [RANDOM] + [i for i in self.allowed_items(loc) if not needle or needle in i.lower()]
        for i, name in enumerate(entries):
            self.items.insert("end", name)
            if name == (chosen or RANDOM):
                self.items.selection_set(i)
                self.items.see(i)

    def set_item(self):
        loc = self.current()
        sel = self.items.curselection()
        if loc is None or not sel:
            return
        item = self.items.get(sel[0])
        if item == RANDOM:
            self.placements.pop(loc.name, None)
        else:
            self.placements[loc.name] = item
        self.fill_tree()
        self.show_location()

    def clear_item(self):
        loc = self.current()
        if loc is not None:
            self.placements.pop(loc.name, None)
            self.fill_tree()
            self.show_location()

    def _update_start_items_button(self):
        self.start_items_button.configure(text=f"Choose starting items… ({len(self.starting_items)})")

    def open_start_items(self):
        if self.world is None:
            return
        world = self.world
        win = tk.Toplevel(self.root)
        win.title("Starting items")
        win.geometry("760x480")
        win.minsize(620, 360)
        win.transient(self.root)

        search_var = tk.StringVar()
        search = ttk.Frame(win, padding=8)
        search.pack(fill="x")
        ttk.Label(search, text="Search").pack(side="left")
        ttk.Entry(search, textvariable=search_var).pack(side="left", fill="x", expand=True, padx=6)

        lists = ttk.PanedWindow(win, orient="horizontal")
        lists.pack(fill="both", expand=True, padx=8)
        available_frame = ttk.LabelFrame(lists, text="Available items")
        chosen_frame = ttk.LabelFrame(lists, text="Selected starting items")
        lists.add(available_frame, weight=1)
        lists.add(chosen_frame, weight=1)
        available = tk.Listbox(available_frame, selectmode="extended", exportselection=False)
        chosen = tk.Listbox(chosen_frame, selectmode="extended", exportselection=False)
        available_scroll = ttk.Scrollbar(available_frame, orient="vertical", command=available.yview)
        chosen_scroll = ttk.Scrollbar(chosen_frame, orient="vertical", command=chosen.yview)
        available.configure(yscrollcommand=available_scroll.set)
        chosen.configure(yscrollcommand=chosen_scroll.set)
        available.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        available_scroll.pack(side="right", fill="y", padx=(0, 5), pady=5)
        chosen.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        chosen_scroll.pack(side="right", fill="y", padx=(0, 5), pady=5)

        def refresh_available():
            needle = search_var.get().lower().strip()
            available.delete(0, "end")
            for name in plando_mod.startable_items(world):
                if not needle or needle in name.lower():
                    available.insert("end", name)

        def refresh_chosen():
            chosen.delete(0, "end")
            for name in self.starting_items:
                chosen.insert("end", name)
            self._update_start_items_button()

        def add_selected():
            self.starting_items.extend(available.get(i) for i in available.curselection())
            refresh_chosen()

        def remove_selected():
            for i in reversed(chosen.curselection()):
                del self.starting_items[i]
            refresh_chosen()

        def add_double_clicked(event: tk.Event):
            index = available.nearest(event.y)
            if index >= 0:
                available.selection_clear(0, "end")
                available.selection_set(index)
                add_selected()

        def remove_on_delete(event: tk.Event):
            if event.widget is chosen:
                remove_selected()

        search_var.trace_add("write", lambda *_: refresh_available())
        available.bind("<Double-Button-1>", add_double_clicked)
        chosen.bind("<Delete>", remove_on_delete)
        buttons = ttk.Frame(win, padding=8)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Add selected →", command=add_selected).pack(side="left")
        ttk.Button(buttons, text="← Remove selected", command=remove_selected).pack(side="left", padx=6)
        ttk.Button(buttons, text="Clear all", command=lambda: (self.starting_items.clear(), refresh_chosen())).pack(
            side="left")
        ttk.Button(buttons, text="Done", command=win.destroy).pack(side="right")
        refresh_available()
        refresh_chosen()

    # ------------------------------------------------------------------ settings dialog
    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry("640x560")
        win.transient(self.root)
        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        variables: dict[str, tk.Variable] = {}
        for page, names in settings_ui.PAGES:
            frame = ttk.Frame(notebook, padding=8)
            notebook.add(frame, text=page)
            row = 0
            for name in names:
                if name == "starting_age":
                    continue  # chosen in the main window
                _, allowed, _ = settings_mod.SETTINGS[name]
                ttk.Label(frame, text=settings_ui.title(name), font=("Segoe UI", 9, "bold")).grid(
                    row=row, column=0, sticky="w", pady=(6, 0))
                value = self.settings.get(name)
                if allowed is bool:
                    var = tk.BooleanVar(value=bool(value))
                    ttk.Checkbutton(frame, variable=var).grid(row=row, column=1, sticky="w")
                elif allowed is int:
                    var = tk.StringVar(value=str(value))
                    ttk.Spinbox(frame, from_=0, to=20, textvariable=var, width=6).grid(row=row, column=1, sticky="w")
                else:
                    labels = {settings_ui.value_label(name, v): v for v in allowed}
                    var = tk.StringVar(value=settings_ui.value_label(name, value))
                    var.labels = labels  # type: ignore[attr-defined]
                    ttk.Combobox(frame, textvariable=var, values=list(labels), state="readonly", width=22).grid(
                        row=row, column=1, sticky="w")
                variables[name] = var
                ttk.Label(frame, text=settings_ui.caption(name), wraplength=560, foreground="#555").grid(
                    row=row + 1, column=0, columnspan=2, sticky="w")
                row += 2
            frame.columnconfigure(0, weight=1)

        def apply():
            new = dict(self.settings)
            for name, var in variables.items():
                _, allowed, _ = settings_mod.SETTINGS[name]
                if allowed is bool:
                    new[name] = bool(var.get())
                elif allowed is int:
                    new[name] = var.get()
                else:
                    new[name] = var.labels[var.get()]  # type: ignore[attr-defined]
            try:
                settings_mod.build({k: v for k, v in new.items() if k != "spawn_point"})
            except settings_mod.SettingsError as exc:
                messagebox.showerror("Settings", str(exc), parent=win)
                return
            self.settings = {k: settings_mod.build(new)[k] for k in new}
            win.destroy()
            self.rebuild_world()

        bar = ttk.Frame(win, padding=8)
        bar.pack(fill="x")
        ttk.Button(bar, text="OK", command=apply).pack(side="right")
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right", padx=6)

    # ------------------------------------------------------------------ files
    def new_plando(self):
        if (self.placements or self.starting_items) and not messagebox.askyesno(
            "New plando", "Forget the chosen placements and starting items?"
        ):
            return
        self.path = None
        self.placements = {}
        self.starting_items = []
        self._update_start_items_button()
        self.seed_var.set("")
        self.root.title("OoTRR Plandomizer")
        self.rebuild_world()

    def to_data(self) -> tuple[str | None, dict, dict | None, dict, list[str]]:
        defaults = settings_mod.defaults()
        settings = {k: v for k, v in self.settings.items() if k != "spawn_point" and v != defaults[k]}
        if self.age_var.get() != defaults["starting_age"]:
            settings["starting_age"] = self.age_var.get()
        return (self.seed_var.get().strip() or None, settings, self.spawn(), dict(self.placements),
                list(self.starting_items))

    def save_to(self, path: Path):
        seed, settings, spawn, placements, start_items = self.to_data()
        plando_mod.save(path, seed, settings, spawn, placements, start_items)

    def save_dialog(self, ask: bool):
        path = self.path
        if ask or path is None:
            name = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json",
                                                filetypes=[("Plando", "*.json")], initialdir=str(OUT))
            if not name:
                return
            path = Path(name)
        self.save_to(path)
        self.path = path
        self.root.title(f"OoTRR Plandomizer - {path.name}")
        self.log_line(f"saved {path}")

    def open_dialog(self):
        name = filedialog.askopenfilename(parent=self.root, filetypes=[("Plando", "*.json")], initialdir=str(OUT))
        if name:
            self.open_file(Path(name))

    def open_file(self, path: Path):
        try:
            data = plando_mod.load(path)
            settings = settings_mod.build(data.get("settings", {}))
        except (plando_mod.PlandoError, settings_mod.SettingsError) as exc:
            messagebox.showerror("Open", str(exc))
            return
        self.settings = {k: v for k, v in settings.items() if k != "spawn_point"}
        age = settings.get("starting_age", "child")
        self.age_var.set(age if age in ("child", "adult") else "child")
        self.seed_var.set(str(data.get("seed", "")))
        self.placements = {str(k): str(v) for k, v in data.get("placements", {}).items()}
        self.starting_items = list(data.get("start_items", []))
        self._update_start_items_button()
        self.fill_spawns(data.get("spawn"))
        self.path = path
        self.root.title(f"OoTRR Plandomizer - {path.name}")
        self.rebuild_world()

    def pick_game(self):
        eden = self.target_var.get() == "eden"
        name = filedialog.askdirectory(parent=self.root, title="Emulator data folder (the one with load/)" if eden
                                       else "Longshot version folder (the one with the Longshot executable)")
        if not name:
            return
        if eden and not (Path(name) / "load").is_dir():
            messagebox.showerror("Emulator", "No load folder in that folder.")
        elif not eden and not longshot_binary(Path(name)):
            messagebox.showerror("Longshot", "Longshot executable not found in that folder.")
        else:
            self.game_var.set(name)

    def pick_romfs(self):
        name = filedialog.askdirectory(parent=self.root, title="RomFS folder (GameData and Pack inside); empty = "
                                                              "Longshot's own")
        if name:
            self.romfs_var.set(name)

    # ------------------------------------------------------------------ generation
    def log_line(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip("\n") + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_log(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item is None:
                    self.running = False
                    self.check_btn.state(["!disabled"])
                    self.install_btn.state(["!disabled"])
                elif isinstance(item, tuple):  # ("log", raw text) from the generator's stdout (QueueWriter)
                    self.log.configure(state="normal")
                    self.log.insert("end", item[1])
                    self.log.see("end")
                    self.log.configure(state="disabled")
                else:
                    self.log_line(item)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log)

    def generate(self, install: bool):
        if self.running:
            return
        if self.world is None:
            messagebox.showerror("Plando", "World data is not available.")
            return
        problems = self.problems()
        if problems:
            messagebox.showerror("Plando", "Fix these placements first:\n\n" + "\n".join(problems.values()))
            return
        start_errors = plando_mod.validate_start_items(self.world, self.starting_items)
        if start_errors:
            messagebox.showerror("Starting items", "Fix the selected starting items:\n\n"
                                  + "\n".join(start_errors))
            return
        OUT.mkdir(parents=True, exist_ok=True)
        current = OUT / "_current.json"
        self.save_to(current)
        argv = ["--plando", str(current), "--out", str(OUT)]
        if install:
            target = self.target_var.get()
            name = TARGETS[target]
            game = Path(self.game_var.get().strip()) if self.game_var.get().strip() else None
            romfs = self.romfs()
            if game is None or not game.is_dir():
                messagebox.showerror(name, f"Pick the {name} folder first.")
                return
            if romfs is None or not valid_romfs(romfs):
                messagebox.showerror("RomFS", "Pick the RomFS folder (it contains GameData and Pack).")
                return
            if game_running(target):
                messagebox.showerror(name, f"{name} is running: its mod files are locked. Close it and try again.")
                return
            self._save_cfg()
            argv += ["--romfs", str(romfs), "--mod-name", MOD_NAME]
            if target == "eden":
                os.environ["OOTRR_EMU_DIR"] = str(game)  # read by modbuild.emulator_root() for --install
                argv.append("--install")
            else:
                (game / "mods").mkdir(parents=True, exist_ok=True)
                argv += ["--mod-out", str(game / "mods")]
        self.running = True
        self.check_btn.state(["disabled"])
        self.install_btn.state(["disabled"])
        self.log_line("> ootrr " + " ".join(argv))
        threading.Thread(target=self._run, args=(argv, install, TARGETS[self.target_var.get()]), daemon=True).start()

    def _run(self, argv: list[str], install: bool, where: str):
        """Runs the generator in this process (also inside the exe); no tkinter call here (worker thread)."""
        from ..__main__ import main as cli
        writer = QueueWriter(self.log_queue)
        code = 1
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                code = cli(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if isinstance(exc.code, str):
                self.log_queue.put(exc.code)
        except Exception as exc:  # shown in the log
            self.log_queue.put(f"{type(exc).__name__}: {exc}")
        if code == 0:
            self.log_queue.put(f"Done. Spoiler in {OUT}" + (f"; mod {MOD_NAME} installed for {where}: start a new "
                                                           "game (only one OoTRR mod active)." if install else "."))
        else:
            self.log_queue.put(f"Failed (code {code}).")
        self.log_queue.put(None)

    def run(self):
        self.root.mainloop()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    PlandoApp(argv[0] if argv else None).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
