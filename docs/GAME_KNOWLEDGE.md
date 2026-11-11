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
- **Cœurs au sol, menu natif [jeu]** (2026-11-11) : l'acteur devient un jeton `OoTRR_Lnnnn` (copie du
  cœur d'origine, `ActorInfo.ActorName` = le jeton lui-même, `PouchActorInfo` copiée du cœur). Au
  ramassage, la séquence « objet obtenu » cherche `<objet>_GetMessage` / `_GetCaption` dans
  `ActorMsg/PouchContent` : **un texte introuvable bloque la partie** (le cœur tourne sans fin) ; les
  textes du jeton sont redirigés vers ceux de l'objet de la seed, puis l'ajout (`0x110d570`) aussi.
- **Modèle d'un objet au sol choisi en jeu [jeu]** (2026-11-11) : les composants d'un acteur (`ModelInfoRef`,
  `AnimationRef`…) sont cherchés par leur chemin dans son archive SARC (`0x32ade0`, chemin -> numéro de
  fichier), pas par le chargeur de ressources `0xa57350`. Le jeton référence `Component/ModelInfo/<jeton>…` ;
  la recherche est redirigée vers le `ModelInfo` / `AnimationParam` de l'objet, copiés dans l'archive du
  jeton sous leur chemin d'origine. Chants : modèle de rubis sans animation, gardent celui du cœur.
- Les rubis de coffre `TBox_Rupee_*` n'ont pas ces textes (les `Obj_Rupee_*` si). Les rubis ne passent
  pas par l'inventaire : l'ajout est sans effet, l'argent est l'entier `PlayerStatus.CurrentRupee` **[jeu]**.
- Inventaire : bloc binaire de la sauvegarde, pas de drapeaux par objet (sauf `PouchData.<objet>.StockNum`).
- Valeurs utiles : `PlayerStatus.MaxLife` (quarts de cœur, 12 = 3 cœurs), `PlayerStatus.Life`,
  `PouchData.Item_Token_Gold.StockNum` (jetons de Skulltula d'or).

## Boutiques, Peste Mojo, Skulltulas

- **Boutiques mélangées (menu natif) [jeu]** (2026-11-11) : voir native/README.md (« Boutiques »).
  Liste des articles d'un marchand : `Component/ShopParam/…` dans son archive, `GoodsList` dans
  l'ordre de `ShopItemIndex` ; `Release` = condition d'apparition (« Coming Soon » : boutique Kokiri
  avant l'Arbre Mojo ; « épuisé » : bombes du bazar avant la pierre du feu). Le marchand des Missiles
  n'apparaît qu'après la pierre du feu (présence retirée). Un article doit être dans la liste ET relié
  au marchand (liens `ForSale`, `Reference`) pour être choisi. Le prix vient de la ligne RSDB
  `PouchActorInfo.BuyingPrice`.

- Article de boutique = acteur `Shop_*` ; `ActorInfo.ActorName` = objet vendu ; prix dans
  `PriceParam` de l'archive. Copie d'un article = autre objet vendu **[jeu]** ; `ActorGameDataSetting`
  = `NoRespawn` pour une vente unique **[jeu]**.
- Peste Mojo vendeurs (`Enemy_Scrub_Business`) : `Dynamic.ScrubBusiness_ShopItemActorName0..2`,
  `TalkEventName`. Le script `Enemy_Scrub_Business_Common` compare le nom à une liste fixe.
  Méthode **[jeu]** : script « sac de bâtons » pour toutes, questions insérées (« objet = X ? »)
  qui mènent à la vente unique `SimpleShopSub_Scrub_Business_OneTime` (prix entier, message).
- **Peste Mojo mélangées (menu natif) [jeu]** (2026-11-11) : 5 vendeuses d'objet unique (plaine,
  cratère, bâtons forêt/Bois Perdus, noix). L'article doit rester un **vrai objet**
  (`EventScrubBusinessWriteGameDataBancItemName` ignore un nom inconnu) : il sert de marque, une
  question insérée vend le jeton. La plaine vend directement (entrée `Secret`). Nom dans le message :
  balise des boutiques `[2:3 Shop_SelectItemName]` (posée avant la vente), résolue par la recherche
  intérieure `0xa6b060` (pas `0xa6afe0`) où le texte du jeton est redirigé.
- Un quart de cœur ajouté sous un autre nom (jeton) n'est **pas compté** : le module incrémente
  `PouchData.Obj_Heart_Piece.StockNum` (passage à 4 quarts -> réceptacle : non vérifié).
- Skulltula d'or : `Dynamic.Drop__DropActor` remplace le jeton **[jeu]** ; il faut un objet
  ramassable (copie de `Obj_Token_Gold` ou du réceptacle). Tant que l'objet n'est pas ramassé, la
  Skulltula réapparaît.
- Skulltulas d'or mélangées : la Skulltula lâche son jeton `OoTRR_Lnnnn` (copie de `Obj_Token_Gold`),
  modèle, textes et ajout redirigés vers l'objet de la seed — **validé en jeu** (Arbre Mojo). Le jeton
  n'est pas remplacé à la source (`KeepsToken`). Jeton d'or placé dans un coffre : **validé en jeu**.
- Paramètres utiles de `Enemy_Skulltula_Gold` (Dynamic) pour identifier chaque Skulltula :
  `Enemy_Skulltula_Gold_IsMagicBeanSoil` (terre meuble, présence = drapeau `Gimmick_MagicBeanSoil_<zone>`,
  posé quand on lâche des insectes), `Enemy_Skulltula_Gold_Nocturnal` (nuit), `AppearPopOut` +
  `AppearWarpRotOffset` (arbre), une caisse `Obj_BrokenBox_A_*` à la même position, `DefaultDungeonRoomIndex`.
  Règles dans `skulltulas.json` (9 incertaines gardent `no_progression`) : **vérifié dans les fichiers**,
  pas encore validées en jeu une par une.

## Messages (Mals)

- `Mals/<langue>.Product.110.sarc.zs` : 16 langues, MSBT en **UTF-8** (octet 0x0C = 0).
- Balises : `0x0E` + groupe, type, taille, données. Ex. couleur `[0:3:0000]`…`[0:3:ffff]`,
  prix `[2:12:…SimpleShop_Price…]` (valeur GameData insérée), pause `[5:0:]`.
- Les réponses d'un dialogue (`ChoiceLabel1 = N`) sont le message nommé `000N` **du même fichier**.
- Noms d'objets : `ActorMsg/PouchContent.msbt`, étiquettes `<objet>_Name`.
- On peut ajouter des messages (`msbt.add_messages`, réécriture identique vérifiée).

## Forêt Kokiri

- Porte de la maison de Link (`Obj_Kokiri_Door_A_01`, seul acteur de ce type) : elle joue
  `Dm_Kokiri_0045` (découverte de la forêt) en s'ouvrant, sans tenir compte du drapeau « déjà vue ».
  Drapeau `KokiriForest_LinkHouseDoor_Open` vrai au départ : porte ouverte, pas de scène **[jeu]**.
  (Retirer la porte laisse un mur invisible ; vider `OpenEventName` l'empêche de s'ouvrir.)
- Carte de première découverte d'un lieu : `IsVisitLocation.<lieu>` vrai = déjà découvert **[jeu]**.

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
- Menu natif : la porte s'ouvre en posant l'Enum à Step06 au début de la partie (fonction `0x3e0980`) ;
  un crochet sur le changement d'étape de quête (`0x2cf54a0`) empêche tout recul. Le module des douves
  crée l'ocarina « après Step03 » au lieu de « = Step04 », pour servir porte fermée comme ouverte.
  Porte ouverte (On) et porte fermée + douves vides (Off) validés **[jeu]** (2026-11-10) ; ocarina des
  douves avec les 3 pierres pas encore testé avec le menu natif.
- Rauru : le premier tirage de l'épée vérifie `HavePlayedEvent.Dm_TimeTemple_0040` ; marqué comme
  vu -> voyage direct, la récompense de la poche de Link est donnée au départ **[jeu]**.
- Retour enfant : `Market_Adult_Prefab_89da` exige `SageOfForest_IsCompleted_Exp` (Temple de la
  Forêt fini). Remplacé par une expression toujours vraie si `free_time_travel` **[jeu]**.
  Menu natif : le module lit `OoTRR_FreeTimeTravel_Exp` (drapeau sauvegardé `OoTRR.FreeTimeTravel`,
  posé par le menu, OU `SageOfForest_IsCompleted_Exp`) **[jeu]** (2026-11-10).

## Récompenses de boss

- Données par des scènes qui nomment l'objet : `Dm_Kokiri_0130` (émeraude), `Dm_DeathMtTrail_0025`
  (rubis), `Dm_ZoraFountain_0030` + `Dm_InsideJabu_Jabu_0030` (saphir), `Dm_Awake_<X>_Get`
  (médaillons, aussi en version `.110`). Remplacer le nom dans ces scènes change la récompense
  (validé pour l'émeraude) **[jeu]**.
- Menu natif : crochet sur l'ajout à l'inventaire `0x110d570` ; un don d'événement (raison 7) d'une
  récompense d'origine est remplacé par celle de la seed. Validé pour la poche de Link au départ
  (médaillon de lumière -> saphir zora) **[jeu]** (2026-11-10) ; scènes de boss : même mécanisme, non
  testées. Raisons vues : 7 = événement, 8 = équipement de départ (bourse, tuniques).

## Pont arc-en-ciel

- Module `GanonCastle_Level_Field_00_Prefab_14ba` : la scène `GanonCastle_Adult_Field_Rainbow`
  (script `Defeat_Ganon`, fait passer la quête à Step01) se déclenche si `Defeat_Ganon_IsAfter_Ready_Exp`
  ET NON `Defeat_Ganon_IsAfter_Step01_Exp` ; le pont (`Obj_GanonCastle_Bridge_A_01`) n'existe qu'une
  fois la scène vue (`HavePlayedEvent`). **Remplacer seulement « Ready »** par la condition du
  randomizer : remplacer les deux empêche la scène, donc le pont **[jeu]** (menu natif, condition
  « ouvert », 2026-11-10). Menu natif : drapeaux sauvegardés `OoTRR.Bridge.<condition>` posés au départ.
- Expressions BoolExp du jeu : 26 éléments au plus ; les longues conditions sont découpées en
  sous-expressions (précaution, limite non vérifiée).

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
- **Cartes et boussoles « au départ » : validé en jeu (2026-11-10, menu natif).** La carte restait
  « ??? » (même celle d'un vrai coffre) parce que les scènes d'arrivée, marquées vues, sont celles qui
  **découvrent** un lieu (`EventTriggerOpenLocationUI`) quand RSDB `Location`
  `IsShowLocationUIFirstTimeInDemo` est vrai (33 lieux sur 36) : champ mis à faux avec
  `skip_cutscenes=safe` (`World.rsdb_changes`), le lieu est découvert à la première entrée.
  Le menu natif donne aussi la carte et la boussole à l'entrée du donjon (fonctions du nœud
  `OneShotDungeonGetMap`, `0x3282fe0` / `0x3283060`).
