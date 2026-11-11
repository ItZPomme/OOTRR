# OoT Remake Randomizer

Randomizer pour le remake d'*Ocarina of Time* (Switch 2), construit sur les
principes d'OoT Randomizer : graphe de régions, logique enfant / adulte,
placement « assumed fill » qui garantit des seeds finissables, spoiler log par
sphères. Il produit un **mod LayeredFS** (seulement les fichiers modifiés) :
les fichiers du jeu d'origine ne sont jamais touchés et ne sont pas dans ce dépôt.

Contributeurs et agents IA : commencer par [`AGENTS.md`](AGENTS.md), puis
[`docs/GAME_KNOWLEDGE.md`](docs/GAME_KNOWLEDGE.md), [`docs/FORMATS.md`](docs/FORMATS.md),
[`docs/ROADMAP.md`](docs/ROADMAP.md) et [`CONTRIBUTING.md`](CONTRIBUTING.md).

## État

- Tous les coffres sont mélangés (114, ou 134 avec les cartes et boussoles), sauf les petites
  clés, les clés du boss, les coffres des mini-jeux et ceux du Boss Rush.
- Quarts de cœur au sol, réceptacles des boss, pierres et médaillons peuvent être mélangés.
- Forêt ouverte, Porte du Temps ouverte, voyage dans le temps libre, conditions du pont,
  objets de départ, nombreuses cinématiques sautées.
- En cours : Peste Mojo vendeurs, Skulltulas, boutiques (mécanismes validés, logique à écrire),
  questions de réglage en jeu.

## Utilisation

Python 3.10+, puis une fois : `python -m pip install -r requirements.txt` (installe `zstandard`).
Il faut la RomFS extraite de **ta propre copie** du jeu (celle de la mise à jour :
`updates\<version>\romfs`).

```bash
python -m ootrr --seed 1234 --romfs "CHEMIN\VERS\updates\<version>\romfs" --install
```

- `--install` copie le mod dans `<émulateur>\load\0400486024DEC000\OoTRR` (émulateur fermé). Dossier détecté : `%APPDATA%\fritchii` (Fritchii récent), sinon `%APPDATA%\eden` ; forcer avec la variable `OOTRR_EMU_DIR`.
- `output\OoTRR_<seed>_<hash>_spoiler.txt` : objets requis, parcours par sphères, contenu de chaque lieu.
- `output\OoTRR_<seed>_<hash>_patch.json` : tout ce que le mod applique.
- Sans `--romfs`, seule la seed est générée (spoiler + patch).
- Réglages : `--set nom=valeur` (répétable) ou `--settings fichier.json` (voir `settings.example.json`).

## Réglages

`python -m ootrr --list-settings` donne la liste à jour.

| Réglage | Valeurs | Effet |
|---|---|---|
| `open_forest` | `closed`, `closed_deku`, `open`, `ask` | Kokiri bloqueurs retirés, murs invisibles désactivés ; `ask` = question au début de la partie (prototype) |
| `open_door_of_time` | oui / non | Porte ouverte ; lettre et berceuse au départ ; l'Ocarina du Temps reste dans les douves (visible avec les 3 pierres) et donne le Chant du Temps |
| `skip_child_zelda` | oui / non | Lettre et berceuse de Zelda au départ |
| `free_time_travel` | oui (défaut) / non | L'épée renvoie enfant à tout moment (le remake exige le Temple de la Forêt) |
| `bridge`, `bridge_count` | `open`, `vanilla`, `stones`, `medallions`, `dungeons`, `hearts` + nombre | Condition du pont arc-en-ciel |
| `shuffle_rewards` | `vanilla`, `shuffled` | Pierres et médaillons mélangés entre les boss et la poche de Link |
| `shuffle_hearts` | `none`, `freestanding`, `all` | Quarts de cœur au sol (et réceptacles des boss) mélangés |
| `maps_compasses` | `vanilla`, `start_with`, `shuffle`, `removed` | Cartes et boussoles |
| `skip_cutscenes` | `none`, `safe` | Cinématiques sans effet marquées comme vues, Rauru et Saria sautés, Kokiri qui interrompent désactivés |
| `logic_lens_required`, `accessibility` | | Options de logique |

Options de test (hors logique, pour expérimenter en jeu) : `--test-chest`, `--test-pickup`,
`--test-drop`, `--test-scrub`, `--test-set`, `--test-flag`, `--test-give OBJET` (inventaire de
départ) et `--test-start BANC=POINT` (ex. `HyruleField_Child=HyruleField_FrontOfMarket`).

## Outils

```bash
python -m ootrr --check                      # valide les données
python -m unittest discover -s tests         # tests (100 seeds par préréglage)
python -m ootrr.tools.verify --romfs ... --mod ... --patch ...   # vérifie un mod installé
python -m ootrr.tools.events --romfs ... DoorOfTime --entry DoorOfTime_Draw   # lit un script du jeu
python -m ootrr.tools.lookup --romfs ... flag IsGet.Item_Hookshot             # drapeaux, messages, acteurs, tables
python -m ootrr.tools.inventory --romfs ... --out inventaire     # liste tous les coffres du jeu
python -m ootrr.tools.roundtrip --romfs ...  # vérifie la réécriture BYML sur toutes les cartes
python -m ootrr.tools.saves backup <nom>     # sauvegardes Eden (aussi restore, list)
```

## Structure

| Chemin | Rôle |
|---|---|
| `ootrr/data/` | Objets, règles nommées, régions, coffres, cinématiques |
| `ootrr/rules.py`, `search.py`, `fill.py` | Règles, accessibilité, placement |
| `ootrr/world.py`, `settings.py` | Données du monde et réglages -> ce que le mod doit faire |
| `ootrr/spoiler.py`, `patch.py` | Spoiler log, patch JSON |
| `ootrr/modbuild.py` | Construction et installation du mod |
| `ootrr/formats/` | Zstd, SARC, BYML, RESTBL, GameData, scripts BFEVFL, messages MSBT |
| `ootrr/tools/` | Vérification, inspection, sauvegardes, mods de test |
| `docs/` | Connaissances du jeu, formats, travail restant |

## Limites actuelles

- Règles marquées `prudent` dans `chests.json` : l'emplacement exact du coffre n'est pas confirmé.
- Non mélangés : PNJ, chants, fées, petites clés, coffres à contenu conditionnel, coffres des
  mini-jeux et 4 coffres à événement d'histoire.
- Améliorations pas encore progressives dans les coffres.
- Le pont arc-en-ciel avec conditions n'a pas encore été testé en jeu.
- Voir [`docs/ROADMAP.md`](docs/ROADMAP.md).
