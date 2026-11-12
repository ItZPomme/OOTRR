"""Spoiler log d'une partie générée dans le jeu (menu natif), sans construire de mod.

    python -m ootrr.tools.ingame_spoiler --romfs ROMFS                 # partie la plus récente
    python -m ootrr.tools.ingame_spoiler --romfs ROMFS --slot 2        # emplacement de sauvegarde 2
    python -m ootrr.tools.ingame_spoiler --seed 726533 --set shuffle_shops=4 --set shuffle_ocarinas=true

Le module natif génère la partie avec la seed affichée dans le menu **mélangée aux réglages**
(MixSettings, FNV-1a 64 bits) : ce n'est pas la seed de `python -m ootrr --seed`. Cet outil refait
exactement ce calcul, puis lance le générateur Python (identique au générateur du jeu, voir
tools/native_check).

- Avec une sauvegarde (Eden / Fritchii fermé ou non) : la seed (`OoTRR.Seed`) et les réglages du menu
  (structures `OoTRRMenu*`) sont relus dans `slot_NN/progress.sav`. Il faut la RomFS (valeurs des listes
  du menu).
- Avec `--seed` : la seed affichée dans le menu (ligne « Seed manuelle ») et les réglages choisis
  (`--set`, mêmes noms que `--list-settings` ; les autres gardent leur valeur par défaut).

Écrit output/OoTRR_menu_<seed>_<hash>_spoiler.txt.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from .. import ingame_menu as menu
from .. import spoiler as spoiler_mod
from ..fill import generate
from ..formats.gamedata import flag_hash, index
from ..settings import SETTINGS, SettingsError, build, defaults
from ..world import World


def mix_settings(seed: int, values: list[int]) -> int:
    """Même calcul que ingame.cpp (MixSettings)."""
    h = 0xCBF29CE484222325

    def mix(v: int) -> None:
        nonlocal h
        v &= 0xFFFFFFFF
        for i in range(4):
            h ^= (v >> (8 * i)) & 0xFF
            h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF

    mix(seed)
    for v in values:
        mix(v)
    return h & 0x7FFFFFFFFFFFFFFF


def value_index(name: str, value) -> int:
    allowed = SETTINGS[name][1]
    if allowed is bool:
        return int(bool(value))
    if allowed is int:
        return int(value)
    return allowed.index(value)


def native_settings(chosen: dict) -> dict:
    """Réglages tels que GenerateFromMenu les construit : défauts, lignes du menu, réglages fixes,
    nombre du pont selon sa condition."""
    s = defaults()
    picks = {r[1]: int(chosen[r[1]]) for r in menu.BRIDGE_ROWS if r[1] in chosen}
    s.update({k: v for k, v in chosen.items() if k not in picks})
    s.update(menu.FIXED_SETTINGS)
    if s["bridge"] in menu.BRIDGE_COUNTS:
        rows = [r[1] for r in menu.BRIDGE_ROWS if r[0] == s["bridge"] and r[1] in picks]
        # nombre requis = somme des lignes de la condition (cœurs : base + supplément)
        s["bridge_count"] = sum(picks[r] for r in rows) if rows else menu.BRIDGE_COUNTS[s["bridge"]]
    return build(s)


def read_save(path: Path) -> dict[int, int]:
    """progress.sav : en-tête 0x20 octets puis paires (hachage u32, valeur u32) ; seules les entrées
    scalaires nous intéressent, cherchées par leur hachage."""
    data = path.read_bytes()
    words = struct.unpack_from(f"<{(len(data) - 0x20) // 4}I", data, 0x20)
    out: dict[int, int] = {}
    for i in range(len(words) - 1):
        out.setdefault(words[i], words[i + 1])
    return out


def settings_from_save(entries: dict[int, int], romfs: Path) -> tuple[int, dict]:
    from ..formats.byml import read_byml
    from ..formats.zs import ZsCodec

    seed = entries.get(flag_hash(menu.SEED_ENTRY))
    if not seed:
        raise SystemExit("pas de seed OoTRR dans cette sauvegarde (partie lancée sans le menu du randomizer ?)")
    codec = ZsCodec(romfs)
    root = read_byml(codec.decompress(next((romfs / "GameData").glob("GameDataList*.byml.zs"))))
    idx = index(root)
    src = next(e for e in root["Data"]["Struct"] if e["Hash"] == flag_hash(menu.OPTION_STRUCT))
    members = {m["Hash"]: m["Value"] for m in src["DefaultValue"]}
    chosen = {}
    missing = []
    for setting, option_type, values in menu.SETTING_ROWS:
        h = flag_hash(f"{menu.STRUCTS[menu.page_of(setting)]}.{option_type}")
        if h not in entries:
            missing.append(setting)
            continue
        raw = entries[h]
        if values is None:
            chosen[setting] = bool(raw & 1)
            continue
        _, entry = idx[members[flag_hash(option_type)]]
        game = [flag_hash(v) for v in entry["RawValues"][:len(values)]]
        if raw in game:
            chosen[setting] = values[game.index(raw)]
        else:
            missing.append(setting)
    for _, row, option_type, numbers in menu.BRIDGE_ROWS:  # nombre requis pour le pont
        h = flag_hash(f"{menu.STRUCTS[menu.page_of(row)]}.{option_type}")
        _, entry = idx[members[flag_hash(option_type)]]
        game = [flag_hash(v) for v in entry["RawValues"][:len(numbers)]]
        all_values = [flag_hash(v) for v in entry["RawValues"]]
        if entries.get(h) in game:
            chosen[row] = numbers[game.index(entries[h])]
        elif entries.get(h) in all_values:  # au-delà des choix de la ligne (membre partagé) : le maximum
            chosen[row] = numbers[-1]
    if missing:
        print(f"attention : réglages absents de la sauvegarde (valeur par défaut) : {', '.join(missing)}")
    return seed, chosen


def find_save(slot: int | None) -> Path:
    from .saves import game_save_dir

    folder = game_save_dir()
    saves = sorted(folder.glob("slot_*/progress.sav"), key=lambda p: p.stat().st_mtime)
    if slot is not None:
        saves = [p for p in saves if p.parent.name == f"slot_{slot:02d}"]
    if not saves:
        raise SystemExit(f"aucune sauvegarde trouvée sous {folder}")
    return saves[-1]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--romfs", help="RomFS de la mise à jour (nécessaire pour relire une sauvegarde)")
    p.add_argument("--slot", type=int, help="emplacement de sauvegarde (défaut : le plus récent)")
    p.add_argument("--save", help="fichier progress.sav à lire (au lieu de chercher dans l'émulateur)")
    p.add_argument("--seed", type=int, help="seed affichée dans le menu (sans sauvegarde)")
    p.add_argument("--set", action="append", default=[], metavar="NOM=VALEUR", help="réglage choisi dans le menu (avec --seed)")
    p.add_argument("--out", default="output")
    a = p.parse_args(argv)

    try:
        if a.seed is not None:
            seed = a.seed
            chosen = {}
            for entry in a.set:
                k, _, v = entry.partition("=")
                chosen[k.strip()] = v.strip()
            settings = native_settings(chosen)
            source = "seed et réglages donnés"
        else:
            if not a.romfs:
                p.error("--romfs est nécessaire pour relire une sauvegarde (ou donner --seed)")
            path = Path(a.save) if a.save else find_save(a.slot)
            seed, chosen = settings_from_save(read_save(path), Path(a.romfs))
            settings = native_settings(chosen)
            source = str(path)
    except SettingsError as exc:
        print(f"Réglages invalides : {exc}", file=sys.stderr)
        return 2

    mixed = mix_settings(seed, [value_index(k, settings[k]) for k in SETTINGS])
    from ..starting import resolve
    settings = build(resolve(settings, mixed))  # âge et point d'apparition (ingame.cpp, ResolveStart)
    world = World(settings)
    result = generate(world, mixed)
    sp = spoiler_mod.build(world, result)
    sp["seed"] = f"{seed} (menu ; générateur : {mixed})"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"OoTRR_menu_{seed}_{sp['hash']}_spoiler.txt"
    dest.write_text(spoiler_mod.to_text(sp), encoding="utf-8")
    print(f"source : {source}")
    print(f"seed du menu {seed} -> seed du générateur {mixed}")
    changed = {k: v for k, v in settings.items() if v != defaults()[k]}
    print("réglages : " + (", ".join(f"{k}={v}" for k, v in changed.items()) or "défaut"))
    print(f"spoiler : {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
