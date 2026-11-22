"""Race helpers: a short settings string to share, and the seed hash shown as 5 item symbols.

Settings string (format 3), e.g. ``R3-3FZC33800HV``, ``R3-3FZC33800V0-727557`` with the seed, or
``R3-3FZC33800BZ-727557-HE668CBE6F0`` with the seed and the host's seed hash:

- ``R3``: format version. Format 2 strings (OoTRR 0.3.0 to 0.4.0) are still read, their missing settings
  (`gerudo_card`, `gerudo_fortress`) at the default; another format is refused (`SettingsStringError`).
- then the settings the desktop app shows (`settings_ui.SHOWN`), packed as one mixed-radix number in a fixed
  order (`FIELDS`, frozen for format 3, independent of the app's pages) and written in Crockford base 32;
- two check characters (10 bits of SHA-256 over everything else, seed included), so a typo is refused;
- optionally ``-<seed>``: the seed as the number the generator uses (`__main__.seed_to_int`: a text seed is
  exported as its number, which generates the same seed);
- optionally, after the seed, ``-H<hash>``: the 10 hex digits of the seed hash the host got (`spoiler.seed_hash`).
  It changes nothing in the generation: a racer who builds the seed compares their hash with it, which catches a
  different OoTRR version (same settings and seed, other placement). The check characters cover it, and strings
  without it are unchanged (an OoTRR without this field refuses strings that have it).

Settings the app does not show (`settings_ui.HIDDEN`, `NATIVE_ONLY`) are not in the string: they keep the
generator's defaults, as in the app. Same string + same OoTRR version = same generated seed (the generator's
version changes the placement, see the hash symbols). Changing `FIELDS`, a setting's values or an integer range
means a new format number (`tests/test_race.py` pins format 4, and format 2 reading). Format 1 (OoTRR before the
dungeon key settings) had the same fields without `small_keys` and `boss_keys`, format 2 without `gerudo_card` and
`gerudo_fortress`, format 3 without `key_locations`.

Hash symbols: the first 25 bits of the seed hash (`spoiler.seed_hash`, 10 hex digits, which covers the settings,
the placement and the version) pick 5 of the 32 `SYMBOLS`. The desktop app draws them, the spoiler log names them.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, NamedTuple

from . import settings as settings_mod

FORMAT = 4
PREFIX = "R"
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base 32 (no I, L, O, U)
_READ_AS = {"I": "1", "L": "1", "O": "0"}

# every setting the app shows, in a fixed order; never reorder. Format 1 = the fields up to starting_age
# (alphabetical when frozen); format 2 added small_keys and boss_keys at the end; format 3 added gerudo_card and
# gerudo_fortress; format 4 added key_locations
FIELDS: tuple[str, ...] = (
    "accessibility", "adult_trade_sequence", "big_poe_count", "blue_fire_arrows", "bridge", "bridge_count",
    "complete_mask_quest", "cucco_count", "fast_bunny_hood", "free_time_travel", "logic", "logic_lens_required",
    "maps_compasses", "open_door_of_time", "open_forest", "scrub_prices", "shuffle_ocarinas", "shuffle_rewards",
    "shuffle_scrubs", "shuffle_skulltulas", "shuffle_songs", "skip_child_zelda", "skip_cutscenes",
    "start_with_consumables", "starting_age",
    "small_keys", "boss_keys",
    "gerudo_card", "gerudo_fortress",
    "key_locations",
)
# older formats still read (their missing settings keep the generator's defaults): format -> its fields
OLD_FIELDS: dict[int, tuple[str, ...]] = {2: FIELDS[:FIELDS.index("gerudo_card")],
                                          3: FIELDS[:FIELDS.index("key_locations")]}
# encoded range of the integer settings (bridge_count: the widest range `settings.build` accepts)
INT_FIELDS = {"bridge_count": (0, 20), "cucco_count": (1, 7), "big_poe_count": (1, 5)}

MAX_SEED_DIGITS = 20
HASH_DIGITS = 10  # spoiler.seed_hash


class RaceCode(NamedTuple):
    settings: dict[str, Any]
    seed: str | None
    seed_hash: str | None  # the host's seed hash (10 hex digits, upper case) or None


class SettingsStringError(ValueError):
    pass


def _values(name: str) -> list[Any]:
    """Every value of a field, in encoding order."""
    allowed = settings_mod.SETTINGS[name][1]
    if allowed is bool:
        return [False, True]
    if allowed is int:
        lo, hi = INT_FIELDS[name]
        return list(range(lo, hi + 1))
    return list(allowed)


def _payload_length(fields: tuple[str, ...] = FIELDS) -> int:
    total = 1
    for name in fields:
        total *= len(_values(name))
    n = 1
    while 32 ** n < total:
        n += 1
    return n


def _to_base32(number: int, length: int) -> str:
    out = []
    for _ in range(length):
        number, digit = divmod(number, 32)
        out.append(ALPHABET[digit])
    return "".join(reversed(out))


def _check(body: str) -> str:
    bits = int(hashlib.sha256(body.encode("ascii")).hexdigest()[:4], 16) >> 6  # 10 bits
    return _to_base32(bits, 2)


def encode(values: dict[str, Any], seed: str | int | None = None, seed_hash: str | None = None) -> str:
    """Settings string for `values` (a full or partial settings dict; missing settings = defaults).

    `seed_hash` (the seed hash of a built seed, needs `seed`) lets the racers who paste the string check that
    they got the same seed."""
    settings = settings_mod.build({k: v for k, v in values.items() if k in FIELDS})
    number = 0
    for name in FIELDS:
        choices = _values(name)
        value = settings[name]
        if value not in choices:
            raise SettingsStringError(f"{name}: {value!r} cannot be written in a settings string")
        number = number * len(choices) + choices.index(value)
    body = f"{PREFIX}{FORMAT}-{_to_base32(number, _payload_length())}"
    has_seed = seed is not None and bool(str(seed).strip())
    if has_seed:
        from .__main__ import seed_to_int
        body += f"|{seed_to_int(str(seed).strip())}"
    if seed_hash:
        if not has_seed:
            raise SettingsStringError("a seed hash needs a seed")
        seed_hash = seed_hash.strip().upper()
        if not re.fullmatch(rf"[0-9A-F]{{{HASH_DIGITS}}}", seed_hash):
            raise SettingsStringError(f"not a seed hash: {seed_hash!r}")
        body += f"#{seed_hash}"
    head, _, tail = body.partition("|")
    seed_part, _, hash_part = tail.partition("#")
    return (head + _check(body) + (f"-{seed_part}" if seed_part else "")
            + (f"-H{hash_part}" if hash_part else ""))


def decode(text: str) -> tuple[dict[str, Any], str | None]:
    """(full settings dict, seed or None) from a settings string; `SettingsStringError` if it is not valid."""
    code = decode_full(text)
    return code.settings, code.seed


def decode_full(text: str) -> RaceCode:
    """`decode`, plus the host's seed hash if the string has one."""
    s = "".join(text.split()).upper()
    if not s:
        raise SettingsStringError("the settings string is empty")
    m = re.fullmatch(rf"{PREFIX}(\d+)-([0-9A-Z]+)(?:-(\d+)(?:-H([0-9A-F]+))?)?", s)
    if not m:
        raise SettingsStringError(f"not an OoTRR settings string (expected {PREFIX}{FORMAT}-...)")
    fmt = int(m.group(1))
    fields = FIELDS if fmt == FORMAT else OLD_FIELDS.get(fmt)
    if fields is None:
        readable = ", ".join(str(f) for f in sorted([FORMAT, *OLD_FIELDS]))
        raise SettingsStringError(f"settings string of format {m.group(1)}; this version of OoTRR reads "
                                  f"formats {readable} (use the same OoTRR version)")
    code = "".join(_READ_AS.get(c, c) for c in m.group(2))
    seed, seed_hash = m.group(3), m.group(4)
    length = _payload_length(fields)
    if len(code) != length + 2 or any(c not in ALPHABET for c in code):
        raise SettingsStringError("the settings string is damaged (wrong length or letters)")
    if seed is not None and len(seed) > MAX_SEED_DIGITS:
        raise SettingsStringError("the seed in the settings string is too long")
    if seed_hash is not None and len(seed_hash) != HASH_DIGITS:
        raise SettingsStringError("the seed hash in the settings string is damaged (wrong length)")
    payload, check = code[:length], code[length:]
    body = (f"{PREFIX}{fmt}-{payload}" + (f"|{seed}" if seed is not None else "")
            + (f"#{seed_hash}" if seed_hash is not None else ""))
    if _check(body) != check:
        raise SettingsStringError("the settings string is damaged (check letters do not match): copy it again")
    number = 0
    for c in payload:
        number = number * 32 + ALPHABET.index(c)
    picked: dict[str, Any] = {}
    for name in reversed(fields):
        choices = _values(name)
        number, index = divmod(number, len(choices))
        picked[name] = choices[index]
    if number:
        raise SettingsStringError("the settings string is damaged (value out of range)")
    try:
        settings = settings_mod.build(picked)
    except settings_mod.SettingsError as exc:
        raise SettingsStringError(f"the settings string holds invalid settings: {exc}") from None
    return RaceCode(settings, str(int(seed)) if seed is not None else None, seed_hash)


# ---- hash symbols ----------------------------------------------------------------------------------------------
# 32 recognisable items of the game (drawn by the app, never read from game files); never reorder
SYMBOLS: tuple[str, ...] = (
    "Deku Stick", "Deku Nut", "Bomb", "Fairy Bow", "Fire Arrow", "Ice Arrow", "Light Arrow", "Slingshot",
    "Ocarina", "Hookshot", "Boomerang", "Lens of Truth", "Magic Bean", "Megaton Hammer", "Bottle", "Kokiri Sword",
    "Master Sword", "Deku Shield", "Hylian Shield", "Iron Boots", "Hover Boots", "Goron Bracelet", "Silver Scale",
    "Heart Container", "Rupee", "Gold Skulltula", "Triforce", "Compass", "Small Key", "Boss Key", "Din's Fire",
    "Fairy",
)
HASH_SYMBOLS = 5


def hash_symbols(seed_hash: str) -> list[str]:
    """The 5 symbol names of a seed hash (hex string, at least 7 digits)."""
    value = int(seed_hash[:7], 16) >> 3  # 25 bits
    return [SYMBOLS[(value >> (5 * (HASH_SYMBOLS - 1 - i))) & 31] for i in range(HASH_SYMBOLS)]
