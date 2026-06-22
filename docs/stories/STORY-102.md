# STORY-102: Découpage par canal de vente et regroupement par séance

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have
**Story Points:** 5
**Status:** Done (implémenté, validé sur event de démo + non-régression, suite pytest verte 26/26)
**Assigned To:** goss
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

- [x] Le builder produit une section par canal de vente présent dans le périmètre.
- [x] Total tous canaux exposé via `report.gross`/`fees`/`net` ; somme des canaux = TOTAL (test `test_channel_filter_restricts_perimeter`).
- [x] Un filtre canal unique (`form_data["channel"]`) restreint correctement le périmètre (positions + frais + weights).
- [x] Le regroupement par séance utilise `SubEvent` ; fallback séance « Event » si pas de sous-événements (test `test_single_event_falls_back_to_event_session`).
- [x] Label de séance = nom + date (`Name (DD/MM/YYYY HH:MM)`) via `_session_label()`.
- [x] La vue croisée Catégorie x Séance est disponible (`report.cross_view()` -> `CrossView`).
- [x] Les frais sont ventilés sur la **bonne séance** de la commande (au prorata du gross si commande multi-séances), corrigeant le placement temporaire de STORY-101 (tout sur `sessions[0]`).
- [x] Cas mono-canal/mono-séance : un seul bloc, pas de section vide. Non-régression detonantes-2 OK (2 578 € / 26,93 €).
- [x] Suite pytest verte : 26/26.

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

## Implementation Notes

- **Builder :** ajout `_channel_filter()`, `_session_label()`, `_order_session_weights()`, refonte `_aggregate_fees()`/`_fill_fees()`/`_deposit_fee()` (frais rattachés à la séance réelle de la commande, prorata gross si multi-séances, split égal si commande sans gross), `report.cross_view()` + dataclass `CrossView`, champ `channel` dans `__init__`.
- **Frais multi-séances :** un OrderFee est au niveau commande ; on calcule la répartition gross par séance de chaque commande (`_order_session_weights`, 1 requête agrégée) et on ventile le frais au prorata. Corrige le placement provisoire de STORY-101.
- **Données de test :** event de démo `demo/recette-demo` créé via `docs/seed_recette_demo.py` (2 séances x 2 canaux x variations x Mollie/SumUp/service x invitations). Sert de banc d'essai pour les renderers (STORY-104/105). Note : suppression à faire en SQL (le `.delete()` Django récursionne sur les events dans le shell).
- **Validé :** démo (frais par séance corrects, filtre canal web/guichet réconcilié, vue croisée) + non-régression detonantes-2. pytest 26/26.

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.
- 2026-06-22 : Implémentée. Séance=SubEvent, filtre canal, vue croisée, frais par séance corrigés. Event de démo créé. pytest 26/26. Statut Done.

**Actual Effort:** ~5 points (conforme).

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
