import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils.timezone import make_aware, now

import requests

from ..models import PSPTransactionCache

logger = logging.getLogger(__name__)


class SumUpClient:
    """Client pour l'API SumUp (Transactions)."""

    BASE_URL = "https://api.sumup.com/v0.1"
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 2

    def __init__(self, api_key, test_mode=False, organizer=None):
        self.api_key = api_key
        self.test_mode = test_mode
        self.organizer = organizer
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    def get_transaction_details(self, transaction_id):
        """
        Récupère les détails d'une transaction SumUp avec frais.

        Args:
            transaction_id: ID de la transaction SumUp

        Returns:
            dict avec amount_fee, fee_details_text, status
        """
        if not transaction_id:
            return None

        # Vérifier le cache
        cached = self._get_from_cache(transaction_id)
        if cached:
            return cached

        try:
            # Récupérer la transaction
            transaction_data = self._get_transaction(transaction_id)
            if not transaction_data:
                logger.warning(f"SumUp transaction not found: {transaction_id}")
                return None

            # Extraire les frais
            fee_data = self._extract_fees(transaction_data)

            # Mettre en cache
            self._save_to_cache(transaction_id, fee_data, transaction_data)

            return fee_data

        except Exception as e:
            logger.error(
                f"Error fetching SumUp transaction {transaction_id}: {e}",
                exc_info=True,
            )
            return None

    def _get_transaction(self, transaction_id):
        """Récupère une transaction SumUp."""
        # SumUp API : GET /v0.1/me/transactions/{id}
        # Mais parfois l'API nécessite de lister et filtrer
        url = f"{self.BASE_URL}/me/transactions"
        params = {"transaction_code": transaction_id, "limit": 1}

        response = self._make_request("GET", url, params=params)
        if not response or not response.get("items"):
            return None

        return response["items"][0]

    def list_transactions(self, date_from, date_to):
        """
        Liste les transactions SumUp pour une période.

        Args:
            date_from: datetime
            date_to: datetime

        Returns:
            Liste de transactions
        """
        url = f"{self.BASE_URL}/me/transactions/history"
        params = {
            "newest_time": date_to.isoformat(),
            "oldest_time": date_from.isoformat(),
            "limit": 100,  # Max par page
        }

        all_transactions = []

        while True:
            response = self._make_request("GET", url, params=params)
            if not response:
                break

            transactions = response.get("items", [])
            if not transactions:
                break

            all_transactions.extend(transactions)

            # Pagination : SumUp utilise oldest_ref
            if len(transactions) < params["limit"]:
                break

            # Mettre à jour le curseur
            params["oldest_time"] = transactions[-1]["timestamp"]

        return all_transactions

    def _extract_fees(self, transaction_data):
        """
        Extrait les frais d'une transaction SumUp.

        SumUp fournit généralement :
        - amount : montant brut
        - fee_amount : frais prélevés par SumUp
        - net_amount : montant net versé au marchand
        """
        amount_str = transaction_data.get("amount", "0.00")
        currency = transaction_data.get("currency", "EUR")

        # Convertir en Decimal
        amount_gross = Decimal(str(amount_str))

        # SumUp peut fournir fee_amount directement
        fee_amount_str = transaction_data.get("fee_amount")
        if fee_amount_str:
            amount_fee = Decimal(str(fee_amount_str))
        else:
            # Fallback : estimer (1.95% + 0.15 EUR pour cartes)
            amount_fee = (amount_gross * Decimal("0.0195")) + Decimal("0.15")

        amount_net = amount_gross - amount_fee

        # Détails des frais
        fee_details = []
        if fee_amount_str:
            fee_details.append(f"SumUp fee: {amount_fee} {currency}")
        else:
            fee_details.append(f"Estimation: 1.95% + 0.15 {currency}")

        # Statut
        status = transaction_data.get("status", "UNKNOWN")
        if status == "SUCCESSFUL":
            status = "ok"
        elif status == "CANCELLED":
            status = "annulé"
        elif status == "FAILED":
            status = "échec"
        elif status == "REFUNDED":
            status = "remboursé"

        return {
            "amount_fee": amount_fee,
            "fee_details_text": "; ".join(fee_details),
            "settlement_id": "",  # SumUp n'a pas de settlement_id comme Mollie
            "status": status,
            "amount_gross": amount_gross,
            "amount_net": amount_net,
            "currency": currency,
        }

    def _make_request(self, method, url, params=None, json=None, retry=0):
        """Effectue une requête avec retry/backoff."""
        try:
            response = self.session.request(method, url, params=params, json=json, timeout=30)

            if response.status_code == 429:  # Rate limit
                if retry < self.MAX_RETRIES:
                    wait_time = self.BACKOFF_FACTOR**retry
                    logger.warning(
                        f"Rate limited by SumUp, waiting {wait_time}s (retry {retry + 1}/{self.MAX_RETRIES})"
                    )
                    time.sleep(wait_time)
                    return self._make_request(method, url, params, json, retry + 1)
                else:
                    logger.error("Max retries reached for SumUp API")
                    return None

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.info(f"SumUp resource not found: {url}")
                return None
            else:
                logger.error(f"SumUp API HTTP error: {e}", exc_info=True)
                if retry < self.MAX_RETRIES:
                    wait_time = self.BACKOFF_FACTOR**retry
                    time.sleep(wait_time)
                    return self._make_request(method, url, params, json, retry + 1)
                return None

        except Exception as e:
            logger.error(f"SumUp API error: {e}", exc_info=True)
            return None

    def _get_from_cache(self, transaction_id):
        """Récupère depuis le cache Django."""
        if not self.organizer:
            return None

        try:
            cached = PSPTransactionCache.objects.get(
                organizer=self.organizer,
                psp_provider="sumup",
                transaction_id=transaction_id,
            )

            # Vérifier si le cache n'est pas trop vieux (1h par défaut)
            if cached.modified > now() - timedelta(hours=1):
                return {
                    "amount_fee": cached.amount_fee,
                    "fee_details_text": (
                        ", ".join([f"{k}: {v}" for k, v in cached.fee_details.items()])
                        if cached.fee_details
                        else ""
                    ),
                    "settlement_id": "",
                    "status": cached.status,
                    "amount_gross": cached.amount_gross,
                    "amount_net": cached.amount_net,
                    "currency": cached.currency,
                }
            else:
                # Cache expiré
                cached.delete()

        except PSPTransactionCache.DoesNotExist:
            pass

        return None

    def _save_to_cache(self, transaction_id, fee_data, transaction_data):
        """Sauvegarde dans le cache Django."""
        if not self.organizer:
            return

        try:
            # Extraire la date de transaction
            timestamp_str = transaction_data.get("timestamp", "")
            if timestamp_str:
                transaction_date = make_aware(
                    datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                )
            else:
                transaction_date = now()

            PSPTransactionCache.objects.update_or_create(
                organizer=self.organizer,
                psp_provider="sumup",
                transaction_id=transaction_id,
                defaults={
                    "amount_gross": fee_data["amount_gross"],
                    "amount_fee": fee_data["amount_fee"],
                    "amount_net": fee_data["amount_net"],
                    "currency": fee_data["currency"],
                    "settlement_id": "",
                    "status": fee_data["status"],
                    "fee_details": {"raw": fee_data["fee_details_text"]},
                    "transaction_date": transaction_date,
                    "settlement_date": None,
                },
            )
        except Exception as e:
            logger.error(f"Error saving to cache: {e}", exc_info=True)
