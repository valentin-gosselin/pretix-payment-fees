# Technical Specification: Export comptable « Recette Manifestation »

**Date:** 2026-06-21
**Author:** goss
**Version:** 1.0
**Project Type:** Pretix plugin feature (nouvel exporter)
**Project Level:** Level 1 (1-10 stories)
**Status:** Draft

---

## Document Overview

Cette spécification technique décrit l'ajout d'un nouvel exporter comptable **« Recette Manifestation »** au plugin `pretix-payment-fees`, inspiré de la complétude du rapport Trium/TicketNet (réf. `docs/Recette Liberté.pdf`), adapté au modèle de données Pretix.

**Related Documents:**
- Modèle de référence : `docs/Recette Liberté.pdf` (rapport Trium « RECETTE MANIFESTATION »)
- Exporter existant (à conserver) : `pretix_payment_fees/exporters/accounting_report_psp.py`

---

## Problem & Solution

### Problem Statement

L'export comptable actuel (`accounting_report_psp.py`) est jugé **trop limité** : il se contente d'hériter du rapport comptable natif Pretix (`ReportExporter`) et d'**ajouter une seule section « Frais PSP »** à la fin. Il ne fournit ni la granularité ligne-à-ligne, ni la ventilation par type de frais, ni le découpage par canal de vente attendus par la billetterie. Le rapport Trium « Recette Manifestation » sert de référence de complétude : matrice détaillée Catégorie × Nature de clientèle, ventilation des frais sur chaque ligne **et** dans les totaux, bloc billetterie, et vue par séance avec TVA.

### Proposed Solution

Créer un **nouvel exporter autonome** `RecetteManifestationExporter` (n'héritant **pas** du `ReportExporter` natif, contrairement à l'existant) qui :

1. Agrège les données de commandes Pretix en une **matrice Catégorie (Item) × Nature de clientèle (Variation)**.
2. Ventile les frais en **une colonne par type de frais Pretix** (`OrderFee.FEE_TYPES` + `internal_type`), aussi bien sur chaque ligne que dans les sous-totaux/totaux.
3. Découpe le rapport **par canal de vente** (sales channel) : une section par canal + section TOTAL, avec possibilité de filtrer sur un canal unique au lancement.
4. Regroupe par **séance** = sous-événement Pretix (ou l'événement lui-même si pas de sous-événements).
5. Produit un **bloc billetterie** (Total payant / Invitations / Places échangées / e-ticket…) et affiche le **taux de TVA** depuis les `TaxRule` Pretix.
6. Est exportable en **PDF** (mise en page façon Trium) **et CSV/Excel**.

L'exporter actuel `accounting_report_psp` est **conservé** (les deux coexistent comme deux entrées d'export distinctes).

---

## Requirements

### What Needs to Be Built

- **REQ-1 — Matrice Catégorie × Nature de clientèle**
  Lignes = combinaison **Item (catégorie, ex. CARRE OR / CAT1)** × **Variation (nature, ex. NORMAL / CE / INVITATION)**.
  Colonnes de base : Quantité, Prix du billet (unitaire), Recette hors frais.
  *Critère d'acceptation :* pour un événement donné, chaque couple Item×Variation vendu apparaît sur une ligne, avec quantité et recette exactes.

- **REQ-2 — Colonnes dynamiques par type de frais**
  Une colonne par type de frais Pretix présent dans le périmètre. Source : `OrderFee` regroupés par `fee_type` (8 valeurs : `service`, `payment`, `shipping`, `cancellation`, `insurance`, `late`, `other`, `giftcard`) et, si renseigné, par `internal_type` pour un libellé plus fin.
  *Critère d'acceptation :* si l'organisateur a configuré 3 types de frais, le rapport affiche 3 colonnes de frais ; un type absent du périmètre n'a pas de colonne (ou colonne à 0,00 selon option de rendu).

- **REQ-3 — Frais sur chaque ligne ET dans les totaux**
  Les frais sont affichés au niveau de chaque ligne Item×Variation, des sous-totaux par catégorie, et du TOTAL général. Colonnes calculées : **Recette frais** (= recette hors frais + frais) et **Réddition de compte**.
  *Critère d'acceptation :* la somme des frais des lignes d'une catégorie = sous-total frais de la catégorie ; la somme des sous-totaux = total général (réconciliation exacte).

- **REQ-4 — Découpage par canal de vente**
  Mode par défaut : **une section par canal de vente** (`Order.sales_channel`) + une section TOTAL tous canaux. Mode alternatif : **filtre sur un canal unique** au lancement de l'export.
  *Critère d'acceptation :* la somme des sections par canal = section TOTAL ; le filtre canal restreint correctement le périmètre.

- **REQ-5 — Regroupement par séance (sous-événement)**
  Une « séance » = un **sous-événement Pretix** (`SubEvent`). Si l'événement n'a pas de sous-événements, l'événement entier constitue une séance unique. Vue détaillée par séance + vue croisée Catégorie × Séance (façon pages 2-3 de Trium).
  *Critère d'acceptation :* pour un événement à dates multiples, chaque date produit son bloc séance ; pour un événement simple, un seul bloc.

- **REQ-6 — Bloc billetterie**
  Tableau secondaire par catégorie : Total payant, Invitations, Places échangées, e-ticket / m-ticket (autres modes à 0 si non applicables Pretix).
  *Critère d'acceptation :* Total payant + Invitations cohérent avec le nombre de positions du périmètre.

- **REQ-7 — TVA par séance / ligne**
  Affichage du taux de TVA issu de la `TaxRule` Pretix associée au produit. Un taux par séance si homogène, sinon par ligne.
  *Critère d'acceptation :* le taux affiché correspond à la `TaxRule` réelle du produit dans Pretix.

- **REQ-8 — Périmètre payées + invitations**
  Inclut les commandes **payées** et les **invitations / places gratuites** (quantité comptée, recette 0,00). Exclut annulées/expirées.
  *Critère d'acceptation :* les invitations apparaissent en quantité avec 0,00 de recette ; les commandes annulées sont absentes.

- **REQ-9 — Sorties PDF + CSV/Excel**
  Rendu PDF mis en page façon Trium (via `renderers/` reportlab existants) **et** export tabulaire CSV/Excel (via `csv_renderer.py` / `excel_renderer.py`).
  *Critère d'acceptation :* les deux formats produisent les mêmes totaux ; le CSV est ré-importable dans un tableur sans corruption d'encodage (UTF-8 + séparateur cohérent).

- **REQ-10 — En-tête de rapport riche**
  Organisateur, Manifestation (+ identifiant), Lieu, Mode de comm / canal, date d'édition, période demandée.
  *Critère d'acceptation :* l'en-tête reflète les métadonnées réelles de l'événement Pretix.

### What This Does NOT Include

- Remplacement ou suppression de l'exporter `accounting_report_psp` existant (les deux coexistent).
- Reproduction littérale des colonnes Trium sans équivalent Pretix (« Frais de Salle », « Frais Magasin », « Frais de commercialisation ») : elles sont **remplacées** par les colonnes dynamiques issues des `OrderFee` réels (REQ-2).
- Nouvelle synchronisation/source de frais : on réutilise l'existant (`OrderFee` Pretix + `PSPTransactionCache` pour les frais PSP réels Mollie/SumUp). Aucun nouvel appel API PSP n'est ajouté.
- Multi-devises avancé au-delà de ce que gère déjà le plugin (regroupement par devise conservé si déjà présent).
- Modèle de données persistant nouveau (l'export est calculé à la volée, voir Data Model).

---

## Technical Approach

### Technology Stack

- **Langage / Framework :** Python 3.11+ / Django (plugin Pretix), API `BaseExporter` de Pretix.
- **Rendu PDF :** ReportLab (déjà utilisé par les renderers du plugin) + WeasyPrint déjà présent dans l'image.
- **Rendu tabulaire :** modules existants `renderers/csv_renderer.py`, `renderers/excel_renderer.py` (openpyxl).
- **Données :** ORM Django sur les modèles Pretix (`Order`, `OrderPosition`, `OrderFee`, `Item`, `ItemVariation`, `SubEvent`, `TaxRule`, `Order.sales_channel`) + modèle plugin `PSPTransactionCache`.
- **i18n :** gettext (8 langues déjà supportées par le plugin) — nouveaux libellés à traduire.
- **Tests :** pytest (dossier `tests/` existant).
- **Déploiement :** image Docker Pretix (`pretix/standalone`), conteneur `pretix-dev` pour le dev/test (commandes via `docker exec`).

### Architecture Overview

```
RecetteManifestationExporter (BaseExporter / ListExporter)
        │
        ├── export_form_render() ──► formulaire : événement(s), période,
        │                            mode canal (sections|filtre), format (PDF|CSV|XLSX)
        │
        ├── 1. RecetteDataBuilder  (services/recette_builder.py)
        │      ├── récupère OrderPosition (payées + invitations) du périmètre
        │      ├── groupe par : SalesChannel → SubEvent(séance) → Item(catégorie) → Variation(nature)
        │      ├── agrège quantité, recette HT/TTC, taux TVA (TaxRule)
        │      ├── ventile OrderFee par fee_type/internal_type → colonnes dynamiques
        │      ├── injecte frais PSP réels (PSPTransactionCache.amount_fee) par commande
        │      └── calcule sous-totaux catégorie + total général + bloc billetterie
        │
        └── 2. Renderers
               ├── RecettePDFRenderer   (renderers/recette_pdf_renderer.py)  ──► PDF façon Trium
               ├── csv_renderer (réutilisé/étendu)                            ──► CSV
               └── excel_renderer (réutilisé/étendu)                          ──► XLSX
```

Flux : le formulaire d'export collecte les filtres → `RecetteDataBuilder` produit une structure de données neutre (dict/dataclass) **indépendante du format** → le renderer choisi sérialise cette structure. Cette séparation builder/renderer garantit que PDF et CSV partagent exactement les mêmes totaux (REQ-9).

**Différence clé avec l'existant :** `accounting_report_psp` hérite du `ReportExporter` natif et patche son rendu. Le nouvel exporter est **autonome** : il construit sa propre structure de données, ce qui permet la matrice ligne-à-ligne, les colonnes dynamiques et le découpage canal/séance impossibles à obtenir en sur-héritant du rapport natif.

### Data Model (if applicable)

Aucun nouveau modèle persistant. Structure **calculée en mémoire** par le builder :

| Niveau | Clé de regroupement | Source Pretix | Mesures agrégées |
|--------|---------------------|---------------|------------------|
| Canal | `Order.sales_channel` | Order | Σ recette, Σ frais, Σ quantité |
| Séance | `OrderPosition.subevent` (ou Event) | SubEvent | idem + taux TVA |
| Catégorie | `OrderPosition.item` | Item | sous-totaux |
| Nature | `OrderPosition.variation` | ItemVariation | ligne de base |
| Frais (colonnes) | `OrderFee.fee_type` / `internal_type` | OrderFee | Σ par type |
| Frais PSP | par `Order` | PSPTransactionCache.amount_fee | rattaché à la commande |
| Billetterie | par Item | OrderPosition (payant vs invitation, mode de delivery) | comptages |

Champs Pretix de référence confirmés :
- `OrderFee.FEE_TYPES` = `service`, `payment`, `shipping`, `cancellation`, `insurance`, `late`, `other`, `giftcard` (+ `internal_type` libre).
- `Order.sales_channel` pour le canal de vente.
- `TaxRule` (via `Item.tax_rule` / position) pour le taux de TVA.

### API Design (if applicable)

Non applicable (pas d'endpoint REST). Point d'intégration = l'API d'export Pretix :
- Enregistrement de l'exporter via le signal `register_data_exporters` (et/ou `register_multievent_data_exporters`) dans `signals.py`.
- Implémentation de `BaseExporter` / `ListExporter` : `identifier`, `verbose_name`, `export_form_render`, `render()`.

---

## Implementation Plan

### Stories

1. **Builder d'agrégation (`RecetteDataBuilder`)** — service `services/recette_builder.py` qui produit la structure de données neutre (canal → séance → catégorie → nature), avec quantités, recettes et sous-totaux/total. Inclut le filtrage périmètre payées+invitations. *(cœur de la feature)*

2. **Ventilation des frais en colonnes dynamiques** — détection des `OrderFee.fee_type`/`internal_type` présents, agrégation par colonne sur chaque ligne + totaux, colonnes « Recette frais » et « Réddition de compte ». Intègre les frais PSP réels depuis `PSPTransactionCache`. *(REQ-2, REQ-3)*

3. **Découpage canal de vente + regroupement séance** — sections par canal + TOTAL, filtre canal unique au lancement ; regroupement par sous-événement (séance) avec fallback événement simple ; vue croisée Catégorie × Séance. *(REQ-4, REQ-5)*

4. **Bloc billetterie + TVA** — tableau payant/invitations/places échangées/e-ticket + affichage du taux de TVA par séance/ligne depuis `TaxRule`. *(REQ-6, REQ-7)*

5. **Renderer PDF façon Trium (`RecettePDFRenderer`)** — mise en page reportlab : en-tête riche, tableaux avec styles (sous-totaux grisés, total en gras), pagination, en-tête/pied de page. *(REQ-9, REQ-10)*

6. **Renderers CSV / Excel** — sérialisation de la même structure en CSV et XLSX, avec contrôle de réconciliation des totaux. *(REQ-9)*

7. **Enregistrement exporter + formulaire + i18n + tests** — câblage dans `signals.py`, formulaire d'export (mode canal, format, période), libellés traduits (8 langues), tests pytest de réconciliation des totaux sur un événement de fixture.

### Development Phases

Ordre logique recommandé : **1 → 2 → 3 → 4 → 5 → 6 → 7**.
Le builder (1-2) est la fondation testable indépendamment du rendu. Les renderers (5-6) consomment une structure déjà figée. La story 7 (câblage + tests + i18n) clôt et rend la feature livrable. Stories 5 et 6 parallélisables une fois 1-4 terminées.

---

## Acceptance Criteria

How we'll know it's done:

- [ ] Un nouvel export « Recette Manifestation » apparaît dans les exports Pretix, distinct de « Rapport comptable avec frais bancaires » (l'existant est conservé).
- [ ] Le PDF reproduit la structure Trium : matrice Catégorie × Nature, sous-totaux par catégorie, total général, bloc billetterie, vue par séance avec taux de TVA.
- [ ] Chaque type de frais Pretix configuré apparaît comme **colonne dédiée**, renseignée sur chaque ligne **et** dans les totaux.
- [ ] Les frais PSP réels (Mollie/SumUp) sont intégrés et le total réconcilie avec `PSPTransactionCache`.
- [ ] Le rapport est découpé **par canal de vente** (sections + TOTAL) et filtrable sur un canal unique.
- [ ] Les invitations sont comptées en quantité avec 0,00 de recette ; les annulées sont exclues.
- [ ] Réconciliation exacte : Σ lignes = sous-total catégorie ; Σ sous-totaux = total général ; Σ canaux = TOTAL.
- [ ] Export disponible en **PDF et CSV/Excel**, avec totaux identiques entre formats.
- [ ] Libellés traduits dans les 8 langues du plugin.
- [ ] Tests pytest de réconciliation des totaux passent sur un événement de fixture.
- [ ] Déployé et vérifié sur le conteneur `pretix-dev`.

---

## Non-Functional Requirements

### Performance

- L'agrégation doit tenir sur des événements de plusieurs milliers de positions sans timeout : privilégier des requêtes ORM agrégées (`values().annotate(Sum())`) plutôt que des boucles Python par commande. Réutiliser le caching Django existant du plugin pour les frais PSP. Génération PDF cible < quelques secondes pour un événement standard.

### Security

- Respecter les permissions Pretix existantes : l'export n'est accessible qu'aux utilisateurs ayant le droit sur l'organisateur/événement (mécanisme natif `BaseExporter`). Aucune donnée d'un autre organisateur ne doit fuiter (filtrage strict par `organizer`/`event`). Pas d'exposition de clés API PSP dans le rapport.

### Other

- **i18n :** 8 langues (parité avec le plugin). **Robustesse :** gérer proprement événement sans sous-événement, sans frais, sans transaction PSP (colonnes/sections à 0,00 plutôt que crash). **Encodage CSV :** UTF-8 (BOM si nécessaire pour Excel FR).

---

## Dependencies

- API d'export Pretix (`BaseExporter`/`ListExporter`, signaux `register_data_exporters`).
- Modèles Pretix : `Order` (`sales_channel`), `OrderPosition`, `OrderFee` (`FEE_TYPES`, `internal_type`), `Item`, `ItemVariation`, `SubEvent`, `TaxRule`.
- Modèle plugin existant : `PSPTransactionCache` (frais PSP réels) — dépend de la synchro PSP déjà en place.
- Renderers existants : `renderers/pdf_renderer.py`, `csv_renderer.py`, `excel_renderer.py` (à étendre).
- Environnement : conteneur `pretix-dev` opérationnel pour tests.

---

## Risks & Mitigation

- **Risk:** Le rattachement des frais PSP réels (au niveau commande) à la granularité ligne (Item×Variation) peut être ambigu.
  - **Mitigation:** Décision actée — colonnes **par type de frais** ; les frais PSP réels sont affichés au niveau commande/séance/total, pas répartis arbitrairement par ligne. Documenter clairement la maille de chaque colonne.

- **Risk:** Le champ `sales_channel` ou son API peut varier selon la version de Pretix.
  - **Mitigation:** Vérifier sur la version cible dans `pretix-dev` avant la story 3 ; isoler l'accès au canal derrière une petite fonction d'abstraction.

- **Risk:** Divergence de totaux entre PDF et CSV (deux chemins de rendu).
  - **Mitigation:** Builder unique produisant une structure neutre consommée par tous les renderers + test de réconciliation automatisé (story 7).

- **Risk:** Colonnes de frais trop nombreuses → débordement de la largeur de page PDF.
  - **Mitigation:** Largeur adaptative / regroupement des types rares sous « Autres » ; format paysage si nécessaire.

- **Risk:** Performance sur gros événements (boucle par commande pour les frais PSP).
  - **Mitigation:** Requêtes agrégées ORM + réutilisation du cache plugin ; jeu de test volumineux.

---

## Timeline

**Target Completion:** à définir avec goss (estimation : 5-8 jours de dev pour les 7 stories).

**Milestones:**
- M1 — Builder + ventilation frais testés unitairement (stories 1-2)
- M2 — Découpage canal/séance + billetterie/TVA (stories 3-4)
- M3 — Renderers PDF + CSV/XLSX (stories 5-6)
- M4 — Câblage, i18n, tests, déploiement `pretix-dev` (story 7)

---

## Approval

**Reviewed By:**
- [ ] goss (Author)
- [ ] Technical Lead
- [ ] Product Owner

---

## Next Steps

### Phase 4: Implementation

Projet **Level 1** (7 stories) :
- Run `/sprint-planning` pour organiser les stories et planifier l'implémentation.
- Puis `/create-story` puis `/dev-story` pour chaque story.

---

**This document was created using BMAD Method v6 - Phase 2 (Planning)**

*To continue: Run `/workflow-status` to see your progress and next recommended workflow.*
