from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from ootrr.longshot_control import Longshot


@unittest.skipUnless(sys.platform == "linux", "Linux Unix-domain control socket")
class LongshotSocketTest(unittest.TestCase):
    def test_request_and_response_over_unix_socket(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "control.sock")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(path)
                listener.listen(1)

                def serve():
                    with listener.accept()[0] as connection:
                        with connection.makefile("rwb") as stream:
                            request = json.loads(stream.readline())
                            stream.write(json.dumps({"id": request["id"], "ok": True, "protocol": 1}).encode() + b"\n")
                            stream.flush()

                thread = threading.Thread(target=serve)
                thread.start()
                try:
                    with Longshot(path, timeout=1) as game:
                        self.assertEqual(game.call("status")["protocol"], 1)
                finally:
                    thread.join(timeout=2)
                self.assertFalse(thread.is_alive())