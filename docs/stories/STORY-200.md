# STORY-200: OrderDetailBuilder, agrégation par commande (export A)

**Epic:** Exports complémentaires (détail commandes + remplissage salle)
**Priority:** Must Have (fondation de l'export A)
**Story Points:** 5
**Status:** Done (implémenté, validé sur detonantes-2, pytest 63/63)
**Assigned To:** goss
**Created:** 2026-06-22
**Sprint:** Exports complémentaires, phase 1

---

## User Story

En tant que **développeur du plugin**,
je veux **un service qui produit une ligne par commande (code, date, canal, places, catégories, montant, frais PSP)**,
afin que **l'exporter A puisse lister les transactions pour l'audit et le rapprochement bancaire**.

---

## Description

### Background
L'export « Recettes détaillées » agrège par produit/séance. L'export A a besoin d'une maille différente : la **commande**. Cette story crée le builder dédié, en réutilisant la logique de frais par PSP (`internal_type`) et le format tabulaire `recette_tabular`.

### Scope
**In scope :**
- Service `services/order_detail_builder.py` exposant `OrderDetailBuilder`.
- Une ligne par commande du périmètre (payées + invitations, exclusion annulées/expirées).
- Colonnes : code commande, date, canal de vente, nombre de places, catégories achetées agrégées (ex. « Tarif plein x2, Réduit x1 »), montant total, frais PSP par fournisseur.
- Aucune donnée personnelle (pas d'email/nom). RGPD.
- Réconciliation : somme des frais des lignes = total OrderFee de l'événement.

**Out of scope :**
- Rendu (STORY-201).
- Ventilation par siège/placement.

### User Flow (déclenchement développeur)
1. `OrderDetailBuilder(events, form_data).build()`.
2. Requêtes ORM agrégées (positions groupées par commande + frais par commande).
3. Retour : liste de lignes-commandes neutres.

---

## Acceptance Criteria

- [x] `OrderDetailBuilder` existe dans `services/order_detail_builder.py`.
- [x] Une ligne par commande ; validé : detonantes-2 = 146 commandes.
- [x] Colonnes : code, date, canal, nb places, catégories agrégées (« Early Bird x2 »), montant, frais par PSP.
- [x] Aucun email ni nom dans la structure (test `test_no_personal_data_in_rows`). RGPD.
- [x] Frais PSP réels par commande, une clé par `internal_type`.
- [x] Somme des frais des lignes = total OrderFee (réconciliation exacte : 26,93 € sur detonantes-2, `fees_reconciled=True`).
- [x] Périmètre payées + invitations ; annulées exclues (test).
- [x] 3 requêtes agrégées ORM (commandes, catégories par commande, frais par commande), pas de boucle par commande.
- [x] Cas sans frais / events vides gérés.
- [x] pytest 63/63 (9 nouveaux + non-régression).

---

## Technical Notes

### Composants
- **Nouveau :** `services/order_detail_builder.py`.
- **Lecture ORM :** `Order` (code, datetime, sales_channel, status), `OrderPosition` (item, price, count), `OrderFee` (internal_type, value), `Item`, `SalesChannel`.

### Agrégation des catégories par commande
- Utiliser une requête positions groupée par (commande, item) avec `Count`, puis assembler en Python le libellé « Item xN » par commande (pas une requête par commande).
- Alternative : `string_agg` côté SQL si supporté, mais l'assemblage Python sur un résultat déjà agrégé reste O(positions distinctes), acceptable.

### Frais
- Réutiliser `fee_label()` / la logique d'`internal_type` du `recette_builder`. Frais réels par commande (pas de répartition) -> réconciliation exacte par construction.

### RGPD
- Ne JAMAIS sélectionner `order.email` / champs nominatifs. Test explicite d'absence.

### Edge cases
- Commande multi-séances : la ligne reste au niveau commande (pas de split).
- Statut paramétrable (form_data), comme le builder existant.

---

## Dependencies

**Prerequisite :** tech-spec `tech-spec-exports-complementaires-2026-06-22.md`, infra existante (recette_builder pour `fee_label`, recette_tabular).
**Blocks :** STORY-201 (exporter A).
**External :** aucune.

---

## Definition of Done

- [ ] Builder implémenté + tests de réconciliation et d'absence de PII.
- [ ] Pas de boucle par commande (vérifié).
- [ ] Validé sur données réelles (detonantes-2).
- [ ] Revue de code.

---

## Story Points Breakdown

- **Backend (builder + agrégations) :** 4 points
- **Tests :** 1 point
- **Total :** 5 points

**Rationale :** Maille commande non triviale (agrégation catégories), réconciliation frais, contrainte RGPD.

---

## Additional Notes

Données de référence (detonantes-2) : commandes type WWLAE (4 places Tarif plein, frais 4,84 €), 3AVPL (Enfant -12 + Tarif plein), etc. Servir aux tests.

---

## Implementation Notes

- **Fichier :** `services/order_detail_builder.py` (`OrderDetailBuilder`, dataclasses `OrderDetailRow`/`OrderDetailReport`). Tests : `tests/test_order_detail_builder.py` (9 tests).
- **3 requêtes agrégées :** commandes (count + gross via `all_positions`, related name réel sur cette version de Pretix), catégories par (commande, item), frais par (commande, fee key). Assemblage Python sur résultats déjà agrégés (pas de boucle par position).
- **RGPD :** aucun champ email/nom sélectionné ni stocké ; test explicite d'absence.
- **Frais réels par commande** (pas de répartition) -> réconciliation exacte par construction. Réutilise `fee_label`/`FeeColumn` de `recette_builder`.
- **Validé :** detonantes-2 (146 commandes, 181 places, 2 578 €, 26,93 € réconciliés).

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.
- 2026-06-22 : Implémentée. Builder par commande validé sur données réelles. pytest 63/63. Statut Done.

**Actual Effort:** ~5 points (conforme).

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
