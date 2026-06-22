# STORY-201: Exporter « Détail par commande » (export A)

**Epic:** Exports complémentaires (détail commandes + remplissage salle)
**Priority:** Must Have
**Story Points:** 3
**Status:** Done (implémenté, PDF/CSV/Excel validés, anti-PII testé, pytest vert)
**Assigned To:** Unassigned
**Created:** 2026-06-22
**Sprint:** Exports complémentaires, phase 1

---

## User Story

En tant que **organisateur / comptable**,
je veux **exporter le détail des commandes avec leurs frais bancaires**,
afin de **rapprocher chaque transaction avec mes relevés et auditer les frais**.

---

## Description

### Background
Le builder de STORY-200 produit une ligne par commande. Cette story le branche dans un exporter Pretix, avec formulaire et les 3 formats, réutilisant les renderers et le style sobre existants.

### Scope
**In scope :**
- `exporters/order_detail.py` (`RecetteOrdersExporter`, BaseExporter autonome).
- Formulaire : période, canal, statut, format (PDF/CSV/XLSX).
- Sérialisation via les renderers existants (PDF mis en page + CSV/Excel tabulaires) adaptés au schéma « commandes ».
- Enregistrement signals (data + multievent).
- i18n des nouveaux libellés.

**Out of scope :**
- Logique d'agrégation (STORY-200).

### User Flow
1. L'organisateur ouvre les exports de l'événement.
2. Sélectionne « Détail par commande ».
3. Choisit période/canal/statut/format.
4. Télécharge le fichier (une ligne par commande).

---

## Acceptance Criteria

- [ ] Export « Détail par commande » apparaît dans Pretix, distinct de « Recettes détaillées ».
- [ ] Formulaire : période, canal, statut, format.
- [ ] PDF/CSV/Excel générés, style indigo sobre cohérent.
- [ ] Colonnes : code, date, canal, nb places, catégories, montant, frais par PSP. Pas d'email/nom.
- [ ] Totaux en pied (nb commandes, total places, total montant, total frais).
- [ ] Réconciliation des frais avec Pretix.
- [ ] Permissions Pretix natives respectées.
- [ ] Libellés traduits (8 langues).

---

## Technical Notes

### Composants
- **Nouveau :** `exporters/order_detail.py`. **Modifié :** `signals.py` (enregistrement).
- **Réutilise :** renderers PDF/CSV/Excel (généraliser légèrement pour accepter un schéma de colonnes « commandes », ou ajouter une variante tabulaire dédiée).

### Rendu
- Le PDF reprend le même style (bandeau titre, filets indigo, totaux). Tableau large (beaucoup de colonnes possibles) -> envisager paysage si nécessaire pour A uniquement, ou colonnes compactes.
- CSV/Excel : réutiliser le pattern `recette_tabular` (flatten -> writers).

### Edge cases
- Beaucoup de commandes (pagination PDF, repeatRows).
- Catégories longues -> tronquer ou retour ligne.

---

## Dependencies

**Prerequisite :** STORY-200 (builder A), infra renderers.
**Blocks :** STORY-203 (tests/i18n/release globale).
**External :** pretix-dev pour test.

---

## Definition of Done

- [ ] Exporter enregistré et visible dans Pretix.
- [ ] 3 formats fonctionnels, sans PII.
- [ ] i18n complétée.
- [ ] Tests (génération, réconciliation, absence PII) passent.
- [ ] Déployé/vérifié sur pretix-dev.

---

## Story Points Breakdown

- **Exporter + formulaire + signaux + rendu :** 2 points
- **Tests + i18n :** 1 point
- **Total :** 3 points

**Rationale :** Câblage réutilisant l'infra ; l'essentiel de la logique est dans STORY-200.

---

## Additional Notes

Suivre les décisions figées : style sobre indigo, vocabulaire Pretix FR via gettext, zéro em-dash.

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
