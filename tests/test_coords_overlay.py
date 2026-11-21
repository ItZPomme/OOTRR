from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ootrr.tools.coords_overlay import last_position, parse_position


class CoordsOverlayTests(unittest.TestCase):
    def test_parses_position_from_emulator_log_line(self):
        self.assertEqual(parse_position("debug OoTRR: position -12.5 0.0 345.6"), (-12.5, 0.0, 345.6))

    def test_ignores_lines_without_position(self):
        self.assertIsNone(parse_position("game started"))

    def test_reads_previous_position_beyond_recent_log_tail(self):
        with TemporaryDirectory() as temp_dir:
            log = Path(temp_dir) / "emulator.log"
            log.write_bytes(b"OoTRR: position -12.5 0.0 345.6\n" + b"unrelated log output\n" * 4000)

            self.assertEqual(last_position(log), (-12.5, 0.0, 345.6))


if __name__ == "__main__":
    unittest.main()
