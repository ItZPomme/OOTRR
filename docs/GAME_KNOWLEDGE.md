# Ce qu'on sait du jeu

Connaissances accumulées en développant le randomizer (version de jeu : mise à jour 131072,
fichiers `*.Product.110/111`). Légende : **[jeu]** validé en jeu, **[fichiers]** constaté dans
les fichiers mais pas encore testé, **[hypothèse]** à confirmer.

## Généralités

- Moteur de *Tears of the Kingdom* : cartes BYML, scripts BFEVFL, modules de logique AINB,
  tables RSDB, sauvegarde GameData (drapeaux identifiés par MurmurHash3 de leur nom).
- Titre : `0400486024DEC000`. Mods : `<émulateur>\load\0400486024DEC000\<mod>\romfs\...` (`%APPDATA%\fritchii` pour Fritchii récent, `%APPDATA%\eden` pour Eden).
- Les réponses des **questions de script** valent **0 = oui, 1 = non** (ex. le script des Peste
  Mojo : « a le sac moyen ? » -> 0 = vend le grand sac). Un cas qui termine le script est **omis**
  du tableau de cas (jamais de saut vers 0xFFFF) **[jeu]**.
- Les drapeaux GameData (`DefaultValue`) ne s'appliquent qu'à une **nouvelle partie** **[jeu]**.

## Objets

- N'importe quel objet dans n'importe quel coffre fonctionne (`Dynamic.Drop__DropActor`) **[jeu]**.
- Les améliorations ne rétrogradent jamais (grappin après super grappin) **[jeu]**, **sauf
  l'ocarina** : recevoir l'Ocarina des fées remplace l'Ocarina du Temps **[jeu]** (garde ajoutée
  dans le script de Saria).
- Les bombes demandent le sac **et** le bracelet goron **[jeu]** (`has_explosives`).
- Le « GetEventName » d'un coffre peut appartenir à l'objet (épée Kokiri : l'épée apparaît dans
  le dos) -> `event: drop` quand l'objet change ; ou au lieu (Dampé, Ruto) -> `keep`.
- Coffres `Obj_TBox_A_06` : contenu conditionnel (`Drop__CheckActor` / `Drop__DropActor_Substitute`).
- **Objets au sol sur mesure** : copie de `Obj_Heart_Container` (archive renommée) + lignes RSDB
  (`ActorInfo.ActorName` = objet donné, `PouchActorInfo` copiée de l'objet). Fonctionne pour les
  objets simples, les chants, les quarts de cœur **[jeu]**. Modèle et animation copiés de l'objet,
  paramètres d'inventaire (`PouchContentRef`) aussi.
- **Un ocarina donné par un objet au sol n'est pas jouable**, même avec ses paramètres
  d'inventaire **[jeu]**. Seuls les « dons » de script (`PouchSystemActor.EventTriggerAddOrRemovePouchContent`)
  et les coffres le rendent jouable. Les équipements (arc, bottes) ne s'ajoutent pas non plus au sol (avant la copie des paramètres d'inventaire ; non retesté).
- Don silencieux au départ : action `EventTriggerAddOrRemovePouchContent` (modèle : `Dm_Kokiri_0155`,
  `IsGetEvent = 0`) insérée dans `OpeningEvent:Opening_Introduction` **[jeu]**.
- Les drapeaux `IsGet.<objet>` sont posés quand on obtient l'objet ; les mettre à vrai **ne**
  supprime **pas** l'animation de première obtention des consommables **[jeu]** (décidée par le moteur).
- Inventaire : bloc binaire de la sauvegarde, pas de drapeaux par objet (sauf `PouchData.<objet>.StockNum`).
- Valeurs utiles : `PlayerStatus.MaxLife` (quarts de cœur, 12 = 3 cœurs), `PlayerStatus.Life`,
  `PouchData.Item_Token_Gold.StockNum` (jetons de Skulltula d'or).

## Boutiques, Peste Mojo, Skulltulas

- Article de boutique = acteur `Shop_*` ; `ActorInfo.ActorName` = objet vendu ; prix dans
  `PriceParam` de l'archive. Copie d'un article = autre objet vendu **[jeu]** ; `ActorGameDataSetting`
  = `NoRespawn` pour une vente unique **[jeu]**.
- Peste Mojo vendeurs (`Enemy_Scrub_Business`) : `Dynamic.ScrubBusiness_ShopItemActorName0..2`,
  `TalkEventName`. Le script `Enemy_Scrub_Business_Common` compare le nom à une liste fixe.
  Méthode **[jeu]** : script « sac de bâtons » pour toutes, questions insérées (« objet = X ? »)
  qui mènent à la vente unique `SimpleShopSub_Scrub_Business_OneTime` (prix entier, message).
- Skulltula d'or : `Dynamic.Drop__DropActor` remplace le jeton **[jeu]** ; il faut un objet
  ramassable (copie de `Obj_Token_Gold` ou du réceptacle). Tant que l'objet n'est pas ramassé, la
  Skulltula réapparaît.

## Messages (Mals)

- `Mals/<langue>.Product.110.sarc.zs` : 16 langues, MSBT en **UTF-8** (octet 0x0C = 0).
- Balises : `0x0E` + groupe, type, taille, données. Ex. couleur `[0:3:0000]`…`[0:3:ffff]`,
  prix `[2:12:…SimpleShop_Price…]` (valeur GameData insérée), pause `[5:0:]`.
- Les réponses d'un dialogue (`ChoiceLabel1 = N`) sont le message nommé `000N` **du même fichier**.
- Noms d'objets : `ActorMsg/PouchContent.msbt`, étiquettes `<objet>_Name`.
- On peut ajouter des messages (`msbt.add_messages`, réécriture identique vérifiée).

## Forêt Kokiri

- Bloqueurs : `Npc_Kokiri_007_Child` (sortie vers le pont), `Npc_Kokiri_Mido_Child` (Arbre Mojo),
  murs invisibles `FldObj_AirWall_Player_GenerateNavMesh` présents selon
  `KokiriForest_Npc_Kokiri_007_Child_Blocker_00` / `KokiriForest_Npc_Kokiri_Mido_Child_Blocker`
  (vrais au départ) **[jeu]**.
- Interruptions : Kokiri du toit = demande d'événement `KokiriForest_Kokiri_011_StopInFrontOfShop_00`
  (rendue absente) **[jeu]** ; tutoriel du bouclier = sous-séquence appelée par la vendeuse après
  l'achat (`Npc_Kokiri_001_Shop_Child` -> `Npc_Kokiri_010_Child:DekuShield_TutorialTalk`) **[jeu]**.
- Saria au pont (`Dm_Kokiri_0155`) donne l'Ocarina des fées par une action d'inventaire.

## Porte du Temps, épée, voyage dans le temps

- Quête `DoorOfTime` = Enum GameData sans nom connu, hash `931730378` (NotReady, Ready, Step01…
  Step06, Complete). La porte (module `Market_Common_f252`) est ouverte si l'étape est **≥ Step06**.
  `Market_Child_TimeTempleDoor_Opened` ne sert qu'à sauter l'animation **[jeu]**.
- Le remake compte **le Rubis Goron et le Saphir Zora** pour la porte (`DoorOfTime_CheckStoneNum`).
- L'ocarina des douves (`Obj_Ocarina_Time_A_01`, module `HyruleField_Child_Prefab_91f9`) n'existe
  qu'à l'étape **= Step04** ; son ramassage lance `DoorOfTime:DoorOfTime_GetOcarinaOfTime`
  (scène `Dm_MelodyGet_Time`). Porte ouverte : module modifié pour Step06 + présence « 3 pierres »
  + dons directs dans le script **[jeu]**.
- Rauru : le premier tirage de l'épée vérifie `HavePlayedEvent.Dm_TimeTemple_0040` ; marqué comme
  vu -> voyage direct, la récompense de la poche de Link est donnée au départ **[jeu]**.
- Retour enfant : `Market_Adult_Prefab_89da` exige `SageOfForest_IsCompleted_Exp` (Temple de la
  Forêt fini). Remplacé par une expression toujours vraie si `free_time_travel` **[jeu]**.

## Récompenses de boss

- Données par des scènes qui nomment l'objet : `Dm_Kokiri_0130` (émeraude), `Dm_DeathMtTrail_0025`
  (rubis), `Dm_ZoraFountain_0030` + `Dm_InsideJabu_Jabu_0030` (saphir), `Dm_Awake_<X>_Get`
  (médaillons, aussi en version `.110`). Remplacer le nom dans ces scènes change la récompense
  (validé pour l'émeraude) **[jeu]**.

## Pont arc-en-ciel

- Module `GanonCastle_Level_Field_00_Prefab_14ba` : expressions `Defeat_Ganon_IsAfter_Ready_Exp`
  et `Defeat_Ganon_IsAfter_Step01_Exp` ; la scène `GanonCastle_Adult_Field_Rainbow` (script
  `Defeat_Ganon`) fait avancer la quête. Les deux noms sont remplacés (même longueur) par des
  expressions du randomizer **[fichiers]** — pas encore testé en jeu.

## Expressions booléennes (GameData `BoolExp`)

Notation postfixe : `0` drapeau Bool, `10` autre expression, `1`/`12` Enum (égal / à partir de)
suivi de `2` valeur, `15` entier + `16` constante (égalité), `3` ET, `4` OU, `5` NON. On peut en
ajouter (non sauvegardées, la taille de sauvegarde ne change pas) **[jeu]**.

## Cinématiques

- `HavePlayedEvent.<scène>` vrai au départ -> la scène est considérée vue **[jeu]**.
- Certaines scènes sont jouées sans vérification (intro : `OpeningEvent` -> `Dm_Kokiri_0000/0030`) :
  on saute l'étape qui les joue (`skip_event_steps`) **[jeu]**.
- Liste générée : `ootrr/data/cutscenes.json` (`python -m ootrr.tools.cutscenes`).

## Pièges rencontrés

- Changer un acteur de type par `Gyaml` (cœur -> coffre) : rien n'apparaît. Un coffre copié dans
  une carte statique (`Obj_TBox_A_01_NoBake`) n'a pas pu s'ouvrir.
- Une copie du réceptacle qui donne des PV (quart de cœur sur mesure) bloque la partie.
- Un acteur dans un groupe de logique (AiGroups) peut ignorer sa condition de présence selon le
  module ; tester.
- PowerShell 5 ajoute un BOM UTF-8 avec `Set-Content -Encoding utf8` : casse les JSON.
- Chemins Windows trop longs : construire dans un dossier temporaire puis copier.

## Pistes non abouties

- Menu de réglages **dans le jeu** : fait avec du code natif (exlaunch), voir `native/README.md`.
- **Cartes et boussoles « au départ » (`maps_compasses=start_with`) : ne fonctionne pas** (validé
  en jeu, 2026-11-10, avec le mod Python seed 1234 et avec le menu natif). Ni le drapeau
  `DungeonInfo.<donjon>.IsGetMap` / `IsGetCompass` à 1 dès la nouvelle partie (valeur par défaut ou
  écrit au départ, relu à 1 dans la sauvegarde et à l'entrée du donjon), ni en plus l'appel des
  fonctions du nœud `OneShotDungeonGetMap` (`0x3282fe0` / `0x3283060` : drapeau + objet
  `Item_Dungeon_Map` / `Item_Dungeon_Compass`) n'affichent la carte. La scène du coffre
  (`InsideTheDekuTree_GetMap`, événement de `GameSystemActor` avec `EventGetDungeonMap`) fait
  donc autre chose : piste à suivre (comparer une sauvegarde avant / après un vrai coffre de carte).
