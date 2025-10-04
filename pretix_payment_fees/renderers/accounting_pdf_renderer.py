"""
Renderer PDF pour rapports comptables avec frais PSP.

Inspiré du système de factures natif de Pretix (BaseReportlabInvoiceRenderer)
mais adapté pour générer des rapports comptables incluant les frais PSP.
"""
import logging
from decimal import Decimal
from io import BytesIO
from typing import Tuple

from django.utils.formats import date_format
from django.utils.translation import gettext as _, pgettext
from reportlab.lib import colors, pagesizes
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, StyleSheet1
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)
from pretix.base.models import OrderFee
from pretix.base.templatetags.money import money_filter

logger = logging.getLogger(__name__)


class NumberedCanvas(Canvas):
    """Canvas avec numérotation de pages."""

    def __init__(self, *args, **kwargs):
        self.font_regular = kwargs.pop('font_regular', 'Helvetica')
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            Canvas.showPage(self)
        Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont(self.font_regular, 8)
        text = pgettext("invoice", "Page %d of %d") % (self._pageNumber, page_count)
        self.drawRightString(self._pagesize[0] - 20 * mm, 10 * mm, text)
        self.restoreState()


class AccountingPDFRenderer:
    """
    Renderer PDF pour rapports comptables avec frais PSP.

    Génère un PDF professionnel listant les commandes avec leurs frais PSP,
    groupés par provider et avec totaux.
    """

    pagesize = pagesizes.A4
    left_margin = 25 * mm
    right_margin = 20 * mm
    top_margin = 20 * mm
    bottom_margin = 15 * mm
    font_regular = 'Helvetica'
    font_bold = 'Helvetica-Bold'

    def __init__(self, event, organizer=None):
        """
        Args:
            event: Événement Pretix (peut être None pour multi-événements)
            organizer: Organisateur (requis si event est None)
        """
        self.event = event
        self.organizer = organizer or (event.organizer if event else None)

    def _get_stylesheet(self):
        """Crée les styles de paragraphe."""
        stylesheet = StyleSheet1()
        stylesheet.add(
            ParagraphStyle(
                name='Normal',
                fontName=self.font_regular,
                fontSize=10,
                leading=12
            )
        )
        stylesheet.add(
            ParagraphStyle(
                name='Heading1',
                parent=stylesheet['Normal'],
                fontName=self.font_bold,
                fontSize=16,
                leading=20,
                spaceAfter=12
            )
        )
        stylesheet.add(
            ParagraphStyle(
                name='Heading2',
                parent=stylesheet['Normal'],
                fontName=self.font_bold,
                fontSize=12,
                leading=15,
                spaceAfter=6
            )
        )
        stylesheet.add(
            ParagraphStyle(
                name='FineprintLeft',
                parent=stylesheet['Normal'],
                fontSize=8,
                alignment=TA_LEFT
            )
        )
        stylesheet.add(
            ParagraphStyle(
                name='FineprintRight',
                parent=stylesheet['Normal'],
                fontSize=8,
                alignment=TA_RIGHT
            )
        )
        return stylesheet

    def generate(self, orders_data, date_from=None, date_to=None, output_file=None) -> Tuple[str, str, bytes]:
        """
        Génère le PDF du rapport comptable.

        Args:
            orders_data: Liste de dicts avec format:
                {
                    'order': Order instance,
                    'payment': OrderPayment instance,
                    'fees': QuerySet[OrderFee],
                    'amount_gross': Decimal,
                    'amount_fees': Decimal,
                    'amount_net': Decimal,
                    'provider': str
                }
            date_from: Date de début (optionnel)
            date_to: Date de fin (optionnel)
            output_file: BytesIO optionnel pour écrire directement

        Returns:
            Tuple (filename, mimetype, content_bytes)
        """
        buffer = output_file or BytesIO()

        # Créer le document
        doc = BaseDocTemplate(
            buffer,
            pagesize=self.pagesize,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin
        )

        # Frame pour le contenu
        frame = Frame(
            doc.leftMargin,
            doc.bottomMargin,
            doc.width,
            doc.height,
            id='normal'
        )

        # Template de page avec canvas numéroté
        template = PageTemplate(
            id='all',
            frames=[frame],
            onPage=lambda canvas, doc: None
        )
        doc.addPageTemplates([template])

        # Canvas personnalisé avec numérotation
        doc.canvasmaker = lambda *args, **kwargs: NumberedCanvas(
            *args, font_regular=self.font_regular, **kwargs
        )

        # Construire le contenu
        stylesheet = self._get_stylesheet()
        story = []

        # En-tête
        story.extend(self._build_header(stylesheet, date_from, date_to))

        # Tableau des commandes
        story.extend(self._build_orders_table(orders_data, stylesheet))

        # Totaux
        story.extend(self._build_totals(orders_data, stylesheet))

        # Générer le PDF
        doc.build(story)

        # Retourner le contenu
        if output_file:
            content = output_file.getvalue()
        else:
            content = buffer.getvalue()

        filename = self._generate_filename(date_from, date_to)

        return filename, 'application/pdf', content

    def _build_header(self, stylesheet, date_from, date_to):
        """Construit l'en-tête du rapport."""
        story = []

        # Titre
        title = _("Accounting Report")
        story.append(Paragraph(title, stylesheet['Heading1']))
        story.append(Spacer(1, 5 * mm))

        # Informations
        info_lines = []

        if self.organizer:
            info_lines.append(f"<b>{_('Organizer')}:</b> {self.organizer.name}")

        if self.event:
            info_lines.append(f"<b>{_('Event')}:</b> {self.event.name}")

        if date_from or date_to:
            period = _("Period: ")
            if date_from and date_to:
                period += f"{date_format(date_from, 'SHORT_DATE_FORMAT')} - {date_format(date_to, 'SHORT_DATE_FORMAT')}"
            elif date_from:
                period += f"{_('from')} {date_format(date_from, 'SHORT_DATE_FORMAT')}"
            elif date_to:
                period += f"{_('until')} {date_format(date_to, 'SHORT_DATE_FORMAT')}"
            info_lines.append(f"<b>{period}</b>")

        for line in info_lines:
            story.append(Paragraph(line, stylesheet['Normal']))

        story.append(Spacer(1, 10 * mm))

        return story

    def _build_orders_table(self, orders_data, stylesheet):
        """Construit le tableau des commandes."""
        story = []

        if not orders_data:
            story.append(Paragraph(_("No orders found for this period."), stylesheet['Normal']))
            return story

        # En-tête du tableau
        story.append(Paragraph(_("Orders"), stylesheet['Heading2']))
        story.append(Spacer(1, 3 * mm))

        # Données du tableau
        table_data = [
            [
                _("Order"),
                _("Date"),
                _("Provider"),
                _("Gross Amount"),
                _("PSP Fees"),
                _("Net Amount")
            ]
        ]

        currency = orders_data[0]['order'].event.currency if orders_data else 'EUR'

        for data in orders_data:
            order = data['order']
            payment = data['payment']

            table_data.append([
                order.code,
                date_format(payment.payment_date, 'SHORT_DATE_FORMAT') if payment.payment_date else '-',
                self._format_provider_name(data['provider']),
                money_filter(data['amount_gross'], currency),
                money_filter(data['amount_fees'], currency),
                money_filter(data['amount_net'], currency)
            ])

        # Style du tableau
        table = Table(table_data, colWidths=[
            30 * mm,  # Order code
            25 * mm,  # Date
            35 * mm,  # Provider
            25 * mm,  # Gross
            25 * mm,  # Fees
            25 * mm   # Net
        ])

        table.setStyle(TableStyle([
            # En-tête
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), self.font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),

            # Corps
            ('FONTNAME', (0, 1), (-1, -1), self.font_regular),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),  # Montants alignés à droite
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]))

        story.append(KeepTogether(table))
        story.append(Spacer(1, 10 * mm))

        return story

    def _build_totals(self, orders_data, stylesheet):
        """Construit la section des totaux."""
        story = []

        if not orders_data:
            return story

        # Calculer les totaux
        total_gross = sum(data['amount_gross'] for data in orders_data)
        total_fees = sum(data['amount_fees'] for data in orders_data)
        total_net = sum(data['amount_net'] for data in orders_data)

        # Totaux par provider
        by_provider = {}
        for data in orders_data:
            provider = data['provider']
            if provider not in by_provider:
                by_provider[provider] = {'gross': Decimal('0'), 'fees': Decimal('0'), 'count': 0}
            by_provider[provider]['gross'] += data['amount_gross']
            by_provider[provider]['fees'] += data['amount_fees']
            by_provider[provider]['count'] += 1

        currency = orders_data[0]['order'].event.currency

        # Section totaux
        story.append(Paragraph(_("Totals"), stylesheet['Heading2']))
        story.append(Spacer(1, 3 * mm))

        # Tableau des totaux globaux
        totals_data = [
            [_("Total Gross Amount"), money_filter(total_gross, currency)],
            [_("Total PSP Fees"), money_filter(total_fees, currency)],
            [_("Total Net Amount"), money_filter(total_net, currency)],
        ]

        totals_table = Table(totals_data, colWidths=[100 * mm, 50 * mm])
        totals_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), self.font_bold),
            ('FONTNAME', (1, 0), (1, -1), self.font_regular),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.black),
        ]))

        story.append(totals_table)
        story.append(Spacer(1, 8 * mm))

        # Tableau par provider
        story.append(Paragraph(_("By Payment Provider"), stylesheet['Heading2']))
        story.append(Spacer(1, 3 * mm))

        provider_data = [
            [_("Provider"), _("Orders"), _("Gross"), _("Fees"), _("Net")]
        ]

        for provider, totals in sorted(by_provider.items()):
            net = totals['gross'] - totals['fees']
            provider_data.append([
                self._format_provider_name(provider),
                str(totals['count']),
                money_filter(totals['gross'], currency),
                money_filter(totals['fees'], currency),
                money_filter(net, currency)
            ])

        provider_table = Table(provider_data, colWidths=[50 * mm, 20 * mm, 30 * mm, 30 * mm, 30 * mm])
        provider_table.setStyle(TableStyle([
            # En-tête
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), self.font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (1, 0), (-1, 0), 'CENTER'),

            # Corps
            ('FONTNAME', (0, 1), (-1, -1), self.font_regular),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        story.append(provider_table)

        return story

    def _format_provider_name(self, provider):
        """Formate le nom du provider pour l'affichage."""
        names = {
            'mollie': 'Mollie',
            'mollie_creditcard': 'Mollie (CB)',
            'mollie_bancontact': 'Mollie (Bancontact)',
            'mollie_ideal': 'Mollie (iDEAL)',
            'mollie_oauth': 'Mollie',
            'sumup': 'SumUp',
        }
        return names.get(provider, provider.title())

    def _generate_filename(self, date_from, date_to):
        """Génère le nom de fichier."""
        parts = ['accounting_report']

        if self.organizer:
            parts.append(self.organizer.slug)

        if self.event:
            parts.append(self.event.slug)

        if date_from:
            parts.append(date_from.strftime('%Y%m%d'))
        if date_to:
            parts.append(date_to.strftime('%Y%m%d'))

        return '_'.join(parts) + '.pdf'
