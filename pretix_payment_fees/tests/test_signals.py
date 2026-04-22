"""
Regression tests for pretix_payment_fees.signals.

These tests lock in the fix shipped in v1.0.1: the ``order_paid`` receiver
must follow Pretix's ``EventPluginSignal`` convention (``sender`` is the
``Event``, the ``Order`` is passed as the ``order`` keyword argument) AND
must never propagate an exception — any failure in the auto-sync path
would otherwise crash the ``perform_order`` Celery task and surface to
buyers as a generic 500 error at checkout.

Run from the pretix container:
    docker exec pretix-dev python -m pytest \
        /usr/local/lib/python3.11/site-packages/pretix_payment_fees/tests/

Or from the plugin source tree (with pretix installed in the env):
    pytest pretix_payment_fees/tests/
"""
from types import SimpleNamespace
from unittest import mock


class _FakeDoesNotExist(Exception):
    """Stand-in for PSPConfig.DoesNotExist in mocks."""


def _fake_event(slug="test-org"):
    return SimpleNamespace(organizer=SimpleNamespace(slug=slug))


def _fake_order(event=None, code="ABCDE"):
    return SimpleNamespace(
        code=code,
        event=event or _fake_event(),
        payments=SimpleNamespace(
            filter=lambda **_: SimpleNamespace(
                order_by=lambda *_args, **_kw: SimpleNamespace(first=lambda: None)
            )
        ),
    )


def test_on_order_paid_uses_eventpluginsignal_convention():
    """
    order_paid is an EventPluginSignal: sender=Event, order=Order via kwargs.
    The receiver must accept that convention without raising, even when the
    organizer has no PSPConfig (common case on test events).
    """
    from pretix_payment_fees import signals

    event = _fake_event()
    order = _fake_order(event=event)

    with mock.patch("pretix_payment_fees.models.PSPConfig") as psp_cls:
        psp_cls.DoesNotExist = _FakeDoesNotExist
        psp_cls.objects.get.side_effect = _FakeDoesNotExist()

        # Must not raise.
        signals.on_order_paid(sender=event, order=order)


def test_on_order_paid_tolerates_missing_order_kwarg():
    """
    Defensive path: if some caller (plugin test harness, future Pretix change)
    emits the signal without an order, the receiver must log and return —
    never raise.
    """
    from pretix_payment_fees import signals

    signals.on_order_paid(sender=_fake_event())
    signals.on_order_paid(sender=_fake_event(), order=None)


def test_on_order_paid_swallows_downstream_exceptions():
    """
    Outermost guard: any exception raised while looking up the PSP config,
    while iterating payments, or inside PSPSyncService must be caught. The
    receiver must never propagate to Pretix's perform_order task.
    """
    from pretix_payment_fees import signals

    event = _fake_event()
    order = _fake_order(event=event)

    with mock.patch("pretix_payment_fees.models.PSPConfig") as psp_cls:
        psp_cls.objects.get.side_effect = RuntimeError("downstream boom")

        # Must not raise.
        signals.on_order_paid(sender=event, order=order)


def test_on_order_paid_triggers_sync_when_config_and_payment_present():
    """
    Happy path: when a PSPConfig exists, at least one PSP is enabled, and a
    confirmed payment with a supported provider is attached, PSPSyncService
    is invoked with that payment.
    """
    from pretix_payment_fees import signals

    event = _fake_event()
    payment = SimpleNamespace(id=42, provider="mollie")

    class _Payments:
        def filter(self, **_):
            return self

        def order_by(self, *_args, **_kw):
            return self

        def first(self):
            return payment

    order = SimpleNamespace(code="ORDER1", event=event, payments=_Payments())

    psp_config = SimpleNamespace(mollie_enabled=True, sumup_enabled=False)

    sync_result = SimpleNamespace(
        synced_payments=1, skipped_payments=0, total_fees=0, errors=[]
    )

    with mock.patch("pretix_payment_fees.models.PSPConfig") as psp_cls, mock.patch(
        "pretix_payment_fees.services.psp_sync.PSPSyncService"
    ) as sync_cls, mock.patch("pretix.base.models.OrderPayment") as order_payment_cls:
        psp_cls.objects.get.return_value = psp_config
        order_payment_cls.PAYMENT_STATE_CONFIRMED = "confirmed"
        sync_instance = sync_cls.return_value
        sync_instance.sync_payments.return_value = sync_result

        signals.on_order_paid(sender=event, order=order)

        sync_cls.assert_called_once_with(organizer=event.organizer, psp_config=psp_config)
        sync_instance.sync_payments.assert_called_once_with(
            [payment], force=False, dry_run=False
        )
