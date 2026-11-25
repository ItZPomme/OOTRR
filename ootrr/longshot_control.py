"""Client of Longshot's control pipe: the way into a running Longshot game from the PC (multiworld bridge, see
docs/MULTIWORLD.md, "Longshot").

Longshot (the PC recompilation) runs no native code of ours and has no `nn::socket`, but it serves a JSON control
API on a named pipe when started with `HOS_CONTROL=<pipe name>` (environment or `longshot_env.txt` in its folder),
this Windows user only. Guest memory commands need `HOS_CONTROL_MEM=ro` (reads) or `rw` (writes too).
Verified with Longshot v3.0.0-rc.6 (2026-11-17), strings of `bin/longshot.exe` and live calls:

- One JSON object per line, `{"id": n, "cmd": ...}`; answer `{"id": n, "ok": true|false, "frame": ..., ...}`
  (`error` / `message` when not ok). Requests are served on a game frame (a read times out while the game boots).
- Commands: status, press, stick, sequence, release, saves, teleport, shot, wait, option_get, option_set,
  subscribe, unsubscribe, quit, relaunch, mem_read, mem_read_many, mem_write, symbols.
- `mem_read {addr, size}` -> `{"data": hex}`. Guest addresses: rtld at 0x80000000, **main at 0x80020000**; its code
  is the build E0F3CCFA of `output/native/main.bin` byte for byte, so the native module's offsets apply.
- `subscribe {events: ["oot", ...], every: frames, flags: [up to 64 GameData names], changes: true}` -> one line
  `{"event": "oot", "sub": id, "game": {map, pos, age, life, max_life, rupees, event, loading, flags: {name: value},
  changed: {"0x<hash>": value}}}` every `every` frames in play (none on the title screen). `changed` lists the
  GameData values (Bool, Int, Enum, UInt) changed since the last line, by hash (`gamedata.flag_hash`).

GameData Int lookup (decompiled `GetInt`, main 0x163d20; reads checked against the event values): manager =
`**(main + 0x4c7e180)`; open-addressing table of `{u32 hash, u32 index}` at `*(manager + 0xe0)`, size
`*(u32*)(manager + 0xec)`, start at `hash % size`, step +1 with wrap, an empty slot (hash 0) ends; entry =
`*(manager + 0xd8) + index * 0x28`, current value at entry + 0x1c (signed). The game's own writes go through a
queue (`manager + 0xf8`, count `+0x100 & 0xfffff`, 12-byte {value, hash, kind}) that `GetInt` reads first. Bools:
`GetBool` (0x3744460) table at +0x20 (size +0x2c), 0x18-byte entries at +0x18, value byte +0x16; queue of `SetBool`
(0x682b00) at +0x38 (capacity +0x30, count +0x40), 8-byte {u8 value, u32 hash at +4}. Enums: `SetEnum` (0x3e0980,
decompiled) table at +0x260 (size +0x26c), queue at +0x278 (capacity +0x270, count +0x280), 8-byte {u32 value, u32
hash}; a value is the `flag_hash` of its raw name. Enum writes: **not tried in game yet**.

Writes (`set_int`, `set_bool`) are appended to these queues and read back until applied (an append can be lost:
see `_queue`); they are saved (seen in game 2026-11-17: a Hookshot given this way fires and is still there after
save + reload). Writing the entry directly, even with its +0x0c "written" flag, shows in game but is **not saved**.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

from .formats.gamedata import flag_hash

MAIN = 0x80020000
GAMEDATA_MANAGER_PTR = 0x4c7e180  # ingame.hpp kGameDataManagerPtr
INT_TABLE, INT_TABLE_SIZE, INT_ENTRIES, INT_ENTRY_SIZE, INT_VALUE = 0xe0, 0xec, 0xd8, 0x28, 0x1c
# GetBool (main 0x3744460, non-array Bools): same kind of table at +0x20 (size +0x2c), 0x18-byte entries, value byte
BOOL_TABLE, BOOL_TABLE_SIZE, BOOL_ENTRIES, BOOL_ENTRY_SIZE, BOOL_VALUE = 0x20, 0x2c, 0x18, 0x18, 0x16
# write queues, applied by the game each frame (low 20 bits of the count word = pending entries):
# Int {s32 value, u32 hash, u32 kind: 0 set, 1 add} (GetInt reads it first), Bool {u8 value, 3 pad, u32 hash}
INT_QUEUE, INT_QUEUE_CAP, INT_QUEUE_COUNT = 0xf8, 0xf0, 0x100
BOOL_QUEUE, BOOL_QUEUE_CAP, BOOL_QUEUE_COUNT = 0x38, 0x30, 0x40


ENUM_TABLE, ENUM_TABLE_SIZE = 0x260, 0x26c
ENUM_QUEUE, ENUM_QUEUE_CAP, ENUM_QUEUE_COUNT = 0x278, 0x270, 0x280


class ControlError(OSError):
    pass


class Longshot:
    def __init__(self, pipe: str = "1", timeout: float = 10.0) -> None:
        path = pipe if pipe.startswith("\\\\") else rf"\\.\pipe\{pipe}"
        deadline = time.time() + timeout
        while True:
            try:
                self._pipe = open(path, "r+b", buffering=0)
                break
            except OSError as exc:  # between two client instances the pipe is briefly missing
                if time.time() > deadline:
                    raise ControlError(f"no Longshot control pipe at {path} (HOS_CONTROL not set?)") from exc
                time.sleep(0.2)
        self._id = 0
        self._events: list[dict[str, Any]] = []

    def close(self) -> None:
        self._pipe.close()

    def __enter__(self) -> "Longshot":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _line(self) -> dict[str, Any]:
        buf = bytearray()
        while not buf.endswith(b"\n"):
            chunk = self._pipe.read(1)
            if not chunk:
                raise ControlError("Longshot closed the pipe")
            buf += chunk
        return json.loads(buf)

    def call(self, cmd: str, **args: Any) -> dict[str, Any]:
        self._id += 1
        self._pipe.write((json.dumps({"id": self._id, "cmd": cmd, **args}) + "\n").encode("utf-8"))
        while True:
            msg = self._line()
            if "event" in msg:
                self._events.append(msg)  # an event of a subscription, read while waiting for our answer
            elif msg.get("id") == self._id:
                if not msg.get("ok"):
                    raise ControlError(f"{cmd}: {msg.get('error')}: {msg.get('message')}")
                return msg

    def events(self) -> Iterator[dict[str, Any]]:
        """Events of the subscriptions, as they come (blocks)."""
        while True:
            while self._events:
                yield self._events.pop(0)
            msg = self._line()
            if "event" in msg:
                yield msg

    # ---- guest memory (HOS_CONTROL_MEM) ----
    def read(self, addr: int, size: int) -> bytes:
        return bytes.fromhex(self.call("mem_read", addr=addr, size=size)["data"])

    def u32(self, addr: int) -> int:
        return int.from_bytes(self.read(addr, 4), "little")

    def u64(self, addr: int) -> int:
        return int.from_bytes(self.read(addr, 8), "little")

    def gamedata_manager(self) -> int:
        return self.u64(self.u64(MAIN + GAMEDATA_MANAGER_PTR))

    def int_address(self, name_or_hash: str | int, manager: int | None = None) -> int | None:
        """Guest address of a (non-array) GameData Int's current value, None if there is no such Int."""
        h = flag_hash(name_or_hash) if isinstance(name_or_hash, str) else name_or_hash
        mgr = manager or self.gamedata_manager()
        index = self._lookup(h, mgr, INT_TABLE, INT_TABLE_SIZE)
        return None if index is None else self.u64(mgr + INT_ENTRIES) + index * INT_ENTRY_SIZE + INT_VALUE

    def _lookup(self, h: int, mgr: int, table_off: int, size_off: int) -> int | None:
        """Index of hash `h` in one of the manager's open-addressing tables ({u32 hash, u32 index} slots)."""
        table, size = self.u64(mgr + table_off), self.u32(mgr + size_off)
        if not table or not size:
            return None
        i = start = h % size
        while True:
            slot = self.read(table + i * 8, 8)
            found = int.from_bytes(slot[:4], "little")
            if found == h:
                return int.from_bytes(slot[4:], "little")
            if found == 0:
                return None
            i = i + 1 if i + 1 < size else 0
            if i == start:
                return None

    def bool_address(self, name_or_hash: str | int, manager: int | None = None) -> int | None:
        """Guest address of a (non-array) GameData Bool (one byte), None if there is no such Bool."""
        h = flag_hash(name_or_hash) if isinstance(name_or_hash, str) else name_or_hash
        mgr = manager or self.gamedata_manager()
        index = self._lookup(h, mgr, BOOL_TABLE, BOOL_TABLE_SIZE)
        return None if index is None else self.u64(mgr + BOOL_ENTRIES) + index * BOOL_ENTRY_SIZE + BOOL_VALUE

    def get_int(self, name_or_hash: str | int) -> int | None:
        addr = self.int_address(name_or_hash)
        return None if addr is None else int.from_bytes(self.read(addr, 4), "little", signed=True)

    def get_bool(self, name_or_hash: str | int) -> bool | None:
        addr = self.bool_address(name_or_hash)
        return None if addr is None else bool(self.read(addr, 1)[0])

    # ---- writes (HOS_CONTROL_MEM=rw) ----
    def write(self, addr: int, data: bytes) -> None:
        self.call("mem_write", addr=addr, hex=data.hex())

    def _queue(self, buf_off: int, cap_off: int, count_off: int, entry: bytes) -> None:
        """Appends a write to one of the game's GameData write queues, as the game's setters do (count + 1 and
        sequence number + 1, bits 20-27 of the count word); the game applies it within a frame or two, as if it
        had written the value itself.

        Seen in Longshot (2026-11-17): only queued writes are saved, and only they reach the objects behind some
        values (rupees, pouch): writing the value's entry directly (even with its +0x0c "written" flag) is shown
        for a while but lost after save + reload, and the entry may then keep a value the game no longer uses.
        So a write cannot be checked by reading the entry back; what is checked is that it is in the queue.

        The game queues its own writes every frame, so the append must not straddle a frame: requests sent
        together (pipelined) are served within one frame (seen: six reads, one frame number), sequential ones
        one frame each. One batch: read the count word, write the entry at slot n, write the count's two low
        bytes (n + 1; the upper bits are a sequence and a phase the game changes every frame), read both back.
        n comes from the previous frame: if the count changed in between, the batch is reported as wrong."""
        mgr = self.gamedata_manager()
        buf, cap = self.u64(mgr + buf_off), self.u32(mgr + cap_off)
        problems = []
        for _ in range(self.QUEUE_TRIES):
            # the count must be the same on two consecutive frames: a queue being emptied or filled is skipped
            # (seen in play, 2026-11-20: count 2 on one frame, 0 on the next; writing 3 then made the game
            # apply stale entries again: one received item given four times)
            n = self.u32(mgr + count_off) & 0xfffff
            if self.u32(mgr + count_off) & 0xfffff != n:
                problems.append("count moving")
                continue
            if not buf or n + 1 >= min(cap, 0x10000):
                raise ControlError("GameData write queue unavailable or full")
            slot = buf + n * len(entry)
            replies = self.batch([
                ("mem_read", {"addr": mgr + count_off, "size": 4}),
                ("mem_write", {"addr": slot, "hex": entry.hex()}),
                ("mem_write", {"addr": mgr + count_off, "hex": (n + 1).to_bytes(2, "little").hex()}),
                ("mem_read", {"addr": slot, "size": len(entry)}),
                ("mem_read", {"addr": mgr + count_off, "size": 4}),
            ])
            frames = {r.get("frame") for r in replies}
            before = int.from_bytes(bytes.fromhex(replies[0]["data"]), "little") & 0xfffff
            after = int.from_bytes(bytes.fromhex(replies[4]["data"]), "little") & 0xfffff
            if len(frames) == 1 and before == n and after == n + 1 and bytes.fromhex(replies[3]["data"]) == entry:
                return
            problems.append(f"count {n} -> {before} before, {after} after")
            time.sleep(0.05)
        raise ControlError(f"GameData queue append failed: {'; '.join(problems)}")

    QUEUE_TRIES = 6

    def batch(self, requests: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Sends the requests together (served within one game frame) and returns their answers in order."""
        ids = []
        lines = []
        for cmd, args in requests:
            self._id += 1
            ids.append(self._id)
            lines.append(json.dumps({"id": self._id, "cmd": cmd, **args}))
        self._pipe.write(("\n".join(lines) + "\n").encode("utf-8"))
        answers: dict[int, dict[str, Any]] = {}
        while len(answers) < len(ids):
            msg = self._line()
            if "event" in msg:
                self._events.append(msg)
            elif msg.get("id") in ids:
                answers[msg["id"]] = msg
        for i, (cmd, _) in zip(ids, requests):
            if not answers[i].get("ok"):
                raise ControlError(f"{cmd}: {answers[i].get('error')}: {answers[i].get('message')}")
        return [answers[i] for i in ids]

    def set_int(self, name_or_hash: str | int, value: int, add: bool = False) -> None:
        """Queued Int write of an absolute value (`add`: the entry's value + `value`, read once)."""
        h = flag_hash(name_or_hash) if isinstance(name_or_hash, str) else name_or_hash
        if add:
            value += self.get_int(h) or 0
        entry = value.to_bytes(4, "little", signed=True) + h.to_bytes(4, "little") + (0).to_bytes(4, "little")
        self._queue(INT_QUEUE, INT_QUEUE_CAP, INT_QUEUE_COUNT, entry)

    def set_bool(self, name_or_hash: str | int, value: bool) -> None:
        """Queued Bool write, like the game's SetBool (main 0x682b00)."""
        h = flag_hash(name_or_hash) if isinstance(name_or_hash, str) else name_or_hash
        self._queue(BOOL_QUEUE, BOOL_QUEUE_CAP, BOOL_QUEUE_COUNT, bytes([1 if value else 0, 0, 0, 0]) + h.to_bytes(4, "little"))

    def set_enum(self, name_or_hash: str | int, value: str) -> None:
        """Queued Enum write, like the game's SetEnum (main 0x3e0980); `value` = raw name of the value."""
        h = flag_hash(name_or_hash) if isinstance(name_or_hash, str) else name_or_hash
        if self._lookup(h, self.gamedata_manager(), ENUM_TABLE, ENUM_TABLE_SIZE) is None:
            raise ControlError(f"no GameData Enum {name_or_hash}")
        self._queue(ENUM_QUEUE, ENUM_QUEUE_CAP, ENUM_QUEUE_COUNT,
                    flag_hash(value).to_bytes(4, "little") + h.to_bytes(4, "little"))


def main(argv: list[str] | None = None) -> int:
    """python -m ootrr.longshot_control [--pipe 1] [NAME ...]: status, then the named GameData Ints."""
    import argparse
    ap = argparse.ArgumentParser(prog="python -m ootrr.longshot_control")
    ap.add_argument("--pipe", default="1")
    ap.add_argument("names", nargs="*")
    args = ap.parse_args(argv)
    with Longshot(args.pipe) as ls:
        st = ls.call("status")
        print(f"Longshot {st.get('version')}: {st.get('state')}, map {st.get('map')}, frame {st.get('frame')}")
        for name in args.names:
            print(f"  {name} = {ls.get_int(name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
