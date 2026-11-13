# Travail restant

Par ordre de priorité. Chaque point : état actuel -> prochaine étape.

## Retours de test en jeu (à corriger au fur et à mesure)
Liste de bugs et d'améliorations issus d'une session de test. Cocher quand corrigé **et** validé en jeu.

### Bugs
- [ ] Médaillon de l'Ombre non obtenu en commençant avec : cause = le module natif ne donnait pas l'objet de « Links Pocket » (corrigé dans `GiveStartItems`, compilé, **à valider en jeu**).
- [ ] La logique suppose qu'on commence au Domaine Zora : départ aléatoire désactivé (`RANDOM_SPAWN_ENABLED = False`, Python et natif) ; la ligne « Random Spawn » est retirée du menu. **À valider en jeu**.
- [ ] Boutique infinie : **corrigé et validé en jeu** (2026-11-12, boutique Kokiri). Entier sauvegardé `OoTRR.ShopSold` (un bit par article jeton, remis à 0 à la génération) ; premier achat = objet de la seed ; ensuite l'article coûte 999 rubis (la boutique ne relit le prix qu'au rechargement de la zone) et un rachat entre-temps ne donne rien et rembourse. **Pas de « Coming Soon » / « Sold out »** : 4 essais ont fait planter le chargement de la boutique (pointeur nul en 0x612850, lecteur BYML générique) : `Release` ajouté à un article qui n'en avait pas (Goron), clés « épuisé » ajoutées (Kokiri), puis même avec les seules clés d'origine (`IsCheckReleaseGameData` vrai, `ReleaseGameData` = nouvelle expression) et 32 drapeaux `OoTRR.Sold.<jeton>` ajoutés au GameData. Pistes non départagées : les 32 drapeaux sauvegardés, ou une condition qui désigne une donnée GameData ajoutée par le mod. Essai à faire séparément.
- [x] Cycle jour/nuit : **corrigé et validé en jeu** (2026-11-12, nouvelle partie : le temps s'écoule, le Chant du Soleil change l'heure ; trace native de l'heure). 0x345c020 (« heure figée ? », lu par l'avance de l'heure 0x3cdf70) répond « libre » seulement si la quête `Meet_DekuTree` est à Ready, ou si `HyruleField_ArriveEntrance` est vrai et `HrlField_HasEnteredFirstTime_Adult` faux ; sinon l'heure ne bouge plus et les demandes d'heure (Chant du Soleil) sont effacées sans être appliquées (constaté : 6 h 00 pendant toute la partie, demandes 0 h et 20 h ignorées). `HyruleField_ArriveEntrance` n'est posé que par la scène du hibou à l'entrée de la plaine (`Goto_HyruleCastle_Kaepora_00`, étape 132), jamais jouée avec les scènes passées ou Zelda passée. Correction : drapeau posé au départ, tous réglages (`world.TIME_FLOW_FLAG`). Aussi : l'étape 182 (`HyruleField_ChangeENV`, palette « First » à soleil forcé) reste sautée. Objet « temps » : `*(*0x4c7e898)+0x510` (+0x28 secondes du jour, +0x48 heure demandée, bit 1 de +0x08 = demande) ; 0xeee640 demande une heure ; avance normale aussi conditionnée par `HavePlayedEvent.Dm_HrlField_0020` (sinon ramenée vers 15 h). La trace de diagnostic (crochets sur 0xeee640 et 0x3cdf70) a été retirée ; la refaire au besoin à partir de ces adresses.
- [ ] Les réceptacles de cœur obtenus par un jeton ne comptent qu'au changement d'âge : le module natif augmente maintenant `PlayerStatus.MaxLife` (+4 quarts) et rend la vie (`AddMaxLife`, compilé, **à valider en jeu** ; boss et réceptacles d'origine non touchés).
- [ ] Épée Kokiri redonnée au retour enfant : `ReplaceEquipmentForEraChange` équipait l'épée Kokiri même sans l'avoir ; garde ajoutée (`_guard_era_sword` : question « épée Kokiri en poche ? », sinon arme vide). La première version était fausse (relu avec `tools.events`) : `Num` écrasé par `set` (entier écrit comme texte : 12304) et réponses inversées ; corrigé (`Num` du modèle = 1, 0 = oui -> équiper). **À valider en jeu**.
- [ ] Chants mélangés : le chant d'origine apparaît aussi dans la liste de l'ocarina (constaté). **Vérifié dans les fichiers** : les 12 dons de `Dm_SY_Ocarina` (étapes 26-31, 32-38) sont tous remplacés ; les autres mentions de `Item_Melody_*` (scènes `Dm_MelodyGet_*`, PNJ, `Dm_SY_Ocarina_SariaSong`) ne sont pas des actions d'inventaire ; dans le code, `Item_Melody_%s` ne sert qu'au son (0x323f420) et à l'icône (0x33bff00). Contre-mesure native : tout ajout direct `Item_Melody_*` est ignoré quand `shuffle_songs` != vanilla, sauf objets de départ et **chant placé dans un coffre** (la version précédente l'aurait bloqué en mode `random`) ; journal « chant d'origine ignore, raison » / « chant d'un coffre accepte ». **À valider en jeu** : si aucune ligne n'apparaît à la leçon, le chant n'est pas ajouté par `PouchAdd` (0x110d570).
- [ ] Talon devant le château : présence liée à `DoorOfTime_IsAfter_Step01_Exp` (comme Impa), donc absent avec Zelda passée ou porte ouverte (`TALON_CASTLE`, construit, **à valider en jeu**).
- [x] Mur invisible au début de la rivière Zora : **comportement du jeu d'origine** (précisé par le testeur) : les rochers à l'entrée (`Obj_BrokenRock_A_01`, carte `ZoraRiver_Child` seulement ; déjà cassés côté adulte) bloquent le passage tant qu'ils ne sont pas détruits à la bombe. La logique le demande déjà (`ZR Front` -> `Zora River` : `is_adult or has_explosives`). Rien à corriger.
- [ ] Jeton de Skulltula en boutique : modèle d'un bouclier Mojo. **Cause trouvée dans le code** : `TokenModelPath` passait l'objet par `GroundItem` (`Obj_Token_Gold` -> `Item_Token_Gold`, nom pour les textes) avant de chercher dans `kGroundModels`, qui ne connaît que `Obj_Token_Gold` : pas de modèle, donc celui de la base (bouclier). Corrigé (nom tel quel d'abord), compilé, **à valider en jeu** (vaut aussi pour un jeton d'or sur un cœur au sol).
- [ ] Check de la Flèche de feu (`LH Sun`, Lac Hylia) : absent du spoiler car l'emplacement n'avait aucun mécanisme de don (ni coffre, ni jeton), donc jamais mélangé. **Ajouté dans les fichiers** : la flèche est un objet posé sur l'eau (`Obj_Arrow_Fire`, hash 4598657944866228526, carte `HyruleField_Adult_Static`), créé par le module `HyruleField_LakeHylia_Adult_Prefab_5313` (quête `SubEvent_GetFireArrow`, tir dans le soleil, plage horaire). Nouveau genre de lieu `pickup: "item"` (+ `actor`) : mélangé avec `shuffle_gifts`, l'acteur devient un jeton (copie de `Obj_Arrow_Fire`) comme les cœurs au sol, objets « au sol » seulement. Toujours au spoiler. Générateur natif identique au Python ; **à valider en jeu** (dépend aussi du cycle jour/nuit).
- [ ] Sortie de la grotte de Dampé : le Grappin est requis pour sortir de la salle d'arrivée et il est dans le coffre de la course. Corrigé **dans les fichiers** (`ModBuilder._dampe_exit`, relu avec `tools.events`) : après le coffre (état `OpenedHookShot`), parler à Dampé au but menait seulement au conseil « utilise le Grappin » (`SuggestExit`, étape 260) ; sans Super Grappin ni Grappin, il ramène maintenant Link dehors comme après une chute (étapes 71 -> 70 -> 68 : soin, `Graveyard_Adult` point `4`, fin de la course). `insert_flow` accepte une cible `{"event": N}`. **À valider en jeu**.

### Mélange à étendre
- [ ] Mini-jeux : récompenses mélangées (Lance-pierres, Arc, etc.).
- [ ] Checks donnant des bouteilles mélangés : Anju, boutique de potions du marché, 5 Poes, Talon, lettre de Ruto (qui doit aussi être mélangée).
- [ ] Cinématique de la Flèche de lumière mélangée.
- [ ] Checks des Grandes Fées (fontaines) mélangés.
- [ ] Gantelet Goron mélangé.
- [ ] Checks donnant les écailles, pêche adulte et plongée (mini-jeux) mélangés.
- [ ] Berceuse de Zelda dans le pool (chant de départ avec Zelda enfant passée et chants aléatoires) : déjà le cas dans le générateur (`Song from Impa` est un lieu de chant mélangé et le départ donne l'objet qui s'y trouve ; vérifié sur 8 seeds Python) ; **à valider en jeu avec le menu**.

### Menu / réglages
- [x] Onglet Key Items : le jeu ne l'ouvre (onglet 0xa69220 et écran 0x33dd6b0) que si un élément de la liste 4 (pierres spirituelles) est obtenu : fermé « ??? » / « Unavailable right now » avec un médaillon seul au départ. Crochets natifs : titre de l'onglet (0xa6ab50) et test « objet obtenu » (0x181160, seulement pour ces deux appels) ouverts dès qu'une pierre ou un médaillon est obtenu ; **validé en jeu** (2026-11-12). Onglet Threads of Time : `UI_IsFinishChallengeMenuOpenEvent` posé au départ (validé en jeu). Les « MsgNotFound » de Threads of Time (étapes de quête sautées) restent à voir.
- [ ] Menu : le bouton de fin de page affiche « Zelda Notes » au lieu de « Next Page ». **Cause trouvée (Ghidra)** : le rappel de texte des mises en page (0x3780cd0) cherche « <volet>-<zone de texte> » directement dans le fichier de messages chargé par 0xa6b250 (x0 fichier, x1 étiquette, résultat 0x18 octets via x8), sans passer par 0xa6afe0 / 0xa6b060 (d'où l'absence de ligne de journal). Nouveau crochet `MessageInFile` : pendant le menu, une étiquette `Pa_…` essaie d'abord `<préfixe de page><étiquette>` ; compilé, **à valider en jeu** (journal « texte de volet du menu (0xa6b250) »). Ancienne analyse : le titre vient du volet partagé `Pa_AmiiboBtn_00-T_BtnTitle_00` (texte du jeu « Zelda Notes », sans préfixe `OoTRR_`) ; `ingame_menu.messages` écrit bien `OoTRR_…BtnTitle_00` mais la mise en page ne le lit pas. Piste : le texte vient d'un `.bflyt` du bouton (pas du `.buil`) ; remplacer le texte globalement changerait aussi l'écran Options normal (à éviter), ou faire lire une autre étiquette à la copie `OoTRRMenu_00`. Non résolu.
- [ ] Condition du pont : nombre requis au choix en haut de la page 2 (voir « Pont arc-en-ciel ») ; menu **validé en jeu**, ouverture du pont au nombre choisi à vérifier.

## Peste Mojo vendeurs (scrubsanity)
- Mécanisme validé en jeu (une Peste Mojo vend n'importe quel objet, message dans la langue du jeu).
- **À faire** : inventaire des ~35 Peste Mojo (`Enemy_Scrub_Business` dans les cartes enfant et
  adulte, avec leurs hashes), région et règle de chacune dans `ootrr/data/world/`, réglage
  `shuffle_scrubs`, prix (ceux du jeu ou fixes). Option de test actuelle : `--test-scrub HASH=OBJET:PRIX`.

## Skulltulas d'or
- Butin remplaçable validé en jeu.
- **À faire** : les 100 emplacements dans la logique (zone, âge, outils), réglage `tokensanity`,
  puis le pont `tokens` (la valeur `PouchData.Item_Token_Gold.StockNum` est connue).

## Boutiques (shopsanity)
- Menu natif : 4 articles par boutique (8 boutiques), réglage 0 à 4, prix Origine / Abordable /
  Aléatoire ; validé en jeu dans la boutique Kokiri.
- **À faire** : vérifier les autres boutiques, la vente unique après sauvegarde, le modèle des objets
  qui traverse la tablette, la version Python (mod sans menu), et des bourses dans la logique pour
  des prix au-delà de 99.

## Pont arc-en-ciel
- Conditions implémentées (open, vanilla, stones, medallions, dungeons, hearts) : **à tester en jeu**.
- Menu natif : nombre requis au choix en page 2 (pierres 1–3, médaillons 1–6, récompenses 1–9, cœurs 3–20),
  lignes affichées selon la condition : **validé en jeu** (2026-11-12). Reste à vérifier en jeu que le pont
  s'ouvre au nombre choisi pour chaque condition.

## Questions en jeu (« menu » au lancement)
- Prototype : `open_forest=ask` (question oui/non au début de la nouvelle partie) — **à tester**.
- Étendre aux réglages décidables pendant la partie : cinématiques, porte du temps, condition du
  pont (expressions qui lisent un drapeau de réponse), objets de départ. Traduire les questions.

## Divers
- Animation de première obtention des consommables : non supprimée (décidée par le moteur).
- Améliorations progressives dans les coffres (mécanisme des coffres A_06 à contenu conditionnel).
- PNJ et chants mélangés (remplacement du nom de l'objet dans leurs scènes — validé pour un PNJ).
- Petites clés / clés du boss : actuellement à leur place d'origine.
- Fenêtre de réglages sur PC (alternative simple au menu en jeu).
- Menu natif dans le jeu (code injecté, exlaunch) : injection validée en jeu, voir `native/README.md` ; reste la rétro-ingénierie de l'écran « Nouvelle partie ».
