import csv
import io

from django.utils.translation import gettext_lazy as _


class CSVRenderer:
    """Renderer CSV pour l'export comptable."""

    HEADERS = [
        "Date Paiement",
        "ID Commande",
        "Moyen Paiement",
        "Montant Brut",
        str(_("VAT Collected")),
        str(_("Total PSP Fees")),
        str(_("Fee Details")),
        "Montant Net",
        "Devise",
        "ID Transaction PSP",
        "Settlement ID",
        "Statut",
    ]

    def render(self, export_data, totals, form_data):
        """
        Génère un CSV.

        Args:
            export_data: Liste de dicts avec les données
            totals: Dict des totaux
            form_data: Paramètres d'export

        Returns:
            bytes: Contenu CSV
        """
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", quotechar='"')

        # En-tête
        writer.writerow(self.HEADERS)

        # Lignes de données
        for row in export_data:
            writer.writerow(
                [
                    row["date_paiement"].strftime("%Y-%m-%d %H:%M:%S"),
                    row["id_commande"],
                    row["moyen_paiement"],
                    str(row["montant_brut"]),
                    str(row["tva_collectee"]),
                    str(row["frais_psp_total"]),
                    row["detail_frais"],
                    str(row["montant_net"]),
                    row["devise"],
                    row["id_transaction_psp"],
                    row["settlement_id"],
                    row["statut"],
                ]
            )

        # Ligne vide
        writer.writerow([])

        # Totaux globaux
        writer.writerow(["=== TOTAUX GLOBAUX ==="])
        writer.writerow(["Nombre de paiements", totals["global"]["count"]])
        writer.writerow(["Montant Brut Total", str(totals["global"]["montant_brut"])])
        writer.writerow([str(_("Total VAT Collected")), str(totals["global"]["tva_collectee"])])
        writer.writerow([str(_("Total PSP Fees")), str(totals["global"]["frais_psp_total"])])
        writer.writerow(["Montant Net Total", str(totals["global"]["montant_net"])])

        # Ligne vide
        writer.writerow([])

        # Totaux par moyen de paiement
        writer.writerow(["=== TOTAUX PAR MOYEN DE PAIEMENT ==="])
        for provider, provider_totals in totals["by_provider"].items():
            writer.writerow([f"--- {provider} ---"])
            writer.writerow(["Nombre", provider_totals["count"]])
            writer.writerow(["Montant Brut", str(provider_totals["montant_brut"])])
            writer.writerow([str(_("VAT Collected")), str(provider_totals["tva_collectee"])])
            writer.writerow([str(_("PSP Fees")), str(provider_totals["frais_psp_total"])])
            writer.writerow(["Montant Net", str(provider_totals["montant_net"])])
            writer.writerow([])

        # Ligne vide
        writer.writerow([])

        # Bloc de contrôle
        writer.writerow(["=== CONTRÔLE COMPTABLE ==="])
        controle_brut_moins_tva = (
            totals["global"]["montant_brut"] - totals["global"]["tva_collectee"]
        )
        controle_final = controle_brut_moins_tva - totals["global"]["frais_psp_total"]
        writer.writerow(["Brut - TVA", str(controle_brut_moins_tva)])
        writer.writerow(["(Brut - TVA) - Frais", str(controle_final)])
        writer.writerow(["Net attendu", str(totals["global"]["montant_net"])])
        writer.writerow(
            [
                str(_("Difference")),
                str(abs(controle_final - totals["global"]["montant_net"])),
            ]
        )

        return output.getvalue().encode("utf-8-sig")  # BOM pour Excel
