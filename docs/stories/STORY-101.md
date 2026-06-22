# STORY-101: Ventilation des frais en colonnes dynamiques par PSP

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have
**Story Points:** 5
**Status:** Not Started
**Assigned To:** Unassigned
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

- [ ] Le jeu de colonnes de frais est calculé dynamiquement à partir des `internal_type`/`fee_type` réellement présents (aucune colonne en dur).
- [ ] Une colonne par PSP (`internal_type`), ex. Mollie CB et SumUp distinctes.
- [ ] Les frais de service (`fee_type=service`) et autres types natifs apparaissent en colonne dès qu'ils existent dans les données.
- [ ] Label lisible par PSP connu (Mollie CB, iDEAL, Bancontact, SumUp...) + fallback humanisé pour type inconnu.
- [ ] Colonne « Recette nette » = Brut moins somme des frais, par ligne et par total.
- [ ] La somme des frais des lignes = sous-total frais de la catégorie ; la somme des sous-totaux = total des frais.
- [ ] Le total des frais PSP réconcilie avec `PSPTransactionCache` (Mollie/SumUp) sur la période.
- [ ] Cas sans aucun frais : aucune colonne de frais, recette nette = brut, pas de crash.

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

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
