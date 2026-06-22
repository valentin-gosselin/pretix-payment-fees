# STORY-102: Découpage par canal de vente et regroupement par séance

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have
**Story Points:** 5
**Status:** Not Started
**Assigned To:** Unassigned
**Created:** 2026-06-22
**Sprint:** Recette Manifestation, phase 2

---

## User Story

En tant que **organisateur**,
je veux **un rapport découpé par canal de vente et par séance**,
afin de **réconcilier ma billetterie web, mon guichet et chaque date d'événement séparément**.

---

## Description

### Background
Les frais PSP varient par canal (ex. 100 % du Mollie sur le web, 0 au guichet dans les données réelles Gosselico). Le rapport doit produire une section par canal + un total tous canaux, et regrouper par séance (sous-événement). C'est ce qui rend le rapport exploitable comptablement.

### Scope
**In scope :**
- Découpage par `Order.sales_channel` : une section par canal + section TOTAL tous canaux.
- Filtre optionnel sur un canal unique au lancement (les deux modes, décision utilisateur initial).
- Regroupement par séance = `SubEvent` ; si l'event n'a pas de sous-événements, séance unique = l'événement.
- Vue croisée Catégorie x Séance (équivalent pages 2-3 Trium).
- Réconciliation : somme des canaux = TOTAL ; somme des séances = total event.

**Out of scope :**
- Bloc billetterie et TVA (STORY-103).
- Rendu (STORY-104, 105) ; ici on produit la structure.

### User Flow
1. L'utilisateur lance l'export (mode sections par canal par défaut, ou filtre un canal).
2. Le builder regroupe par canal puis par séance.
3. La structure expose les sections + la vue croisée + les totaux réconciliés.

---

## Acceptance Criteria

- [ ] Le builder produit une section par canal de vente présent dans le périmètre.
- [ ] Une section TOTAL tous canaux est produite ; somme des canaux = TOTAL (réconciliation exacte).
- [ ] Un filtre canal unique restreint correctement le périmètre.
- [ ] Le regroupement par séance utilise `SubEvent` ; fallback événement unique si pas de sous-événements.
- [ ] La vue croisée Catégorie x Séance est disponible dans la structure.
- [ ] Les frais (STORY-101) sont ventilés correctement par canal et par séance.
- [ ] Cas event mono-canal et mono-séance : un seul bloc, pas de section vide.

---

## Technical Notes

### Composants
- **Modifié :** `services/recette_builder.py` (niveaux canal et séance dans la hiérarchie).

### Mapping Pretix (figé)
- Canal = `Order.sales_channel` (le champ d'accès réel est `sales_channel_id` ; lire le label via `SalesChannel`). Isoler derrière une petite fonction d'abstraction (le champ peut varier selon la version Pretix, cf. risque tech-spec).
- Séance = `OrderPosition.subevent` ; si nul -> séance unique représentant l'événement.

### Edge cases
- Canal présent en base mais sans vente payante -> ne pas créer de section vide.
- Event sans sous-événement -> une seule séance, en-tête de séance = date de l'événement.
- Plusieurs séances et plusieurs canaux -> matrice complète canal x séance x catégorie x nature.

---

## Dependencies

**Prerequisite :** STORY-100 (builder), STORY-101 (frais ventilés par maille).
**Blocks :** STORY-104, 105 (rendu des sections).
**External :** aucune.

---

## Definition of Done

- [ ] Sections par canal + TOTAL tous canaux implémentés.
- [ ] Filtre canal unique fonctionnel.
- [ ] Regroupement séance (SubEvent) avec fallback event unique.
- [ ] Vue croisée Catégorie x Séance disponible.
- [ ] Tests de réconciliation (somme canaux = total, somme séances = total) passent.
- [ ] Revue de code.
- [ ] Critères d'acceptation validés.

---

## Story Points Breakdown

- **Backend (canal + séance + vue croisée) :** 4 points
- **Tests :** 1 point
- **Total :** 5 points

**Rationale :** Hiérarchie multi-niveaux, abstraction sales_channel par sécurité de version, vue croisée à structurer.

---

## Additional Notes

Données réelles de référence (pretix-dev, event detonantes-2) : 2 canaux (Boutique en ligne `web`, Guichet `api.guichet`), une seule séance. Utiliser pour les tests.

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
