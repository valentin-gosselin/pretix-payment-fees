# STORY-000: Maquette PDF (spike) de l'export « Recette Manifestation »

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have (pré-requis de cadrage avant implémentation)
**Story Points:** 2
**Status:** Done (maquette validée par goss le 2026-06-22, décisions de layout figées)
**Assigned To:** goss
**Created:** 2026-06-21
**Closed:** 2026-06-22
**Sprint:** Spike / Story 0

---

## User Story

En tant que **goss (organisateur / product owner du plugin)**,
je veux **valider une maquette PDF du futur export « Recette Manifestation » avec des données réelles**,
afin de **figer la mise en page, le vocabulaire, les colonnes et la structure AVANT d'écrire la logique d'agrégation réelle**, et éviter de coder un rendu qui ne correspond pas à l'attendu.

---

## Description

### Background
La tech-spec [`tech-spec-recette-manifestation-2026-06-21.md`](../tech-spec-recette-manifestation-2026-06-21.md) définit un nouvel exporter complet inspiré du rapport Trium (`docs/Recette Liberté.pdf`). Avant d'implémenter le `RecetteDataBuilder` et les renderers réels (stories 1-7), il fallait valider le visuel cible sur une maquette. C'est un *spike* : produire un PDF d'exemple, le faire valider, et **figer les décisions** qui serviront de référence au renderer PDF réel.

### Résultat
Maquette produite avec de **vraies données Pretix** (base locale `pretix-dev`, organisateur Gosselico, event « Les Détonantes #2 »), itérée sur plusieurs cycles de retour goss, puis validée. Les décisions de layout/vocabulaire sont figées (voir section dédiée ci-dessous).

### Scope
**In scope (réalisé) :**
- Générateur reportlab **standalone** (sans Django) avec données réelles extraites de `pretix-dev`.
- Structure : matrice Produit, découpage par canal de vente + total, colonnes de frais PSP dynamiques.
- Validation visuelle par goss + gel des décisions.

**Out of scope (relève des stories 1-7) :**
- Logique d'agrégation sur l'ORM Pretix (stories 1-4).
- Intégration comme exporter Pretix réel / formulaire / signaux (story 7).
- Export CSV/Excel (story 6).
- i18n multi-langues (story 7).
- Bloc billetterie détaillé et vue par séance/sous-événement (stories 4-5).

---

## Décisions de layout FIGÉES (référence contractuelle pour STORY-005)

Ces choix ont été validés par goss et **doivent être respectés** par le renderer PDF réel.

### Format & police
- **Orientation : A4 portrait** (économie de papier ; le landscape était surdimensionné).
- **Police : OpenSans** (TTF natif de Pretix, `static/fonts/OpenSans-Regular.ttf` + `OpenSans-Bold.ttf`), embarquée dans le PDF. Helvetica par défaut de reportlab **ne rend pas les accents** : OpenSans est obligatoire.
- **Largeurs de colonnes dynamiques** (auto-fit au contenu via `stringWidth`), jamais fixes : aucun texte ne doit déborder. 1ʳᵉ colonne (Produit) plafonnée.

### Langue & vocabulaire
- **Texte en français.**
- **Vocabulaire natif Pretix** (vérifié dans son `django.po` FR), PAS le vocabulaire arbitraire de Trium :
  - Produit (et non « Catégorie / Nature de clientèle »)
  - Brut (Gross), Recette nette (Net), Quantité (Count), Prix unitaire
  - Canal de vente, Taux de TVA, Organisateur, Lieu
- **Aucun em-dash** nulle part (règle goss systématique) : utiliser parenthèses, `|` ou reformuler.

### Devises
- Tous les **montants affichent le symbole `€`** au format FR : `1 234,56 €` (espace pour milliers, virgule décimale). La quantité reste un entier nu.
- Ligne **Devise : EUR** dans l'en-tête.

### Frais PSP : colonnes dynamiques par prestataire (Option 2 retenue)
- **Une colonne par PSP**, dérivée du champ `OrderFee.internal_type` (et non une colonne unique « payment » regroupant tout).
- Le jeu de colonnes est l'**union des `internal_type` réellement présents** dans le périmètre, généré automatiquement. 0 colonne config à faire.
- Labels lisibles mappés pour les PSP connus (`mollie_creditcard_fee` → « Frais Mollie (CB) », `sumup_fee` → « Frais SumUp »…) ; **fallback humanisé** pour tout type inconnu (`xyz_fee` → « Frais Xyz »).
- Les **frais de service** (`fee_type=service`) et autres types `OrderFee` natifs Pretix suivront la même logique dynamique le jour où ils existeront dans les données (aucun présent aujourd'hui chez Gosselico).
- **Recette nette = Brut − somme des frais** de la ligne.

### Structure du document
- En-tête riche : Organisateur, Événement (+ slug), Date, Lieu, Devise, Édité le.
- **Une section par canal de vente** (titre « Canal de vente : <nom> (taux de TVA X) »), tableau Produit | Quantité | Prix unitaire | Brut | <colonnes PSP…> | Recette nette + **ligne TOTAL** par canal.
- **Une seule ligne par Produit** ; pas de doublon détail/sous-total quand un produit n'a qu'une ligne (le sous-total par catégorie n'apparaît que s'il y a plusieurs natures/variations sous une catégorie).
- Section finale **« Total tous canaux de vente »**.
- Styles : en-tête de tableau fond sombre/texte blanc ; ligne TOTAL fond gris + gras ; montants alignés à droite.

---

## Acceptance Criteria

- [x] Générateur standalone : [`docs/mock_recette_manifestation.py`](../mock_recette_manifestation.py).
- [x] PDF produit : [`docs/mock_recette_manifestation.pdf`](../mock_recette_manifestation.pdf).
- [x] En-tête riche (Organisateur, Événement, Date, Lieu, Devise, Édité le).
- [x] Une section par canal de vente + total tous canaux.
- [x] Matrice Produit avec Quantité, Prix unitaire, Brut, Recette nette.
- [x] **Colonnes de frais PSP dynamiques par `internal_type`** (Mollie CB + SumUp démontrés), frais sur chaque ligne et dans les totaux.
- [x] Texte en **français**, vocabulaire **Pretix**, **devises €**, **accents** corrects.
- [x] **Portrait A4**, largeurs dynamiques, espacements propres, zéro em-dash.
- [x] **Validation visuelle par goss** (2026-06-22).
- [x] **Décisions de layout figées** (section ci-dessus).

---

## Technical Notes

### Livrables
- `docs/mock_recette_manifestation.py` (générateur reportlab, données réelles).
- `docs/mock_recette_manifestation.pdf` (sortie de référence).

### Données réelles utilisées
Event `detonantes-2` (Gosselico), commandes payées : 2 canaux (Boutique en ligne `web`, Guichet `api.guichet`), produits réels (Tarif plein, Tarif étudiant / demandeur d'emploi, Destination Rennes…, Invitation), frais PSP réels Mollie CB 26,93 €. Un montant SumUp (3,25 €, réel sur l'event `mansion-gondhawa`) a été ajouté au guichet pour démontrer la 2ᵉ colonne PSP.

### Contrainte d'exécution (environnement)
Le conteneur `pretix-dev` monte `/docker/pretix-dev/plugins/pretix-payment-fees` (PAS `/docker/pretix_pluginexportfrais/...` : deux copies du plugin coexistent). Le dossier monté est read-only pour le process → écrire le PDF dans `/tmp` puis `docker cp`. Commande de génération :
```bash
sed 's#OUT = ".*"#OUT = "/tmp/mock_recette_manifestation.pdf"#' \
  docs/mock_recette_manifestation.py | docker exec -i pretix-dev python3 -
docker cp pretix-dev:/tmp/mock_recette_manifestation.pdf docs/mock_recette_manifestation.pdf
```

### Notes pour le renderer réel (STORY-005)
- Le builder lira `Item.name`, `ItemVariation.value`, `OrderFee.fee_type`/`internal_type`, `Order.sales_channel`, `TaxRule.rate` via l'ORM → les accents seront exacts par construction (le mock les avait à la main, source d'un bug corrigé).
- Le calcul « répartition des frais PSP au prorata de la recette » du mock est une **approximation de présentation**. Le builder réel rattachera les frais PSP à la maille décidée en spec (commande/séance/total) ; la répartition par ligne reste à confirmer côté comptable.
- Edge cases à gérer (absents du mock) : event sans variation, sans frais, sans transaction PSP → colonnes/sections à 0,00 € plutôt que crash.

---

## Dependencies

**Prerequisite :** tech-spec (faite), conteneur `pretix-dev` + reportlab + OpenSans (confirmés).
**Blocks :** STORY-005 (renderer PDF réel) consomme les décisions figées ici ; sert de cible visuelle aux stories 1-4 (builder).
**External :** aucune.

---

## Definition of Done

- [x] Générateur mock committable dans `docs/`.
- [x] PDF d'exemple généré et lisible.
- [x] PDF revu et **approuvé par goss**.
- [x] Ajustements de layout intégrés (portrait, FR, Pretix vocab, €, accents, PSP dynamiques, espacements).
- [x] **Décisions de layout consignées** comme référence pour STORY-005.
- [x] Statut **Done**.

---

## Story Points Breakdown

- **Génération mock + itérations layout :** 2 points.
- **Total :** 2 points.

**Rationale :** Spike de cadrage à faible incertitude technique. Plusieurs cycles d'itération visuelle avec goss (portrait, vocabulaire Pretix, devises, accents, colonnes PSP dynamiques).

---

## Additional Notes

- Spike **jetable** : le code mock standalone n'est pas l'implémentation finale. Le renderer réel (STORY-005) réutilisera les renderers du plugin (`renderers/`) avec la structure du `RecetteDataBuilder`, mais **doit reproduire le layout figé ici**.
- Référence visuelle d'origine : `docs/Recette Liberté.pdf` (Trium / TicketNet) — pour la complétude, pas pour le vocabulaire.

---

## Progress Tracking

**Status History:**
- 2026-06-21 : Créée ; mock généré (données factices initiales).
- 2026-06-22 : Itérations sur données réelles pretix-dev (vocabulaire Pretix FR, devises €, accents, portrait, espacements, colonnes PSP dynamiques par internal_type). Validée par goss. Décisions figées. Statut Done.

**Actual Effort:** ~2 points (plusieurs cycles d'itération visuelle).

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
