# STORY-103: Bloc billetterie et taux de TVA

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Should Have
**Story Points:** 3
**Status:** Not Started
**Assigned To:** Unassigned
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

- [ ] Bloc billetterie par catégorie : payant, invitations (recette 0), places échangées, e-ticket (et modes non applicables à 0).
- [ ] Total payant + invitations cohérent avec le nombre de positions du périmètre.
- [ ] Le taux de TVA affiché provient de la `TaxRule` réelle des produits.
- [ ] Taux affiché par séance si homogène, sinon par ligne.
- [ ] Cas TVA 0,00 % (cas réel Gosselico) géré correctement.
- [ ] Cas taux multiples sur une même séance géré sans confusion.

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

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
