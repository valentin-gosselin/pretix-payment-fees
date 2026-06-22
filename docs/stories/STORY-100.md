# STORY-100: RecetteDataBuilder, service d'agrégation des recettes

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have (fondation de toute la feature)
**Story Points:** 5
**Status:** Done (code implémenté, validé sur données réelles, suite pytest verte 20/20)
**Assigned To:** goss
**Created:** 2026-06-22
**Sprint:** Recette Manifestation, phase 1

---

## User Story

En tant que **développeur du plugin**,
je veux **un service d'agrégation qui transforme les commandes Pretix en une structure de données neutre (canal vers séance vers catégorie vers nature)**,
afin que **les renderers PDF et CSV/Excel consomment exactement les mêmes totaux sans dupliquer la logique métier**.

---

## Description

### Background
La tech-spec impose une séparation builder/renderer : un service unique produit une structure de données indépendante du format de sortie. C'est la fondation des stories 101 à 106. Sans ce builder, aucun rendu n'est possible. Le builder remplace l'approche de l'exporter actuel `accounting_report_psp` (qui hérite du rapport natif Pretix et ne permet pas la granularité ligne à ligne).

### Scope
**In scope :**
- Nouveau service `services/recette_builder.py` exposant une classe `RecetteDataBuilder`.
- Récupération des `OrderPosition` du périmètre : commandes **payées** + **invitations / places gratuites** (recette 0). Exclusion des annulées/expirées.
- Agrégation hiérarchique : Canal de vente, puis Séance, puis Catégorie (Item), puis Nature (Variation).
- Mesures de base par ligne : quantité, prix unitaire, recette brute (Brut / Gross).
- Sous-totaux par catégorie et total général.
- Structure de retour neutre (dataclasses ou dicts) documentée et stable.

**Out of scope :**
- Ventilation des frais (STORY-101).
- Logique fine canal/séance et vue croisée (STORY-102).
- Bloc billetterie et TVA (STORY-103).
- Tout rendu (STORY-104, 105).

### User Flow (déclenchement développeur)
1. Le code appelle `RecetteDataBuilder(events, form_data).build()`.
2. Le builder requête l'ORM Pretix sur le périmètre payées+invitations.
3. Il agrège en structure hiérarchique.
4. Il retourne un objet neutre prêt à être sérialisé par un renderer.

---

## Acceptance Criteria

- [x] `RecetteDataBuilder` existe dans `services/recette_builder.py` et est importable.
- [x] Le périmètre inclut les commandes payées ET les invitations (quantité comptée, recette 0,00). Validé sur detonantes-2 : 37 invitations comptées à 0,00 €.
- [x] Les commandes annulées/expirées sont exclues (filtre `status__in=(STATUS_PAID,)`).
- [x] La structure retournée expose, par canal puis séance puis catégorie (Item) puis nature (Variation) : quantité, prix unitaire, recette brute.
- [x] Sous-totaux par catégorie cohérents (somme des natures = sous-total catégorie). Vérifié par assertions.
- [x] Total général cohérent (somme des sous-totaux = total). Vérifié : 2 578,00 € sur detonantes-2 (web 1919 + guichet 659).
- [x] Les requêtes sont agrégées au niveau ORM (`values().annotate(Count, Sum)`), une seule requête, pas de boucle Python par commande.
- [x] Cas limites gérés sans crash : event sans variation (nature « (default) », `is_single_line=True`), recette 0, liste d'events vide.
- [x] Tests unitaires de réconciliation : `tests/test_recette_builder.py` passe (pytest + pytest-django ajoutés aux deps dev du plugin ; suite complète 20/20 verte dans pretix-dev).

---

## Technical Notes

### Composants
- **Nouveau :** `pretix_payment_fees/services/recette_builder.py`.
- **Lecture ORM Pretix :** `Order` (filtre `status`), `OrderPosition` (`item`, `variation`, `subevent`, `price`), `Item`, `ItemVariation`.

### Mapping Pretix (figé)
- Catégorie = `OrderPosition.item` (Item).
- Nature = `OrderPosition.variation` (ItemVariation), libellé « (défaut) » si pas de variation.
- Séance = `OrderPosition.subevent` (SubEvent) ou l'événement si pas de sous-événement (détail complet en STORY-102 ; ici prévoir la clé).
- Canal = `Order.sales_channel` (détail STORY-102 ; ici prévoir la clé).

### Structure de retour proposée (à stabiliser)
```python
@dataclass
class RecetteLine:
    category: str          # Item name
    nature: str            # Variation value or "(défaut)"
    count: int
    unit_price: Decimal
    gross: Decimal
    fees: dict             # rempli en STORY-101, vide ici

@dataclass
class RecetteGroup:        # un niveau (canal / séance / catégorie)
    key: str
    lines: list
    subtotals: dict
```

### Périmètre des statuts
- Inclure `Order.STATUS_PAID`. Inclure les positions à prix 0 (invitations). Exclure `STATUS_CANCELED`, `STATUS_EXPIRED`. Statut paramétrable plus tard (STORY-106 via le formulaire).

### Edge cases
- Event sans variation : nature unique « (défaut) », pas de doublon détail/sous-total (décision STORY-000).
- Multi-devises : conserver le regroupement par devise si déjà géré dans le plugin.

### Performance
- Cible : plusieurs milliers de positions sans timeout. Requêtes agrégées obligatoires.

---

## Dependencies

**Prerequisite :** tech-spec, STORY-000 (décisions figées).
**Blocks :** STORY-101, 102, 103 (toutes consomment le builder), et indirectement 104/105/106.
**External :** aucune.

---

## Definition of Done

- [ ] Code implémenté dans `services/recette_builder.py`.
- [ ] Tests unitaires de réconciliation des totaux passent (fixture event payées + invitations).
- [ ] Structure de retour documentée (docstring) et stable.
- [ ] Pas de boucle Python par commande (vérifié).
- [ ] Revue de code.
- [ ] Critères d'acceptation validés.

---

## Story Points Breakdown

- **Backend (builder + requêtes ORM) :** 4 points
- **Tests :** 1 point
- **Total :** 5 points

**Rationale :** Cœur de la feature, requêtes d'agrégation non triviales, structure à concevoir proprement car consommée par tout le reste.

---

## Additional Notes

Respecter strictement les décisions figées dans STORY-000. Le builder ne fait AUCUN rendu : il ne connaît ni PDF ni CSV.

---

## Implementation Notes

- **Fichiers :** `services/recette_builder.py` (builder + dataclasses neutres `RecetteLine/RecetteCategory/RecetteSession/RecetteChannel/RecetteReport`), `tests/test_recette_builder.py` (pytest).
- **django-scopes (important pour les stories suivantes) :** Pretix protège l'ORM par `django_scopes`. Toute requête `Order/OrderPosition.objects` exige un `scope(organizer=...)` actif, fourni par l'exporter Pretix au runtime. Le builder n'active PAS le scope lui-même (il s'exécute dans le contexte de l'exporter). Les tests doivent l'activer (`scope(...)`/`scopes_disabled()`).
- **Mapping confirmé sur la version Pretix cible :** `Order.sales_channel` = FK vers `SalesChannel` (clé `__identifier`, label `__label`) ; `OrderPosition.subevent/item/variation/price` ; `STATUS_PAID="p"`.
- **Prix unitaire** = moyenne `gross/count` (les positions d'un même Item x Variation peuvent avoir des prix différents ; la moyenne est cohérente avec un rapport agrégé).
- **Deux copies du plugin** (piège STORY-000) : la source est `/docker/pretix_pluginexportfrais/...`, la copie montée dans `pretix-dev` est `/docker/pretix-dev/plugins/...`. Penser à synchroniser les deux lors des tests.
- **Reste pour la story suivante :** le champ `fees` des lignes est présent mais vide (rempli en STORY-101) ; séance toujours « Event » tant que les sous-événements ne sont pas gérés finement (STORY-102).

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.
- 2026-06-22 : Implémentée. Builder validé sur données réelles (event detonantes-2, 181 positions, 2 578,00 €, réconciliation exacte). Test pytest écrit. Statut In Review.

**Actual Effort:** ~5 points (conforme à l'estimation).

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
