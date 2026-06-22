# STORY-106: Enregistrement de l'exporter, formulaire, i18n et tests

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have (rend la feature livrable)
**Story Points:** 5
**Status:** Not Started
**Assigned To:** Unassigned
**Created:** 2026-06-22
**Sprint:** Recette Manifestation, phase 4

---

## User Story

En tant que **organisateur**,
je veux **trouver l'export « Recette Manifestation » dans l'interface Pretix avec ses options et dans ma langue**,
afin de **le lancer moi-même sans intervention technique**.

---

## Description

### Background
Les stories précédentes produisent le builder et les renderers. Cette story les câble dans Pretix : enregistrement de l'exporter, formulaire d'export, traductions, et tests d'intégration de réconciliation. C'est la story qui rend la feature utilisable et livrable.

### Scope
**In scope :**
- Classe exporter `RecetteManifestationExporter` (BaseExporter / ListExporter) autonome (n'hérite PAS du ReportExporter natif).
- Enregistrement via le signal `register_data_exporters` (et multi-event si pertinent) dans `signals.py`.
- Formulaire d'export : sélection période, mode canal (sections ou filtre canal unique), format (PDF / CSV / XLSX), statut de commande.
- i18n : nouveaux libellés traduits dans les 8 langues du plugin.
- Tests pytest d'intégration : réconciliation des totaux, génération des 3 formats sans erreur.
- L'exporter existant `accounting_report_psp` est conservé (coexistence).

**Out of scope :**
- Modification de la logique builder/renderers (figée dans les stories précédentes).

### User Flow
1. L'organisateur ouvre les exports de son événement.
2. Il sélectionne « Recette Manifestation ».
3. Il choisit période, mode canal, format.
4. Il lance et télécharge le rapport.

---

## Acceptance Criteria

- [ ] Un export « Recette Manifestation » apparaît dans Pretix, distinct de « Rapport comptable avec frais bancaires » (existant conservé).
- [ ] L'exporter est autonome (n'hérite pas du ReportExporter natif).
- [ ] Le formulaire propose : période, mode canal (sections / filtre canal unique), format (PDF/CSV/XLSX), statut de commande.
- [ ] Les 3 formats se génèrent sans erreur et avec des totaux identiques.
- [ ] Permissions Pretix respectées (accès limité aux droits sur l'organisateur/événement, pas de fuite inter-organisateur).
- [ ] Libellés traduits dans les 8 langues du plugin.
- [ ] Tests pytest d'intégration (réconciliation + génération 3 formats) passent.
- [ ] Déployé et vérifié sur le conteneur pretix-dev.

---

## Technical Notes

### Composants
- **Nouveau :** `exporters/recette_manifestation.py` (classe exporter + formulaire).
- **Modifié :** `signals.py` (enregistrement), fichiers `locale/*/LC_MESSAGES/django.po` (8 langues).
- **Consomme :** builder (100 à 103) + renderers (104, 105).

### API d'intégration Pretix
- `BaseExporter` / `ListExporter` : `identifier`, `verbose_name`, `export_form_render`, `render()`.
- Signal `register_data_exporters` (et `register_multievent_data_exporters` si export multi-événements souhaité).

### Sécurité
- S'appuyer sur le mécanisme de permissions natif des exporters Pretix. Filtrage strict par organizer/event. Ne pas exposer de clés API PSP.

### Déploiement
- Conteneur pretix-dev : plugin monté en editable sur `/plugins/pretix-payment-fees`. Tester via l'interface après redémarrage du worker si nécessaire.

### Edge cases
- Event sans frais / sans sous-événement / sans transaction PSP -> export valide (colonnes/sections vides ou à 0).

---

## Dependencies

**Prerequisite :** STORY-100, 101, 102, 103 (builder), STORY-104 (PDF), STORY-105 (CSV/Excel).
**Blocks :** aucune (story finale de l'epic).
**External :** environnement pretix-dev pour test/déploiement.

---

## Definition of Done

- [ ] Exporter enregistré et visible dans Pretix.
- [ ] Formulaire fonctionnel (période, canal, format, statut).
- [ ] 3 formats générés, totaux identiques.
- [ ] i18n 8 langues complétée.
- [ ] Tests d'intégration de réconciliation passent.
- [ ] Permissions vérifiées.
- [ ] Déployé et vérifié sur pretix-dev.
- [ ] Revue de code.
- [ ] Validation goss.

---

## Story Points Breakdown

- **Exporter + formulaire + signaux :** 3 points
- **i18n 8 langues :** 1 point
- **Tests d'intégration :** 1 point
- **Total :** 5 points

**Rationale :** Câblage Pretix, formulaire à options, traductions multiples, tests d'intégration de bout en bout.

---

## Additional Notes

Story de clôture de l'epic. Après elle, la feature est livrable. Conserver l'exporter `accounting_report_psp` existant.

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
