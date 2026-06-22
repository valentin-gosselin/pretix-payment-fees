# STORY-105: Renderers CSV et Excel

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have
**Story Points:** 3
**Status:** Done (implémenté, CSV+Excel générés sur l'event de démo, réconciliation OK, pytest 43/43)
**Assigned To:** goss
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

- [x] Export CSV produit, en-têtes incluant les colonnes de frais dynamiques (une par PSP).
- [x] Export Excel (XLSX) produit avec les mêmes colonnes.
- [x] Totaux CSV/Excel strictement identiques (même `flatten()`), et identiques au PDF (même builder). Vérifié par `test_csv_and_excel_totals_match`.
- [x] CSV UTF-8 **avec BOM** (Excel FR), séparateur `;`, décimales FR (virgule), accents préservés.
- [x] Montants exploitables : Excel = **nombres réels** (format cellule €) ; CSV = texte FR (virgule décimale).
- [x] Découpage canal/séance reflété en colonnes (Canal de vente, Séance) + colonne `Type de ligne` (detail/subtotal/total/grand_total).
- [x] Cas sans frais / report vide gérés sans colonne fantôme (`test_empty_report_renders_both`).
- [x] Suite pytest verte : 43/43.

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

## Implementation Notes

- **Fichiers :** `renderers/recette_tabular.py` (aplatissement commun `flatten()` + `column_headers()`), `renderers/recette_csv_renderer.py`, `renderers/recette_excel_renderer.py`. Tests : `tests/test_recette_tabular_renderers.py` (8 tests).
- **Source unique de vérité :** CSV et Excel sérialisent la MÊME sortie de `flatten(report)` -> totaux garantis identiques entre eux et avec le PDF (qui consomme le même builder).
- **Format tabulaire :** une ligne par ligne de tableau (detail), + lignes subtotal/total/grand_total marquées par une colonne `Type de ligne`. Colonnes : Canal de vente, Séance, Produit, Nature, Taux de TVA, Quantité, Prix unitaire, Brut, <frais dynamiques>, Recette nette.
- **CSV :** UTF-8 BOM, séparateur `;`, décimales virgule (Excel FR).
- **Excel :** openpyxl, montants en nombres réels (format `# ##0.00 €`), en-tête + totaux stylés (indigo léger), colonne technique `Type de ligne` retirée du rendu, autosize, freeze de la 1ʳᵉ ligne.
- **i18n :** libellés FR en constantes (comme STORY-104), gettext complet en STORY-106.
- **Démo :** `docs/recette_demo.csv` + `docs/recette_demo.xlsx`. pytest 43/43.

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.
- 2026-06-22 : Implémentée. CSV + Excel via aplatissement commun, réconciliation avec le PDF. pytest 43/43. Statut Done.

**Actual Effort:** ~3 points (conforme).

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
