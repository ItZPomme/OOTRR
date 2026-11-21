"""Show Link's live world position in a click-through overlay above Fritchii.

The active mod must include the native module built with ``menutest --live-coords``.
Run this tool after starting Fritchii:

    python -m ootrr.tools.coords_overlay
"""

from __future__ import annotations

import argparse
import ctypes
import os
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from .coords import LINE, default_log

OVERLAY_WIDTH = 360
OVERLAY_HEIGHT = 68
COLOR_KEY = "#010203"
POLL_MS = 100
WINDOW_POLL_MS = 500
WINDOW_OFFSET = 20
PROCESS_ACCESS = 0x1000
PROCESS_NAME = "fritchii"
STYLE_INDEX = -20
EXT_TRANSPARENT = 0x00000020
EXT_TOOLWINDOW = 0x00000080
EXT_LAYERED = 0x00080000
EXT_NOACTIVATE = 0x08000000
LWA_COLORKEY = 0x00000001
COLOR_KEYREF = 0x00030201  # Windows COLORREF stores #010203 as 0x00030201.


def parse_position(line: str) -> tuple[float, float, float] | None:
    match = LINE.search(line)
    if not match:
        return None
    return tuple(float(value) for value in match.groups())


def last_position(path: Path) -> tuple[float, float, float] | None:
    with path.open("rb") as stream:
        end = stream.seek(0, os.SEEK_END)
        pending = b""
        while end:
            start = max(0, end - 65536)
            stream.seek(start)
            block = stream.read(end - start) + pending
            lines = block.splitlines()
            if start:
                pending = lines[0] if lines else block
                lines = lines[1:]
            else:
                pending = b""
            for line in reversed(lines):
                position = parse_position(line.decode("utf-8", errors="replace"))
                if position is not None:
                    return position
            end = start
    return None


class Win32:
    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure()

    def _configure(self) -> None:
        self.user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
                                           wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.IsIconic.argtypes = [wintypes.HWND]
        self.user32.IsIconic.restype = wintypes.BOOL
        self.user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.GetClientRect.restype = wintypes.BOOL
        self.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.user32.ClientToScreen.restype = wintypes.BOOL
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.user32.SetLayeredWindowAttributes.argtypes = [
            wintypes.HWND, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD
        ]
        self.user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

        get_long = getattr(self.user32, "GetWindowLongPtrW", self.user32.GetWindowLongW)
        set_long = getattr(self.user32, "SetWindowLongPtrW", self.user32.SetWindowLongW)
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        get_long.restype = ctypes.c_ssize_t
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_long.restype = ctypes.c_ssize_t
        self.get_window_long = get_long
        self.set_window_long = set_long

    def process_path(self, hwnd: int) -> str:
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = self.kernel32.OpenProcess(PROCESS_ACCESS, False, pid.value)
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(1024)
            length = wintypes.DWORD(len(buffer))
            if self.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                return buffer.value
            return ""
        finally:
            self.kernel32.CloseHandle(handle)

    def window_title(self, hwnd: int) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def emulator_rect(self, title_filter: str | None) -> tuple[int, int, int, int] | None:
        matches: list[tuple[int, tuple[int, int, int, int]]] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def visit(hwnd: int, _: int) -> bool:
            if not self.user32.IsWindowVisible(hwnd) or self.user32.IsIconic(hwnd):
                return True
            if self.user32.GetWindow(hwnd, 4):  # GW_OWNER
                return True
            title = self.window_title(hwnd)
            if title_filter:
                if title_filter.casefold() not in title.casefold():
                    return True
            else:
                process = Path(self.process_path(hwnd)).stem.casefold()
                if PROCESS_NAME not in process and "eden" not in process and PROCESS_NAME not in title.casefold():
                    return True
            rect = wintypes.RECT()
            origin = wintypes.POINT(0, 0)
            if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
                return True
            if not self.user32.ClientToScreen(hwnd, ctypes.byref(origin)):
                return True
            width, height = rect.right - rect.left, rect.bottom - rect.top
            if width > 0 and height > 0:
                matches.append((width * height, (origin.x, origin.y, width, height)))
            return True

        if not self.user32.EnumWindows(callback_type(visit), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return max(matches, default=(0, None), key=lambda entry: entry[0])[1]

    def make_click_through(self, hwnd: int) -> None:
        style = self.get_window_long(hwnd, STYLE_INDEX)
        flags = EXT_LAYERED | EXT_TRANSPARENT | EXT_TOOLWINDOW | EXT_NOACTIVATE
        ctypes.set_last_error(0)
        if self.set_window_long(hwnd, STYLE_INDEX, style | flags) == 0:
            error = ctypes.get_last_error()
            if error:
                raise ctypes.WinError(error)
        if not self.user32.SetLayeredWindowAttributes(hwnd, COLOR_KEYREF, 255, LWA_COLORKEY):
            raise ctypes.WinError(ctypes.get_last_error())

class PositionOverlay:
    def __init__(self, path: Path, title_filter: str | None, x_offset: int, y_offset: int) -> None:
        self.path = path
        self.title_filter = title_filter
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.api = Win32()
        self.root = tk.Tk()
        self.root.title("OoTRR Link Coordinates")
        self.root.overrideredirect(True)
        self.root.configure(bg=COLOR_KEY)
        try:
            self.root.wm_attributes("-transparentcolor", COLOR_KEY)
        except tk.TclError as exc:
            self.root.destroy()
            raise RuntimeError("This Tk installation does not support a transparent overlay.") from exc
        self.root.attributes("-topmost", True)
        self.canvas = tk.Canvas(
            self.root, width=OVERLAY_WIDTH, height=OVERLAY_HEIGHT, bg=COLOR_KEY, highlightthickness=0, bd=0
        )
        self.canvas.pack()
        self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+20+20")
        self.root.update_idletasks()
        self.hwnd = int(self.root.wm_frame(), 0)
        self.api.make_click_through(self.hwnd)
        self.file = path.open("rb")
        self.file.seek(0, os.SEEK_END)
        self.file_identity = self._file_identity(os.fstat(self.file.fileno()))
        self.position = last_position(path)
        self.window_rect: tuple[int, int, int, int] | None = None
        self.attached = False
        self.window_poll = 0
        self.draw()
        self.root.after(POLL_MS, self.update)

    @staticmethod
    def _file_identity(stat: os.stat_result) -> tuple[int, int]:
        return stat.st_dev, stat.st_ino

    def draw_text(self, text: str, x: int, y: int, size: int, color: str, bold: bool = False) -> None:
        font = ("Consolas", size, "bold" if bold else "normal")
        self.canvas.create_text(x + 1, y + 1, text=text, anchor="nw", font=font, fill="#17202b")
        self.canvas.create_text(x, y, text=text, anchor="nw", font=font, fill=color)

    def draw(self) -> None:
        self.canvas.delete("all")
        self.draw_text("LINK POSITION  (world X / Y / Z)", 8, 6, 11, "#8de1ff", True)
        if not self.attached:
            self.draw_text("Waiting for Fritchii window...", 8, 31, 14, "#ffffff")
        elif self.position is None:
            self.draw_text("Waiting for live position...", 8, 31, 14, "#ffffff")
        else:
            x, y, z = self.position
            self.draw_text(f"X {x:9.1f}   Y {y:9.1f}   Z {z:9.1f}", 8, 31, 14, "#ffffff")
        self.root.update_idletasks()

    def poll_log(self) -> None:
        path_stat = self.path.stat()
        if (
            self._file_identity(path_stat) != self.file_identity
            or path_stat.st_size < self.file.tell()
        ):
            self.file.close()
            self.file = self.path.open("rb")
            self.file_identity = self._file_identity(os.fstat(self.file.fileno()))
            self.position = last_position(self.path)
            self.file.seek(0, os.SEEK_END)
            self.draw()
            return
        while True:
            line = self.file.readline()
            if not line:
                break
            position = parse_position(line.decode("utf-8", errors="replace"))
            if position is not None:
                self.position = position
                self.draw()

    def update(self) -> None:
        self.poll_log()
        self.window_poll += POLL_MS
        if self.window_poll >= WINDOW_POLL_MS:
            self.window_poll = 0
            self.window_rect = self.api.emulator_rect(self.title_filter)
            if self.window_rect is None:
                self.attached = False
                self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+20+20")
            else:
                left, top, width, height = self.window_rect
                x = left + min(self.x_offset, max(0, width - OVERLAY_WIDTH))
                y = top + min(self.y_offset, max(0, height - OVERLAY_HEIGHT))
                self.attached = True
                self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+{x}+{y}")
            self.draw()
        self.root.after(POLL_MS, self.update)

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.file.close()
            self.root.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, help="Fritchii log path (defaults to the latest detected emulator log)")
    parser.add_argument("--window-title", help="attach to a visible window whose title contains this text")
    parser.add_argument("--x", type=int, default=WINDOW_OFFSET, help="overlay offset from the game client left (default 20)")
    parser.add_argument("--y", type=int, default=WINDOW_OFFSET, help="overlay offset from the game client top (default 20)")
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("the desktop overlay currently requires Windows")
    path = args.log or default_log()
    if path is None or not path.is_file():
        parser.error("emulator log not found; start Fritchii or pass --log")
    try:
        print(f"Reading emulator log: {path}")
        PositionOverlay(path, args.window_title, args.x, args.y).run()
    except (OSError, RuntimeError, tk.TclError) as exc:
        parser.exit(1, f"coords_overlay: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
