# STORY-103: Bloc billetterie et taux de TVA

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Should Have
**Story Points:** 3
**Status:** Done (implémenté, validé sur event de démo, suite pytest verte 30/30)
**Assigned To:** goss
**Created:** 2026-06-22
**Sprint:** Recette Manifestation, phase 2

---

## User Story

En tant que **organisateur**,
je veux **un tableau de comptage billetterie (payant, invitations, places échangées, e-ticket) et l'affichage du taux de TVA**,
afin de **disposer d'un état comptable complet, pas seulement des recettes**.

---

## Description

### Background
Le rapport Trium de référence affiche un bloc billetterie (Total payant / Invitations / Places échangées / e-ticket) et un taux de TVA par séance. Cette story ajoute ces deux dimensions au builder, en restant sur le vocabulaire Pretix.

### Scope
**In scope :**
- Bloc billetterie par catégorie : nombre de places payantes, invitations (gratuit), places échangées, et modes de délivrance disponibles (e-ticket...).
- Affichage du taux de TVA issu de la `TaxRule` Pretix, par séance si homogène, sinon par ligne.

**Out of scope :**
- HT/TTC détaillé en colonnes (option non retenue en v1, voir tech-spec).
- Rendu (STORY-104, 105).

### User Flow
1. Le builder calcule, par catégorie, les comptages billetterie.
2. Il récupère le taux de TVA via la `TaxRule` des produits.
3. La structure expose le bloc billetterie + le taux par séance/ligne.

---

## Acceptance Criteria

- [x] Bloc billetterie par catégorie : payant + invitations (`report.ticketing()` -> `TicketingBlock`). Les modes de délivrance e-ticket/m-ticket/billetcollector de Trium n'existent pas dans Pretix : non inventés (voir note).
- [x] Total payant + invitations cohérent avec le périmètre (test `test_ticketing_counts_paid_and_invitations`).
- [x] Le taux de TVA provient de `OrderPosition.tax_rate` (figé depuis la `TaxRule`).
- [x] Taux affiché par séance (`session.tax_rate_display`) si homogène ; marqueur « mixed » + `tax_is_uniform=False` si plusieurs taux (le renderer affichera alors par ligne via `line.tax_rate`).
- [x] Cas TVA 0,00 % géré (pas de taux -> `tax_is_uniform` vrai, affichage vide).
- [x] Cas taux multiples : `tax_rates` (set) sur la séance, `tax_rate_display="mixed"`.
- [x] Suite pytest verte : 30/30.

### Note billetterie (vocabulaire)
Trium détaille e-ticket / m-ticket / billetcollector / places échangées. Ces notions sont **propres à TicketNet**, absentes du modèle Pretix. Conformément à la décision « ne pas inventer », le bloc se limite aux comptages Pretix réels : **payant** (prix > 0) et **invitations** (prix 0). Les modes de délivrance ne sont pas fabriqués.

---

## Technical Notes

### Composants
- **Modifié :** `services/recette_builder.py` (bloc billetterie + taux TVA).

### Mapping Pretix
- TVA = `TaxRule.rate` via `OrderPosition.tax_rule` / `Item.tax_rule`.
- Invitation = position à prix 0 / type d'admission gratuite.
- Mode de délivrance (e-ticket...) : dériver des données disponibles Pretix ; modes non applicables affichés à 0 (parité Trium).

### Edge cases
- Plusieurs `TaxRule` sur une séance -> taux par ligne plutôt que par séance.
- Places échangées : si la notion n'existe pas telle quelle dans Pretix, mettre 0 et documenter (ne pas inventer).

---

## Dependencies

**Prerequisite :** STORY-100 (builder), STORY-102 (séance).
**Blocks :** STORY-104, 105 (rendu du bloc).
**External :** aucune.

---

## Definition of Done

- [ ] Bloc billetterie implémenté dans le builder.
- [ ] Taux de TVA depuis `TaxRule` implémenté.
- [ ] Tests (comptages cohérents, taux correct, cas 0 % et multi-taux) passent.
- [ ] Revue de code.
- [ ] Critères d'acceptation validés.

---

## Story Points Breakdown

- **Backend (billetterie + TVA) :** 2 points
- **Tests :** 1 point
- **Total :** 3 points

**Rationale :** Comptages et lecture TaxRule modérés ; quelques cas limites (multi-taux, places échangées).

---

## Additional Notes

Rester sur le vocabulaire Pretix. Ne pas inventer de notion absente de Pretix (documenter et mettre 0 le cas échéant).

---

## Implementation Notes

- **Builder :** `RecetteLine` enrichie (`paid_count`, `free_count`, `tax_rate`), propriétés `paid_count`/`free_count` sur Category/Session, `tax_rates` (set) + `tax_rate_display`/`tax_is_uniform` sur Session, `report.ticketing()` -> `TicketingBlock`, helper `_fmt_rate()` (format FR « 2,10 % »), `_get_or_add_line()` (fusionne les lignes par cat/nature quand le group-by `tax_rate` les scinderait).
- **Requête :** `_aggregate` ajoute `tax_rate` au group-by + `Count(filter=Q(price__gt=0))` / `Q(price=0)` pour payant/invitation. Toujours une seule requête agrégée.
- **TVA :** lue depuis `OrderPosition.tax_rate` (taux figé à l'achat, fiable même si la TaxRule change après). Affichage par séance si uniforme, sinon « mixed » + détail par ligne disponible.
- **Billetterie :** uniquement payant/invitations (notions Pretix réelles). Pas de e-ticket/m-ticket (absent de Pretix).
- **Validé :** recette-demo (Place 6 payants, Invitation 2 gratuits, TVA 2,10 %) + non-régression. pytest 30/30.

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.
- 2026-06-22 : Implémentée. Bloc billetterie (payant/invitations) + TVA par séance/ligne depuis tax_rate. pytest 30/30. Statut Done.

**Actual Effort:** ~3 points (conforme).

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
