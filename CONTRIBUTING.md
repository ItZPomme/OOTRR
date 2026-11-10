# Contribuer

## Mise en place

1. Python 3.10 ou plus récent, puis `python -m pip install -r requirements.txt`.
2. Extraire **sa propre copie** du jeu (mise à jour comprise) : on a besoin du dossier `romfs` de
   la mise à jour (`.../updates/<version>/romfs`). Ne jamais l'ajouter au dépôt.
3. Émulateur : Eden (ou dérivé de Yuzu). Les mods vont dans
   `%APPDATA%\eden\load\0400486024DEC000\<nom du mod>`.
4. Vérifier : `python -m ootrr --check` puis `python -m unittest discover -s tests`.

## Façon de travailler

- Une fonctionnalité en jeu suit toujours le même cycle : chercher dans les fichiers
  (`tools.events`, `tools.lookup`), prototyper avec une option `--test-*`, installer sous
  `--mod-name OoTRR-essai`, **tester en jeu** (nouvelle partie si des drapeaux de départ
  changent), puis intégrer au générateur + tests + doc.
- Consigner chaque découverte dans `docs/GAME_KNOWLEDGE.md` avec son niveau de certitude
  (**[jeu]**, **[fichiers]**, **[hypothèse]**) et mettre `docs/ROADMAP.md` à jour.
- Sauvegarder ses parties avant un test : `python -m ootrr.tools.saves backup <nom>` (Eden fermé).
- Langue du code, des commentaires et des docs : français.

## Avant un commit

- `python -m unittest discover -s tests` vert.
- `python -m ootrr --check` OK.
- Aucun fichier du jeu, aucune sauvegarde, aucun chemin personnel.
