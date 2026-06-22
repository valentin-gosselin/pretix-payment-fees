# STORY-104: Renderer PDF « Recette Manifestation »

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have
**Story Points:** 5
**Status:** Not Started
**Assigned To:** Unassigned
**Created:** 2026-06-22
**Sprint:** Recette Manifestation, phase 3

---

## User Story

En tant que **organisateur**,
je veux **télécharger le rapport de recette en PDF lisible et mis en page**,
afin de **l'archiver, l'imprimer et le transmettre à ma comptabilité**.

---

## Description

### Background
La maquette validée (STORY-000, `docs/mock_recette_manifestation.pdf`) fixe le layout cible. Cette story implémente le renderer PDF réel qui sérialise la structure du builder (STORY-100 à 103) en respectant exactement les décisions figées.

### Scope
**In scope :**
- `renderers/recette_pdf_renderer.py` consommant la structure du builder.
- Respect strict des décisions figées STORY-000 (voir critères).
- En-tête riche, sections par canal, tableaux, totaux, bloc billetterie, taux TVA.

**Out of scope :**
- CSV/Excel (STORY-105).
- Enregistrement exporter et formulaire (STORY-106).

### User Flow
1. L'exporter passe la structure du builder au renderer PDF.
2. Le renderer produit le PDF mis en page.
3. L'utilisateur télécharge le fichier.

---

## Acceptance Criteria (décisions figées STORY-000)

- [ ] Orientation **A4 portrait**.
- [ ] Police **OpenSans** embarquée (accents corrects) ; pas de Helvetica par défaut.
- [ ] **Largeurs de colonnes dynamiques** (auto-fit), aucun débordement de texte.
- [ ] Texte en **français**, vocabulaire **Pretix natif** (Produit, Brut, Recette nette, Quantité, Canal de vente, Taux de TVA).
- [ ] **Aucun em-dash** dans le document.
- [ ] Montants avec symbole **€**, format FR (`1 234,56 €`) ; quantité en entier nu.
- [ ] **Une colonne de frais par PSP** (`internal_type`), dynamique.
- [ ] En-tête riche (Organisateur, Événement + slug, Date, Lieu, Devise, Édité le).
- [ ] Section par canal de vente + ligne TOTAL par canal + section Total tous canaux.
- [ ] Une seule ligne par produit (pas de doublon détail/sous-total quand une seule nature).
- [ ] Bloc billetterie et taux de TVA rendus (STORY-103).
- [ ] Styles : en-tête tableau fond sombre/texte blanc ; ligne TOTAL fond gris + gras ; montants alignés à droite.
- [ ] Le PDF généré sur l'event detonantes-2 reproduit visuellement la maquette validée.

---

## Technical Notes

### Composants
- **Nouveau :** `renderers/recette_pdf_renderer.py`.
- **Réutilise :** patterns du mock `docs/mock_recette_manifestation.py` (auto_widths, enregistrement OpenSans, euro()).
- **Lib :** reportlab (présent), OpenSans depuis `pretix/static/fonts/`.

### Points de vigilance
- Trop de colonnes PSP -> débordement largeur : regrouper les types rares ou réduire la police ; rester en portrait (décision figée). Documenter le seuil de bascule éventuel.
- Pagination : en-tête/pied de page, répétition de l'en-tête de tableau sur les pages suivantes.
- Le renderer ne recalcule RIEN : il ne fait que sérialiser la structure du builder (garantit l'égalité des totaux avec CSV/Excel).

### Edge cases
- Aucune colonne de frais (event sans frais) -> tableau valide sans colonne frais.
- Section canal vide -> non rendue.

---

## Dependencies

**Prerequisite :** STORY-100, 101, 102, 103 (structure complète), STORY-000 (layout figé).
**Blocks :** STORY-106 (intégration dans l'exporter).
**External :** reportlab + OpenSans (présents dans pretix-dev).

---

## Definition of Done

- [ ] `recette_pdf_renderer.py` implémenté.
- [ ] PDF reproduit la maquette validée sur detonantes-2.
- [ ] Toutes les décisions figées STORY-000 respectées (checklist ci-dessus).
- [ ] Test : génération sans erreur + cohérence des totaux affichés vs structure.
- [ ] Revue de code.
- [ ] Critères d'acceptation validés.

---

## Story Points Breakdown

- **Renderer (mise en page, styles, pagination) :** 4 points
- **Tests / vérification visuelle :** 1 point
- **Total :** 5 points

**Rationale :** Mise en page reportlab détaillée, gestion pagination et largeurs dynamiques, fidélité à la maquette.

---

## Additional Notes

Référence visuelle : `docs/mock_recette_manifestation.pdf`. Le générateur mock sert de base de code mais doit être porté proprement dans `renderers/` et consommer le builder, pas des données en dur.

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
