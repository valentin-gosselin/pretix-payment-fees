# STORY-202: Export « Remplissage de salle » (export B) avec quotas et taux

**Epic:** Exports complémentaires (détail commandes + remplissage salle)
**Priority:** Must Have
**Story Points:** 5
**Status:** Done (implémenté, validé sur detonantes-2, pytest 78/78)
**Assigned To:** Unassigned
**Created:** 2026-06-22
**Sprint:** Exports complémentaires, phase 2

---

## User Story

En tant que **organisateur / responsable production**,
je veux **un état simple du remplissage de la salle (places par catégorie + taux de remplissage par quota), sans aucune valeur financière**,
afin de **le partager avec mes partenaires et piloter la jauge sans exposer les montants**.

---

## Description

### Background
Les partenaires/producteurs ont besoin de savoir « combien de places vendues » et « à quel point la salle se remplit », pas des chiffres comptables. Cette story produit un export épuré : comptage par catégorie + bloc quotas avec taux de remplissage. Aucune valeur monétaire.

### Scope
**In scope :**
- Exporter `exporters/remplissage_salle.py` (`RemplissageSalleExporter`, BaseExporter).
- **Bloc catégories** : par Item, nombre de places (payant / invitations / total). Réutilise `RecetteDataBuilder.ticketing()` (déjà calculé).
- **Bloc quotas** : par quota Pretix, places vendues / capacité (`Quota.size`) / **taux de remplissage en %**.
- En-tête : événement, date, lieu, total places vendues.
- 3 formats (PDF épuré « feuille de salle », CSV, Excel).
- i18n.

**Out of scope :**
- Toute valeur monétaire (prix, recette, frais).
- Plan de salle / placement par siège.
- Détail par séance par défaut (option future).

### User Flow
1. L'organisateur ouvre les exports.
2. Sélectionne « Remplissage de salle ».
3. Choisit période/canal/format.
4. Télécharge l'état (places + taux de remplissage), partageable tel quel.

---

## Acceptance Criteria

- [ ] Export « Remplissage de salle » apparaît dans Pretix.
- [ ] **Bloc catégories** : une ligne par Item avec payant / invitations / total ; total général cohérent avec le périmètre.
- [ ] **Bloc quotas** : par quota, vendu / capacité (`Quota.size`) / taux % = vendu / capacité.
- [ ] **Aucune valeur monétaire** nulle part (test explicite).
- [ ] Cas sans quota (capacité illimitée) : comptage affiché **sans colonne taux** (pas de division), pas de crash.
- [ ] En-tête avec total places vendues.
- [ ] PDF épuré + CSV + Excel.
- [ ] Libellés traduits (8 langues).

---

## Technical Notes

### Composants
- **Nouveau :** `exporters/remplissage_salle.py`, un renderer « feuille de salle » (ou réutilisation du renderer PDF avec un sous-ensemble de blocs).
- **Réutilise :** `RecetteDataBuilder.ticketing()` pour le comptage par catégorie ; nouvelles requêtes pour les quotas.

### Quotas (mapping Pretix confirmé)
- `Quota.size` = capacité (None = illimité).
- Liaison quota -> items via la table `pretixbase_quota_items` (M2M `Quota.items`).
- Places vendues d'un quota = positions payées des items du quota (filtrer le périmètre/séance).
- Taux = `vendu / size` quand `size` non nul ; sinon pas de taux.
- Pretix expose aussi `Quota.availability()` (vendu/bloqué/disponible) ; on peut s'en servir, mais un comptage direct des positions payées suffit et reste explicite. Documenter le choix.
- Attention aux quotas par sous-événement (`Quota.subevent`) pour les events multi-dates.

### Données de référence (detonantes-2)
- « Billets » size 720 -> 66 vendus (9,2%) ; « Invitation » size 80 -> 37 vendus (46,3%).

### Edge cases
- Item dans plusieurs quotas / quota multi-items : compter sans double-comptage (dédup des positions).
- Event sans quota : bloc quotas masqué ou sans taux.
- Quota size illimité (None).

---

## Dependencies

**Prerequisite :** tech-spec, `RecetteDataBuilder` existant, infra renderers.
**Blocks :** STORY-203 (tests/i18n/release).
**External :** aucune.

---

## Definition of Done

- [ ] Exporter enregistré et visible.
- [ ] Bloc catégories + bloc quotas/taux corrects (validés sur detonantes-2).
- [ ] Aucune valeur monétaire (test).
- [ ] Cas sans quota géré.
- [ ] 3 formats + i18n.
- [ ] Déployé/vérifié pretix-dev.

---

## Story Points Breakdown

- **Exporter + requêtes quotas + renderer épuré :** 4 points
- **Tests + i18n :** 1 point
- **Total :** 5 points

**Rationale :** Le comptage catégories réutilise l'existant, mais les quotas (liaison M2M, dédup, taux, sous-événements, cas illimité) ajoutent de la logique et des cas limites.

---

## Additional Notes

Export volontairement minimal et non financier : la valeur est la simplicité et le partage sans donnée sensible. Style sobre indigo, vocabulaire Pretix FR.

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
