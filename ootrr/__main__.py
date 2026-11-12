"""Ligne de commande.

    python -m ootrr --seed 1234
    python -m ootrr --seed 1234 --romfs "D:\\...\\romfs" --install
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

from . import __version__, settings as settings_mod, spoiler as spoiler_mod
from .fill import FillError, generate
from .patch import build_patch, chest_changes, pickup_changes
from .world import DataError, World


def seed_to_int(seed: str | None) -> int:
    if seed is None:
        return random.SystemRandom().randrange(1, 10**9)
    if seed.isdigit():
        return int(seed)
    # une seed texte (« poulet ») donne toujours le même nombre
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)


def _parse_value(text: str):
    """« true » / « false » / nombre entier, sinon texte."""
    low = text.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(text)
    except ValueError:
        return text.strip()


def build_mod(patch: dict, romfs: Path, mod_name: str, install: bool, keep_dir: Path | None,
              test_pickups: list[str] | None = None, test_chests: list[str] | None = None,
              test_sets: list[str] | None = None, test_flags: list[str] | None = None,
              test_drops: list[str] | None = None, test_start: str | None = None,
              test_give: list[str] | None = None, test_scrubs: list[str] | None = None) -> None:
    from .modbuild import ModBuilder, TITLE_ID, emulator_root

    changes = chest_changes(patch)
    ground_changes, pickups = pickup_changes(patch)
    # objets ramassables de test ajoutés à la main (hors logique) : HASH=OBJET
    for i, entry in enumerate(test_pickups or []):
        h, item = entry.split("=", 1)
        name = f"Obj_OoTRR_Test_{i:03d}"
        pickups[name] = item.strip()
        ground_changes[int(h)] = {"Gyaml": name}
        print(f"Test : acteur {h} -> {name} (donne {item.strip()}, hors logique)")
    # coffres de test (hors logique) : HASH=OBJET ou HASH=OBJET@ÉVÉNEMENT
    for entry in test_chests or []:
        h, item = entry.split("=", 1)
        item, _, event = item.strip().partition("@")
        change = {"Drop__DropActor": item}
        if event:
            change["GetEventName"] = event
        changes[int(h)] = change
        print(f"Test : coffre {h} -> {item}" + (f" (événement {event})" if event else "") + ", hors logique")
    # butin d'un ennemi (ex. Skulltula d'or) : HASH=OBJET -> objet ramassable sur mesure qui donne OBJET
    for i, entry in enumerate(test_drops or []):
        h, item = entry.split("=", 1)
        name = f"Obj_OoTRR_Drop_{i:03d}"
        pickups[name] = item.strip()
        changes.setdefault(int(h), {})["Drop__DropActor"] = name
        print(f"Test : butin de {h} -> {name} (donne {item.strip()}, hors logique)")
    # Peste Mojo de test : HASH=OBJET[:PRIX] -> vend OBJET (vente unique) via le script commun
    from .patch import scrub_changes, skulltula_changes
    gs = skulltula_changes(patch, pickups)
    for h, change in gs.items():
        changes.setdefault(h, {}).update(change)
    if gs:
        print(f"Skulltulas d'or mélangées : {len(gs)} acteurs")
    from .world import SCRUB_SECRET_LOCATION
    scrubs, scrub_sales = scrub_changes(patch)
    for h, change in scrubs.items():
        changes.setdefault(h, {}).update(change)
    secret = next(((c["item"], scrub_sales[c["item"]]) for c in patch["chests"]
                   if c.get("scrub") and c["location"] == SCRUB_SECRET_LOCATION), None)
    if scrubs:
        print(f"Peste Mojo mélangées : {len(scrub_sales)} objets vendus")
    for entry in test_scrubs or []:
        h, spec = entry.split("=", 1)
        item, _, price = spec.partition(":")
        scrub_sales[item] = int(price or 40)
        changes.setdefault(int(h), {}).update({
            "ScrubBusiness_ShopItemActorName0": item, "ScrubBusiness_ShopItemActorName1": None,
            "ScrubBusiness_ShopItemActorName2": None, "TalkEventName": "Enemy_Scrub_Business_DekuStickPouch_01"})
        print(f"Test : Peste Mojo {h} -> vend {item} ({scrub_sales[item]} rubis), hors logique")
    # champ quelconque d'un acteur : HASH=CHAMP=VALEUR (ex. objet vendu par une Peste Mojo)
    for entry in test_sets or []:
        h, key, value = entry.split("=", 2)
        changes.setdefault(int(h), {})[key] = _parse_value(value)
        print(f"Test : acteur {h} : {key} = {value}")
    for h, change in (patch.get("actor_changes") or {}).items():
        changes.setdefault(int(h), {}).update(change)
    pickups.update(patch.get("extra_pickups") or {})
    removed = patch.get("removed_actors") or []
    for h in removed:
        changes[int(h)] = {"__delete": True}
    if removed:
        print(f"Acteurs retirés des cartes : {len(removed)}")
    print(f"Construction du mod : {len(changes)} coffres et {len(ground_changes)} cœurs au sol modifiés "
          f"({len(pickups)} objets ramassables sur mesure) — lecture des cartes du jeu…")
    changes.update(ground_changes)
    with tempfile.TemporaryDirectory(prefix="ootrr_") as tmp:
        mod_dir = Path(tmp) / mod_name
        flags = dict(patch.get("start_flags") or {})
        for entry in test_flags or []:
            name, value = entry.split("=", 1)
            flags[name] = _parse_value(value)
            print(f"Test : drapeau de départ {name} = {value}")
        if flags:
            print(f"Nouvelle partie : {len(flags)} drapeaux activés dès le départ")
        skips = patch.get("event_skips") or {}
        if skips:
            print(f"Scènes d'introduction sautées : {sum(len(v) for v in skips.values())}")
        start_items = list(patch.get("start_items") or []) + list(test_give or [])
        if start_items:
            print(f"Inventaire de départ : {', '.join(start_items)}")
        logic = patch.get("logic_patches") or {}
        if logic:
            print(f"Modules de logique modifiés : {', '.join(sorted(logic))}")
        if (patch.get("settings") or {}).get("shuffle_gifts"):
            print("Cadeaux mélangés : les objets sont donnés sous leur nom (non validé en jeu hors du menu natif)")
        event_changes = patch.get("event_changes") or {}
        if event_changes:
            print(f"Récompenses de boss modifiées dans {len(event_changes)} scènes")
        builder = ModBuilder(romfs)
        builder.scrub_secret = secret
        if patch.get("moat_items"):
            builder.moat_items = tuple(patch["moat_items"])
        builder.ocarina_guard = bool(patch.get("ocarina_guard", True))
        builder.gift_edits = {f: [tuple(e) for e in v] for f, v in (patch.get("gift_changes") or {}).items()}
        builder.build(changes, mod_dir / "romfs", flags, event_changes=event_changes or None,
                                event_skips=skips, pickups=pickups or None,
                                start_items=start_items, moat_gate=bool(patch.get("ocarina_moat_gate")),
                                logic_patches=logic, bool_exps=patch.get("bool_exps") or None,
                                start_warp=tuple(test_start.split("=", 1)) if test_start
                                else (tuple(patch["start_warp"]) if patch.get("start_warp") else None),
                                scrub_sales=scrub_sales or None,
                                questions=patch.get("ingame_questions") or None,
                                rsdb_changes=patch.get("rsdb_changes") or None,
                                pack_changes=patch.get("pack_changes") or None)
        if keep_dir:
            dest = keep_dir / mod_name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(mod_dir, dest)
            print(f"Mod copié dans {dest}")
        if install:
            load_dir = emulator_root() / "load" / TITLE_ID
            load_dir.mkdir(parents=True, exist_ok=True)
            test_mod = load_dir / "OoTRR-test"
            dest = load_dir / mod_name
            try:
                if test_mod.exists():
                    shutil.rmtree(test_mod)
                    print("Ancien mod de test OoTRR-test supprimé (il modifiait les mêmes fichiers).")
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(mod_dir, dest)
            except PermissionError:
                raise SystemExit("Erreur : fichiers du mod verrouillés. Ferme Eden (ou le jeu) puis relance la commande.")
            others = [p.name for p in load_dir.iterdir() if p.is_dir() and p.name != mod_name]
            print(f"Mod installé dans Eden : {dest}")
            if others:
                print(f"Attention : autres mods présents pour ce jeu ({', '.join(others)}). "
                      "S'ils modifient les mêmes fichiers, désactive-les.")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="ootrr", description="Randomizer Ocarina of Time Remake")
    p.add_argument("--seed", help="nombre ou texte ; aléatoire si absent")
    p.add_argument("--settings", help="fichier JSON de réglages")
    p.add_argument("--set", action="append", default=[], metavar="NOM=VALEUR", help="surcharge un réglage")
    p.add_argument("--out", default="output", help="dossier du spoiler et du patch (défaut : output)")
    p.add_argument("--no-spoiler", action="store_true", help="ne pas écrire le spoiler log")
    p.add_argument("--romfs", help="RomFS extraite du jeu (dossier updates\\...\\romfs) : construit le mod")
    p.add_argument("--install", action="store_true", help="installe le mod dans Eden (nécessite --romfs)")
    p.add_argument("--mod-name", default="OoTRR", help="nom du dossier du mod (défaut : OoTRR)")
    p.add_argument("--mod-out", help="copie aussi le mod dans ce dossier")
    p.add_argument("--test-pickup", action="append", default=[], metavar="HASH=OBJET",
                   help="test : remplace l'acteur HASH par un objet ramassable qui donne OBJET (hors logique)")
    p.add_argument("--test-chest", action="append", default=[], metavar="HASH=OBJET[@ÉVÉNEMENT]",
                   help="test : met OBJET dans le coffre HASH (hors logique), avec un événement d'ouverture optionnel")
    p.add_argument("--test-set", action="append", default=[], metavar="HASH=CHAMP=VALEUR",
                   help="test : change un champ Dynamic de l'acteur HASH (hors logique)")
    p.add_argument("--test-drop", action="append", default=[], metavar="HASH=OBJET",
                   help="test : l'ennemi HASH laisse un objet ramassable sur mesure qui donne OBJET (hors logique)")
    p.add_argument("--test-start", metavar="BANC=POINT",
                   help="test : la nouvelle partie commence ailleurs, ex. HyruleField_Child=HyruleField_FrontOfMarket")
    p.add_argument("--test-scrub", action="append", default=[], metavar="HASH=OBJET[:PRIX]",
                   help="test : la Peste Mojo HASH vend OBJET une seule fois (hors logique)")
    p.add_argument("--test-give", action="append", default=[], metavar="OBJET",
                   help="test : objet ajouté à l'inventaire de départ (hors logique)")
    p.add_argument("--test-flag", action="append", default=[], metavar="NOM=VALEUR",
                   help="test : valeur d'un drapeau GameData au début d'une nouvelle partie")
    p.add_argument("--check", action="store_true", help="valider les données et quitter")
    p.add_argument("--list-settings", action="store_true", help="afficher les réglages disponibles")
    p.add_argument("--version", action="version", version=f"ootrr {__version__}")
    args = p.parse_args(argv)

    if args.list_settings:
        for name, (default, allowed, desc) in settings_mod.SETTINGS.items():
            choices = ", ".join(allowed) if isinstance(allowed, tuple) else allowed.__name__
            print(f"{name:<22} défaut={default!r:<12} [{choices}]\n{'':<22} {desc}")
        return 0
    if args.install and not args.romfs:
        p.error("--install nécessite --romfs")

    try:
        settings = settings_mod.load(args.settings, args.set)
        if settings.get("shuffle_shops", "off") != "off":
            # les boutiques ne sont appliquées que par le menu dans le jeu (module natif)
            raise settings_mod.SettingsError("shuffle_shops : boutiques disponibles seulement avec le menu "
                                             "dans le jeu (python -m ootrr.tools.menutest)")
        world = World(settings)
    except (settings_mod.SettingsError, DataError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2

    if args.check:
        print(f"Données valides : {len(world.regions)} régions, {len(world.locations)} lieux "
              f"({len(world.shuffled_locations())} coffres mélangés, {len(world.fixed_locations())} fixes), "
              f"{len(world.events)} événements, {len(world.items)} objets.")
        return 0

    if args.romfs:
        bad = settings_mod.unsupported_by_patcher(settings)
        if bad:
            print(f"Erreur : le patcher ne sait pas encore modifier le jeu pour {', '.join(bad)}. "
                  "Garde les valeurs par défaut pour générer un mod jouable.", file=sys.stderr)
            return 2

    seed = seed_to_int(args.seed)
    from .starting import resolve
    resolved = settings_mod.build(resolve(settings, seed))  # âge et point d'apparition tirés par la seed
    if resolved != settings:
        world = World(resolved)
    t0 = time.perf_counter()
    try:
        result = generate(world, seed)
    except FillError as exc:
        print(f"Seed {seed} : {exc}", file=sys.stderr)
        return 1
    spoiler = spoiler_mod.build(world, result)
    patch = build_patch(world, result, spoiler["hash"])

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"OoTRR_{seed}_{spoiler['hash']}"
    (out_dir / f"{stem}_patch.json").write_text(json.dumps(patch, indent=2, ensure_ascii=False), encoding="utf-8")
    if not args.no_spoiler:
        (out_dir / f"{stem}_spoiler.txt").write_text(spoiler_mod.to_text(spoiler), encoding="utf-8")
    print(f"Seed {seed}  hash {spoiler['hash']}  {len(spoiler['playthrough'])} sphères  "
          f"({result.attempts} essai(s), {time.perf_counter() - t0:.2f}s) -> {out_dir / stem}_*")

    if args.romfs:
        build_mod(patch, Path(args.romfs), args.mod_name, args.install,
                  Path(args.mod_out) if args.mod_out else None, args.test_pickup, args.test_chest, args.test_set, args.test_flag, args.test_drop, args.test_start, args.test_give, args.test_scrub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
