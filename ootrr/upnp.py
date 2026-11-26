"""UPnP port mapping on the home router (IGD), standard library only: lets a multiworld host be reached from the
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


def _local_ipv4() -> list[str]:
    if sys.platform == "linux":
        import fcntl

        addrs = set()
        for _, name in socket.if_nameindex():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    request = struct.pack("256s", name.encode()[:15])
                    response = fcntl.ioctl(s.fileno(), 0x8915, request)  # SIOCGIFADDR
                addrs.add(socket.inet_ntoa(response[20:24]))
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
    """The router's UPnP port mapping service, None if no router answers (UPnP off, no UPnP router)."""
    for location in _search(timeout):
        gw = _gateway_from(location)
        if gw:
            return gw
    return None
