"""
Client OAuth pour Mollie Connect.

Gère l'authentification OAuth 2.0 avec Mollie pour accéder aux APIs
nécessitant des permissions étendues (Balances, Settlements).
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from django.utils.timezone import now

import requests

logger = logging.getLogger(__name__)


class MollieOAuthClient:
    """
    Client pour gérer OAuth 2.0 avec Mollie Connect.

    Endpoints OAuth Mollie:
    - Autorisation: https://www.mollie.com/oauth2/authorize
    - Token: https://api.mollie.com/oauth2/tokens
    - Révocation: https://api.mollie.com/oauth2/tokens/revoke
    """

    OAUTH_AUTHORIZE_URL = "https://www.mollie.com/oauth2/authorize"
    OAUTH_TOKEN_URL = "https://api.mollie.com/oauth2/tokens"
    OAUTH_REVOKE_URL = "https://api.mollie.com/oauth2/tokens/revoke"
    API_BASE_URL = "https://api.mollie.com/v2"

    def __init__(self, client_id: str, client_secret: str, access_token: str = None):
        """
        Initialise le client OAuth.

        Args:
            client_id: Client ID de l'application Mollie Connect
            client_secret: Client Secret de l'application
            access_token: Access token OAuth (optionnel)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        scope: str = "payments.read balances.read settlements.read",
    ) -> str:
        """
        Génère l'URL d'autorisation OAuth.

        Args:
            redirect_uri: URL de callback après autorisation
            state: Token CSRF pour sécurité
            scope: Permissions demandées (espace-séparé)

        Returns:
            URL complète d'autorisation Mollie
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": scope,
            "response_type": "code",
            "approval_prompt": "auto",  # Ne redemander que si nécessaire
        }

        query_string = "&".join([f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()])
        auth_url = f"{self.OAUTH_AUTHORIZE_URL}?{query_string}"

        logger.info(f"Generated OAuth authorization URL: {auth_url}")
        return auth_url

    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict:
        """
        Échange le code d'autorisation contre un access token.

        Args:
            code: Code d'autorisation reçu de Mollie
            redirect_uri: URL de callback (doit correspondre exactement)

        Returns:
            Dict contenant: access_token, refresh_token, expires_in, token_type, scope

        Raises:
            requests.exceptions.HTTPError: Si l'échange échoue
        """
        logger.info(f"Exchanging authorization code for access token")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = requests.post(self.OAUTH_TOKEN_URL, data=data, timeout=30)
            response.raise_for_status()

            token_data = response.json()
            logger.info(
                f"Successfully obtained access token (expires in {token_data.get('expires_in')}s)"
            )

            return token_data

        except requests.exceptions.HTTPError as e:
            logger.error(f"OAuth token exchange failed: {e}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token exchange: {e}", exc_info=True)
            raise

    def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Rafraîchit l'access token expiré.

        Args:
            refresh_token: Refresh token OAuth

        Returns:
            Dict contenant: access_token, refresh_token (nouveau), expires_in

        Raises:
            requests.exceptions.HTTPError: Si le refresh échoue
        """
        logger.info(f"Refreshing access token")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = requests.post(self.OAUTH_TOKEN_URL, data=data, timeout=30)
            response.raise_for_status()

            token_data = response.json()
            logger.info(
                f"Successfully refreshed access token (expires in {token_data.get('expires_in')}s)"
            )

            return token_data

        except requests.exceptions.HTTPError as e:
            logger.error(f"Token refresh failed: {e}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}", exc_info=True)
            raise

    def revoke_token(self, token: str, token_type_hint: str = "access_token") -> bool:
        """
        Révoque un access token ou refresh token.

        Args:
            token: Token à révoquer
            token_type_hint: Type de token ('access_token' ou 'refresh_token')

        Returns:
            True si la révocation a réussi, False sinon
        """
        logger.info(f"Revoking {token_type_hint}")

        data = {
            "token": token,
            "token_type_hint": token_type_hint,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = requests.post(self.OAUTH_REVOKE_URL, data=data, timeout=30)
            response.raise_for_status()

            logger.info(f"Successfully revoked {token_type_hint}")
            return True

        except requests.exceptions.HTTPError as e:
            logger.error(f"Token revocation failed: {e}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during token revocation: {e}", exc_info=True)
            return False

    def get_balance_transactions(
        self, balance_id: str = "primary", payment_id: str = None, limit: int = 250
    ) -> Optional[Dict]:
        """
        Récupère les transactions d'un balance (pour obtenir les frais réels).

        Args:
            balance_id: ID du balance (default: 'primary')
            payment_id: Filtrer sur un paiement spécifique (optionnel)
            limit: Nombre max de transactions à récupérer

        Returns:
            Dict contenant les transactions, ou None si erreur
        """
        if not self.access_token:
            logger.error("No access token available for balance transactions API")
            return None

        url = f"{self.API_BASE_URL}/balances/{balance_id}/transactions"
        params = {"limit": limit}

        if payment_id:
            # Filtrer sur le paiement spécifique si possible
            # Note: l'API Mollie ne supporte pas toujours ce filtre, il faudra chercher manuellement
            pass

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            logger.info(f"Fetching balance transactions from {url}")
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Successfully fetched {data.get('count', 0)} balance transactions")

            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Access token expired or invalid (401 Unauthorized)")
            else:
                logger.error(f"Balance transactions API error: {e}")
                logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching balance transactions: {e}", exc_info=True)
            return None

    def get_settlement_details(self, settlement_id: str) -> Optional[Dict]:
        """
        Récupère les détails d'un settlement via OAuth (nécessaire pour accéder aux frais).

        Args:
            settlement_id: ID du settlement Mollie (stl_xxx)

        Returns:
            Dict avec les détails du settlement ou None
        """
        if not self.access_token:
            logger.error("No access token available for settlements API")
            return None

        url = f"{self.API_BASE_URL}/settlements/{settlement_id}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            logger.info(f"Fetching settlement {settlement_id} with OAuth")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.debug(f"Settlement data: {data}")
            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Access token expired or invalid (401 Unauthorized)")
            elif e.response.status_code == 403:
                logger.error("Access forbidden - OAuth scopes may be insufficient")
            else:
                logger.error(f"Settlements API error: {e}")
                logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching settlement: {e}", exc_info=True)
            return None

    def get_payment_fees_from_settlement(
        self, payment_id: str, settlement_id: str
    ) -> Optional[Dict]:
        """
        Récupère les frais réels d'un paiement depuis son settlement via OAuth.

        La vraie logique: Mollie ne montre pas les frais dans l'API Payment standard.
        Les frais sont visibles dans le Settlement, qui nécessite OAuth.

        Args:
            payment_id: ID du paiement Mollie (tr_xxx)
            settlement_id: ID du settlement (stl_xxx)

        Returns:
            Dict avec amount_fee, currency, fee_details ou None
        """
        logger.info(f"Fetching real fees for payment {payment_id} from settlement {settlement_id}")

        settlement_data = self.get_settlement_details(settlement_id)
        if not settlement_data:
            logger.warning(f"Could not fetch settlement {settlement_id}")
            return None

        # Structure du settlement:
        # {
        #   "amount": {"value": "123.45", "currency": "EUR"},  // Total payé
        #   "periods": { ... },
        #   "revenue": [
        #     {
        #       "description": "iDEAL",
        #       "method": "ideal",
        #       "count": 5,
        #       "amountNet": {"value": "100.00", "currency": "EUR"},
        #       "amountVat": {"value": "0.00", "currency": "EUR"},
        #       "amountGross": {"value": "101.45", "currency": "EUR"}
        #     }
        #   ],
        #   "costs": [
        #     {
        #       "description": "iDEAL transaction costs",
        #       "amountNet": {"value": "1.45", "currency": "EUR"},
        #       "amountVat": {"value": "0.00", "currency": "EUR"},
        #       "amountGross": {"value": "1.45", "currency": "EUR"},
        #       "count": 5,
        #       "rate": {
        #         "fixed": {"value": "0.29", "currency": "EUR"},
        #         "percentage": "0.00"
        #       }
        #     }
        #   ]
        # }

        # Malheureusement, le settlement contient les frais GLOBAUX par méthode,
        # pas par paiement individuel. On ne peut pas isoler les frais d'un seul paiement.
        # SOLUTION: Utiliser get_payment_fees_from_balance() à la place

        logger.warning(
            f"Settlement API donne les frais globaux, pas par paiement. "
            f"Utilisez get_payment_fees_from_balance() pour les frais réels."
        )
        return None

    def get_payment_fees_from_balance(self, payment_id: str) -> Optional[Dict]:
        """
        Récupère les VRAIS frais d'un paiement depuis Balance Transactions.

        DÉCOUVERTE MAJEURE (tests réels effectués):
        Les Balance Transactions contiennent un champ 'deductions' qui donne
        les VRAIS frais par paiement, incluant TOUS les coûts (transaction fees,
        chargebacks reserves, application fees, etc.)

        Structure réelle confirmée:
        {
          "type": "payment",
          "context": {"paymentId": "tr_xxx", "paymentDescription": "..."},
          "initialAmount": {"value": "20.00", "currency": "EUR"},
          "resultAmount": {"value": "15.51", "currency": "EUR"},
          "deductions": {"value": "-4.49", "currency": "EUR"}  ← VRAIS FRAIS!
        }

        Args:
            payment_id: ID du paiement Mollie (tr_xxx)

        Returns:
            Dict avec amount_fee, currency, fee_details ou None
        """
        logger.info(
            f"Fetching REAL fees for payment {payment_id} from Balance Transactions deductions"
        )

        if not self.access_token:
            logger.error("No access token available for balance transactions")
            return None

        url = f"{self.API_BASE_URL}/balances/primary/transactions"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        params = {"limit": 250}  # Maximum par page

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            transactions = data.get("_embedded", {}).get("balance_transactions", [])

            logger.debug(f"Fetched {len(transactions)} balance transactions")

            # Chercher la transaction correspondant à ce paiement
            for tx in transactions:
                context = tx.get("context", {})
                tx_payment_id = context.get("paymentId", "")

                if tx_payment_id == payment_id and tx.get("type") == "payment":
                    # TROUVÉ ! Extraire les frais depuis deductions
                    deductions = tx.get("deductions", {})
                    deductions_value = deductions.get("value", "0.00")
                    currency = deductions.get("currency", "EUR")

                    # deductions est négatif (ex: -4.49), on prend la valeur absolue
                    fee_amount = abs(Decimal(deductions_value))

                    initial_amt = tx.get("initialAmount", {}).get("value", "0.00")
                    result_amt = tx.get("resultAmount", {}).get("value", "0.00")

                    logger.info(
                        f"✓ VRAIS FRAIS trouvés pour {payment_id}: "
                        f"{initial_amt} → {result_amt} (frais: {fee_amount} {currency})"
                    )

                    return {
                        "amount_fee": fee_amount,
                        "currency": currency,
                        "fee_details_text": f"Mollie fees (real OAuth): {fee_amount:.2f} {currency}",
                        "source": "oauth_balance_deductions",
                        "initial_amount": Decimal(initial_amt),
                        "result_amount": Decimal(result_amt),
                    }

            # Paiement non trouvé dans les transactions récentes
            logger.warning(
                f"Payment {payment_id} not found in last {len(transactions)} balance transactions. "
                f"May be too old or not yet settled."
            )
            return None

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Access token expired or invalid (401)")
            elif e.response.status_code == 403:
                logger.error("Access forbidden - check OAuth scopes (balances.read required)")
            else:
                logger.error(f"Balance Transactions API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching balance transactions: {e}", exc_info=True)
            return None

    def is_token_valid(self, expires_at: datetime) -> bool:
        """
        Vérifie si le token est encore valide.

        Args:
            expires_at: Date d'expiration du token

        Returns:
            True si le token est valide, False sinon
        """
        if not expires_at:
            return False

        # Considérer le token comme expiré 5 minutes avant l'expiration réelle
        buffer = timedelta(minutes=5)
        return now() < (expires_at - buffer)

    def get_settlement_rates(
        self, settlement_id: str, organizer
    ) -> Optional[Dict[str, Dict[str, str]]]:
        """
        Récupère les rates de frais d'un settlement.

        Cette méthode utilise le cache SettlementRateCache pour éviter les appels répétés.
        Les rates retournés permettent de calculer les frais EXACTS par transaction:
        fee = fixed + (amount × percentage / 100)

        Args:
            settlement_id: ID du settlement Mollie (stl_xxx)
            organizer: Instance Organizer (pour le cache)

        Returns:
            Dict des rates par type de carte:
            {
                "Credit card - Carte Bancaire": {"fixed": "0.25", "percentage": "1.2"},
                "Credit card - Domestic consumer cards": {"fixed": "0.25", "percentage": "1.8"},
                ...
            }
            ou None si erreur
        """
        from ..models import PSPConfig, SettlementRateCache

        # 1. Vérifier le cache
        try:
            cached = SettlementRateCache.objects.get(
                settlement_id=settlement_id, organizer=organizer
            )
            logger.info(f"✓ Settlement rates trouvés en cache: {settlement_id}")
            return cached.rates_data
        except SettlementRateCache.DoesNotExist:
            logger.info(f"Settlement rates non en cache, appel API: {settlement_id}")

        # 2. Appeler l'API Settlement
        settlement_data = self.get_settlement_details(settlement_id)
        if not settlement_data:
            logger.error(f"Impossible de récupérer le settlement {settlement_id}")
            return None

        # 3. Parser les rates depuis periods.{year}.{month}.costs
        rates_dict = {}
        periods = settlement_data.get("periods", {})

        settled_at = settlement_data.get("settledAt")
        period_year = None
        period_month = None

        for year_str, year_data in periods.items():
            if not isinstance(year_data, dict):
                continue

            for month_str, month_data in year_data.items():
                if not isinstance(month_data, dict):
                    continue

                # Extraire year/month
                period_year = int(year_str)
                period_month = int(month_str)

                # Extraire les costs
                costs = month_data.get("costs", [])
                for cost_entry in costs:
                    description = cost_entry.get("description", "")
                    rate_data = cost_entry.get("rate", {})

                    if not rate_data:
                        continue

                    # Extraire fixed et percentage
                    fixed_obj = rate_data.get("fixed", {})
                    fixed_value = fixed_obj.get("value", "0.00")
                    percentage = rate_data.get("percentage", "0.00")

                    rates_dict[description] = {
                        "fixed": str(fixed_value),
                        "percentage": str(percentage),
                    }

                    logger.debug(
                        f"Rate trouvé: {description} → "
                        f"fixed={fixed_value}, percentage={percentage}%"
                    )

        if not rates_dict:
            logger.warning(f"Aucun rate trouvé dans le settlement {settlement_id}")
            return None

        logger.info(f"✓ {len(rates_dict)} rates extraits du settlement {settlement_id}")

        # 4. Sauvegarder en cache
        try:
            SettlementRateCache.objects.create(
                organizer=organizer,
                settlement_id=settlement_id,
                period_year=period_year or 2025,
                period_month=period_month or 1,
                rates_data=rates_dict,
                settled_at=settled_at,
            )
            logger.info(f"✓ Rates sauvegardés en cache pour {settlement_id}")
        except Exception as e:
            logger.warning(f"Impossible de sauvegarder en cache: {e}")

        # 5. Mettre à jour last_known_settlement_rates
        try:
            psp_config = PSPConfig.objects.get(organizer=organizer)
            psp_config.last_known_settlement_rates = rates_dict
            psp_config.save(update_fields=["last_known_settlement_rates"])
            logger.info(f"✓ last_known_settlement_rates mis à jour")
        except PSPConfig.DoesNotExist:
            logger.warning(f"PSPConfig non trouvé pour mettre à jour last_known_settlement_rates")

        return rates_dict

    def calculate_exact_fee(
        self, payment_data: Dict, rates: Dict[str, Dict[str, str]]
    ) -> Optional[Decimal]:
        """
        Calcule le frais EXACT d'un paiement en utilisant les rates du settlement.

        Formule: fee = fixed + (amount × percentage / 100)

        Args:
            payment_data: Données du paiement (depuis API /v2/payments/{id})
                Contient: amount, details.cardLabel, details.feeRegion
            rates: Dict des rates par type de carte (depuis get_settlement_rates)

        Returns:
            Montant exact des frais en Decimal, ou None si impossible de calculer
        """
        # 1. Extraire les infos du paiement
        amount_obj = payment_data.get("amount", {})
        amount_value = amount_obj.get("value", "0.00")
        amount = Decimal(amount_value)

        details = payment_data.get("details", {})
        fee_region = details.get("feeRegion")
        card_label = details.get("cardLabel", "")

        logger.debug(
            f"Calcul fee pour payment: amount={amount}, "
            f"feeRegion={fee_region}, cardLabel={card_label}"
        )

        # 2. Mapper feeRegion vers le type de coût dans le settlement
        # Mapping découvert via tests réels:
        # - "carte-bancaire" → "Credit card - Carte Bancaire"
        # - "intra-eu" / "eu-card" → "Credit card - Domestic consumer cards"
        # - "other" / null → "Credit card - Other"

        fee_region_mapping = {
            "carte-bancaire": "Credit card - Carte Bancaire",
            "intra-eu": "Credit card - Domestic consumer cards",
            "eu-card": "Credit card - Domestic consumer cards",
            "other": "Credit card - Other",
        }

        rate_description = fee_region_mapping.get(fee_region)

        if not rate_description:
            logger.warning(
                f"feeRegion inconnu: {fee_region}. "
                f"Tentative de recherche par cardLabel ou fallback."
            )
            # Fallback: chercher "Carte Bancaire" dans rates
            if "Credit card - Carte Bancaire" in rates:
                rate_description = "Credit card - Carte Bancaire"
            else:
                # Prendre le premier rate disponible (en excluant Rounding differences)
                for key in rates.keys():
                    if "Rounding" not in key:
                        rate_description = key
                        break
                if not rate_description:
                    rate_description = list(rates.keys())[0] if rates else None

        if not rate_description or rate_description not in rates:
            logger.error(
                f"Impossible de trouver le rate pour feeRegion={fee_region}. "
                f"Rates disponibles: {list(rates.keys())}"
            )
            return None

        # FILTRER les "Rounding differences" - ce ne sont pas de vrais paiements clients
        if "Rounding" in rate_description:
            logger.info(
                f"⊗ Paiement ignoré: {rate_description} (ajustement comptable Mollie, pas un vrai paiement client)"
            )
            return None

        # 3. Extraire les rates
        rate_data = rates[rate_description]
        fixed_str = rate_data.get("fixed", "0.00")
        percentage_str = rate_data.get("percentage", "0.00")

        fixed = Decimal(fixed_str)
        percentage = Decimal(percentage_str)

        # 4. Calculer le frais
        # fee = fixed + (amount × percentage / 100)
        fee = fixed + (amount * percentage / Decimal("100"))

        logger.info(
            f"✓ Fee calculé: {rate_description} → "
            f"{fixed} + ({amount} × {percentage}%) = {fee:.2f} EUR"
        )

        return fee
