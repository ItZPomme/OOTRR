# Travail restant

Par ordre de priorité. Chaque point : état actuel -> prochaine étape.

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
- Article de boutique sur mesure validé en jeu (vente unique).
- **À faire** : liste des articles par boutique (enfant/adulte), logique, prix, réglage.

## Pont arc-en-ciel
- Conditions implémentées (open, vanilla, stones, medallions, dungeons, hearts) : **à tester en jeu**.

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
- Menu natif dans le jeu (code injecté) : voir « Pistes non abouties » dans GAME_KNOWLEDGE.
