# Technical Specification: Exports complémentaires (détail commandes + remplissage salle)

**Date:** 2026-06-22
**Author:** goss
**Version:** 1.0
**Project Type:** Pretix plugin feature (2 nouveaux exporters)
**Project Level:** Level 1 (1-10 stories)
**Status:** Draft

---

## Document Overview

Cette spécification décrit deux nouveaux exports pour le plugin `pretix-payment-fees`, en complément de l'export « Recettes détaillées » (v1.1.x, déjà en prod) :

- **Export A — Détail par commande** : une ligne par commande, orienté audit/comptable, avec le détail des frais bancaires par transaction.
- **Export B — Remplissage de salle** : comptage des ventes par catégorie, orienté partenaires/production, **sans valeurs comptables**.

**Related Documents:**
- Tech-spec de référence : `docs/tech-spec-recette-manifestation-2026-06-21.md`
- Infra existante réutilisée : `services/recette_builder.py`, `renderers/recette_pdf_renderer.py`, `recette_tabular.py`, `recette_csv_renderer.py`, `recette_excel_renderer.py`

---

## Problem & Solution

### Problem Statement

L'export « Recettes détaillées » agrège les ventes par produit/séance/canal, ce qui est parfait pour la compta consolidée mais ne répond pas à deux besoins distincts : (1) un **détail transaction par transaction** (une ligne par commande, avec ses frais réels) pour l'audit ou le rapprochement bancaire, et (2) un état **simple et non financier** du remplissage de la salle, à partager avec des partenaires/producteurs qui n'ont pas à voir les montants.

### Proposed Solution

Ajouter deux exporters Pretix autonomes, réutilisant l'infrastructure existante (renderers PDF/CSV/Excel, style indigo sobre, i18n) :
- **Export A** liste les commandes du périmètre, une ligne chacune, avec code+date, canal, nb de places, catégories achetées, montant et frais PSP détaillés par fournisseur.
- **Export B** produit un comptage par catégorie (nb de places vendues, payant vs invitations), sans aucune valeur monétaire, dans une mise en page épurée façon « feuille de salle ».

---

## Requirements

### What Needs to Be Built

**Export A — Détail par commande**

- **A-REQ-1 — Une ligne par commande**
  Chaque commande du périmètre = une ligne. Colonnes : code commande, date, canal de vente, nombre de places, catégories achetées (avec quantité, ex. « Tarif plein x2, Réduit x1 »), montant total.
  *Critère :* le nombre de lignes = nombre de commandes du périmètre ; les comptages de places se réconcilient avec l'export principal.

- **A-REQ-2 — Frais PSP détaillés par commande**
  Affichage des frais bancaires réels de la commande, par fournisseur (Mollie/SumUp), depuis `OrderFee`. Une colonne par PSP présent (dynamique), ou une colonne « Frais » + une colonne « Fournisseur » selon le rendu retenu.
  *Critère :* la somme des frais des lignes = total des frais PSP de l'événement (réconciliation exacte avec Pretix).

- **A-REQ-3 — Pas de donnée personnelle**
  L'email et le nom de l'acheteur ne sont PAS inclus (RGPD). Seul le code commande identifie la transaction.
  *Critère :* aucun champ email/nom dans l'export.

- **A-REQ-4 — 3 formats**
  PDF, CSV, Excel, via les renderers existants.

**Export B — Remplissage de salle**

- **B-REQ-1 — Comptage par catégorie**
  Une ligne par catégorie (Item) : nombre de places vendues, dont payant et invitations. Total général.
  *Critère :* « 10 Tarif plein, 5 Réduit, 3 Invitations… » ; total cohérent avec le périmètre.

- **B-REQ-2 — Aucune valeur monétaire**
  Pas de prix, pas de recette, pas de frais. Uniquement des comptages.
  *Critère :* aucun montant € dans l'export.

- **B-REQ-3 — Mise en page épurée**
  PDF simple et lisible (façon feuille de salle), réutilisant le style sobre. En-tête : événement, date, lieu, total places.

- **B-REQ-4 — 3 formats**
  PDF, CSV, Excel.

### What This Does NOT Include

- Données personnelles des acheteurs (export A : pas d'email/nom).
- Ventilation par siège/placement (pas de plan de salle).
- Pour l'export B : aucune dimension financière, ni détail par séance par défaut (option possible plus tard).
- Nouvelle source de données : on réutilise `OrderPosition`/`OrderFee` et le builder existant.

---

## Technical Approach

### Technology Stack

- **Langage / Framework :** Python 3.11+ / Django, API `BaseExporter` Pretix.
- **Rendu :** renderers existants ReportLab (PDF) + `recette_tabular`/openpyxl (CSV/Excel), style indigo sobre.
- **Données :** ORM Pretix (`Order`, `OrderPosition`, `OrderFee`, `Item`, `SalesChannel`).
- **i18n :** gettext (8 langues), même mécanisme que l'export principal.
- **Tests :** pytest + pytest-django.

### Architecture Overview

```
Export A (RecetteOrdersExporter)              Export B (RemplissageSalleExporter)
        │                                              │
        ├── OrderDetailBuilder                         ├── réutilise RecetteDataBuilder
        │   (1 ligne / commande : code, date,          │   (comptages déjà calculés :
        │    canal, places, catégories, montant,       │    paid_count / free_count par
        │    frais OrderFee par PSP)                    │    catégorie via .ticketing())
        │                                              │
        └── renderers (PDF/CSV/Excel réutilisés)       └── renderers (PDF/CSV/Excel réutilisés)
```

Décision : **réutiliser l'infra existante**.
- Export B s'appuie quasi entièrement sur le builder existant (le bloc billetterie `report.ticketing()` fait déjà le comptage payant/invitation par catégorie). Travail = un renderer « feuille de salle » épuré + l'exporter.
- Export A nécessite un **petit builder dédié** (`OrderDetailBuilder`) car la maille est la commande, pas l'agrégat produit. Il réutilise la logique de frais par `internal_type` et le format tabulaire `recette_tabular`.

### Data Model (if applicable)

Aucun modèle persistant. Structures calculées :

| Export | Maille | Source | Mesures |
|--------|--------|--------|---------|
| A | commande | `Order` + ses `OrderPosition`/`OrderFee` | nb places, catégories (agrégées), montant, frais par PSP |
| B | catégorie (Item) | `OrderPosition` (réutilise builder) | places payantes, invitations, total |

### API Design (if applicable)

Non applicable. Intégration via `register_data_exporters` (+ multievent), comme l'export principal.

---

## Implementation Plan

### Stories

1. **OrderDetailBuilder (export A)** — service produisant une ligne par commande : code, date, canal, nb places, catégories agrégées (« Tarif plein x2 »), montant, frais par PSP. Réconciliation des frais avec le total Pretix. *(cœur de A)*

2. **RecetteOrdersExporter (export A)** — exporter Pretix + formulaire (période, canal, statut, format), branché sur le builder A et les renderers existants ; enregistrement signals. PDF/CSV/Excel. i18n.

3. **Renderer + RemplissageSalleExporter (export B)** — exporter Pretix réutilisant `RecetteDataBuilder.ticketing()` ; renderer « feuille de salle » épuré (PDF) + CSV/Excel sans montants ; formulaire (période, canal, format) ; i18n ; signals.

4. **Tests + release** — tests pytest (réconciliation A, comptages B, 3 formats chacun, pas de PII/montant), i18n des nouveaux libellés (8 langues), bump version, release PyPI + déploiement prod.

### Development Phases

Ordre : **1 → 2 → 3 → 4**. L'export B (story 3) est parallélisable avec A (1-2) car il dépend du builder existant, pas du builder A. La story 4 clôt (tests + i18n + release).

---

## Acceptance Criteria

- [ ] Export A « Détail par commande » apparaît dans Pretix, distinct de « Recettes détaillées ».
- [ ] Export A : une ligne par commande, sans email/nom ; frais PSP par fournisseur ; réconciliation exacte du total des frais.
- [ ] Export B « Remplissage de salle » apparaît dans Pretix.
- [ ] Export B : comptage par catégorie (payant/invitations/total), aucun montant €.
- [ ] Les deux exports disponibles en PDF, CSV et Excel, avec le style sobre indigo.
- [ ] Libellés traduits dans les 8 langues.
- [ ] Tests pytest passent (réconciliation, comptages, formats, absence de PII/montant).
- [ ] Déployé en prod et vérifié.

---

## Non-Functional Requirements

### Performance
Requêtes ORM agrégées ; export A sur des milliers de commandes sans timeout (une requête par commande proscrite : agrégation par `values().annotate()`).

### Security
Permissions Pretix natives (`BaseExporter`). Export A : **pas de donnée personnelle** (RGPD). Pas d'exposition de clés PSP.

### Other
i18n 8 langues. Robustesse : événement sans frais / sans vente géré sans crash. Encodage CSV UTF-8 BOM.

---

## Dependencies

- Infra existante : `RecetteDataBuilder` (export B), renderers, `recette_tabular`, exporter pattern.
- Modèles Pretix : `Order`, `OrderPosition`, `OrderFee`, `Item`, `SalesChannel`.
- Environnement : conteneur `pretix-dev` pour dev/test ; chaîne de release PyPI + `update.sh` prod.

---

## Risks & Mitigation

- **Risk:** Agrégation des catégories par commande (« Tarif plein x2, Réduit x1 ») coûteuse si faite en Python par commande.
  - **Mitigation:** agréger via `string_agg`/annotations ORM ou une requête positions groupée par commande, puis assemblage léger.

- **Risk:** Frais par commande dans l'export A vs réconciliation globale (arrondis).
  - **Mitigation:** afficher les frais `OrderFee` réels par commande (pas de répartition) : la somme est exacte par construction.

- **Risk:** Export B trop proche de l'export principal (redondance perçue).
  - **Mitigation:** B est volontairement minimal et sans €, ciblé partenaires ; valeur = simplicité et absence de donnée sensible.

- **Risk:** Donnée personnelle introduite par erreur dans A.
  - **Mitigation:** test explicite vérifiant l'absence d'email/nom dans la sortie.

---

## Timeline

**Target Completion:** à définir avec goss (estimation : 3-5 jours pour les 4 stories).

**Milestones:**
- M1 — Export A (builder + exporter) testé (stories 1-2)
- M2 — Export B (renderer + exporter) testé (story 3)
- M3 — i18n + tests + release prod (story 4)

---

## Approval

**Reviewed By:**
- [ ] goss (Author)
- [ ] Technical Lead
- [ ] Product Owner

---

## Next Steps

### Phase 4: Implementation

Projet **Level 1** (4 stories) :
- Run `/sprint-planning` pour organiser, ou `/bmad:create-story` pour détailler la première story (OrderDetailBuilder).
- Puis `/bmad:dev-story` pour implémenter.

---

**This document was created using BMAD Method v6 - Phase 2 (Planning)**
