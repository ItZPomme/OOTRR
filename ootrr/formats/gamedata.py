"""Drapeaux de sauvegarde (GameData/GameDataList*.byml.zs).

Chaque drapeau est identifié par le MurmurHash3 (32 bits, graine 0) de son nom,
par exemple « IsGet.Weapon_Shield_Deku ». Sa valeur DefaultValue est la valeur
d'une nouvelle partie : la modifier change l'état de départ du jeu.
"""

from __future__ import annotations


def murmur3_32(data: bytes | str, seed: int = 0) -> int:
    if isinstance(data, str):
        data = data.encode("utf-8")
    c1, c2 = 0xCC9E2D51, 0x1B873593
    h = seed
    n = len(data) // 4
    for i in range(n):
        k = int.from_bytes(data[4 * i:4 * i + 4], "little")
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
    tail = data[4 * n:]
    if tail:
        k = 0
        for i, b in enumerate(tail):
            k |= b << (8 * i)
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h


def flag_hash(name: str) -> int:
    """Hash d'un drapeau : « #1234 » désigne directement un hash (entrée dont le nom est inconnu)."""
    return int(name[1:]) if name.startswith("#") else murmur3_32(name)


def enum_value(entry: dict, raw_name: str) -> int:
    """Valeur stockée d'une entrée Enum pour le nom de valeur raw_name."""
    if raw_name not in entry["RawValues"]:
        raise KeyError(f"valeur d'enum inconnue {raw_name!r} (connues : {entry['RawValues']})")
    return entry["Values"][entry["RawValues"].index(raw_name)]


def index(gamedata_root: dict) -> dict[int, tuple[str, dict]]:
    """{hash: (type, entrée)} pour toutes les entrées du GameDataList décodé."""
    data = gamedata_root.get("Data", gamedata_root)
    out = {}
    for section, entries in data.items():
        if isinstance(entries, list):
            for e in entries:
                if isinstance(e, dict) and "Hash" in e:
                    out[int(e["Hash"])] = (section, e)
    return out


BOOL_EXP_OPS = {"Bool": 0, "Exp": 10, "AND": 3, "OR": 4, "NOT": 5}


def encode_bool_exp(program: list) -> list[list[int]]:
    """Expression booléenne en notation postfixe, ex. [("Bool", "IsGet.X"), ("Bool", "IsGet.Y"), ("AND",)].

    Codes relevés dans GameDataList : 0 = drapeau Bool, 10 = autre expression,
    3 = ET, 4 = OU, 5 = NON (les opérateurs prennent les valeurs de la pile)."""
    out = []
    for step in program:
        if step[0] == "IntEq":  # entier == constante : codes 15 (drapeau Int) puis 16 (constante)
            out += [[15, flag_hash(step[1])], [16, int(step[2])]]
            continue
        op = BOOL_EXP_OPS[step[0]]
        out.append([op, flag_hash(step[1])] if len(step) > 1 else [op])
    return out
