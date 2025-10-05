import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal

import requests
from django.core.cache import cache
from django.utils.timezone import make_aware, now

from ..models import PSPTransactionCache

logger = logging.getLogger(__name__)


class MollieClient:
    """Client pour l'API Mollie (Balances & Settlements)."""

    BASE_URL = "https://api.mollie.com/v2"
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 2

    def __init__(self, api_key, test_mode=False, organizer=None, access_token=None):
        self.api_key = api_key
        self.test_mode = test_mode
        self.organizer = organizer
        self.access_token = access_token  # OAuth access token for Balances API
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    def get_transaction_details(self, transaction_id):
        """
        Récupère les détails d'une transaction Mollie avec frais.

        Args:
            transaction_id: ID de la transaction Mollie (tr_xxx ou autre)

        Returns:
            dict avec amount_fee, fee_details_text, settlement_id, status
        """
        if not transaction_id:
            return None

        # Vérifier le cache
        cached = self._get_from_cache(transaction_id)
        if cached:
            return cached

        try:
            # Récupérer les détails du paiement
            payment_data = self._get_payment(transaction_id)
            if not payment_data:
                logger.warning(f"Payment not found: {transaction_id}")
                return None

            # Settlement API nécessite OAuth, on ne l'appelle plus ici
            # Les frais sont maintenant récupérés via OAuth dans _calculate_fees
            settlement_data = None

            # Calculer les frais
            fee_data = self._calculate_fees(payment_data, settlement_data)

            # Mettre en cache
            self._save_to_cache(transaction_id, fee_data, payment_data)

            return fee_data

        except Exception as e:
            logger.error(
                f"Error fetching Mollie transaction {transaction_id}: {e}",
                exc_info=True,
            )
            return None

    def _get_payment(self, payment_id):
        """Récupère un paiement Mollie."""
        url = f"{self.BASE_URL}/payments/{payment_id}"
        return self._make_request("GET", url)

    def _get_settlement(self, settlement_id):
        """Récupère un settlement Mollie."""
        url = f"{self.BASE_URL}/settlements/{settlement_id}"
        return self._make_request("GET", url)

    def list_balance_transactions(self, date_from, date_to, balance_id="primary"):
        """
        Liste les transactions du balance report.

        Args:
            date_from: datetime
            date_to: datetime
            balance_id: ID du balance (default: "primary")

        Returns:
            Liste de transactions
        """
        url = f"{self.BASE_URL}/balances/{balance_id}/transactions"
        params = {
            "from": date_from.strftime("%Y-%m-%d"),
            "until": date_to.strftime("%Y-%m-%d"),
            "limit": 250,  # Max par page
        }

        all_transactions = []

        while url:
            response = self._make_request("GET", url, params=params)
            if not response:
                break

            transactions = response.get("_embedded", {}).get("balance_transactions", [])
            all_transactions.extend(transactions)

            # Pagination
            url = response.get("_links", {}).get("next", {}).get("href")
            params = {}  # Les params sont dans l'URL next

        return all_transactions

    def _get_exact_fees_with_settlement_rates(self, payment_data):
        """
        Calcule les VRAIS frais en utilisant les settlement rates.

        MÉTHODE FINALE (après recherche approfondie demandée par l'utilisateur):
        Les Settlements API contiennent les rates par type de carte qui permettent
        de calculer les frais EXACTS par transaction: fee = fixed + (amount × percentage / 100)

        Structure des rates (confirmée par tests):
        {
          "Credit card - Carte Bancaire": {"fixed": "0.25", "percentage": "1.2"},
          "Credit card - Domestic consumer cards": {"fixed": "0.25", "percentage": "1.8"},
          ...
        }

        Args:
            payment_data: Données complètes du paiement depuis API

        Returns:
            Dict avec amount_fee ou None
        """
        if not self.access_token or not self.organizer:
            logger.debug(f"No OAuth access_token or organizer, using estimation")
            return None

        try:
            from .mollie_oauth_client import MollieOAuthClient
            from ..models import PSPConfig

            payment_id = payment_data.get('id', '')
            settlement_id = payment_data.get('settlementId')

            # 1. Créer le client OAuth
            oauth_client = MollieOAuthClient(
                client_id="",  # Not needed for read operations
                client_secret="",
                access_token=self.access_token
            )

            # 2. Récupérer les rates du settlement
            rates = None

            if settlement_id:
                # Paiement déjà settlé: utiliser les rates du settlement
                logger.info(f"Payment {payment_id} has settlement {settlement_id}")
                rates = oauth_client.get_settlement_rates(settlement_id, self.organizer)
            else:
                # Paiement récent non encore settlé: utiliser last_known_settlement_rates
                logger.info(f"Payment {payment_id} not yet settled, using last known rates")
                try:
                    psp_config = PSPConfig.objects.get(organizer=self.organizer)
                    rates = psp_config.last_known_settlement_rates
                    if rates:
                        logger.info(f"✓ Using last_known_settlement_rates")
                    else:
                        logger.warning(f"No last_known_settlement_rates available")
                except PSPConfig.DoesNotExist:
                    logger.warning(f"PSPConfig not found for organizer")

            if not rates:
                logger.warning(f"No rates available for payment {payment_id}")
                return None

            # 3. Calculer le fee exact
            fee = oauth_client.calculate_exact_fee(payment_data, rates)
            if fee is not None:
                logger.info(f"✓ Exact fee calculated for {payment_id}: {fee} EUR")
                return {
                    "amount_fee": fee,
                    "fee_details_text": f"Frais Mollie (calculés avec rates settlement): {fee:.2f} EUR",
                    "source": "oauth_settlement_rates",
                }
            else:
                logger.info(f"⊗ Skipping {payment_id}: Rounding difference or unsupported payment type")
                return None

        except Exception as e:
            logger.error(f"Error calculating exact fees for {payment_id}: {e}", exc_info=True)
            return None

    def _estimate_mollie_fees(self, payment_data, amount_gross):
        """
        Estime les frais Mollie basés sur les tarifs standards.

        Tarifs Mollie (2025):
        - Cartes Bancaires (FR): 0,29 € + 1,19%
        - Cartes EU: 0,29 € + 1,79%
        - Cartes non-EU: 0,29 € + 2,89%
        - iDEAL: 0,29 €
        - Bancontact: 0,29 €
        """
        payment_method = payment_data.get("method", "")
        details = payment_data.get("details", {})
        fee_region = details.get("feeRegion", "")

        # Frais fixe par défaut
        fixed_fee = Decimal("0.29")
        percentage_fee = Decimal("0.0")

        if payment_method == "creditcard":
            # Carte bancaire - déterminer le taux selon la région
            if fee_region == "carte-bancaire":
                # Carte Bancaire française
                percentage_fee = Decimal("0.0119")  # 1,19%
                logger.debug(f"Using Carte Bancaire FR rate: 1.19%")
            elif fee_region in ["eu-card", "european-eea-card"]:
                # Carte européenne
                percentage_fee = Decimal("0.0179")  # 1,79%
                logger.debug(f"Using EU card rate: 1.79%")
            else:
                # Carte internationale (hors UE)
                percentage_fee = Decimal("0.0289")  # 2,89%
                logger.debug(f"Using international card rate: 2.89%")

        elif payment_method in ["ideal", "bancontact"]:
            # iDEAL et Bancontact: frais fixe uniquement
            percentage_fee = Decimal("0.0")
            logger.debug(f"Using {payment_method} flat rate: €0.29")

        elif payment_method == "paypal":
            # PayPal: 0,29 € + 3,49%
            fixed_fee = Decimal("0.29")
            percentage_fee = Decimal("0.0349")
            logger.debug(f"Using PayPal rate: €0.29 + 3.49%")

        elif payment_method == "sofort":
            # SOFORT: 0,29 € + 1,29%
            fixed_fee = Decimal("0.29")
            percentage_fee = Decimal("0.0129")
            logger.debug(f"Using SOFORT rate: €0.29 + 1.29%")

        else:
            # Méthode inconnue: taux conservateur
            percentage_fee = Decimal("0.0179")
            logger.warning(f"Unknown payment method '{payment_method}', using default 1.79% rate")

        # Calculer les frais totaux
        variable_fee = amount_gross * percentage_fee
        total_fee = fixed_fee + variable_fee

        logger.info(
            f"Estimated fees for {payment_method} ({fee_region}): "
            f"€{fixed_fee} + {percentage_fee*100}% of €{amount_gross} = €{total_fee:.2f}"
        )

        return total_fee

    def _calculate_fees(self, payment_data, settlement_data):
        """
        Calcule les frais PSP Mollie - VRAIE SOLUTION FINALE.

        DÉCOUVERTE (après recherche approfondie demandée par l'utilisateur):
        ✓ Settlement API contient les 'rates' par type de carte pour calculer les VRAIS frais!

        Structure confirmée par tests réels:
        {
          "periods": {
            "2025": {
              "4": {
                "costs": [
                  {
                    "description": "Credit card - Carte Bancaire",
                    "rate": {
                      "fixed": {"value": "0.25"},
                      "percentage": "1.2"
                    }
                  }
                ]
              }
            }
          }
        }

        LOGIQUE FINALE:
        1. PRIORITÉ: Frais calculés avec settlement rates (fee = fixed + amount × percentage / 100)
           - Si paiement settlé: utiliser les rates de son settlement
           - Si paiement récent: utiliser last_known_settlement_rates
        2. FALLBACK: Estimation avec grille tarifaire standard si pas de rates disponibles

        Cette approche donne:
        - ✓ VRAIS FRAIS EXACTS: calcul précis par transaction sans reserves ni chargebacks
        - ✓ PRÉCIS: utilise les rates officiels Mollie historiques
        - ✓ ÉVOLUTIF: conserve les rates historiques pour chaque période
        """
        amount_gross = Decimal(payment_data.get("amount", {}).get("value", "0.00"))
        currency = payment_data.get("amount", {}).get("currency", "EUR")
        payment_method = payment_data.get("method", "")
        payment_id = payment_data.get("id", "")

        amount_fee = Decimal("0.00")
        fee_details = []

        # PRIORITÉ 1: Frais exacts calculés avec settlement rates
        if self.access_token:
            exact_fees = self._get_exact_fees_with_settlement_rates(payment_data)
            if exact_fees:
                amount_fee = exact_fees.get("amount_fee", Decimal("0.00"))
                fee_details.append(exact_fees.get("fee_details_text", "Frais Mollie (calculés settlement rates)"))
                logger.info(f"✓ Payment {payment_id}: Using EXACT fees from settlement rates = {amount_fee} EUR")
            else:
                # Fallback: estimation si rates non disponibles
                amount_fee = self._estimate_mollie_fees(payment_data, amount_gross)
                fee_details.append(f"Frais Mollie (estimés - rates non disponibles): {amount_fee:.2f} {currency}")
                logger.info(f"Payment {payment_id}: Using estimated fees (no rates) = {amount_fee} EUR")
        else:
            # Pas d'OAuth: estimer avec grille tarifaire
            amount_fee = self._estimate_mollie_fees(payment_data, amount_gross)
            fee_details.append(f"Frais Mollie (estimés): {amount_fee:.2f} {currency}")
            logger.info(f"Payment {payment_id}: Using estimated fees (no OAuth) = {amount_fee} EUR")

        # Application fee (frais d'application si vous utilisez Mollie Connect)
        app_fee_data = payment_data.get("applicationFee")
        if app_fee_data:
            app_fee = Decimal(app_fee_data.get("value", "0.00"))
            if app_fee > 0:
                amount_fee += app_fee
                fee_details.append(f"Application fee: {app_fee:.2f} {currency}")

        # Statut
        status = payment_data.get("status", "unknown")
        if status == "paid":
            status = "ok"
        elif status == "refunded":
            status = "remboursé"
        elif status == "chargeback":
            status = "chargeback"

        return {
            "amount_fee": amount_fee,
            "fee_details_text": "; ".join(fee_details) if fee_details else "N/A",
            "settlement_id": payment_data.get("settlementId", ""),
            "status": status,
            "amount_gross": amount_gross,
            "amount_net": amount_gross - amount_fee,
            "currency": currency,
        }

    def _make_request(self, method, url, params=None, json=None, retry=0):
        """Effectue une requête avec retry/backoff."""
        try:
            response = self.session.request(
                method, url, params=params, json=json, timeout=30
            )

            if response.status_code == 429:  # Rate limit
                if retry < self.MAX_RETRIES:
                    wait_time = self.BACKOFF_FACTOR ** retry
                    logger.warning(
                        f"Rate limited by Mollie, waiting {wait_time}s (retry {retry + 1}/{self.MAX_RETRIES})"
                    )
                    time.sleep(wait_time)
                    return self._make_request(method, url, params, json, retry + 1)
                else:
                    logger.error("Max retries reached for Mollie API")
                    return None

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [404, 410]:
                # Resource not found - normal pour certaines transactions
                logger.info(f"Mollie resource not found: {url}")
                return None
            else:
                logger.error(f"Mollie API HTTP error: {e}", exc_info=True)
                if retry < self.MAX_RETRIES:
                    wait_time = self.BACKOFF_FACTOR ** retry
                    time.sleep(wait_time)
                    return self._make_request(method, url, params, json, retry + 1)
                return None

        except Exception as e:
            logger.error(f"Mollie API error: {e}", exc_info=True)
            return None

    def _get_from_cache(self, transaction_id):
        """Récupère depuis le cache Django."""
        if not self.organizer:
            return None

        try:
            cached = PSPTransactionCache.objects.get(
                organizer=self.organizer,
                psp_provider="mollie",
                transaction_id=transaction_id,
            )

            # Vérifier si le cache n'est pas trop vieux (1h par défaut)
            if cached.modified > now() - timedelta(hours=1):
                return {
                    "amount_fee": cached.amount_fee,
                    "fee_details_text": ", ".join(
                        [f"{k}: {v}" for k, v in cached.fee_details.items()]
                    )
                    if cached.fee_details
                    else "",
                    "settlement_id": cached.settlement_id or "",
                    "status": cached.status,
                    "amount_gross": cached.amount_gross,
                    "amount_net": cached.amount_net,
                    "currency": cached.currency,
                }
            else:
                # Cache expiré, le supprimer
                cached.delete()

        except PSPTransactionCache.DoesNotExist:
            pass

        return None

    def _extract_settlement_date(self, settlement_id):
        """
        Extract settlement date from Mollie settlement API.

        Args:
            settlement_id: Mollie settlement ID (e.g., 'stl_xxxxx')

        Returns:
            datetime: Settlement date if available, None otherwise
        """
        if not settlement_id or not settlement_id.startswith('stl_'):
            return None

        try:
            settlement_url = f"{self.API_BASE_URL}/settlements/{settlement_id}"
            settlement_data = self._make_request("GET", settlement_url)

            if settlement_data and 'settledAt' in settlement_data:
                return make_aware(
                    datetime.fromisoformat(
                        settlement_data['settledAt'].replace("Z", "+00:00")
                    )
                )
        except Exception as e:
            logger.warning(f"Could not extract settlement date for {settlement_id}: {e}")

        return None

    def _save_to_cache(self, transaction_id, fee_data, payment_data):
        """Sauvegarde dans le cache Django."""
        if not self.organizer:
            return

        try:
            PSPTransactionCache.objects.update_or_create(
                organizer=self.organizer,
                psp_provider="mollie",
                transaction_id=transaction_id,
                defaults={
                    "amount_gross": fee_data["amount_gross"],
                    "amount_fee": fee_data["amount_fee"],
                    "amount_net": fee_data["amount_net"],
                    "currency": fee_data["currency"],
                    "settlement_id": fee_data.get("settlement_id", ""),
                    "status": fee_data["status"],
                    "fee_details": {"raw": fee_data["fee_details_text"]},
                    "transaction_date": make_aware(
                        datetime.fromisoformat(
                            payment_data.get("createdAt", "").replace("Z", "+00:00")
                        )
                    ),
                    "settlement_date": self._extract_settlement_date(fee_data.get("settlement_id")),
                },
            )
        except Exception as e:
            logger.error(f"Error saving to cache: {e}", exc_info=True)