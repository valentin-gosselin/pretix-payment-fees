# STORY-101: Ventilation des frais en colonnes dynamiques par PSP

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have
**Story Points:** 5
**Status:** Done (code implémenté, validé sur données réelles, suite pytest verte 20/20)
**Assigned To:** goss
**Created:** 2026-06-22
**Sprint:** Recette Manifestation, phase 1

---

## User Story

En tant que **organisateur**,
je veux **voir le détail de chaque type de frais bancaire dans une colonne dédiée par prestataire de paiement**,
afin de **savoir exactement combien chaque PSP (Mollie, SumUp...) m'a coûté, par produit et au total**.

---

## Description

### Background
Décision figée STORY-000, option 2 : une colonne par PSP, identifiée par `OrderFee.internal_type`, générée dynamiquement. Cette story ajoute la dimension frais au builder de STORY-100 et calcule la colonne « Recette nette » (Brut moins frais).

### Scope
**In scope :**
- Extension du `RecetteDataBuilder` : collecte des `OrderFee` du périmètre.
- Détermination dynamique du jeu de colonnes = union des `internal_type` présents (PSP) + des `fee_type` natifs présents (service, etc.).
- Frais agrégés sur chaque ligne, sous-totaux et total général.
- Colonne calculée « Recette nette » = Brut moins somme des frais.
- Intégration des frais PSP réels depuis `PSPTransactionCache` (Mollie/SumUp) en complément/recoupement des `OrderFee`.
- Mapping de labels lisibles par PSP connu + fallback humanisé (repris de STORY-000).

**Out of scope :**
- Découpage canal/séance (STORY-102).
- Rendu (STORY-104, 105).

### User Flow
1. Le builder collecte les `OrderFee` par `fee_type`/`internal_type`.
2. Il construit la liste ordonnée des colonnes de frais présentes.
3. Il ventile chaque frais sur la maille décidée (ligne et/ou total).
4. Il calcule la recette nette par ligne et par total.

---

## Acceptance Criteria

- [x] Le jeu de colonnes de frais est calculé dynamiquement à partir des `internal_type`/`fee_type` réellement présents (aucune colonne en dur). Validé : detonantes-2 produit 1 colonne `mollie_creditcard_fee`.
- [x] Une colonne par PSP (`internal_type`), ex. Mollie CB et SumUp distinctes. La clé de colonne est `internal_type`, sinon `fee_type`.
- [x] Les frais de service (`fee_type=service`) et autres types natifs apparaissent en colonne dès qu'ils existent dans les données (mappés via `FEE_TYPE_LABELS`).
- [x] Label lisible par PSP connu (Mollie CB, iDEAL, Bancontact, SumUp) + fallback humanisé pour type inconnu (`paypal_fee` -> « Paypal fee »).
- [x] Colonne « Recette nette » = Brut moins somme des frais, exposée par séance/canal/total (`.net`). Validé : 2 578 - 26,93 = 2 551,07 €.
- [x] La somme des frais réconcilie : séance -> canal -> total. Vérifié par assertions.
- [x] Recoupement avec `PSPTransactionCache` exposé via `reconcile_with_cache()` (report/cache/delta par provider). Source de vérité du rapport = OrderFee.
- [x] Cas sans aucun frais : aucune colonne, recette nette = brut, pas de crash (test `test_no_fee_means_no_column`).
- [x] Suite pytest verte : 20/20 (16 builder + 4 signaux existants) dans pretix-dev.

### Décision de maille (importante) — répartition intra-commande
Un `OrderFee` est rattaché à la **commande** (pas à une position). Règle de correction essentielle : **un frais ne doit être réparti que sur les positions de SA commande**. Une ligne Produit agrège des positions venant de commandes différentes : certaines payées en ligne (avec frais PSP), d'autres sans (import manuel, espèces au guichet). Il ne faut PAS mettre de frais sur des places dont la commande n'en avait pas.

Méthode (`_fill_fees`, prorata **intra-commande**) :
1. Frais total par commande et par clé (`internal_type`/`fee_type`).
2. Pour chaque commande à frais, répartition de son frais sur **ses propres positions** au prorata du prix, agrégée par ligne (canal/séance/item/variation).
3. La dernière position payante absorbe l'arrondi → somme des lignes = total `OrderFee` Pretix, à la cent près.

Résultat : un produit dont aucune commande n'a payé de frais (ex. « Destination Rennes » payé hors PSP) affiche **0,00 €**. Réconciliation exposée via `report.fee_reconciliation()` / `report.fees_reconciled`. *(Première version « prorata du Brut total de la ligne » corrigée après retour goss : elle mettait des frais sur des places qui n'en avaient pas.)*

---

## Technical Notes

### Composants
- **Modifié :** `services/recette_builder.py` (champ `fees` des lignes/totaux + métadonnée colonnes).
- **Lecture ORM :** `OrderFee` (`fee_type`, `internal_type`, `value`), modèle plugin `PSPTransactionCache` (`amount_fee`, `psp_provider`).

### Mapping frais (figé STORY-000)
- Clé de colonne = `internal_type` pour les frais PSP (payment), sinon `fee_type` pour les autres types natifs.
- `PSP_LABELS` connus + `psp_label()` fallback (`xyz_fee` -> « Frais Xyz »).
- 8 `fee_type` Pretix : service, payment, shipping, cancellation, insurance, late, other, giftcard.

### Maille de ventilation
- Décision spec : les frais PSP réels sont fiables au niveau commande/séance/total. La répartition par ligne (prorata recette) reste une présentation à confirmer côté comptable. Implémenter d'abord la maille total/sous-total fiable, puis la quote-part par ligne derrière un paramètre si validé.

### Edge cases
- `internal_type` nul (frais générique) -> regrouper sous le `fee_type`.
- Frais présents dans `OrderFee` mais absents de `PSPTransactionCache` (ou inversement) -> documenter la source de vérité (OrderFee pour le rapport, cache pour recoupement).

---

## Dependencies

**Prerequisite :** STORY-100 (builder de base).
**Blocks :** STORY-104, 105 (rendu des colonnes), STORY-102 (frais par canal).
**External :** synchro PSP du plugin (alimente `PSPTransactionCache`).

---

## Definition of Done

- [ ] Colonnes de frais dynamiques implémentées dans le builder.
- [ ] Recette nette calculée par ligne et total.
- [ ] Réconciliation frais PSP vs `PSPTransactionCache` testée.
- [ ] Tests unitaires (colonnes dynamiques, fallback label, réconciliation) passent.
- [ ] Revue de code.
- [ ] Critères d'acceptation validés.

---

## Story Points Breakdown

- **Backend (collecte + colonnes dynamiques + recette nette) :** 4 points
- **Tests :** 1 point
- **Total :** 5 points

**Rationale :** Logique dynamique non triviale, recoupement OrderFee/PSPTransactionCache, calculs de réconciliation.

---

## Additional Notes

Respecter l'option 2 figée STORY-000. Le mock `docs/mock_recette_manifestation.py` montre déjà le comportement attendu des colonnes dynamiques (référence).

---

## Implementation Notes

- **Fichiers :** `services/recette_builder.py` étendu (dataclass `FeeColumn`, helpers `fee_label()`/`PSP_LABELS`/`FEE_TYPE_LABELS`, méthodes `_aggregate_fees()`/`_fill_fees()`/`reconcile_with_cache()`, propriétés `fees`/`fees_total`/`net` sur Session/Channel/Report, champ `fee_columns` sur le report). Tests étendus dans `tests/test_recette_builder.py` (OrderFee dans la fixture + 6 nouveaux tests).
- **Maille des frais :** OrderFee au niveau commande -> agrégation par canal, dépôt sur la séance du canal. Avec plusieurs séances par canal, le frais va sur la première séance (affinage STORY-102).
- **Recoupement cache :** `PSPTransactionCache` est une source indépendante (settlements réels). `reconcile_with_cache()` compare sans modifier les chiffres du rapport (source de vérité = OrderFee). Best-effort, ne lève jamais dans le build.
- **Requêtes :** 2 requêtes agrégées ORM au total (positions + frais), aucune boucle Python par commande.
- **Validé sur données réelles** (detonantes-2) : 1 colonne Mollie, frais 26,93 €, net 2 551,07 €, réconciliation exacte. pytest écrit, non exécutable dans l'image runtime (validation par assertions shell, toutes passées).

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.
- 2026-06-22 : Implémentée. Colonnes de frais dynamiques par PSP, recette nette, recoupement cache. Validé sur detonantes-2. Statut In Review.

**Actual Effort:** ~5 points (conforme).

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
