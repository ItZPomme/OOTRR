"""UPnP IGD and Linux NAT-PMP port mapping, standard library only: lets a multiworld host be reached from the
internet without opening the port by hand (docs/MULTIWORLD.md, "Joining").

    gw = find_gateway()                       # SSDP discovery on the local network, None if no UPnP router
    gw.external_ip()                          # the address the others connect to
    gw.add_mapping(38300, gw.local_ip, 38300, "OoTRR multiworld", lease=0)
    gw.delete_mapping(38300)

Only the router answering on the local network is contacted. Many routers allow UPnP by default; some have it off,
some (4G, carrier-grade NAT) get a private "external" address: `is_public` tells it, and the host then needs another
way (port opened by hand on the real router, or a VPN such as Tailscale / ZeroTier).
"""

from __future__ import annotations

import ipaddress
import re
import select
import socket
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

SSDP = ("239.255.255.250", 1900)
SEARCH_TARGETS = ("urn:schemas-upnp-org:device:InternetGatewayDevice:1",
                  "urn:schemas-upnp-org:service:WANIPConnection:1", "urn:schemas-upnp-org:service:WANIPConnection:2",
                  "urn:schemas-upnp-org:service:WANPPPConnection:1")
SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:2", "urn:schemas-upnp-org:service:WANIPConnection:1",
            "urn:schemas-upnp-org:service:WANPPPConnection:1")
CRLF = "\r\n"


class UpnpError(OSError):
    pass


def is_public(address: str) -> bool:
    try:
        return ipaddress.IPv4Address(address).is_global
    except ipaddress.AddressValueError:
        return False


def local_ip_towards(host: str) -> str:
    """This PC's address on the network that leads to `host` (no packet is sent: UDP connect only picks a route)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, 1900))
        return s.getsockname()[0]


@dataclass
class Gateway:
    control_url: str
    service: str
    local_ip: str

    def _soap(self, action: str, args: dict[str, object], timeout: float = 5.0) -> dict[str, str]:
        body = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
        envelope = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
                    f'<u:{action} xmlns:u="{self.service}">{body}</u:{action}></s:Body></s:Envelope>')
        req = urllib.request.Request(self.control_url, data=envelope.encode("utf-8"), method="POST", headers={
            "Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{self.service}#{action}"'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                xml = resp.read()
        except urllib.error.HTTPError as exc:  # UPnP errors come as HTTP 500 with a fault body
            detail = exc.read().decode("utf-8", "replace")
            code = re.search(r"<errorCode>(\d+)</errorCode>", detail)
            desc = re.search(r"<errorDescription>([^<]*)</errorDescription>", detail)
            raise UpnpError(f"{action}: router refused ({code.group(1) if code else exc.code} "
                            f"{desc.group(1) if desc else ''})".strip()) from None
        except OSError as exc:
            raise UpnpError(f"{action}: {exc}") from None
        out = {}
        for el in ET.fromstring(xml).iter():
            tag = el.tag.rsplit("}", 1)[-1]
            if el.text is not None and not list(el):
                out[tag] = el.text.strip()
        return out

    def external_ip(self) -> str:
        return self._soap("GetExternalIPAddress", {}).get("NewExternalIPAddress", "")

    def add_mapping(self, external_port: int, internal_ip: str, internal_port: int, description: str,
                    lease: int = 0) -> None:
        self._soap("AddPortMapping", {
            "NewRemoteHost": "", "NewExternalPort": external_port, "NewProtocol": "TCP",
            "NewInternalPort": internal_port, "NewInternalClient": internal_ip, "NewEnabled": 1,
            "NewPortMappingDescription": description, "NewLeaseDuration": lease})

    def delete_mapping(self, external_port: int) -> None:
        self._soap("DeletePortMapping", {"NewRemoteHost": "", "NewExternalPort": external_port, "NewProtocol": "TCP"})


@dataclass
class NatPmpGateway:
    gateway_ip: str
    local_ip: str
    timeout: float = 1.0
    protocol: str = "NAT-PMP"

    def _exchange(self, request: bytes, opcode: int) -> bytes:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(self.timeout)
                sock.bind((self.local_ip, 0))
                sock.sendto(request, (self.gateway_ip, 5351))
                response, _ = sock.recvfrom(32)
        except OSError as exc:
            raise UpnpError(f"NAT-PMP: {exc}") from None
        if len(response) < 4:
            raise UpnpError("NAT-PMP: short response")
        version, response_opcode, result = struct.unpack("!BBH", response[:4])
        if version != 0 or response_opcode != opcode + 128:
            raise UpnpError("NAT-PMP: invalid response")
        if result:
            reasons = {1: "unsupported version", 2: "not authorized", 3: "network failure",
                       4: "out of resources", 5: "unsupported opcode"}
            raise UpnpError(f"NAT-PMP: router refused the request ({reasons.get(result, f'error {result}')})")
        return response

    def external_ip(self) -> str:
        response = self._exchange(b"\x00\x00", 0)
        if len(response) < 12:
            raise UpnpError("NAT-PMP: short external-address response")
        return socket.inet_ntoa(response[8:12])

    def add_mapping(self, external_port: int, internal_ip: str, internal_port: int, description: str,
                    lease: int = 0) -> None:
        if lease <= 0:
            raise UpnpError("NAT-PMP requires a nonzero mapping lifetime; lifetime zero deletes the mapping")
        self._set_mapping(external_port, internal_port, lease)

    def _set_mapping(self, external_port: int, internal_port: int, lease: int) -> None:
        request = struct.pack("!BBHHHI", 0, 2, 0, internal_port, external_port, lease)
        response = self._exchange(request, 2)
        if len(response) < 16:
            raise UpnpError("NAT-PMP: short port-mapping response")
        mapped_port = struct.unpack("!H", response[10:12])[0]
        if mapped_port != external_port:
            raise UpnpError(f"NAT-PMP: router mapped external port {mapped_port}, expected {external_port}")

    def delete_mapping(self, external_port: int) -> None:
        self._set_mapping(external_port, external_port, 0)


def _interface_ipv4(name: str) -> str:
    import fcntl

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        request = struct.pack("256s", name.encode()[:15])
        response = fcntl.ioctl(sock.fileno(), 0x8915, request)  # SIOCGIFADDR
    return socket.inet_ntoa(response[20:24])


def _linux_default_gateways(route_file=None) -> list[tuple[str, str]]:
    """Default router IPv4 and local interface address pairs from the Linux route table."""
    if route_file is None:
        from pathlib import Path
        route_file = Path("/proc/net/route")
    try:
        lines = route_file.read_text(encoding="ascii").splitlines()[1:]
    except OSError:
        return []
    gateways = []
    for line in lines:
        fields = line.split()
        if len(fields) < 4 or fields[1] != "00000000":
            continue
        try:
            flags = int(fields[3], 16)
            if flags & 0x3 != 0x3:
                continue
            router = socket.inet_ntoa(struct.pack("<I", int(fields[2], 16)))
            local = _interface_ipv4(fields[0])
        except (OSError, ValueError):
            continue
        if not router.startswith("127.") and not local.startswith("127."):
            gateways.append((router, local))
    return gateways


def _find_natpmp_gateway(timeout: float = 1.0) -> NatPmpGateway | None:
    if sys.platform != "linux":
        return None
    for router, local in _linux_default_gateways():
        gateway = NatPmpGateway(router, local, timeout)
        try:
            gateway.external_ip()
        except UpnpError:
            continue
        return gateway
    return None


def _local_ipv4() -> list[str]:
    if sys.platform == "linux":
        addrs = set()
        for _, name in socket.if_nameindex():
            try:
                addrs.add(_interface_ipv4(name))
            except OSError:
                continue
        usable = sorted(a for a in addrs if not a.startswith("127."))
        if usable:
            return usable
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        addrs = set()
    return sorted(a for a in addrs if not a.startswith("127.")) or [""]


def _search(timeout: float) -> list[str]:
    """LOCATION URLs of the UPnP devices answering an SSDP search, sent on every local IPv4 interface (on Windows
    the default one may be a virtual adapter: WSL, Hyper-V, VPN)."""
    found: list[str] = []
    socks = []
    for addr in _local_ipv4():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            if addr:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(addr))
                s.bind((addr, 0))
            for st in SEARCH_TARGETS:
                lines = ["M-SEARCH * HTTP/1.1", f"HOST: {SSDP[0]}:{SSDP[1]}", 'MAN: "ssdp:discover"', "MX: 2",
                         f"ST: {st}", "", ""]
                s.sendto(CRLF.join(lines).encode("ascii"), SSDP)
            socks.append(s)
        except OSError:
            s.close()
    deadline = time.time() + timeout
    try:
        while socks and time.time() < deadline:
            ready, _, _ = select.select(socks, [], [], max(0.0, deadline - time.time()))
            for s in ready:
                try:
                    data, _ = s.recvfrom(4096)
                except OSError:
                    continue
                m = re.search(rb"(?im)^location:[ \t]*([^\r\n]+)", data)
                if m:
                    url = m.group(1).decode("ascii", "replace").strip()
                    if url not in found:
                        found.append(url)
    finally:
        for s in socks:
            s.close()
    return found


def _gateway_from(location: str) -> Gateway | None:
    try:
        with urllib.request.urlopen(location, timeout=4) as resp:
            xml = resp.read()
    except OSError:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    ns = {"d": "urn:schemas-upnp-org:device-1-0"}
    base = root.findtext("d:URLBase", default="", namespaces=ns) or location
    services = {svc.findtext("d:serviceType", default="", namespaces=ns):
                svc.findtext("d:controlURL", default="", namespaces=ns)
                for svc in root.iter("{urn:schemas-upnp-org:device-1-0}service")}
    for wanted in SERVICES:
        if services.get(wanted):
            host = urllib.parse.urlparse(location).hostname or ""
            return Gateway(urllib.parse.urljoin(base, services[wanted]), wanted, local_ip_towards(host))
    return None


def find_gateway(timeout: float = 3.0) -> Gateway | None:
    """Find the router's UPnP IGD service, then try Linux NAT-PMP if SSDP found nothing."""
    for location in _search(timeout):
        gw = _gateway_from(location)
        if gw:
            return gw
    return _find_natpmp_gateway(min(timeout, 1.0))
