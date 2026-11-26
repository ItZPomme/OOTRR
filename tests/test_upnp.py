from __future__ import annotations

import socket
import sys
import unittest
from unittest import mock

from ootrr.upnp import _local_ipv4


@unittest.skipUnless(sys.platform == "linux", "Linux interface enumeration")
class LocalIPv4Test(unittest.TestCase):
    def test_reads_interface_address_when_hostname_has_no_lan_address(self):
        response = b"\0" * 20 + socket.inet_aton("192.168.1.151") + b"\0" * 232
        with (mock.patch("socket.if_nameindex", return_value=[(2, "enp10s0")]),
              mock.patch("socket.getaddrinfo", return_value=[]),
              mock.patch("fcntl.ioctl", return_value=response),
              mock.patch("socket.socket") as socket_factory):
            socket_factory.return_value.__enter__.return_value.fileno.return_value = 7
            self.assertEqual(_local_ipv4(), ["192.168.1.151"])


if __name__ == "__main__":
    unittest.main()