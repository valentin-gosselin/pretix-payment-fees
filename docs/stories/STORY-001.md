# STORY-001: Corriger le crash du signal `order_paid` qui bloque la validation des commandes

**Epic:** Stabilité / Bug critique production
**Priority:** Must Have (bloquant — aucune vente possible plugin activé)
**Story Points:** 2 (simple, ~2-4h incluant tests et redéploiement)
**Status:** Not Started
**Assigned To:** Unassigned
**Created:** 2026-04-22
**Sprint:** Hotfix

---

## User Story

En tant qu'**acheteur** sur la boutique Pretix,
je veux **pouvoir valider ma commande normalement**,
afin que **le paiement aboutisse sans voir l'erreur « Une erreur inattendue s'est produite »** quand le plugin Payment Provider Fees Tracker est activé.

En tant qu'**organisateur d'événement**,
je veux **activer le plugin de suivi des frais PSP sans risquer de bloquer mes ventes**,
afin de **bénéficier de la synchronisation automatique des frais sans sacrifier la disponibilité de la boutique**.

---

## Description

### Background
Le plugin `pretix-payment-fees` v1.0.0 enregistre un receiver sur le signal Pretix `order_paid` (fichier `pretix_payment_fees/signals.py`, fonction `on_order_paid`). Ce receiver lève une `AttributeError` systématiquement lors de la validation d'une commande payée, ce qui provoque l'erreur générique « Une erreur inattendue s'est produite, veuillez réessayer plus tard » côté utilisateur.

### Cause racine
`order_paid` est un `EventPluginSignal`. D'après la définition dans `pretix/base/signals.py` :

> Arguments: `order`
> As with all event-plugin signals, the `sender` keyword argument will contain the event.

Donc `sender = Event` et la commande arrive dans `kwargs['order']`. Or le receiver fait :

```python
# signals.py:103
def on_order_paid(sender, **kwargs):
    order = sender  # ❌ sender est un Event, pas un Order
    ...
    psp_config = PSPConfig.objects.get(organizer=order.event.organizer)  # ❌ ligne 110
```

La stack trace confirme exactement cela :
```
File "/usr/local/lib/python3.11/site-packages/pretix_payment_fees/signals.py", line 110, in on_order_paid
AttributeError: 'Event' object has no attribute 'event'
```

L'exception remonte dans la tâche Celery `pretix.base.services.orders.perform_order`, qui échoue ; l'UI de checkout reçoit alors une erreur 500 générique.

### Scope
**In scope:**
- Correction de la signature du receiver `on_order_paid` pour récupérer l'order depuis `kwargs` (signature `EventPluginSignal`).
- Vérification du receiver périodique `auto_sync_payment_fees` et des autres receivers du fichier signals.py (au cas où un pattern similaire existe).
- Ajout d'un test unitaire qui invoque le signal de la même façon que Pretix (sender=event, order=kwargs) pour éviter toute régression.
- Rebump de version (1.0.1), rebuild de la wheel, réinstallation dans le container `pretix-dev` (car le plugin est installé via pip, pas monté en volume).
- Validation manuelle : passer une commande de test sur l'événement de test avec le plugin activé.

**Out of scope:**
- Refonte de la logique de synchronisation PSP.
- Ajout de nouveaux providers.
- Revue complète des autres plugins du dépôt (mollie, pretix-producer-report).

### User Flow (après fix)
1. L'acheteur remplit son panier et arrive au checkout.
2. Il paie via Mollie (ou autre PSP supporté).
3. Pretix passe la commande en état payé et émet le signal `order_paid`.
4. Le receiver récupère correctement l'order, cherche la `PSPConfig` de l'organizer et lance la synchronisation des frais en tâche de fond.
5. L'acheteur voit la page de confirmation standard — aucun message d'erreur.
6. Côté backend, les frais PSP sont bien rattachés à la commande (ou l'échec de sync est loggé sans impacter la commande).

---

## Acceptance Criteria

- [ ] Une commande peut être validée et payée sur l'événement de test avec le plugin `pretix-payment-fees` activé, sans voir « Une erreur inattendue s'est produite ».
- [ ] Les logs de `pretix-dev` ne contiennent plus l'erreur `AttributeError: 'Event' object has no attribute 'event'` lors d'un paiement.
- [ ] Le receiver `on_order_paid` récupère l'instance `Order` via `kwargs['order']` (ou via paramètre nommé `order`), conformément à l'API `EventPluginSignal` de Pretix.
- [ ] Même en cas d'échec interne du service de synchronisation PSP, l'exception est catchée et **n'est jamais propagée** à la tâche `perform_order` (la commande ne doit jamais être bloquée par ce plugin). Le `try/except` existant ligne 152 est conservé et couvre désormais aussi la récupération de `PSPConfig`.
- [ ] Un test unitaire simule `order_paid.send(sender=event, order=order)` et vérifie : (a) aucune exception remontée, (b) le service `PSPSyncService.sync_payments` est appelé avec le bon payment quand la config existe, (c) rien n'est appelé si aucune `PSPConfig` n'existe.
- [ ] Les autres receivers du fichier `signals.py` sont relus et documentés comme utilisant la bonne convention (rien à corriger attendu pour `order_fee_type_name`, `register_data_exporters`, `nav_organizer`, `periodic_task`).
- [ ] La version du plugin est incrémentée (1.0.0 → 1.0.1) et le `CHANGELOG.md` mentionne le correctif.
- [ ] La nouvelle wheel est réinstallée dans le container `pretix-dev` (`pip install --force-reinstall` de la wheel construite) et `pretix-dev` est redémarré.

---

## Technical Notes

### Composants concernés
- **Fichier à modifier :** `pretix-payment-fees/pretix_payment_fees/signals.py` (fonction `on_order_paid`, lignes 95-167).
- **Fichier à créer/compléter :** test unitaire (pas de dossier `tests/` actuellement ; à créer sous `pretix_payment_fees/tests/test_signals.py`).
- **Build :** `Makefile` + `pyproject.toml` — bump version à 1.0.1 dans `pretix_payment_fees/__init__.py`.

### Correction proposée
```python
@receiver(order_paid, dispatch_uid="export_frais_order_paid")
def on_order_paid(sender, order=None, **kwargs):
    """
    sender = Event (convention EventPluginSignal)
    order  = instance Order fournie par Pretix dans kwargs
    """
    if order is None:
        logger.warning("order_paid signal received without order kwarg, skipping")
        return

    from .models import PSPConfig
    from .services.psp_sync import PSPSyncService

    try:
        psp_config = PSPConfig.objects.get(organizer=order.event.organizer)
    except PSPConfig.DoesNotExist:
        logger.debug(
            f"No PSP config for organizer {order.event.organizer.slug}, skipping auto-sync"
        )
        return

    # ... reste inchangé ...
```

Le reste de la fonction (lignes 117-167) reste identique puisqu'il manipule `order` correctement une fois la variable bien définie.

### Dépendance de packaging
Le plugin est actuellement **installé via pip** (`/usr/local/lib/python3.11/site-packages/pretix_payment_fees/`), pas monté en volume depuis `/docker/pretix_pluginexportfrais/plugins/`. Le workflow de correction doit donc inclure :
```bash
cd /docker/pretix_pluginexportfrais/plugins/pretix-payment-fees
make build   # ou python -m build
docker exec pretix-dev pip install --force-reinstall /path/to/dist/pretix_payment_fees-1.0.1-*.whl
docker restart pretix-dev
```
(Idéalement, envisager à terme un montage en volume en dev pour éviter ce cycle.)

### Considérations de sécurité / robustesse
- Le bug actuel est un **déni de service auto-infligé** dès qu'un paiement est confirmé. Criticité : haute.
- Après fix, le `try/except Exception` existant autour de `sync_payments` (ligne 152) garantit que tout échec futur côté API Mollie/SumUp n'impactera pas la validation de commande. On étend juste ce filet au reste de la fonction.

### Edge cases à couvrir dans les tests
- Signal émis sans `order` (ne doit pas crasher).
- Organizer sans `PSPConfig` (retour silencieux, debug log).
- `PSPConfig` existante mais aucun PSP activé (retour silencieux).
- Paiement avec provider non supporté (`banktransfer` par ex.) → retour silencieux.
- Exception interne du `PSPSyncService` → catchée, log d'erreur, pas de propagation.

---

## Dependencies

**Prerequisite Stories:** aucune.

**Blocked Stories:** aucune identifiée, mais **bloque la mise en production** de tout événement utilisant ce plugin.

**External Dependencies:**
- Accès au container `pretix-dev` pour réinstaller la wheel.
- Événement de test fonctionnel avec un PSP configuré pour validation finale.

---

## Definition of Done

- [ ] Correctif implémenté dans `signals.py` et committé.
- [ ] Version bumpée à 1.0.1 dans `pretix_payment_fees/__init__.py` et `pyproject.toml`.
- [ ] `CHANGELOG.md` mis à jour avec l'entrée 1.0.1.
- [ ] Test unitaire `test_signals.py::test_on_order_paid_uses_kwargs_order` écrit et passant.
- [ ] Les autres receivers relus rapidement (pas de correction attendue).
- [ ] Wheel 1.0.1 construite, réinstallée dans `pretix-dev`, container redémarré.
- [ ] Test manuel : commande de bout en bout sur l'événement de test → confirmation OK, logs propres.
- [ ] Aucune régression sur les exports comptables (`/control/event/.../export/...`) ni sur la navigation organizer (`nav_organizer`).
- [ ] Commit avec message clair référençant la story.

---

## Story Points Breakdown

- **Correction code + signature :** 0.5 point
- **Test unitaire :** 1 point
- **Build, réinstallation, test manuel :** 0.5 point
- **Total :** 2 points

**Rationale :** bug ciblé, cause racine identifiée, correctif trivial mais exigeant un test de non-régression et un cycle de rebuild/réinstall du plugin puisqu'il n'est pas monté en volume.

---

## Additional Notes

### Trace d'origine (logs pretix-dev du 2026-04-22 12:38)
```
[2026-04-22 12:38:38,872: ERROR/ForkPoolWorker-7] Task pretix.base.services.orders.perform_order[cf809516-...] raised unexpected: AttributeError("'Event' object has no attribute 'event'")
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/pretix_payment_fees/signals.py", line 110, in on_order_paid
AttributeError: 'Event' object has no attribute 'event'
```

### Observation annexe
Le même pattern (sender = Order) pourrait avoir été copié depuis un autre signal Pretix (ex. `order_placed`, `order_changed`) qui sont *également* des `EventPluginSignal` avec la même convention. Il faudrait vérifier qu'aucun autre code interne ne présuppose `sender = order` ; à ce stade, seul `on_order_paid` est concerné dans `signals.py`.

---

## Progress Tracking

**Status History:**
- 2026-04-22 : Créée par Valentin suite à signalement d'une boutique bloquée sur événement de test.

**Actual Effort:** TBD

---

**This story was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
