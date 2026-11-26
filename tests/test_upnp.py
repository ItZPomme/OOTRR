from __future__ import annotations

import struct
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ootrr.upnp import NatPmpGateway, _linux_default_gateways, _local_ipv4, find_gateway


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


@unittest.skipUnless(sys.platform == "linux", "Linux route table")
class NatPmpDiscoveryTest(unittest.TestCase):
    def test_reads_default_gateway_and_interface(self):
        with tempfile.TemporaryDirectory() as temp:
            routes = Path(temp) / "route"
            routes.write_text("Iface Destination Gateway Flags RefCnt Use Metric Mask\n"
                              "enp10s0 00000000 0101A8C0 0003 0 0 100 00000000\n", encoding="ascii")
            with mock.patch("ootrr.upnp._interface_ipv4", return_value="192.168.1.151"):
                self.assertEqual(_linux_default_gateways(routes), [("192.168.1.1", "192.168.1.151")])

    def test_falls_back_to_natpmp_when_ssdp_finds_no_igd(self):
        gateway = NatPmpGateway("192.168.1.1", "192.168.1.151")
        with (mock.patch("ootrr.upnp._search", return_value=[]),
              mock.patch("ootrr.upnp._find_natpmp_gateway", return_value=gateway)):
            self.assertIs(find_gateway(), gateway)


class NatPmpProtocolTest(unittest.TestCase):
    def setUp(self):
        self.gateway = NatPmpGateway("192.168.1.1", "192.168.1.151")
        self.sock = mock.MagicMock()
        self.socket_patch = mock.patch("ootrr.upnp.socket.socket", return_value=self.sock)
        self.socket_patch.start()
        self.addCleanup(self.socket_patch.stop)
        self.sock.__enter__.return_value = self.sock

    def test_public_address_request(self):
        self.sock.recvfrom.return_value = (b"\0\x80\0\0" + b"\0" * 4 + socket.inet_aton("8.8.8.8"), None)
        self.assertEqual(self.gateway.external_ip(), "8.8.8.8")
        self.sock.sendto.assert_called_once_with(b"\0\0", ("192.168.1.1", 5351))

    def test_tcp_mapping_request(self):
        self.sock.recvfrom.return_value = (b"\0\x82\0\0" + b"\0" * 4 + struct.pack("!HHI", 38300, 38300, 21600), None)
        self.gateway.add_mapping(38300, "192.168.1.151", 38300, "OoTRR", lease=21600)
        self.sock.sendto.assert_called_once_with(struct.pack("!BBHHHI", 0, 2, 0, 38300, 38300, 21600),
                                                 ("192.168.1.1", 5351))

    def test_rejects_router_mapping_to_different_external_port(self):
        self.sock.recvfrom.return_value = (b"\0\x82\0\0" + b"\0" * 4 + struct.pack("!HHI", 38300, 40000, 21600), None)
        with self.assertRaisesRegex(OSError, "expected 38300"):
            self.gateway.add_mapping(38300, "192.168.1.151", 38300, "OoTRR", lease=21600)

    def test_zero_lifetime_is_reserved_for_deleting_the_mapping(self):
        with self.assertRaisesRegex(OSError, "lifetime zero deletes"):
            self.gateway.add_mapping(38300, "192.168.1.151", 38300, "OoTRR", lease=0)
        self.sock.sendto.assert_not_called()

    def test_deletes_mapping_with_zero_lifetime(self):
        self.sock.recvfrom.return_value = (b"\0\x82\0\0" + b"\0" * 4 + struct.pack("!HHI", 38300, 38300, 0), None)
        self.gateway.delete_mapping(38300)
        self.sock.sendto.assert_called_once_with(struct.pack("!BBHHHI", 0, 2, 0, 38300, 38300, 0),
                                                 ("192.168.1.1", 5351))


if __name__ == "__main__":
    unittest.main()