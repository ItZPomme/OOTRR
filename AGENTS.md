# AGENTS.md — guide pour les agents IA (et les humains pressés)

Randomizer pour *The Legend of Zelda: Ocarina of Time* — remake Switch 2 (moteur de
*Tears of the Kingdom*). Python 3.10+, dépendances : `zstandard` (et `ainb` pour le menu en jeu). Le générateur
produit un **mod LayeredFS** (fichiers modifiés seulement) que l'on installe dans
l'émulateur Eden (ou un dérivé de Yuzu). Code, commentaires et docs sont en **français**.

Lire ensuite, dans cet ordre :
1. [`README.md`](README.md) — utilisation, réglages ; [`docs/GUIDE.md`](docs/GUIDE.md) pour les joueurs.
2. [`docs/GAME_KNOWLEDGE.md`](docs/GAME_KNOWLEDGE.md) — tout ce qu'on sait du jeu (drapeaux,
   quêtes, scripts, pièges). **À lire avant de toucher au jeu.**
3. [`docs/FORMATS.md`](docs/FORMATS.md) — formats de fichiers et outils de lecture.
4. [`docs/ROADMAP.md`](docs/ROADMAP.md) — travail restant, par priorité.

## Règles

- **Aucun fichier du jeu dans le dépôt** (RomFS, exefs, clés, sauvegardes). Chacun extrait sa
  propre copie ; le chemin est passé avec `--romfs`. `output/` et `saves/` sont ignorés par git.
- Ne jamais déclarer une fonctionnalité « faite » sans test en jeu : le moteur réagit souvent
  autrement que prévu (voir « Pièges » dans GAME_KNOWLEDGE). Distinguer dans les messages et
  la doc : **vérifié dans les fichiers** (outils `verify`, `events`, `lookup`) / **validé en jeu**.
- Toute modification de la logique doit garder les tests verts :
  `python -m unittest discover -s tests` (100 seeds par préréglage ; `OOTRR_TEST_SEEDS=20` pour aller vite).
- Les fichiers de règles sont des données (`ootrr/data/**.json`) ; les règles sont compilées
  depuis des expressions de type Python par `ootrr/rules.py` (jamais `eval`).
- Pour une expérience en jeu, utiliser les options `--test-*` (hors logique) plutôt que
  modifier le générateur, puis installer sous `--mod-name OoTRR-essai`.
- Eden doit être **fermé** pour installer (fichiers verrouillés sinon). Un seul mod OoTRR actif à la fois.

## Commandes utiles

```bash
python -m pip install -r requirements.txt
python -m ootrr --check                                  # valide les données
python -m ootrr --list-settings                          # réglages
python -m ootrr --seed 1234 --romfs ROMFS --install      # génère + construit + installe
python -m unittest discover -s tests                     # tests
python -m ootrr.tools.verify --romfs ROMFS --mod MOD --patch output/..._patch.json
python -m ootrr.tools.events --romfs ROMFS DoorOfTime --entry DoorOfTime_Draw   # lire un script
python -m ootrr.tools.events --romfs ROMFS Dm_Kokiri_0155 --find Item_Ocarina_Fairy
python -m ootrr.tools.lookup --romfs ROMFS flag IsGet.Item_Hookshot             # drapeau de sauvegarde
python -m ootrr.tools.lookup --romfs ROMFS msg EventFlowMsg/Enemy_Event 0001    # message
python -m ootrr.tools.lookup --romfs ROMFS actor Banc/KokiriForest Npc_Kokiri   # acteurs d'une zone
python -m ootrr.tools.saves backup NOM                   # sauvegardes Eden (Eden fermé)
```

`ROMFS` = dossier `romfs` de la **mise à jour** extraite (ex. `.../updates/<version>/romfs`).

## Carte du code

| Chemin | Rôle |
|---|---|
| `ootrr/__main__.py` | Ligne de commande, options de test, `build_mod` (patch JSON -> ModBuilder) |
| `ootrr/settings.py` | Réglages : valeurs, validation, description |
| `ootrr/world.py` | Chargement des données, réglages -> lieux, drapeaux de départ, acteurs retirés, expressions, etc. |
| `ootrr/rules.py` | Compilateur de règles (vocabulaire en tête de fichier) |
| `ootrr/search.py` | Accessibilité enfant / adulte, sphères (l'enfant n'utilise les objets d'adulte qu'après le retour) |
| `ootrr/fill.py` | Placement « assumed fill », récompenses de boss mélangées |
| `ootrr/patch.py` | Résultat -> patch JSON (tout ce que le constructeur doit appliquer) |
| `ootrr/modbuild.py` | Construction du mod : cartes, GameData, scripts, RSDB, archives d'acteurs, messages, modules AINB |
| `ootrr/formats/` | Lecture/écriture : zstd, SARC, BYML, RESTBL, GameData, BFEVFL (scripts), MSBT (messages) |
| `ootrr/tools/` | Outils : vérification, inspection, sauvegardes, mods de test |
| `ootrr/data/` | Objets, règles nommées, régions, coffres, cinématiques |
| `tests/` | Tests de génération et de formats |

## Flux d'une seed

`settings` -> `World` (données + réglages) -> `fill.generate` (placement + vérification
« finissable ») -> `patch.build_patch` (JSON) -> `__main__.build_mod` -> `ModBuilder.build`
(écrit le mod dans un dossier temporaire puis le copie dans Eden).

## Ajouter quelque chose : recettes

- **Un coffre** : entrée dans `ootrr/data/world/chests.json` (hash de l'acteur, région, règle,
  objet d'origine, `event: keep|drop`). Trouver le hash : `tools.inventory` ou `tools.lookup actor`.
- **Un drapeau au départ** : `World.start_flags()` (nom du drapeau GameData -> valeur ;
  `#hash` pour une entrée sans nom connu ; valeur texte pour un Enum).
- **Un objet donné au départ** : lieu déplacé vers `Root` (voir `_start_location_names`) ; le
  constructeur insère une action « ajouter à l'inventaire » dans l'introduction.
- **Modifier un script** : `formats/evfl.py` — `replace_strings`, `skip_event_steps`,
  `add_actions`, `insert_flow` (questions, actions, copies d'étapes ; avant un événement ou au
  début d'un point d'entrée), `ensure_actor_member`. Toujours relire le résultat avec `tools.events`.
- **Une condition de présence d'acteur** : `World.actor_changes()` -> `{"Presence": {...}}`.
- **Une condition calculée** (« a les 3 pierres », « N médaillons ») : `World.bool_exps()`
  (expressions postfixes, voir `gamedata.encode_bool_exp`).
- **Changer une chaîne d'un module de logique AINB** : `World.logic_patches()` — même longueur obligatoire.
