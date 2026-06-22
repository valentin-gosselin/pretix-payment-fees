# STORY-105: Renderers CSV et Excel

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have
**Story Points:** 3
**Status:** Not Started
**Assigned To:** Unassigned
**Created:** 2026-06-22
**Sprint:** Recette Manifestation, phase 3

---

## User Story

En tant que **comptable**,
je veux **exporter le rapport de recette en CSV et Excel**,
afin de **retraiter les données dans mon tableur ou mon logiciel comptable**.

---

## Description

### Background
La même structure de builder doit produire CSV et Excel, avec des totaux strictement identiques au PDF. Le plugin a déjà `renderers/csv_renderer.py` et `renderers/excel_renderer.py` réutilisables.

### Scope
**In scope :**
- Sérialisation tabulaire de la structure builder en CSV et XLSX.
- Réutilisation/extension de `csv_renderer.py` et `excel_renderer.py`.
- Colonnes dynamiques (PSP) reflétées dans les en-têtes tabulaires.
- Contrôle de réconciliation : totaux CSV/Excel = totaux PDF.

**Out of scope :**
- Mise en page riche (le PDF s'en charge).
- Enregistrement exporter / formulaire (STORY-106).

### User Flow
1. L'utilisateur choisit le format CSV ou Excel au lancement.
2. Le renderer sérialise la structure builder.
3. Le fichier est téléchargé, ré-importable sans corruption.

---

## Acceptance Criteria

- [ ] Export CSV produit, en-têtes incluant les colonnes de frais dynamiques.
- [ ] Export Excel (XLSX) produit avec les mêmes colonnes.
- [ ] Les totaux CSV/Excel sont strictement identiques à ceux du PDF (même structure builder).
- [ ] Encodage CSV UTF-8 (BOM si nécessaire pour Excel FR), séparateur cohérent, ré-importable sans corruption des accents.
- [ ] Montants au format exploitable (nombre ou texte FR documenté) ; devise indiquée.
- [ ] Découpage canal/séance reflété (colonnes ou feuilles selon le format).
- [ ] Cas sans frais / sans séance multiple géré sans colonne fantôme.

---

## Technical Notes

### Composants
- **Réutilisé/étendu :** `renderers/csv_renderer.py`, `renderers/excel_renderer.py` (openpyxl).
- **Consomme :** structure du builder (STORY-100 à 103).

### Points de vigilance
- Le renderer ne recalcule rien : il sérialise la structure (garantit l'égalité avec le PDF).
- Excel : envisager une feuille par canal + une feuille total, ou une colonne canal. Choisir et documenter.
- CSV pour Excel FR : BOM UTF-8 + séparateur point-virgule possible selon la locale ; documenter le choix.

### Edge cases
- Caractères accentués dans les noms de produits -> encodage strict.
- Colonnes de frais variables d'un export à l'autre -> en-têtes dynamiques.

---

## Dependencies

**Prerequisite :** STORY-100, 101, 102, 103.
**Blocks :** STORY-106 (intégration).
**External :** openpyxl (déjà utilisé par le plugin).

---

## Definition of Done

- [ ] CSV et XLSX implémentés.
- [ ] Test de réconciliation : totaux CSV = totaux Excel = totaux PDF.
- [ ] Test d'encodage (accents) sur réimport.
- [ ] Revue de code.
- [ ] Critères d'acceptation validés.

---

## Story Points Breakdown

- **Renderers CSV + Excel :** 2 points
- **Tests (réconciliation, encodage) :** 1 point
- **Total :** 3 points

**Rationale :** Renderers existants à étendre, complexité modérée ; l'essentiel est la réconciliation et l'encodage.

---

## Additional Notes

Parallélisable avec STORY-104 une fois le builder (100 à 103) terminé.

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
