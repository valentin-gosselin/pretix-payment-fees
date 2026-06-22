# STORY-106: Enregistrement de l'exporter, formulaire, i18n et tests

**Epic:** Export comptable « Recette Manifestation »
**Priority:** Must Have (rend la feature livrable)
**Story Points:** 5
**Status:** In Review (exporter enregistré, 3 formats rendus, déployé sur pretix-dev ; pytest 51/51. Reste : validation UI par goss + i18n .po)
**Assigned To:** goss
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

- [x] Un export « Rapport de recette (par canal et séance) » apparaît dans Pretix, distinct de « Rapport comptable avec frais bancaires » (existant conservé). Vérifié : présent dans `register_data_exporters` pour l'event.
- [x] L'exporter est autonome (`BaseExporter`, n'hérite pas du ReportExporter natif).
- [x] Le formulaire propose : période (`DateFrameField`), canal (choix dynamiques + « tous »), format (PDF/CSV/XLSX), statut (payées / payées+attente).
- [x] Les 3 formats se génèrent sans erreur (PDF 34 Ko, CSV, XLSX) ; totaux identiques (mêmes builder + renderers que 104/105).
- [x] Permissions Pretix : mécanisme natif `BaseExporter` (accès lié aux droits sur l'organisateur/événement), filtrage strict par event/organizer.
- [~] i18n : libellés en `gettext_lazy`/`gettext` (sources FR) ; extraction + traduction .po des 8 langues à finaliser (reste documenté).
- [x] Tests pytest (enregistrement, formulaire, 3 formats, filtre canal, event_meta) : 51/51.
- [x] Déployé sur `pretix-dev` (conteneur redémarré, exporter visible via le signal).
- [ ] **Validation UI par goss** (ouvrir l'export dans l'interface Pretix) — en attente.

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

## Implementation Notes

- **Fichiers :** `exporters/recette_manifestation.py` (`RecetteManifestationExporter(BaseExporter)`), `signals.py` (enregistrement data + multievent). Tests : `tests/test_recette_exporter.py` (8 tests).
- **Formulaire (`export_form_fields`) :** `date_range` (DateFrameField), `channel` (ChoiceField dynamique depuis `organizer.sales_channels`), `status` (payées / payées+attente), `_format` (pdf/csv/xlsx).
- **render() -> (filename, content_type, bytes)** : route vers le renderer du format choisi. PDF reçoit `_event_meta()` (organisateur/événement/slug/date/lieu réels). Le `form_data` est mappé vers le builder (`channel`, `statuses`).
- **Nom final :** « Recettes détaillées » (retour goss). Libellés du formulaire en français (Période / Canal de vente / Statut de la commande / Format d'export / Tous les canaux).
- **Nettoyage (retour goss) :** les anciens exporters `accounting_report_psp` et `payment_list_psp` ont été **supprimés** (+ leurs renderers `pdf_renderer`/`csv_renderer`/`excel_renderer`/`accounting_pdf_renderer`). Le nouvel export les remplace entièrement. Le plugin n'expose plus qu'un seul export.
- **django-scopes :** l'UI Pretix fournit le scope ; le builder s'exécute dedans (cf. STORY-100).
- **Déploiement :** plugin monté editable ; après ajout d'un signal il faut **redémarrer le conteneur** (`docker restart pretix-dev`) pour que `register_data_exporters` le voie.
- **Reste (hors-bloquant) :** extraction i18n (`makemessages`) + traduction des .po pour les 8 langues. Les sources sont déjà en FR via `gettext_lazy`, donc le rapport est correct en français dès maintenant.
- pytest 51/51 (toute la feature, builder + 3 renderers + exporter).

---

## Progress Tracking

**Status History:**
- 2026-06-22 : Créée par goss.
- 2026-06-22 : Implémentée. Exporter BaseExporter + formulaire + signaux, 3 formats, déployé sur pretix-dev (enregistrement vérifié). pytest 51/51. Statut In Review (validation UI goss + i18n .po à finaliser).

**Actual Effort:** ~5 points (conforme).

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
