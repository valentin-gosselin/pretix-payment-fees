from django.utils.translation import gettext_lazy as _
import io
from decimal import Decimal

from django.template.loader import render_to_string
from weasyprint import HTML


class PDFRenderer:
    """Renderer PDF pour l'export comptable."""

    def __init__(self, organizer=None):
        self.organizer = organizer

    def render(self, export_data, totals, form_data):
        """
        Génère un PDF comptable.

        Args:
            export_data: Liste de dicts avec les données
            totals: Dict des totaux
            form_data: Paramètres d'export

        Returns:
            bytes: Contenu PDF
        """
        # Préparer le contexte pour le template
        context = {
            "organizer": self.organizer,
            "export_data": export_data,
            "totals": totals,
            "form_data": form_data,
            "date_from": form_data.get("date_from"),
            "date_to": form_data.get("date_to"),
            "controle": self._calculate_controle(totals),
        }

        # Rendre le template HTML
        html_content = self._render_html(context)

        # Convertir en PDF avec WeasyPrint
        pdf_file = HTML(string=html_content).write_pdf()

        return pdf_file

    def _render_html(self, context):
        """Génère le HTML pour le PDF."""
        # Template HTML inline pour éviter de créer un fichier séparé
        html_template = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Export Comptable PSP</title>
    <style>
        @page {
            size: A4 landscape;
            margin: 1cm;
        }
        body {
            font-family: 'DejaVu Sans', Arial, sans-serif;
            font-size: 10pt;
            color: #333;
        }
        h1 {
            text-align: center;
            color: #366092;
            font-size: 18pt;
            margin-bottom: 5px;
        }
        .header-info {
            text-align: center;
            margin-bottom: 20px;
            font-size: 9pt;
            color: #666;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            font-size: 9pt;
        }
        table.data-table th {
            background-color: #366092;
            color: white;
            padding: 8px 4px;
            text-align: left;
            border: 1px solid #ddd;
        }
        table.data-table td {
            padding: 6px 4px;
            border: 1px solid #ddd;
        }
        table.data-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .totals-section {
            margin-top: 30px;
        }
        .totals-box {
            background-color: #D9E1F2;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        .totals-box h3 {
            margin-top: 0;
            color: #366092;
            font-size: 12pt;
        }
        .totals-row {
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
        }
        .totals-label {
            font-weight: bold;
        }
        .totals-value {
            text-align: right;
        }
        .provider-section {
            margin-bottom: 15px;
            padding: 10px;
            background-color: #f5f5f5;
            border-left: 4px solid #366092;
        }
        .provider-section h4 {
            margin: 0 0 10px 0;
            color: #366092;
        }
        .controle-box {
            background-color: #FFF4E6;
            border: 2px solid #FF9800;
            padding: 15px;
            border-radius: 5px;
        }
        .controle-box h3 {
            margin-top: 0;
            color: #FF9800;
        }
        .amount {
            text-align: right;
            font-family: 'Courier New', monospace;
        }
        .footer {
            margin-top: 30px;
            text-align: center;
            font-size: 8pt;
            color: #999;
        }
    </style>
</head>
<body>
    <h1>" + str(_("Accounting Export with PSP Fees")) + "</h1>

    <div class="header-info">
        {% if organizer %}
        <strong>{{ organizer.name }}</strong><br>
        {% endif %}
        Période : {{ date_from|date:"d/m/Y" }} au {{ date_to|date:"d/m/Y" }}<br>
        Généré le : {{ now|date:"d/m/Y à H:i" }}
    </div>

    <table class="data-table">
        <thead>
            <tr>
                <th>Date</th>
                <th>Commande</th>
                <th>PSP</th>
                <th class="amount">Brut</th>
                <th class="amount">TVA</th>
                <th class="amount">Frais</th>
                <th class="amount">Net</th>
                <th>Devise</th>
                <th>ID Transaction</th>
                <th>Statut</th>
            </tr>
        </thead>
        <tbody>
            {% for row in export_data %}
            <tr>
                <td>{{ row.date_paiement|date:"d/m/Y H:i" }}</td>
                <td>{{ row.id_commande }}</td>
                <td>{{ row.moyen_paiement }}</td>
                <td class="amount">{{ row.montant_brut|floatformat:2 }}</td>
                <td class="amount">{{ row.tva_collectee|floatformat:2 }}</td>
                <td class="amount">{{ row.frais_psp_total|floatformat:2 }}</td>
                <td class="amount">{{ row.montant_net|floatformat:2 }}</td>
                <td>{{ row.devise }}</td>
                <td>{{ row.id_transaction_psp|truncatechars:20 }}</td>
                <td>{{ row.statut }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="totals-section">
        <div class="totals-box">
            <h3>Totaux Globaux</h3>
            <div class="totals-row">
                <span class="totals-label">Nombre de paiements :</span>
                <span class="totals-value">{{ totals.global.count }}</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">Montant Brut Total :</span>
                <span class="totals-value">{{ totals.global.montant_brut|floatformat:2 }} EUR</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">TVA Collectée Total :</span>
                <span class="totals-value">{{ totals.global.tva_collectee|floatformat:2 }} EUR</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">" + str(_("Total PSP Fees:")) + "</span>
                <span class="totals-value">{{ totals.global.frais_psp_total|floatformat:2 }} EUR</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">Montant Net Total :</span>
                <span class="totals-value"><strong>{{ totals.global.montant_net|floatformat:2 }} EUR</strong></span>
            </div>
        </div>

        <h3>Totaux par Moyen de Paiement</h3>
        {% for provider, provider_totals in totals.by_provider.items %}
        <div class="provider-section">
            <h4>{{ provider }}</h4>
            <div class="totals-row">
                <span class="totals-label">Nombre :</span>
                <span class="totals-value">{{ provider_totals.count }}</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">Montant Brut :</span>
                <span class="totals-value">{{ provider_totals.montant_brut|floatformat:2 }} EUR</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">" + str(_("PSP Fees:")) + "</span>
                <span class="totals-value">{{ provider_totals.frais_psp_total|floatformat:2 }} EUR</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">Montant Net :</span>
                <span class="totals-value"><strong>{{ provider_totals.montant_net|floatformat:2 }} EUR</strong></span>
            </div>
        </div>
        {% endfor %}

        <div class="controle-box">
            <h3>Contrôle Comptable</h3>
            <div class="totals-row">
                <span class="totals-label">Brut - TVA :</span>
                <span class="totals-value">{{ controle.brut_moins_tva|floatformat:2 }} EUR</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">(Brut - TVA) - Frais :</span>
                <span class="totals-value">{{ controle.final|floatformat:2 }} EUR</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">Net attendu :</span>
                <span class="totals-value">{{ totals.global.montant_net|floatformat:2 }} EUR</span>
            </div>
            <div class="totals-row">
                <span class="totals-label">Différence :</span>
                <span class="totals-value">{{ controle.difference|floatformat:2 }} EUR</span>
            </div>
        </div>
    </div>

    <div class="footer">
        Export généré par Pretix Export Frais - Plugin comptable PSP
    </div>
</body>
</html>
        """

        # Rendre avec Django template
        from django.template import Context, Template
        from django.utils.timezone import now

        context["now"] = now()
        template = Template(html_template)
        return template.render(Context(context))

    def _calculate_controle(self, totals):
        """Calcule les valeurs de contrôle."""
        brut_moins_tva = (
            totals["global"]["montant_brut"] - totals["global"]["tva_collectee"]
        )
        final = brut_moins_tva - totals["global"]["frais_psp_total"]
        difference = abs(final - totals["global"]["montant_net"])

        return {
            "brut_moins_tva": brut_moins_tva,
            "final": final,
            "difference": difference,
        }