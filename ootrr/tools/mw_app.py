"""Multiworld window of the desktop app: host a multiworld (code to share) or join one with a code, then play
(docs/MULTIWORLD.md, "Joining").

    python -m ootrr.tools.mw_app          # alone; the desktop app opens it with its "Multiworld" button

Host: "Open the waiting room" starts the server in the app (port opened on the router by UPnP when possible) and
shows the code. The others join with the code and their own app's settings; the host sees them arrive, then
"Generate and start" generates the multiworld, every player with their settings (the host: the app's). The code
stays the same. "Host a file..." serves a multiworld generated before (to resume a game).
Join (also the host, for their own game): code -> "Look up" -> "Join with my settings" while the room waits, then,
once generated, pick your name -> "Install and play": the player's data is fetched (never the other worlds), the
mod is built and installed into Longshot, Longshot is started with its control pipe and the bridge runs in the
app; the log shows who sent what to whom.
Only Longshot can play a multiworld for now (Eden has no client yet).
"""

from __future__ import annotations

import contextlib
import os
import queue
import random
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .. import multiworld as mw
from .. import mw_protocol as P
from .. import settings as settings_mod
from ..mw_code import CodeError, RoomCode, decode
from ..mw_session import Host, SessionError, fetch_slot, join_room, room_players, room_state, save_slot
from .longshot_support import app_data_dir, longshot_binary

APP_DIR = app_data_dir() / "OoTRR"
MW_DIR = APP_DIR / "multiworld"
PIPE = "ootrr-mw"  # Longshot's HOS_CONTROL value (its control pipe name)
WAIT_EVERY = 3.0  # seconds between two looks at a waiting room (joined player)


class QueueText:
    """stdout -> the window's log (the mod builder prints its report)."""

    def __init__(self, q: queue.Queue) -> None:
        self.q = q

    def write(self, text: str) -> int:
        if text.strip():
            self.q.put(("log", text.rstrip("\n")))
        return len(text)

    def flush(self) -> None:
        pass


def changed_settings(values: dict) -> dict:
    """The settings that differ from the defaults."""
    defaults = settings_mod.defaults()
    return {k: v for k, v in values.items() if defaults.get(k) != v}


def describe(values: dict) -> str:
    changed = changed_settings(values)
    return ", ".join(f"{k}={v}" for k, v in changed.items()) if changed else "all defaults"


class MultiworldWindow:
    def __init__(self, master: tk.Misc | None = None, settings: dict | None = None, longshot: Path | None = None,
                 romfs: Path | None = None) -> None:
        from .longshot_app import find_longshot
        self.root = tk.Toplevel(master) if master is not None else tk.Tk()
        self.root.title("OoTRR · Multiworld")
        self.root.geometry("780x680")
        self.settings = settings_mod.build(dict(settings or settings_mod.defaults()))
        self.longshot = Path(longshot) if longshot else find_longshot()
        self.romfs = Path(romfs) if romfs else (self.longshot / "romfs" if self.longshot else None)
        self.q: queue.Queue = queue.Queue()
        self.host: Host | None = None
        self.host_file: Path | None = None
        self.bridge_stop: threading.Event | None = None
        self.wait_stop: threading.Event | None = None
        self.busy = False
        self._shown_players: list[tuple[str, str]] = []
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._after = self.root.after(100, self._poll)

    # ---- layout ----
    def _build(self) -> None:
        tabs = ttk.Notebook(self.root)
        tabs.pack(fill="x", padx=10, pady=(10, 4))
        self.tabs = tabs
        mine = f"Your settings (the app's): {describe(self.settings)}"

        host = ttk.Frame(tabs, padding=10)
        tabs.add(host, text="Host")
        ttk.Label(host, text="Your name").grid(row=0, column=0, sticky="w")
        self.host_name_var = tk.StringVar(value="Player 1")
        ttk.Entry(host, textvariable=self.host_name_var, width=24).grid(row=1, column=0, sticky="w")
        ttk.Label(host, text="Port").grid(row=0, column=1, sticky="w", padx=(16, 0))
        self.port_var = tk.StringVar(value=str(P.DEFAULT_PORT))
        ttk.Entry(host, textvariable=self.port_var, width=8).grid(row=1, column=1, sticky="w", padx=(16, 0))
        ttk.Label(host, text="Address for the code (empty: automatic)").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.address_var = tk.StringVar()
        ttk.Entry(host, textvariable=self.address_var, width=20).grid(row=1, column=2, sticky="w", padx=(16, 0))
        bar = ttk.Frame(host)
        bar.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.open_button = ttk.Button(bar, text="Open the waiting room", command=self.open_room)
        self.open_button.pack(side="left")
        self.file_button = ttk.Button(bar, text="Host a file...", command=self.host_file_dialog)
        self.file_button.pack(side="left", padx=6)
        self.stop_host_button = ttk.Button(bar, text="Stop hosting", command=self.stop_hosting, state="disabled")
        self.stop_host_button.pack(side="left")

        ttk.Label(host, text="Players (each with their own settings)").grid(row=3, column=0, columnspan=3,
                                                                          sticky="w", pady=(10, 0))
        self.players_list = tk.Listbox(host, height=6, width=96, exportselection=False)
        self.players_list.grid(row=4, column=0, columnspan=3, sticky="we")
        bar = ttk.Frame(host)
        bar.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.remove_button = ttk.Button(bar, text="Remove player", command=self.remove_player, state="disabled")
        self.remove_button.pack(side="left")
        ttk.Label(bar, text="Seed (empty: random)").pack(side="left", padx=(16, 4))
        self.seed_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.seed_var, width=14).pack(side="left")
        self.generate_button = ttk.Button(bar, text="Generate and start", command=self.generate, state="disabled")
        self.generate_button.pack(side="left", padx=(10, 0))
        ttk.Label(host, text=mine + ". Set them in the app before opening this window.", foreground="#666",
                  wraplength=740).grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))

        join = ttk.Frame(tabs, padding=10)
        tabs.add(join, text="Join / Play")
        ttk.Label(join, text="Room code").grid(row=0, column=0, sticky="w")
        self.code_var = tk.StringVar()
        ttk.Entry(join, textvariable=self.code_var, width=30, font=("Consolas", 12)).grid(row=1, column=0, sticky="w")
        ttk.Button(join, text="Look up", command=self.look_up).grid(row=1, column=1, padx=6, sticky="w")
        ttk.Button(join, text="Copy", command=self.copy_code).grid(row=1, column=2, sticky="w")
        ttk.Label(join, text="Your name").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.player_var = tk.StringVar()
        self.player_box = ttk.Combobox(join, textvariable=self.player_var, width=27)
        self.player_box.grid(row=3, column=0, sticky="w")
        self.state_var = tk.StringVar(value="Paste the host's code, then Look up.")
        ttk.Label(join, textvariable=self.state_var, foreground="#666").grid(row=3, column=1, columnspan=2,
                                                                            sticky="w", padx=6)
        bar = ttk.Frame(join)
        bar.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.join_button = ttk.Button(bar, text="Join with my settings", command=self.join, state="disabled")
        self.join_button.pack(side="left")
        self.play_button = ttk.Button(bar, text="Install and play", command=self.install_and_play)
        self.play_button.pack(side="left", padx=6)
        self.stop_bridge_button = ttk.Button(bar, text="Stop", command=self.stop_bridge, state="disabled")
        self.stop_bridge_button.pack(side="left")
        ttk.Label(join, text=mine, foreground="#666", wraplength=740).grid(row=5, column=0, columnspan=3,
                                                                          sticky="w", pady=(8, 0))
        where = f"Longshot: {self.longshot}" if self.longshot else "Longshot not found: install it, or start the app once"
        ttk.Label(join, text=where, foreground="#666").grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))

        ttk.Label(self.root, text="Log").pack(anchor="w", padx=10)
        self.log = scrolledtext.ScrolledText(self.root, height=16, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # ---- helpers ----
    def say(self, text: str) -> None:
        self.q.put(("log", text))

    def _poll(self) -> None:
        while not self.q.empty():
            kind, value = self.q.get()
            if kind == "log":
                self.log.configure(state="normal")
                self.log.insert("end", value + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
            elif kind == "hosted":  # (code, waiting room?)
                code, waiting = value
                self.code_var.set(code)
                self.stop_host_button.configure(state="normal")
                for b in (self.open_button, self.file_button):
                    b.configure(state="disabled")
                if waiting:
                    self.remove_button.configure(state="normal")
                    self.generate_button.configure(state="normal")
                    self.player_var.set(self.host_name_var.get().strip())
                else:
                    self.q.put(("players", (True, self.host.lobby.names() if self.host.lobby else
                                            [p.name for p in mw.load(self.host_file).players])))
            elif kind == "players":  # (generated, names)
                generated, names = value
                self.player_box.configure(values=names)
                if generated:
                    self.join_button.configure(state="disabled")
                    self.state_var.set("Started: pick your name, then Install and play.")
                    if names and self.player_var.get() not in names:
                        self.player_var.set(names[0])
                else:
                    self.join_button.configure(state="normal" if not self._is_host_room() else "disabled")
                    self.state_var.set("Waiting room: " + ", ".join(names))
            elif kind == "generated":
                self.remove_button.configure(state="disabled")
                self.generate_button.configure(state="disabled")
                self.q.put(("players", (True, value)))
                self.player_var.set(self.host_name_var.get().strip())
                self.tabs.select(1)
            elif kind == "bridge":
                self.stop_bridge_button.configure(state="normal" if value else "disabled")
            elif kind == "idle":
                self.busy = False
                for b in (self.play_button,):
                    b.configure(state="normal")
                if self.host is None:
                    for b in (self.open_button, self.file_button):
                        b.configure(state="normal")
            elif kind == "error":
                messagebox.showerror("Multiworld", value, parent=self.root)
        self._refresh_players()
        self._after = self.root.after(100, self._poll)

    def _refresh_players(self) -> None:
        """The host's list: the waiting room's players and their settings, as they join."""
        lobby = self.host.lobby if self.host is not None else None
        if lobby is None:
            return
        rows = [(n, describe(s)) for n, s in lobby.players_copy()]
        if rows == self._shown_players:
            return
        self._shown_players = rows
        self.players_list.delete(0, "end")
        for i, (name, text) in enumerate(rows):
            self.players_list.insert("end", f"{i + 1}. {name}{' (you)' if i == 0 else ''}: {text}")

    def _start(self, target) -> None:
        if self.busy:
            return
        self.busy = True
        for b in (self.open_button, self.file_button, self.play_button):
            b.configure(state="disabled")

        def run():
            try:
                target()
            except (SessionError, CodeError, ValueError, OSError) as exc:
                self.say(f"error: {exc}")
                self.q.put(("error", str(exc)))
            except Exception as exc:  # shown, never a silent thread death
                self.say(f"error: {type(exc).__name__}: {exc}")
                self.q.put(("error", f"{type(exc).__name__}: {exc}"))
            finally:
                self.q.put(("idle", None))

        threading.Thread(target=run, daemon=True).start()

    def _port(self) -> int | None:
        try:
            return int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Multiworld", "The port must be a number.", parent=self.root)
            return None

    def _announce(self, host: Host, waiting: bool) -> None:
        for note in host.notes:
            self.say(note)
        self.say(f"Room code: {host.code}  (share it; the others use Join with it)")
        if host.local_code and host.local_code != host.code:
            self.say(f"Players on your own network (same box) use this one instead: {host.local_code}")
        if waiting:
            self.say("Waiting for the players: they paste the code, Look up, then Join with my settings. Then click "
                     "Generate and start.")
        self.q.put(("hosted", (host.code, waiting)))

    # ---- host ----
    def open_room(self) -> None:
        if self.host is not None:
            return
        port = self._port()
        name = self.host_name_var.get().strip()
        if port is None:
            return
        if not name:
            messagebox.showerror("Multiworld", "Enter your name.", parent=self.root)
            return
        address = self.address_var.get().strip() or None

        def work():
            host = Host(None, port=port, address=address, log=self.say)
            host.open_room(name, self.settings, MW_DIR)
            self.host = host
            self.say(f"{name} (you): {describe(self.settings)}")
            self._announce(host, waiting=True)

        self._start(work)

    def host_file_dialog(self) -> None:
        if self.host is not None:
            return
        port = self._port()
        if port is None:
            return
        path = filedialog.askopenfilename(parent=self.root, title="Multiworld file", initialdir=str(MW_DIR),
                                          filetypes=[("Multiworld", "mw_*.json"), ("JSON", "*.json")])
        if not path:
            return
        address = self.address_var.get().strip() or None

        def work():
            host = Host(Path(path), port=port, address=address, log=self.say)
            host.start()
            self.host, self.host_file = host, Path(path)
            self._announce(host, waiting=False)

        self._start(work)

    def remove_player(self) -> None:
        if self.host is None or self.host.lobby is None:
            return
        sel = self.players_list.curselection()
        if not sel or sel[0] == 0:
            return
        name = self._shown_players[sel[0]][0]
        self.host.lobby.remove(name)
        self.say(f"{name} removed from the waiting room")

    def generate(self) -> None:
        if self.host is None or self.host.lobby is None:
            return
        seed_text = self.seed_var.get().strip()
        if len(self.host.lobby.names()) < 2:
            messagebox.showinfo("Multiworld", "Nobody has joined yet.", parent=self.root)
            return

        def work():
            from .. import __main__ as cli
            seed = cli.seed_to_int(seed_text) if seed_text else random.SystemRandom().randrange(1, 10 ** 9)
            for name, values in self.host.lobby.players_copy():
                self.say(f"{name}: {describe(values)}")
            path = self.host.generate(seed)
            self.host_file = path
            self.say(f"Multiworld written: {path} (spoiler: {path.with_suffix('.txt').name})")
            self.say("Started: everyone can now Install and play (the code is the same).")
            self.q.put(("generated", [p.name for p in mw.load(path).players]))

        self._start(work)

    def stop_hosting(self) -> None:
        if self.host is None:
            return
        if not messagebox.askyesno("Multiworld", "Stop the server? The others will be disconnected (their progress "
                                   "is kept: Host a file... with the same file to resume).", parent=self.root):
            return
        self.host.stop()
        self.say("Server stopped.")
        self.host = None
        self._shown_players = []
        self.players_list.delete(0, "end")
        for b in (self.stop_host_button, self.remove_button, self.generate_button):
            b.configure(state="disabled")
        for b in (self.open_button, self.file_button):
            b.configure(state="normal")

    # ---- join ----
    def _host_ids(self) -> set[str]:
        if self.host is None or not self.host.code:
            return set()
        ids = {decode(self.host.code).room_hash}
        if self.host_file is not None:
            ids.add(self.host_file.stem.split("_")[-1].upper())
        return ids

    def _hosting(self, code: RoomCode) -> bool:
        return code.room_hash.upper() in self._host_ids()

    def _is_host_room(self) -> bool:
        with contextlib.suppress(CodeError):
            return self._hosting(decode(self.code_var.get().strip()))
        return False

    def _reach(self, code: RoomCode) -> RoomCode:
        """The host reaches their own server on this PC: a router usually refuses a connection from inside to its
        own internet address (seen 2026-11-21, "actively refused")."""
        return RoomCode("127.0.0.1", code.port, code.room_hash) if self._hosting(code) else code

    def copy_code(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.code_var.get().strip())

    def look_up(self) -> None:
        code = self.code_var.get().strip()

        def work():
            generated, names = room_state(self._reach(decode(code)))
            self.say(("Players: " if generated else "Waiting room, players so far: ") + ", ".join(names))
            self.q.put(("players", (generated, names)))

        self._start(work)

    def join(self) -> None:
        code_text = self.code_var.get().strip()
        name = self.player_var.get().strip()
        if not code_text or not name:
            messagebox.showinfo("Multiworld", "Enter the room code and your name.", parent=self.root)
            return

        def work():
            code = self._reach(decode(code_text))
            names = join_room(code, name, self.settings)
            self.say(f"Joined as {name} with your settings ({describe(self.settings)}). Players: {', '.join(names)}")
            self.say("Waiting for the host to start the multiworld...")
            self.q.put(("players", (False, names)))
            self._wait_for_start(code)

        self._start(work)

    def _wait_for_start(self, code: RoomCode) -> None:
        """Looks at the waiting room every few seconds until the host generates the multiworld."""
        if self.wait_stop is not None:
            self.wait_stop.set()
        stop = self.wait_stop = threading.Event()

        def run():
            last = None
            while not stop.wait(WAIT_EVERY):
                try:
                    generated, names = room_state(code)
                except (SessionError, OSError) as exc:
                    self.say(f"waiting room: {exc}")
                    continue
                if (generated, names) != last:
                    self.q.put(("players", (generated, names)))
                    last = (generated, names)
                if generated:
                    self.say("The host started the multiworld: Install and play.")
                    return

        threading.Thread(target=run, daemon=True).start()

    def install_and_play(self) -> None:
        from .longshot_app import game_running
        code_text = self.code_var.get().strip()
        player = self.player_var.get().strip()
        if not code_text or not player:
            messagebox.showinfo("Multiworld", "Enter the room code, Look up, and pick your name.", parent=self.root)
            return
        if not self.longshot or not self.romfs:
            messagebox.showerror("Multiworld", "Longshot was not found (a multiworld needs Longshot for now).",
                                 parent=self.root)
            return
        if game_running("longshot"):
            messagebox.showinfo("Multiworld", "Close Longshot first: its mod files are locked while it runs. The "
                                "app starts it again afterwards.", parent=self.root)
            return
        self.stop_bridge()

        def work():
            from ..__main__ import build_mod
            code = self._reach(decode(code_text))
            names = room_players(code)
            if player not in names:
                raise SessionError(f"no player named {player} (players: {', '.join(names)})")
            slot = names.index(player) + 1
            if self._hosting(code) and self.host_file is not None:  # the host plays too: their own file
                data = mw.load_slot(self.host_file, slot)
            else:
                data = fetch_slot(code, slot)
            server = f"{code.host}:{code.port}"
            path = save_slot(data, MW_DIR)
            self.say(f"Building {player}'s mod (multiworld {data.room_hash}, player {slot})...")
            patch = mw.slot_patch(data)
            with contextlib.redirect_stdout(QueueText(self.q)):
                build_mod(patch, self.romfs, "OoTRR", False, self.longshot / "mods")
            self.say("Mod installed. Starting Longshot (start a new game, or load this multiworld's save)...")
            env = dict(os.environ, HOS_CONTROL=PIPE, HOS_CONTROL_MEM="rw")
            executable = longshot_binary(self.longshot)
            if executable is None:
                raise SessionError("Longshot executable not found in its folder")
            subprocess.Popen([str(executable)], cwd=str(self.longshot), env=env)
            self.bridge_stop = threading.Event()
            self.q.put(("bridge", True))
            from .mw_longshot import run_until_stopped
            threading.Thread(target=run_until_stopped, args=(path, server, self.bridge_stop, self.say),
                             kwargs={"pipe": PIPE}, daemon=True).start()

        self._start(work)

    def stop_bridge(self) -> None:
        if self.bridge_stop is not None:
            self.bridge_stop.set()
            self.bridge_stop = None
            self.say("Bridge stopped.")
        self.q.put(("bridge", False))

    def close(self) -> None:
        if self.host is not None and not messagebox.askyesno(
                "Multiworld", "You are hosting: closing stops the server for everyone. Close anyway?", parent=self.root):
            return
        self.stop_bridge()
        if self.wait_stop is not None:
            self.wait_stop.set()
        if self.host is not None:
            self.host.stop()
        with contextlib.suppress(tk.TclError):
            self.root.after_cancel(self._after)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    MultiworldWindow().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
