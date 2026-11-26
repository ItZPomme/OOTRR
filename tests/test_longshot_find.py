"""Desktop app: finding the Longshot version folder (tools.longshot_app.find_longshot / saved_longshot)."""

from __future__ import annotations

import tempfile
import os
import sys
import unittest
from pathlib import Path

from ootrr.tools.longshot_support import _version_key, find_longshot, game_running, longshot_game_binary, saved_longshot


def _install(base: Path, *parts: str) -> Path:
    folder = base.joinpath(*parts)
    folder.mkdir(parents=True)
    executable = folder / ("longshot.exe" if os.name == "nt" else "longshot")
    executable.write_bytes(b"")
    if os.name != "nt":
        executable.chmod(0o755)
    return folder


class FindLongshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "Longshot"

    def tearDown(self):
        self.tmp.cleanup()

    @unittest.skipUnless(sys.platform == "linux", "Linux game executable layout")
    def test_game_executable_is_not_the_launcher(self):
        folder = _install(self.base, "stable", "v3.2.0")
        self.assertIsNone(longshot_game_binary(folder))
        game = folder / "bin" / "longshot"
        game.parent.mkdir()
        game.write_bytes(b"")
        game.chmod(0o755)
        self.assertEqual(longshot_game_binary(folder), game)

    def test_versions_compare_as_numbers(self):
        names = ["v3.0.0-rc.4", "v3.0.0", "v3.0.0-rc.10", "v2.10.0", "v2.9.1"]
        self.assertEqual(sorted(names, key=_version_key), ["v2.9.1", "v2.10.0", "v3.0.0-rc.4", "v3.0.0-rc.10", "v3.0.0"])

    def test_channels(self):
        _install(self.base, "rc", "v3.0.0-rc.7")
        self.assertEqual(find_longshot((self.base,)).name, "v3.0.0-rc.7")
        stable = _install(self.base, "stable", "v3.0.0")
        _install(self.base, "stable", "v2.9.0")
        self.assertEqual(find_longshot((self.base,)), stable)  # stable first, the newest one

    def test_old_layout_and_unknown_channel(self):
        old = _install(self.base, "v3.0.0-rc.4")
        self.assertEqual(find_longshot((self.base,)), old)
        old.joinpath("longshot.exe" if os.name == "nt" else "longshot").unlink()
        beta = _install(self.base, "beta", "v3.1.0")
        self.assertEqual(find_longshot((self.base,)), beta)
        self.assertIsNone(find_longshot((Path(self.tmp.name) / "nothing",)))

    def test_platform_executable_name_is_supported(self):
        folder = self.base / "stable" / "v3.0.0"
        folder.mkdir(parents=True)
        executable = folder / ("longshot.exe" if os.name == "nt" else "longshot")
        executable.write_bytes(b"")
        if os.name != "nt":
            executable.chmod(0o755)
        self.assertEqual(find_longshot((self.base,)), folder)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux /proc process detection")
    def test_detects_running_longshot_process(self):
        proc_root = Path(self.tmp.name) / "proc"
        process = proc_root / "1234"
        process.mkdir(parents=True)
        (process / "comm").write_text("longshot\n", encoding="utf-8")
        self.assertTrue(game_running(proc_root=proc_root))
        (process / "comm").write_text("OoTRR-App\n", encoding="utf-8")
        self.assertFalse(game_running(proc_root=proc_root))

    def test_saved_path_deleted_by_the_launcher(self):
        kept = _install(self.base, "rc", "v3.0.0-rc.7")
        self.assertEqual(saved_longshot(str(kept)), kept)
        gone = self.base / "v3.0.0-rc.3"
        found = saved_longshot(str(gone))
        self.assertTrue(found is None or (found / ("longshot.exe" if os.name == "nt" else "longshot")).is_file())


if __name__ == "__main__":
    unittest.main()
