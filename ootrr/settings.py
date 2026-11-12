"""Réglages du randomizer : valeurs par défaut, validation, chargement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Réglages qui décrivent le comportement du jeu. Le patcher ne sait pas encore
# modifier ces comportements : pour jouer, garde les valeurs du jeu d'origine.
GAME_LOCKED = {"open_kakariko": False}

# nom -> (valeur par défaut, valeurs autorisées ou type, description)
SETTINGS: dict[str, tuple[Any, Any, str]] = {
    "bridge": ("vanilla", ("open", "vanilla", "stones", "medallions", "dungeons", "hearts"),
               "Condition du pont arc-en-ciel : open, vanilla (jeu d'origine), stones, medallions, "
               "dungeons (pierres + médaillons) ou hearts (cœurs) ; le nombre est bridge_count"),
    "bridge_count": (6, int, "Nombre de pierres / médaillons / récompenses / cœurs requis pour le pont"),
    "open_forest": ("closed", ("closed", "closed_deku", "open", "ask"),
                    "Forêt Kokiri : closed = jeu d'origine ; closed_deku = sortie vers le pont ouverte dès le départ "
                    "(le Kokiri qui la bloque est retiré) ; open = aussi l'Arbre Mojo (Mido est retiré) ; ask = question au début de la nouvelle partie (la logique suppose la forêt fermée)"),
    "open_door_of_time": (False, bool, "Porte du Temps ouverte dès le départ (jeu d'origine : non ; dans le remake, la porte demande le Rubis Goron et le Saphir Zora)"),
    "open_kakariko": (False, bool, "Garde du Mont du Péril ouvert sans la lettre (jeu d'origine : non)"),
    "maps_compasses": ("vanilla", ("vanilla", "start_with", "shuffle", "removed"),
                       "Cartes et boussoles : à leur place, possédées dès le départ, mélangées dans leur "
                       "propre donjon, ou retirées (remplacées par des rubis)"),
    "shuffle_hearts": ("none", ("none", "freestanding", "all"),
                       "Cœurs posés au sol : freestanding = les 13 quarts de cœur libres deviennent des "
                       "emplacements mélangés ; all = aussi les 8 réceptacles des boss (vérifié en jeu avec Gohma)"),
    "shuffle_scrubs": (False, bool,
                       "Peste Mojo vendeurs : les 5 qui vendent un objet unique (quarts de cœur de la plaine et du "
                       "cratère, améliorations des bâtons et des noix) vendent une fois l'objet placé, 40 rubis"),
    "shuffle_shops": ("off", ("off", "1", "2", "3", "4"),
                      "Boutiques : nombre d'articles par boutique (8 boutiques, sans les masques) qui vendent "
                      "un objet de la seed, une seule fois"),
    "shop_prices": ("vanilla", ("vanilla", "affordable", "random"),
                    "Prix des articles mélangés : vanilla = prix de l'article remplacé ; affordable = 10 rubis ; "
                    "random = 0 à 95 rubis tirés par la seed (achetables sans bourse)"),
    "scrub_prices": ("vanilla", ("vanilla", "affordable", "random"),
                     "Prix des Peste Mojo mélangées : vanilla = 40 rubis ; affordable = 10 rubis ; "
                     "random = 0 à 95 rubis tirés par la seed"),
    "shuffle_skulltulas": ("off", ("off", "overworld", "all"),
                           "Skulltulas d'or : overworld = les Skulltulas hors donjons lâchent l'objet placé à la "
                           "place de leur jeton ; all = aussi celles des donjons (règles prudentes : jamais d'objet "
                           "nécessaire pour finir)"),
    "skip_cutscenes": ("none", ("none", "safe"),
                       "safe : les cinématiques sans effet sur la partie (liste data/cutscenes.json) "
                       "sont marquées comme déjà vues dès la nouvelle partie"),
    "shuffle_rewards": ("vanilla", ("vanilla", "shuffled"),
                        "Pierres et médaillons : vanilla = à leur place ; shuffled = mélangés entre les 8 boss "
                        "et la poche de Link (donnée au départ, la scène de Rauru est sautée)"),
    "free_time_travel": (True, bool,
                         "L'épée de légende renvoie Link enfant à tout moment (jeu d'origine du remake : "
                         "seulement après le Temple de la Forêt)"),
    "skip_child_zelda": (False, bool,
                         "Lettre de Zelda et Berceuse de Zelda dans l'inventaire dès la nouvelle partie "
                         "(plus besoin de passer par la cour du château)"),
    "logic_lens_required": (True, bool, "La logique exige le Monocle de Vérité pour les passages invisibles"),
    "accessibility": ("all", ("all", "beatable"),
                      "all : tous les lieux atteignables ; beatable : seul Ganon doit être battable"),
    "shuffle_ocarinas": (False, bool,
                         "Ocarinas mélangés : l'Ocarina des fées (Saria, au pont) et l'Ocarina du Temps (douves) "
                         "rejoignent le pool, un objet de la seed est donné à leur place ; désactivé : à leur place "
                         "d'origine. Dans le jeu, le deuxième ocarina obtenu est toujours l'Ocarina du Temps"),
}


class SettingsError(ValueError):
    pass


def defaults() -> dict[str, Any]:
    return {k: v[0] for k, v in SETTINGS.items()}


def _coerce(name: str, value: Any) -> Any:
    default, allowed, _ = SETTINGS[name]
    if allowed is bool:
        if isinstance(value, str):
            low = value.lower()
            if low in ("true", "1", "yes", "oui", "on"):
                return True
            if low in ("false", "0", "no", "non", "off"):
                return False
        if isinstance(value, bool):
            return value
        raise SettingsError(f"{name} : booléen attendu, reçu {value!r}")
    if allowed is int:
        try:
            return int(value)
        except (TypeError, ValueError):
            raise SettingsError(f"{name} : entier attendu, reçu {value!r}") from None
    if value not in allowed:
        raise SettingsError(f"{name} : valeur {value!r} invalide (choix : {', '.join(allowed)})")
    return value


def build(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = defaults()
    for name, value in (overrides or {}).items():
        if name.startswith("_"):
            continue
        if name not in SETTINGS:
            raise SettingsError(f"réglage inconnu « {name} » (connus : {', '.join(SETTINGS)})")
        settings[name] = _coerce(name, value)
    limits = {"stones": 3, "medallions": 6, "dungeons": 9, "hearts": 20}
    if settings["bridge"] in limits and not 0 <= settings["bridge_count"] <= limits[settings["bridge"]]:
        raise SettingsError(
            f"bridge_count doit être entre 0 et {limits[settings['bridge']]} pour bridge={settings['bridge']}")
    return settings


def unsupported_by_patcher(settings: dict[str, Any]) -> list[str]:
    return [f"{k}={settings[k]!r}" for k, v in GAME_LOCKED.items() if settings[k] != v]


def load(path: str | Path | None, cli_overrides: list[str] | None = None) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if path:
        with Path(path).open(encoding="utf-8") as fh:
            raw = json.load(fh)
    for entry in cli_overrides or []:
        if "=" not in entry:
            raise SettingsError(f"--set attend nom=valeur, reçu « {entry} »")
        key, value = entry.split("=", 1)
        raw[key.strip()] = value.strip()
    return build(raw)
