import pytest
from decimal import Decimal
from datetime import datetime
from django.utils.timezone import make_aware

from pretix_payment_fees.renderers.csv_renderer import CSVRenderer
from pretix_payment_fees.renderers.excel_renderer import ExcelRenderer


def test_csv_renderer():
    """Test le renderer CSV."""
    export_data = [
        {
            "date_paiement": make_aware(datetime(2025, 9, 1, 10, 30)),
            "id_commande": "ABC123",
            "moyen_paiement": "mollie",
            "montant_brut": Decimal("100.00"),
            "tva_collectee": Decimal("20.00"),
            "frais_psp_total": Decimal("2.35"),
            "detail_frais": "Mollie fee: 2.35 EUR",
            "montant_net": Decimal("97.65"),
            "devise": "EUR",
            "id_transaction_psp": "tr_abc123",
            "settlement_id": "stl_xyz789",
            "statut": "ok",
        }
    ]

    totals = {
        "global": {
            "count": 1,
            "montant_brut": Decimal("100.00"),
            "tva_collectee": Decimal("20.00"),
            "frais_psp_total": Decimal("2.35"),
            "montant_net": Decimal("97.65"),
        },
        "by_provider": {
            "mollie": {
                "count": 1,
                "montant_brut": Decimal("100.00"),
                "tva_collectee": Decimal("20.00"),
                "frais_psp_total": Decimal("2.35"),
                "montant_net": Decimal("97.65"),
            }
        },
    }

    form_data = {"date_from": datetime(2025, 9, 1).date(), "date_to": datetime(2025, 9, 30).date()}

    renderer = CSVRenderer()
    csv_content = renderer.render(export_data, totals, form_data)

    assert isinstance(csv_content, bytes)
    assert b"ABC123" in csv_content
    assert b"mollie" in csv_content
    assert b"100.00" in csv_content


def test_excel_renderer():
    """Test le renderer Excel."""
    export_data = [
        {
            "date_paiement": make_aware(datetime(2025, 9, 1, 10, 30)),
            "id_commande": "ABC123",
            "moyen_paiement": "mollie",
            "montant_brut": Decimal("100.00"),
            "tva_collectee": Decimal("20.00"),
            "frais_psp_total": Decimal("2.35"),
            "detail_frais": "Mollie fee: 2.35 EUR",
            "montant_net": Decimal("97.65"),
            "devise": "EUR",
            "id_transaction_psp": "tr_abc123",
            "settlement_id": "stl_xyz789",
            "statut": "ok",
        }
    ]

    totals = {
        "global": {
            "count": 1,
            "montant_brut": Decimal("100.00"),
            "tva_collectee": Decimal("20.00"),
            "frais_psp_total": Decimal("2.35"),
            "montant_net": Decimal("97.65"),
        },
        "by_provider": {
            "mollie": {
                "count": 1,
                "montant_brut": Decimal("100.00"),
                "tva_collectee": Decimal("20.00"),
                "frais_psp_total": Decimal("2.35"),
                "montant_net": Decimal("97.65"),
            }
        },
    }

    form_data = {"date_from": datetime(2025, 9, 1).date(), "date_to": datetime(2025, 9, 30).date()}

    renderer = ExcelRenderer()
    excel_content = renderer.render(export_data, totals, form_data)

    assert isinstance(excel_content, bytes)
    assert len(excel_content) > 0
    # Vérifier que c'est un fichier Excel valide (commence par PK pour ZIP)
    assert excel_content[:2] == b"PK"