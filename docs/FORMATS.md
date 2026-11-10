# Formats de fichiers

Tous les lecteurs/écrivains sont dans `ootrr/formats/` et réécrivent les fichiers d'origine
**à l'identique** quand rien ne change (vérifié pour BYML, RESTBL, RELT des BFEVFL, MSBT).

| Format | Fichiers | Module | Notes |
|---|---|---|---|
| Zstandard + dictionnaires | `*.zs` | `zs.py` | dictionnaires dans `Pack/ZsDic.pack.zs` (zs, bcett.byml, pack, bkprb) |
| SARC | `Pack/**/*.pack.zs`, `Mals/*.sarc.zs` | `sarc.py` | l'écrivain garde l'alignement de chaque fichier |
| BYML v7 | cartes `Banc/**`, `GameData`, `RSDB`, paramètres `*.bgyml` | `byml.py` | types U32/I64/U64/F64 conservés ; sous-arbres identiques dédupliqués |
| RESTBL | `System/Resource/ResourceSizeTable*.rsizetable.zs` | `restbl.py` | taille réservée par fichier ; carte = taille décompressée + 292 |
| GameData | `GameData/GameDataList*.byml.zs` | `gamedata.py` | MurmurHash3 32 bits du nom ; `#hash` pour un nom inconnu ; expressions |
| BFEVFL | `Event/EventFlow/*.bfevfl.zs` | `evfl.py` | voir ci-dessous |
| MSBT | dans `Mals/<langue>.*.sarc.zs` | `msbt.py` | UTF-8 ; LBL1 (hash ×0x492) + TXT2 |
| AINB | `Logic/*.logic.module.ainb` | `modbuild._write_logic` | non compressé ; seul le remplacement de chaînes de même longueur est géré |

## BFEVFL (scripts d'événements)

- En-tête : `0x18` offset de la table RELT, `0x1C` taille ; pointeurs 64 bits absolus.
- RELT : liste de tous les emplacements de pointeurs (une section couvrant le fichier). Toute
  modification qui ajoute des données reconstruit RELT (`evfl.build_relt`).
- Flowchart (« EVFL ») : `+0x10` nombres (acteurs, actions, questions, événements, entrées),
  `+0x28` acteurs, `+0x30` événements, `+0x38` dictionnaire des entrées, `+0x40` entrées.
- Acteur 0x38 : nom, nom secondaire, argument, actions (tableau de pointeurs de texte),
  questions, paramètres ; `+0x30` nb d'actions, `+0x32` nb de questions.
- Événement 0x30 : nom, `+8` type (0 action, 1 question, 2 fork, 3 join, 4 sous-séquence),
  `+0x0A` suivant (ou nb de cas), `+0x0C` acteur, `+0x0E` action/question, `+0x10` paramètres,
  `+0x18` cas (question) ou script de la sous-séquence, `+0x20` point d'entrée de la sous-séquence.
- Cas d'une question : 8 octets (`u32` valeur, `u16` événement). 0 = oui.
- Entrée 0x20 : `+0x1C` premier événement.
- Paramètres : conteneur (type 1) + dictionnaire « DIC » + valeurs ; textes souvent stockés
  juste après leur valeur.
- Pour ajouter des étapes sans décaler le fichier, les tableaux d'acteurs et d'événements sont
  **recopiés en fin de fichier** avec les nouveaux éléments (les indices existants ne changent pas).

Outil : `python -m ootrr.tools.events --romfs ROMFS <script> [--entry E | --find TEXTE]`.

## Cartes (Banc)

`Banc/<Zone>/<Zone>_{Child,Adult}_{Dynamic,Static}.bcett.byml.zs` : `Actors` (Gyaml, Hash,
SRTHash, Translate, Rotate, Dynamic, Presence, Links, Phive), `AiGroups` (modules de logique et
leurs acteurs), `FarDeleteGroups`, `SimultaneousGroups`, `Rails`. Un même coffre a le même hash
dans les cartes enfant et adulte.
