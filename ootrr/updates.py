"""Update check: is there a newer OoTRR release on GitHub than this one (`__version__`)?

The desktop app asks once at start, in a background thread, and shows a button that opens the release page. Nothing
is downloaded or installed: the player gets the new exe from the release page themself. Offline, rate limited or
any other error: no answer, the app says nothing.
"""

from __future__ import annotations

import json
import re
import urllib.request

from . import __version__

REPO = "ItZPomme/OOTRR"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"  # latest published, non-prerelease release
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def parse_version(text: str) -> tuple[int, ...] | None:
    """(0, 3, 0) from "v0.3.0" or "0.3.0"; None if it is not a version number."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", text.strip(), re.IGNORECASE)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def is_newer(tag: str, current: str = __version__) -> bool:
    new, cur = parse_version(tag), parse_version(current)
    if new is None or cur is None:
        return False
    width = max(len(new), len(cur))
    return new + (0,) * (width - len(new)) > cur + (0,) * (width - len(cur))


def latest_release(timeout: float = 5.0) -> dict | None:
    """{"tag": "v0.4.0", "name": ..., "url": release page} of the latest release, or None on any error."""
    req = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": "OoTRR-App"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    tag = data.get("tag_name")
    if not isinstance(tag, str):
        return None
    url = data.get("html_url")
    if not (isinstance(url, str) and url.startswith(f"https://github.com/{REPO}/")):
        url = RELEASES_PAGE
    return {"tag": tag, "name": data.get("name") or tag, "url": url}


def check(timeout: float = 5.0) -> dict | None:
    """The latest release if it is newer than this version, else None."""
    rel = latest_release(timeout)
    return rel if rel and is_newer(rel["tag"]) else None
