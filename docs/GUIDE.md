# Guide d'installation et d'utilisation

Ce guide s'adresse à quelqu'un qui veut **jouer** au randomizer, sans connaître le code. Pour contribuer,
voir [`AGENTS.md`](../AGENTS.md) et [`CONTRIBUTING.md`](../CONTRIBUTING.md).

Le randomizer existe sous deux formes :

| | Menu dans le jeu (recommandé) | Mod généré sur PC |
|---|---|---|
| Où choisir les réglages | Dans le jeu, après « Nouvelle partie » | En ligne de commande, avant de générer |
| Nouvelle seed | À chaque nouvelle partie, sans rien réinstaller | Une installation par seed |
| Fonctions | Toutes (boutiques, Peste Mojo, départ adulte…) | Pas de boutiques mélangées |
| Spoiler log | `ootrr.tools.ingame_spoiler` (relit la sauvegarde) | Écrit avec la seed |
| À installer en plus | Rien avec une release (module natif fourni) ; devkitPro depuis les sources | Rien |

---

## 1. Ce qu'il faut

1. **Ta propre copie** du jeu *The Legend of Zelda: Ocarina of Time* (Switch 2) **et de sa mise à jour**
   (version 131072, appelée « 2.0.0 » dans le code). Aucun fichier du jeu n'est fourni ici.
2. Un émulateur dérivé de Yuzu : **Eden** ou **Fritchii**, avec tes propres clés.
3. **Python 3.10 ou plus récent** (Windows : cocher « Add python.exe to PATH » à l'installation).
4. Le randomizer :
   - **Recommandé** : la dernière **release** GitHub (onglet *Releases* du dépôt). Télécharge le code
     source (*Source code (zip)*) **et** le fichier `subsdk9` (module natif déjà compilé) de la **même**
     release, puis décompresse le code source et mets `subsdk9` dans son dossier.
   - Ou les sources à jour (bouton « Code » -> « Download ZIP », ou `git clone`) : il faut alors compiler le
     module natif avec **devkitPro** (devkitA64 + libnx, installé dans `C:\devkitPro`, composant
     « Switch development » de l'installateur Windows).

Le module `subsdk9` d'une release ne fonctionne qu'avec le code source de **cette** release (il contient la
logique et les réglages du menu de cette version) : ne mélange pas les versions.

## 1 bis. Récupérer ton jeu

Le randomizer ne contient **aucun fichier du jeu** et n'en distribue aucun : chaque joueur construit le mod à
partir de **sa propre copie** du jeu. Il te faut, depuis **ta** console et **ton** jeu acheté :

- le jeu et sa **mise à jour** (version 131072 / 2.0.0), copiés avec un outil de sauvegarde (*dump*) pour
  console ;
- les **clés** de ta console (`prod.keys`, `title.keys`), placées dans l'émulateur (voir sa documentation).

Installe ensuite le jeu **et** sa mise à jour dans l'émulateur (*Fichier* -> *Installer des fichiers dans la
NAND*), puis vérifie qu'il démarre normalement avant d'aller plus loin.

## 2. Extraire la RomFS de la mise à jour

Le randomizer lit les fichiers du jeu dans la **RomFS de la mise à jour** (pas celle du jeu de base).
Avec Eden / Fritchii : clic droit sur le jeu -> *Dump RomFS* (ou *Extract*), en choisissant la mise à jour,
ou un outil d'extraction de ton choix. Tu dois obtenir un dossier qui contient `Banc`, `Event`, `Pack`,
`GameData`, etc., par exemple :

```
D:\dumpnup\The Legend of Zelda Ocarina of Time\updates\131072\romfs
```

C'est ce chemin qu'on appelle **ROMFS** dans la suite (à mettre entre guillemets s'il contient des espaces).

## 3. Installer les dépendances Python

Ouvre un terminal dans le dossier du dépôt, puis :

```bash
python -m pip install -r requirements.txt
```

Vérifie que tout est en place :

```bash
python -m ootrr --check
```

## 4. Où le mod est installé

`--install` copie le mod dans `<émulateur>\load\0400486024DEC000\<nom du mod>` :

- `%APPDATA%\fritchii` s'il existe (Fritchii), sinon `%APPDATA%\eden` (Eden) ;
- pour un autre dossier, définir la variable d'environnement `OOTRR_EMU_DIR` (dossier qui contient `load`).

Règles à respecter :

- **L'émulateur doit être fermé** pendant l'installation (sinon des fichiers restent verrouillés et le mod
  est installé à moitié).
- **Un seul mod OoTRR actif à la fois** : dans l'émulateur, clic droit sur le jeu -> *Propriétés* ->
  *Add-Ons*, ne cocher que `OoTRR-menu` **ou** `OoTRR` (désactiver `OoTRR-essai`, `OoTRR-options`,
  `OoTRR-native`… s'ils existent).

---

## 5. Menu dans le jeu (recommandé)

### Installer

Émulateur **fermé**, dans un terminal ouvert dans le dossier du randomizer :

- avec une **release** (module natif fourni, pas besoin de devkitPro) :

  ```bash
  python -m ootrr.tools.menutest --romfs "ROMFS" --native subsdk9 --install
  ```

- depuis les **sources** (compile le module natif avec devkitPro) :

  ```bash
  python -m ootrr.tools.menutest --romfs "ROMFS" --install
  ```

La commande prépare les fichiers du jeu modifiés à partir de **ta** RomFS et installe le tout sous le nom
`OoTRR-menu`. Compte quelques minutes. À refaire seulement quand tu changes de version du randomizer.
Ensuite, dans l'émulateur : clic droit sur le jeu -> *Propriétés* -> *Add-Ons*, coche `OoTRR-menu`.

### Jouer

1. Lance le jeu, choisis **Nouvelle partie**.
2. Le menu du randomizer s'ouvre (3 pages). Change les réglages avec la croix directionnelle.
3. Passe à la page suivante avec le bouton **Next Page** en bas de la page (A). **B** revient à la page
   précédente (depuis la page 1 : au menu principal). Sur la dernière page, **Start the Game** mène à la
   confirmation habituelle.
4. La seed est générée au début de la partie. Elle est enregistrée dans la sauvegarde : recharger la partie
   redonne exactement la même répartition des objets.

La seed affichée dans la description de « Manual Seed » est celle qui sera utilisée. Active **Manual Seed**
pour taper une seed au clavier au lancement (même seed + mêmes réglages = même partie).

### Les réglages du menu

**Page 1 — le monde**

| Réglage | Effet |
|---|---|
| Manual Seed | Désactivé : seed aléatoire (affichée). Activé : un clavier s'ouvre au lancement pour la saisir. |
| Kokiri Forest | Closed (jeu d'origine), Closed Deku (sortie vers la plaine ouverte), Open (Arbre Mojo ouvert aussi). |
| Open Door of Time | Porte du Temps ouverte dès le départ. |
| Free Time Travel | L'Épée de légende renvoie Link enfant à tout moment (le remake exige sinon le Temple de la Forêt). |
| Skip Child Zelda | Lettre et Berceuse de Zelda au départ ; la quête du château est finie (le cycle jour / nuit démarre). |
| Rainbow Bridge | Condition du pont vers le château de Ganon : Open, Vanilla, Stones, Medallions, Dungeons, Hearts. Le nombre requis se choisit en haut de la page 2. |
| Starting Age | Child (maison de Link), Adult (Temple du Temps, Épée de légende donnée, porte ouverte et voyage libre imposés) ou Random. |
| Start With Consumables | Petits sacs de bâtons et de noix Mojo pleins (10 et 20). |

**Page 2 — ce qui est mélangé**

En haut de la page, selon la condition du pont choisie page 1 : Stones Required (1–3), Medallions Required
(1–6), Rewards Required (1–9), ou Hearts Required (3 ou 12) + Extra Hearts (+0 à +8).

| Réglage | Effet |
|---|---|
| Dungeon Rewards | Pierres et médaillons mélangés entre les boss et la poche de Link. |
| Heart Pieces | Quarts de cœur au sol (Freestanding), et aussi réceptacles des boss (All). |
| Gold Skulltulas | Les Skulltulas d'or lâchent un objet de la seed (Overworld : hors donjons ; All : toutes). |
| Maps and Compasses | À leur place, données au départ, ou retirées. |
| Shuffle Ocarinas | Saria et les douves donnent un objet de la seed ; le 2e ocarina obtenu est l'Ocarina du Temps. |
| Lens Required | La logique exige le Monocle de Vérité pour les passages invisibles. |

**Page 3 — boutiques, Peste Mojo, chants et cadeaux**

| Réglage | Effet |
|---|---|
| Shops | 0 à 4 articles par boutique (8 boutiques) vendent un objet de la seed, une fois. |
| Shop Prices | Vanilla (prix de l'article remplacé, 99 max), Affordable (10), Random (0 à 95). |
| Deku Scrubs | Les 5 Peste Mojo qui vendent un objet unique vendent un objet de la seed. |
| Deku Scrub Prices | Vanilla (40), Affordable (10), Random (0 à 95). |
| Songs | Vanilla (chants à leur place), Shuffle (mélangés entre les 12 emplacements de chants), Random (les emplacements de chants rejoignent le pool : un chant peut être dans un coffre, et un PNJ peut donner n'importe quel objet). |
| Gifts | Récompenses de mini-jeux (tirs, bowling, tir à cheval, plongée, pêche), Anju, Darunia, carte Gerudo, Flèches de lumière et Grandes Fées donnent un objet de la seed (nouveau, pas encore validé en jeu). |

Toujours actif dans le menu : les cinématiques sans effet sur la partie sont passées.

### Voir le spoiler log de ta partie

Sans rien construire : l'outil relit la seed et les réglages dans la sauvegarde la plus récente.

```bash
python -m ootrr.tools.ingame_spoiler --romfs "ROMFS"
```

- `--slot 2` : un emplacement de sauvegarde précis ;
- avant de jouer, avec la seed affichée dans le menu et les réglages choisis :
  `python -m ootrr.tools.ingame_spoiler --seed 727557 --set shuffle_shops=4 --set starting_age=adult`
  (noms des réglages : `python -m ootrr --list-settings`).

Le spoiler est écrit dans `output\OoTRR_menu_<seed>_<hash>_spoiler.txt` : départ, objets requis, parcours par
sphères et contenu de chaque emplacement.

---

## 6. Mod généré sur PC (sans menu)

Une seed = un mod. Les réglages se donnent en ligne de commande :

```bash
python -m ootrr --seed 1234 --romfs "ROMFS" --install --set open_forest=open --set shuffle_hearts=all
```

- `--set nom=valeur` (répétable) ou `--settings fichier.json` (modèle : `settings.example.json`) ;
- `python -m ootrr --list-settings` liste tous les réglages et leurs valeurs ;
- le mod est installé sous `OoTRR` ; le spoiler et le patch sont dans `output\` ;
- sans `--romfs`, seule la seed est générée (spoiler + patch), sans mod.

Les boutiques mélangées ne sont disponibles qu'avec le menu dans le jeu.

---

## 7. Sauvegardes

Les parties sont dans les sauvegardes de l'émulateur. Pour garder une copie (émulateur fermé) :

```bash
python -m ootrr.tools.saves backup avant_gohma
python -m ootrr.tools.saves list
python -m ootrr.tools.saves restore avant_gohma
```

Quand le mod change (mise à jour du dépôt), une ancienne partie peut être régénérée autrement au chargement :
commence une nouvelle partie après chaque mise à jour.

## 8. En cas de problème

- **Chargement sans fin ou plantage** : ferme l'émulateur et regarde la fin du journal
  `%APPDATA%\fritchii\log\eden_log.txt` (ou `%APPDATA%\eden\log\…`). Les lignes `OoTRR:` viennent du module
  natif (seed, réglages lus, objets donnés). Joins ce fichier quand tu signales un problème, avec la seed et
  les réglages.
- **Le menu n'apparaît pas après « Nouvelle partie »** : vérifie que `OoTRR-menu` est le seul mod OoTRR coché
  et qu'il contient bien `exefs\subsdk9` (sinon la compilation a échoué : relance `menutest` et lis l'erreur).
- **« devkitPro absent »** : tu installes depuis une release : ajoute `--native subsdk9` (fichier `subsdk9` de la même release, dans le dossier du randomizer).
- **« compilation du module natif impossible »** : devkitPro doit être dans `C:\devkitPro` avec devkitA64.
- **L'installation ne change rien** : l'émulateur était ouvert pendant l'installation ; ferme-le et relance la
  commande.

## 9. État et limites

Fonctions **validées en jeu** : coffres mélangés, cœurs au sol, Skulltulas d'or, Peste Mojo, boutiques
(boutique Kokiri), récompenses des boss (poche de Link), forêt ouverte, Porte du Temps, voyage libre, pont
(ouvert), cartes et boussoles au départ, objets de Saria mélangés, consommables au départ.

Fonctions **pas encore validées en jeu** (retours bienvenus) : départ adulte, cycle
jour / nuit avec « Skip Child Zelda », bombes d'un coffre sans sac (rubis à la place), garde de l'épée Kokiri,
Ocarina du Temps mélangé (douves), chants mélangés, prix aléatoires élevés des Peste Mojo, titre du bouton « Next Page ».

Non mélangés : PNJ (sauf Saria et les chants), petites clés, clés du boss, coffres des mini-jeux. Travail restant :
[`ROADMAP.md`](ROADMAP.md).
