# Travail restant

Par ordre de priorité. Chaque point : état actuel -> prochaine étape.

## Retours de test en jeu (à corriger au fur et à mesure)
Liste de bugs et d'améliorations issus d'une session de test. Cocher quand corrigé **et** validé en jeu.

### Bugs
- [ ] Médaillon de l'Ombre non obtenu en commençant avec : cause = le module natif ne donnait pas l'objet de « Links Pocket » (corrigé dans `GiveStartItems`, compilé, **à valider en jeu**).
- [ ] La logique suppose qu'on commence au Domaine Zora : départ aléatoire désactivé (`RANDOM_SPAWN_ENABLED = False`, Python et natif) ; la ligne « Random Spawn » est retirée du menu. **À valider en jeu**.
- [ ] Boutique infinie (article rachetable à l'infini, constaté en jeu) : **bloqué, besoin d'une expérience en jeu**. Le jeton copie `Shop_Weapon_Shield_Deku` (ligne `PouchActorInfo` du bouclier, rachetable) ; `NoRespawn` ne suffit pas. Un drapeau « vendu » par article (32 emplacements, `OoTRR.Sold<n>`, expression `Shop<rang> ET NON Sold<n>` en condition de présence) retirerait le jeton, mais un lien du marchand vers un acteur absent bloque le curseur (voir `dual_actor_changes`) : risque de boutique inutilisable. Pistes à tester d'abord : jeton basé sur une ligne `PouchActorInfo` d'article à achat unique ; observer ce que fait le jeu d'un article d'origine acheté (panneau `Shop_Board_SoldOut`).
- [ ] Cycle jour/nuit toujours non fonctionnel : **bloqué, rétro-ingénierie nécessaire**. Les drapeaux de départ (`Goto_HyruleCastle=Complete`, `DoorOfTime=Step01`) sont bien posés (menu natif : `kStartEnums`) mais ne suffisent pas. Cherché dans les fichiers sans succès : aucun nom de drapeau ni paramètre lié à l'écoulement du temps (`WorldParam` ne contient que lever/coucher du soleil ; seules actions d'événement connues : `EventTrigger_SetTime`, `EventTrigger_RequestVisualOnlyTime`, `EventQueryTimeDivision`, Chant du Soleil dans `Dm_SY_Ocarina_SunSong`). Le blocage est dans le code du jeu (Ghidra : gestionnaire du monde / `WorldManagerController`). Test utile : le Chant du Soleil change-t-il l'heure ? Le temps passe-t-il après avoir rencontré Zelda dans une partie normale ?
- [ ] Les réceptacles de cœur obtenus par un jeton ne comptent qu'au changement d'âge : le module natif augmente maintenant `PlayerStatus.MaxLife` (+4 quarts) et rend la vie (`AddMaxLife`, compilé, **à valider en jeu** ; boss et réceptacles d'origine non touchés).
- [ ] Épée Kokiri redonnée au retour enfant : `ReplaceEquipmentForEraChange` équipait l'épée Kokiri même sans l'avoir ; garde ajoutée (`_guard_era_sword` : question « épée Kokiri en poche ? », sinon arme vide). Mod construit et tests verts, **à valider en jeu** (le mod Python est toujours modifié pour ce flux).
- [ ] Chants mélangés : le chant d'origine apparaît aussi dans la liste de l'ocarina (constaté). Hypothèse : la leçon l'ajoute à l'inventaire en plus du don de la seed. Contre-mesure native : tout ajout direct `Item_Melody_*` est ignoré quand `shuffle_songs` != vanilla (sauf objets de départ) ; ligne de journal « chant d'origine ignore ». **À valider en jeu** : si la ligne n'apparaît pas, l'ajout ne passe pas par `PouchAdd` (autre piste : drapeau de leçon du moteur).
- [ ] Talon devant le château : présence liée à `DoorOfTime_IsAfter_Step01_Exp` (comme Impa), donc absent avec Zelda passée ou porte ouverte (`TALON_CASTLE`, construit, **à valider en jeu**).
- [ ] Mur invisible au début de la rivière Zora : cause non identifiée (aucun acteur de blocage conditionnel trouvé dans `ZoraRiver_Child` : seuls des `FldObj_AirWall_*` fixes et ceux du mini-jeu des grenouilles). Probablement lié à un départ aléatoire (point `ZoraRiver_FromZoraDomain`, désormais désactivé) ou à la collision du terrain. À revérifier en jeu sans départ aléatoire ; préciser sinon l'endroit exact (côté Domaine Zora ou côté plaine, enfant ou adulte).
- [ ] Jeton de Skulltula en boutique : modèle d'un bouclier Mojo. Cause non vérifiée : `Obj_Token_Gold` a bien une entrée dans `ground_models.hpp`, mais les articles de boutique (copie de `Shop_Weapon_Shield_Deku`) lisent peut-être leur modèle ailleurs (ASRef `Item_Shop`, animation du jeton). À tester en jeu avec les logs de modèle (`g_model_logs`).
- [ ] Check de la Flèche de feu (`LH Sun`, Lac Hylia) : emplacement sans coffre ni jeton, donc non mélangé (famille « cadeaux d'événements », session dédiée) ; préciser le problème observé s'il s'agit d'autre chose.
- [ ] Sortie de la grotte de Dampé : le Grappin est requis pour en sortir et il est dans le coffre de la course (`Graveyard Dampe Race Hookshot Chest`) : risque de blocage si l'objet est mélangé. Pistes : (a) téléportation de sortie après l'ouverture du coffre (`EventReserveBancChange` vers `Graveyard_*` dans le script de la course `MiniGame_DampeRace`, entrées `..._Clear` / `UnderTheGrave_DampeRace_NPC_IsGoal_*`) ; (b) sortie ajoutée dans la carte. Non commencé (carte de la course à localiser).

### Mélange à étendre
- [ ] Mini-jeux : récompenses mélangées (Lance-pierres, Arc, etc.).
- [ ] Checks donnant des bouteilles mélangés : Anju, boutique de potions du marché, 5 Poes, Talon, lettre de Ruto (qui doit aussi être mélangée).
- [ ] Cinématique de la Flèche de lumière mélangée.
- [ ] Checks des Grandes Fées (fontaines) mélangés.
- [ ] Gantelet Goron mélangé.
- [ ] Checks donnant les écailles, pêche adulte et plongée (mini-jeux) mélangés.
- [ ] Berceuse de Zelda dans le pool (chant de départ avec Zelda enfant passée et chants aléatoires) : déjà le cas dans le générateur (`Song from Impa` est un lieu de chant mélangé et le départ donne l'objet qui s'y trouve ; vérifié sur 8 seeds Python) ; **à valider en jeu avec le menu**.

### Menu / réglages
- [ ] Menu : le bouton de fin de page affiche « Zelda Notes » au lieu de « Next Page » : le titre vient du volet partagé `Pa_AmiiboBtn_00-T_BtnTitle_00` (texte du jeu « Zelda Notes », sans préfixe `OoTRR_`) ; `ingame_menu.messages` écrit bien `OoTRR_…BtnTitle_00` mais la mise en page ne le lit pas. Piste : le texte vient d'un `.bflyt` du bouton (pas du `.buil`) ; remplacer le texte globalement changerait aussi l'écran Options normal (à éviter), ou faire lire une autre étiquette à la copie `OoTRRMenu_00`. Non résolu.
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
