"""Multiworld window of the desktop app: host a multiworld (code to share) or join one with a code, then play
(docs/MULTIWORLD.md, "Joining").

    python -m ootrr.tools.mw_app          # alone; the desktop app opens it with its "Multiworld" button

Host: player names (one per line), seed; "Create and host" generates the multiworld with the app's settings for
every player, starts the server in the app (port opened on the router by UPnP when possible) and shows the code.
Join (also the host, for their own game): code -> players -> pick yours -> "Install and play": the player's data
is fetched (never the other worlds), the mod is built and installed into Longshot, Longshot is started with its
control pipe and the bridge runs in the app; the log shows who sent what to whom.
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
from tkinter import messagebox, scrolledtext, ttk

from .. import multiworld as mw
from .. import mw_protocol as P
from .. import settings as settings_mod
from ..mw_code import CodeError, decode
from ..mw_session import Host, SessionError, fetch_slot, room_players, save_slot

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "OoTRR"
MW_DIR = APP_DIR / "multiworld"
PIPE = "ootrr-mw"  # Longshot's HOS_CONTROL value (its control pipe name)


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


class MultiworldWindow:
    def __init__(self, master: tk.Misc | None = None, settings: dict | None = None, longshot: Path | None = None,
                 romfs: Path | None = None) -> None:
        from .longshot_app import find_longshot
        self.root = tk.Toplevel(master) if master is not None else tk.Tk()
        self.root.title("OoTRR · Multiworld")
        self.root.geometry("760x620")
        self.settings = dict(settings or settings_mod.defaults())
        self.longshot = Path(longshot) if longshot else find_longshot()
        self.romfs = Path(romfs) if romfs else (self.longshot / "romfs" if self.longshot else None)
        self.q: queue.Queue = queue.Queue()
        self.host: Host | None = None
        self.host_file: Path | None = None
        self.bridge_stop: threading.Event | None = None
        self.busy = False
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._after = self.root.after(100, self._poll)

    # ---- layout ----
    def _build(self) -> None:
        tabs = ttk.Notebook(self.root)
        tabs.pack(fill="x", padx=10, pady=(10, 4))
        self.tabs = tabs

        host = ttk.Frame(tabs, padding=10)
        tabs.add(host, text="Host")
        ttk.Label(host, text="Players (one name per line, you first)").grid(row=0, column=0, sticky="w")
        self.names = tk.Text(host, width=28, height=6)
        self.names.insert("1.0", "Player 1\nPlayer 2")
        self.names.grid(row=1, column=0, rowspan=4, sticky="nw", pady=(2, 0))
        ttk.Label(host, text="Seed (empty: random)").grid(row=0, column=1, sticky="w", padx=(16, 0))
        self.seed_var = tk.StringVar()
        ttk.Entry(host, textvariable=self.seed_var, width=16).grid(row=1, column=1, sticky="nw", padx=(16, 0))
        ttk.Label(host, text="Port").grid(row=2, column=1, sticky="w", padx=(16, 0))
        self.port_var = tk.StringVar(value=str(P.DEFAULT_PORT))
        ttk.Entry(host, textvariable=self.port_var, width=8).grid(row=3, column=1, sticky="nw", padx=(16, 0))
        ttk.Label(host, text="Address for the code (empty: automatic)").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.address_var = tk.StringVar()
        ttk.Entry(host, textvariable=self.address_var, width=20).grid(row=1, column=2, sticky="nw", padx=(16, 0))
        ttk.Label(host, text="Every player uses the app's settings.", foreground="#666").grid(
            row=2, column=2, sticky="w", padx=(16, 0))
        bar = ttk.Frame(host)
        bar.grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.host_button = ttk.Button(bar, text="Create and host", command=self.create_and_host)
        self.host_button.pack(side="left")
        self.stop_host_button = ttk.Button(bar, text="Stop hosting", command=self.stop_hosting, state="disabled")
        self.stop_host_button.pack(side="left", padx=6)

        join = ttk.Frame(tabs, padding=10)
        tabs.add(join, text="Join / Play")
        ttk.Label(join, text="Room code").grid(row=0, column=0, sticky="w")
        self.code_var = tk.StringVar()
        ttk.Entry(join, textvariable=self.code_var, width=30, font=("Consolas", 12)).grid(row=1, column=0, sticky="w")
        ttk.Button(join, text="Look up", command=self.look_up).grid(row=1, column=1, padx=6, sticky="w")
        ttk.Button(join, text="Copy", command=self.copy_code).grid(row=1, column=2, sticky="w")
        ttk.Label(join, text="You are").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.player_var = tk.StringVar()
        self.player_box = ttk.Combobox(join, textvariable=self.player_var, state="readonly", width=27)
        self.player_box.grid(row=3, column=0, sticky="w")
        bar = ttk.Frame(join)
        bar.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.play_button = ttk.Button(bar, text="Install and play", command=self.install_and_play)
        self.play_button.pack(side="left")
        self.stop_bridge_button = ttk.Button(bar, text="Stop", command=self.stop_bridge, state="disabled")
        self.stop_bridge_button.pack(side="left", padx=6)
        where = f"Longshot: {self.longshot}" if self.longshot else "Longshot not found: install it, or start the app once"
        ttk.Label(join, text=where, foreground="#666").grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(self.root, text="Log").pack(anchor="w", padx=10)
        self.log = scrolledtext.ScrolledText(self.root, height=18, state="disabled", font=("Consolas", 9))
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
            elif kind == "hosted":
                self.code_var.set(value)
                self.player_box.configure(values=self._names())
                if self._names():
                    self.player_var.set(self._names()[0])
                self.stop_host_button.configure(state="normal")
                self.tabs.select(1)
            elif kind == "players":
                self.player_box.configure(values=value)
                if value and self.player_var.get() not in value:
                    self.player_var.set(value[0])
            elif kind == "bridge":
                self.stop_bridge_button.configure(state="normal" if value else "disabled")
            elif kind == "idle":
                self.busy = False
                for b in (self.host_button, self.play_button):
                    b.configure(state="normal")
            elif kind == "error":
                messagebox.showerror("Multiworld", value, parent=self.root)
        self._after = self.root.after(100, self._poll)

    def _names(self) -> list[str]:
        return [n.strip() for n in self.names.get("1.0", "end").splitlines() if n.strip()]

    def _start(self, target) -> None:
        if self.busy:
            return
        self.busy = True
        for b in (self.host_button, self.play_button):
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

    # ---- host ----
    def create_and_host(self) -> None:
        if self.host is not None:
            messagebox.showinfo("Multiworld", "Already hosting: stop it first.", parent=self.root)
            return
        names = self._names()
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Multiworld", "The port must be a number.", parent=self.root)
            return
        seed_text = self.seed_var.get().strip()
        address = self.address_var.get().strip() or None

        def work():
            from .. import __main__ as cli
            players = [mw.Player(n, settings_mod.build(dict(self.settings))) for n in names]
            seed = cli.seed_to_int(seed_text) if seed_text else random.SystemRandom().randrange(1, 10 ** 9)
            self.say(f"Generating the multiworld (seed {seed}, {len(players)} players)...")
            defaults = settings_mod.defaults()
            changed = {k: v for k, v in players[0].settings.items() if defaults.get(k) != v}
            self.say("Settings (the app's, same for every player): "
                     + (", ".join(f"{k}={v}" for k, v in changed.items()) if changed else "all defaults"))
            worlds = mw.build_worlds(players)
            result = mw.generate(players, seed, worlds=worlds)
            data = mw.to_json(result, worlds)
            MW_DIR.mkdir(parents=True, exist_ok=True)
            path = MW_DIR / f"mw_{data['hash']}.json"
            import json
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            path.with_suffix(".txt").write_text(mw.to_text(data), encoding="utf-8")
            self.say(f"Multiworld {data['hash']} written: {path} (spoiler: {path.with_suffix('.txt').name})")
            host = Host(path, port=port, address=address, log=self.say)
            code = host.start()
            self.host, self.host_file = host, path
            for note in host.notes:
                self.say(note)
            self.say(f"Room code: {code}  (share it; the others use Join with it)")
            if host.local_code and host.local_code != code:
                self.say(f"Players on your own network (same box) use this one instead: {host.local_code}")
            self.q.put(("hosted", code))

        self._start(work)

    def stop_hosting(self) -> None:
        if self.host is None:
            return
        if not messagebox.askyesno("Multiworld", "Stop the server? The others will be disconnected (their progress "
                                   "is kept: host again with the same file to resume).", parent=self.root):
            return
        self.host.stop()
        self.say("Server stopped.")
        self.host = None
        self.stop_host_button.configure(state="disabled")

    # ---- join ----
    def _hosting(self, code) -> bool:
        return self.host is not None and self.host_file is not None and code.room_hash in self.host_file.name

    def _reach(self, code):
        """The host reaches their own server on this PC: a router usually refuses a connection from inside to its
        own internet address (seen 2026-11-21, "actively refused")."""
        from ..mw_code import RoomCode
        return RoomCode("127.0.0.1", code.port, code.room_hash) if self._hosting(code) else code

    def copy_code(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.code_var.get().strip())

    def look_up(self) -> None:
        code = self.code_var.get().strip()

        def work():
            names = room_players(self._reach(decode(code)))
            self.say(f"Players of {decode(code).room_hash}: {', '.join(names)}")
            self.q.put(("players", names))

        self._start(work)

    def install_and_play(self) -> None:
        from .longshot_app import game_running
        code_text = self.code_var.get().strip()
        player = self.player_var.get()
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
            slot = names.index(player) + 1
            if self._hosting(code):  # the host plays too: their own file, their own server
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
            subprocess.Popen([str(self.longshot / "longshot.exe")], cwd=str(self.longshot), env=env)
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
