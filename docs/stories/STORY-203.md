# STORY-203: Tests, i18n et release des exports complémentaires

**Epic:** Exports complémentaires (détail commandes + remplissage salle)
**Priority:** Must Have (rend les 2 exports livrables)
**Story Points:** 3
**Status:** Done (implémenté, validé sur detonantes-2, pytest 78/78)
**Assigned To:** Unassigned
**Created:** 2026-06-22
**Sprint:** Exports complémentaires, phase 3

---

## User Story

En tant que **organisateur**,
je veux **les deux nouveaux exports finalisés, traduits et déployés en production**,
afin de **les utiliser dans ma langue depuis l'interface Pretix**.

---

## Description

### Background
Les exports A (STORY-200/201) et B (STORY-202) sont implémentés. Cette story finalise : couverture de tests, i18n des 8 langues, bump de version, release PyPI et déploiement prod.

### Scope
**In scope :**
- Tests pytest d'intégration des 2 exports (enregistrement, formulaire, 3 formats, réconciliation frais A, comptages/quotas B, absence PII A, absence de montant B).
- i18n : extraction des nouveaux libellés, traduction des 8 .po (fr/en/de/es/nl/it/pt/pl), compilation .mo.
- Bump de version (minor) + CHANGELOG.
- Release : merge dev->main, CI verte, tag, PyPI.
- Déploiement prod via `update.sh` (depuis `/docker/pretix`).

**Out of scope :**
- Nouvelles fonctionnalités (figées dans 200/201/202).

### User Flow
1. CI verte sur main.
2. Tag -> release PyPI.
3. `update.sh` rebuild l'image prod.
4. Les 2 exports apparaissent en prod, traduits.

---

## Acceptance Criteria

- [ ] Tests pytest des 2 exports passent (suite globale verte).
- [ ] Réconciliation des frais (export A) testée ; absence de PII testée.
- [ ] Comptages + quotas/taux (export B) testés ; absence de montant testée.
- [ ] Libellés des 2 exports traduits dans les 8 langues (.po + .mo compilés et packagés).
- [ ] CI verte sur main (Python 3.11 + 3.12).
- [ ] Version bumpée + CHANGELOG à jour.
- [ ] Release PyPI réussie ; version dispo.
- [ ] Déployé en prod ; les 2 exports visibles et traduits.

---

## Technical Notes

### i18n
- Même mécanisme que l'export principal : libellés en `gettext_lazy` (sources FR), `.po` remplis, `.mo` compilés via msgfmt dans le conteneur (dossier writable), `.mo` inclus dans le package (MANIFEST.in + package-data déjà OK).
- Rappel : les labels figés à la construction du report doivent l'être dans le contexte de langue de l'export (cf. note STORY-101/i18n).

### Release (process rappelé)
- Bump `pyproject.toml` ET `pretix_payment_fees/__init__.py` (les deux doivent matcher le tag).
- CI installe `pip install -e ".[dev]"` (pytest-django).
- `update.sh` à lancer DEPUIS `/docker/pretix` (le `./build.sh` est relatif). Le "❌" final du script est un faux négatif connu (le build réussit, l'image latest est à jour).

### Tests anti-régression
- Vérifier que l'export « Recettes détaillées » existant n'est pas impacté.

---

## Dependencies

**Prerequisite :** STORY-200, 201, 202.
**Blocks :** aucune (clôture de l'epic).
**External :** chaîne PyPI + serveur prod (192.168.0.13).

---

## Definition of Done

- [ ] Suite pytest verte (anciens + nouveaux tests).
- [ ] i18n 8 langues compilée et packagée.
- [ ] CI verte, tag, PyPI, prod déployée et vérifiée.
- [ ] CHANGELOG à jour.
- [ ] Validation goss en prod.

---

## Story Points Breakdown

- **Tests d'intégration :** 1 point
- **i18n 8 langues :** 1 point
- **Release + déploiement :** 1 point
- **Total :** 3 points

**Rationale :** Tâches mécaniques bien rodées (process release déjà éprouvé en v1.1.x).

---

## Additional Notes

Process de release identique à celui validé pour la v1.1.x (i18n « Recettes détaillées »).

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
