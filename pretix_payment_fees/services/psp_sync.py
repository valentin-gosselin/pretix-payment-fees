"""
Service de synchronisation des frais PSP.

Ce service récupère les frais réels depuis les APIs PSP (Mollie, SumUp)
et les stocke dans Pretix via OrderFee et payment.info_data.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from django.db import transaction
from django.utils.timezone import now
from pretix.base.models import Order, OrderFee, OrderPayment

from ..models import PSPConfig
from ..psp.mollie_client import MollieClient
from ..psp.sumup_client import SumUpClient

logger = logging.getLogger(__name__)


class PSPSyncResult:
    """PSP synchronization result."""

    def __init__(self):
        self.total_payments = 0
        self.synced_payments = 0
        self.skipped_payments = 0
        self.failed_payments = 0
        self.total_fees = Decimal("0.00")
        self.errors = []

    def add_success(self, fee_amount: Decimal):
        """Add a successfully synchronized payment."""
        self.synced_payments += 1
        self.total_fees += fee_amount

    def add_skip(self, reason: str):
        """Add an ignored payment."""
        self.skipped_payments += 1
        logger.debug(f"Payment skipped: {reason}")

    def add_error(self, payment_id: str, error: str):
        """Add a synchronization error."""
        self.failed_payments += 1
        self.errors.append({"payment_id": payment_id, "error": error})
        logger.error(f"Failed to sync payment {payment_id}: {error}")

    def __str__(self):
        return (
            f"PSP Sync Result: {self.synced_payments}/{self.total_payments} payments synced, "
            f"{self.skipped_payments} skipped, {self.failed_payments} failed, "
            f"Total fees: {self.total_fees} EUR"
        )


class PSPSyncService:
    """PSP fee synchronization service."""

    def __init__(self, organizer, psp_config: Optional[PSPConfig] = None):
        """
        Initialise le service de synchronisation.

        Args:
            organizer: Organisateur Pretix
            psp_config: Configuration PSP (si None, sera récupérée)
        """
        self.organizer = organizer
        self.psp_config = psp_config or PSPConfig.objects.filter(organizer=organizer).first()

        # Initialiser les clients PSP
        self.mollie_client = None
        self.sumup_client = None

        if self.psp_config:
            if self.psp_config.mollie_enabled and self.psp_config.mollie_api_key:
                # Vérifier et rafraîchir le token OAuth si nécessaire
                access_token = None
                if self.psp_config.mollie_oauth_connected:
                    access_token = self._ensure_valid_mollie_token()

                self.mollie_client = MollieClient(
                    api_key=self.psp_config.mollie_api_key,
                    test_mode=self.psp_config.mollie_test_mode,
                    organizer=organizer,
                    access_token=access_token,
                )

            if self.psp_config.sumup_enabled and self.psp_config.sumup_api_key:
                self.sumup_client = SumUpClient(
                    api_key=self.psp_config.sumup_api_key,
                    test_mode=self.psp_config.sumup_test_mode,
                    organizer=organizer,
                )

    def _ensure_valid_mollie_token(self) -> Optional[str]:
        """
        Vérifie si le token OAuth Mollie est valide et le rafraîchit si expiré.

        Returns:
            access_token valide ou None si échec
        """
        if not self.psp_config.mollie_oauth_connected:
            return None

        # Vérifier si le token est encore valide (avec buffer de 5 minutes)
        from ..psp.mollie_oauth_client import MollieOAuthClient

        oauth_client = MollieOAuthClient(
            client_id=self.psp_config.mollie_client_id,
            client_secret=self.psp_config.mollie_client_secret,
            access_token=self.psp_config.mollie_access_token,
        )

        if oauth_client.is_token_valid(self.psp_config.mollie_token_expires_at):
            logger.debug("Mollie OAuth token is still valid")
            return self.psp_config.mollie_access_token

        # Token expiré - tenter de rafraîchir
        logger.info("Mollie OAuth token expired, refreshing...")
        try:
            token_data = oauth_client.refresh_access_token(self.psp_config.mollie_refresh_token)

            # Mettre à jour la config avec le nouveau token
            from datetime import timedelta

            expires_in = token_data.get("expires_in", 3600)

            self.psp_config.mollie_access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                self.psp_config.mollie_refresh_token = token_data["refresh_token"]
            self.psp_config.mollie_token_expires_at = now() + timedelta(seconds=expires_in)
            self.psp_config.save(
                update_fields=[
                    "mollie_access_token",
                    "mollie_refresh_token",
                    "mollie_token_expires_at",
                ]
            )

            logger.info("Successfully refreshed Mollie OAuth token")
            return self.psp_config.mollie_access_token

        except Exception as e:
            logger.error(f"Failed to refresh Mollie OAuth token: {e}", exc_info=True)
            # Marquer OAuth comme déconnecté
            self.psp_config.mollie_oauth_connected = False
            self.psp_config.save(update_fields=["mollie_oauth_connected"])
            return None

    def sync_payments(
        self,
        payments: List[OrderPayment],
        force: bool = False,
        dry_run: bool = False,
        skip_already_synced: bool = True,
    ) -> PSPSyncResult:
        """
        Synchronise les frais PSP pour une liste de paiements.

        Args:
            payments: Liste des paiements à synchroniser
            force: Si True, resynchronise même si déjà fait
            dry_run: Si True, simule sans modifier la base
            skip_already_synced: Si True, exclut les paiements déjà synchronisés (optimisation)

        Returns:
            PSPSyncResult avec les statistiques
        """
        # Filtrer les paiements déjà synchronisés (optimisation pour auto-sync)
        if skip_already_synced and not force:
            # Créer une liste des paiements déjà synchronisés
            already_synced_payment_ids = set()
            for payment in payments:
                provider_fee_type = f"{payment.provider}_fee"
                has_fee = OrderFee.objects.filter(
                    order=payment.order,
                    fee_type=OrderFee.FEE_TYPE_PAYMENT,
                    internal_type=provider_fee_type,
                ).exists()
                if has_fee:
                    already_synced_payment_ids.add(payment.id)

            # Exclure les paiements déjà synchronisés
            if already_synced_payment_ids:
                # Fonctionne que payments soit une liste ou un queryset
                payments = [p for p in payments if p.id not in already_synced_payment_ids]
                logger.info(f"Skipping {len(already_synced_payment_ids)} already synced payments")

        result = PSPSyncResult()
        result.total_payments = len(payments)

        logger.info(
            f"Starting PSP sync for {result.total_payments} payments "
            f"(force={force}, dry_run={dry_run})"
        )

        for payment in payments:
            try:
                self._sync_single_payment(payment, force=force, dry_run=dry_run, result=result)
            except Exception as e:
                result.add_error(str(payment.id), f"Unexpected error: {str(e)}")
                logger.exception(f"Unexpected error syncing payment {payment.id}")

        logger.info(str(result))
        return result

    def _sync_single_payment(
        self,
        payment: OrderPayment,
        force: bool,
        dry_run: bool,
        result: PSPSyncResult,
    ):
        """Synchronize a single payment."""
        # Vérifier si le paiement est confirmé
        if payment.state != OrderPayment.PAYMENT_STATE_CONFIRMED:
            logger.info(f"⊗ Payment {payment.id} SKIPPED: not confirmed (state={payment.state})")
            result.add_skip(f"Payment {payment.id} not confirmed (state={payment.state})")
            return

        # Vérifier si déjà synchronisé (sauf si force)
        if not force and payment.info_data.get("psp_fees", {}).get("synced_at"):
            logger.info(f"⊗ Payment {payment.id} SKIPPED: already synced")
            result.add_skip(f"Payment {payment.id} already synced")
            return

        # Récupérer les données PSP
        psp_data = self._fetch_psp_data(payment)
        if not psp_data:
            logger.warning(
                f"⊗ Payment {payment.id} FAILED: no PSP data (provider={payment.provider}, transaction_id={payment.info_data.get('id') if payment.info_data else 'NO INFO_DATA'})"
            )
            result.add_error(
                str(payment.id), "Failed to fetch PSP data (API error or transaction not found)"
            )
            return

        # Provider non configuré ou non supporté -> skip silencieux (pas une erreur)
        if psp_data.get("_skip"):
            result.add_skip(psp_data.get("_reason", "Provider not configured"))
            return

        fee_amount = psp_data.get("amount_fee", Decimal("0.00"))
        if fee_amount == Decimal("0.00"):
            logger.info(f"⊗ Payment {payment.id} SKIPPED: zero fees")
            result.add_skip(f"Payment {payment.id} has zero fees")
            return

        if dry_run:
            logger.info(
                f"[DRY RUN] Would create OrderFee for payment {payment.id}: {fee_amount} EUR"
            )
            result.add_success(fee_amount)
            return

        # Créer ou mettre à jour OrderFee et info_data
        with transaction.atomic():
            self._create_or_update_order_fee(payment, psp_data)
            self._update_payment_info_data(payment, psp_data)

        result.add_success(fee_amount)
        logger.info(f"Successfully synced payment {payment.id}: fee={fee_amount} EUR")

    def _fetch_psp_data(self, payment: OrderPayment) -> Optional[Dict]:
        """
        Récupère les données de frais depuis l'API PSP.

        Args:
            payment: Paiement Pretix

        Returns:
            Dict avec amount_fee, fee_details_text, etc. ou None
        """
        provider = payment.provider

        # Extraire le transaction_id selon le provider
        transaction_id = ""
        if payment.info_data:
            if provider == "sumup":
                # SumUp: l'ID est dans sumup_transaction.transaction_code ou sumup_transaction.id
                sumup_tx = payment.info_data.get("sumup_transaction", {})
                transaction_id = sumup_tx.get("transaction_code") or sumup_tx.get("id", "")
            else:
                # Mollie et autres: l'ID est directement dans info_data.id
                transaction_id = payment.info_data.get("id", "")

        if not transaction_id:
            logger.warning(
                f"⊗ Payment {payment.id} has NO transaction ID! "
                f"provider={provider}, "
                f"order={payment.order.code}, "
                f"amount={payment.amount}, "
                f"info_data keys={list(payment.info_data.keys()) if payment.info_data else 'None'}"
            )
            return None

        # Mollie
        if provider in ["mollie", "mollie_bancontact", "mollie_ideal", "mollie_creditcard"]:
            if not self.mollie_client:
                logger.debug(f"Mollie client not configured, skipping payment {payment.id}")
                return {"_skip": True, "_reason": "Mollie not configured"}

            logger.info(
                f"Fetching Mollie data for payment {payment.id}, transaction_id={transaction_id}"
            )
            return self.mollie_client.get_transaction_details(transaction_id)

        # SumUp
        elif provider == "sumup":
            if not self.sumup_client:
                logger.debug(f"SumUp client not configured, skipping payment {payment.id}")
                return {"_skip": True, "_reason": "SumUp not configured"}

            logger.info(
                f"Fetching SumUp data for payment {payment.id}, transaction_id={transaction_id}"
            )
            return self.sumup_client.get_transaction_details(transaction_id)

        else:
            logger.debug(f"Provider {provider} not supported for PSP sync")
            return {"_skip": True, "_reason": f"Provider {provider} not supported"}

    def _create_or_update_order_fee(self, payment: OrderPayment, psp_data: Dict):
        """
        Crée ou met à jour un OrderFee pour les frais PSP.

        Args:
            payment: Paiement Pretix
            psp_data: Données depuis l'API PSP
        """
        provider = payment.provider
        fee_amount = psp_data.get("amount_fee", Decimal("0.00"))
        fee_details = psp_data.get("fee_details_text", "PSP Fees")

        # Identifier le type interne basé sur le provider
        internal_type = f"{provider}_fee"

        # Description human-readable
        description = f"Fees {provider.replace('_', ' ').title()}: {fee_details}"

        # Chercher si un OrderFee existe déjà
        existing_fee = OrderFee.objects.filter(
            order=payment.order,
            fee_type=OrderFee.FEE_TYPE_PAYMENT,
            internal_type=internal_type,
        ).first()

        if existing_fee:
            # Mettre à jour
            existing_fee.value = fee_amount
            existing_fee.description = description
            existing_fee.save()
            logger.info(f"Updated existing OrderFee {existing_fee.id} for payment {payment.id}")
        else:
            # Créer nouveau
            order_fee = OrderFee.objects.create(
                order=payment.order,
                fee_type=OrderFee.FEE_TYPE_PAYMENT,
                internal_type=internal_type,
                description=description,
                value=fee_amount,
                tax_rate=Decimal("0.00"),  # Les frais PSP ne sont généralement pas taxés
                tax_value=Decimal("0.00"),
            )
            logger.info(f"Created new OrderFee {order_fee.id} for payment {payment.id}")

    def _update_payment_info_data(self, payment: OrderPayment, psp_data: Dict):
        """
        Enrichit payment.info_data avec les données PSP.

        Args:
            payment: Paiement Pretix
            psp_data: Données depuis l'API PSP
        """
        if not payment.info_data:
            payment.info_data = {}

        # Ajouter la section psp_fees
        payment.info_data["psp_fees"] = {
            "gross_amount": str(psp_data.get("amount_gross", Decimal("0.00"))),
            "settlement_amount": str(psp_data.get("amount_net", Decimal("0.00"))),
            "fee_amount": str(psp_data.get("amount_fee", Decimal("0.00"))),
            "currency": psp_data.get("currency", "EUR"),
            "fee_details": psp_data.get("fee_details_text", ""),
            "settlement_id": psp_data.get("settlement_id", ""),
            "synced_at": now().isoformat(),
        }

        payment.save(update_fields=["info"])
        logger.debug(f"Updated info_data for payment {payment.id}")

    def sync_event_payments(
        self,
        event,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        days_back: Optional[int] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> PSPSyncResult:
        """
        Synchronise tous les paiements d'un événement.

        Args:
            event: Événement Pretix
            date_from: Date de début (optionnel)
            date_to: Date de fin (optionnel)
            days_back: Nombre de jours en arrière (alternatif à date_from/date_to)
            force: Resynchroniser même si déjà fait
            dry_run: Simuler sans modifier

        Returns:
            PSPSyncResult
        """
        # Calculer les dates
        if days_back:
            date_to = now()
            date_from = date_to - timedelta(days=days_back)
        # Si pas de date_from spécifiée, ne pas filtrer par date de début
        # (event.date_from peut être dans le futur pour des préventes)
        if not date_to:
            date_to = now()

        logger.info(f"Syncing payments for event {event.slug} from {date_from or 'beginning'} to {date_to}")

        # Récupérer les paiements
        payments_qs = OrderPayment.objects.filter(
            order__event=event,
            payment_date__lte=date_to,
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
        ).select_related("order")

        # Filtrer par date_from seulement si spécifiée
        if date_from:
            payments_qs = payments_qs.filter(payment_date__gte=date_from)

        return self.sync_payments(payments_qs, force=force, dry_run=dry_run)

    def sync_organizer_payments(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        days_back: Optional[int] = None,
        force: bool = False,
        dry_run: bool = False,
        max_payments: Optional[int] = None,
    ) -> PSPSyncResult:
        """
        Synchronise tous les paiements d'un organisateur.

        Args:
            date_from: Date de début (optionnel, si None synchronise TOUS les paiements non synchro)
            date_to: Date de fin (optionnel)
            days_back: Nombre de jours en arrière
            force: Resynchroniser même si déjà fait
            dry_run: Simuler sans modifier
            max_payments: Limiter le nombre de paiements (pour éviter timeout web)

        Returns:
            PSPSyncResult
        """
        # Construire le queryset de base
        payments_qs = (
            OrderPayment.objects.filter(
                order__event__organizer=self.organizer,
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                provider__in=[
                    "mollie",
                    "mollie_bancontact",
                    "mollie_ideal",
                    "mollie_creditcard",
                    "sumup",
                ],
            )
            .select_related("order", "order__event")
            .order_by("-payment_date")
        )

        # Calculer les dates SI spécifiées
        if days_back:
            date_to = now()
            date_from = date_to - timedelta(days=days_back)

        # Filtrer par date UNIQUEMENT si date_from ou date_to est spécifié
        if date_from or date_to:
            if date_from:
                payments_qs = payments_qs.filter(payment_date__gte=date_from)
            if date_to:
                payments_qs = payments_qs.filter(payment_date__lte=date_to)
            logger.info(
                f"Syncing payments for organizer {self.organizer.slug} from {date_from or 'début'} to {date_to or 'fin'}"
            )
        else:
            # Pas de filtre de date: synchroniser TOUS les paiements non synchronisés
            logger.info(
                f"Syncing ALL pending payments for organizer {self.organizer.slug} (no date filter)"
            )

        # Limiter si nécessaire (pour appels web)
        if max_payments:
            payments_qs = payments_qs[:max_payments]
            logger.info(f"Limited to {max_payments} payments to avoid timeout")

        return self.sync_payments(list(payments_qs), force=force, dry_run=dry_run)
