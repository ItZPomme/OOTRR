from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ootrr.tools.mw_app import MultiworldWindow


@unittest.skipUnless(sys.platform == "linux", "Linux Longshot launch")
class MultiworldLinuxLaunchTest(unittest.TestCase):
    def test_install_launches_game_and_bridge_with_same_socket(self):
        window = MultiworldWindow.__new__(MultiworldWindow)
        window.code_var = mock.Mock()
        window.code_var.get.return_value = "ROOM"
        window.player_var = mock.Mock()
        window.player_var.get.return_value = "Player"
        window.longshot = Path("/game")
        window.romfs = Path("/game/romfs")
        window.host_file = None
        window.q = mock.Mock()
        window.say = mock.Mock()
        window.stop_bridge = mock.Mock()
        window._start = lambda task: task()
        window._reach = lambda code: code
        window._hosting = lambda code: False
        code = SimpleNamespace(host="localhost", port=38300)
        data = SimpleNamespace(room_hash="1234")
        control_dir = mock.Mock()
        control_dir.name = "/run/user/1000/ootrr-test"
        with (mock.patch("ootrr.tools.longshot_app.game_running", return_value=False),
              mock.patch("ootrr.tools.mw_app.decode", return_value=code),
              mock.patch("ootrr.tools.mw_app.room_players", return_value=["Player"]),
              mock.patch("ootrr.tools.mw_app.fetch_slot", return_value=data),
              mock.patch("ootrr.tools.mw_app.save_slot", return_value=Path("/tmp/slot.json")),
              mock.patch("ootrr.tools.mw_app.mw.slot_patch", return_value={}),
              mock.patch("ootrr.__main__.build_mod"),
              mock.patch("ootrr.tools.mw_app.longshot_game_binary", return_value=Path("/game/bin/longshot")),
              mock.patch("ootrr.tools.mw_app.tempfile.TemporaryDirectory", return_value=control_dir),
              mock.patch("ootrr.tools.mw_app.sys.frozen", True, create=True),
              mock.patch.dict("os.environ", {"LD_LIBRARY_PATH": "/bundled", "LD_LIBRARY_PATH_ORIG": "/host"}),
              mock.patch("ootrr.tools.mw_app.subprocess.Popen") as popen,
              mock.patch("ootrr.tools.mw_app.threading.Thread") as thread):
            window.install_and_play()

        launch = popen.call_args
        self.assertEqual(launch.args[0], ["/game/bin/longshot"])
        self.assertEqual(launch.kwargs["cwd"], "/game")
        self.assertEqual(launch.kwargs["env"]["HOS_CONTROL"], "/run/user/1000/ootrr-test/control.sock")
        self.assertEqual(launch.kwargs["env"]["HOS_CONTROL_MEM"], "rw")
        self.assertEqual(launch.kwargs["env"]["LD_LIBRARY_PATH"], "/host")
        self.assertEqual(thread.call_args_list[-1].kwargs["kwargs"]["pipe"],
                         launch.kwargs["env"]["HOS_CONTROL"])