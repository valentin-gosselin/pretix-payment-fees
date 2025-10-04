"""
Commande Django pour synchroniser les frais PSP.

Usage:
    python manage.py sync_psp_fees --organizer=myorg --from=2025-01-01 --to=2025-12-31
    python manage.py sync_psp_fees --organizer=myorg --event=myevent --days=30
    python manage.py sync_psp_fees --organizer=myorg --days=7 --force
    python manage.py sync_psp_fees --organizer=myorg --dry-run
"""
import logging
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, now
from pretix.base.models import Event, Organizer

from ...services.psp_sync import PSPSyncService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Synchronise les frais PSP depuis Mollie et SumUp"

    def add_arguments(self, parser):
        parser.add_argument(
            "--organizer",
            type=str,
            required=True,
            help="Organizer slug (required)",
        )
        parser.add_argument(
            "--event",
            type=str,
            help="Event slug (optional, if absent = all organizer events)",
        )
        parser.add_argument(
            "--from",
            dest="date_from",
            type=str,
            help="Date de début (format: YYYY-MM-DD ou YYYY-MM-DD HH:MM:SS)",
        )
        parser.add_argument(
            "--to",
            dest="date_to",
            type=str,
            help="Date de fin (format: YYYY-MM-DD ou YYYY-MM-DD HH:MM:SS)",
        )
        parser.add_argument(
            "--days",
            type=int,
            help="Nombre de jours en arrière (alternatif à --from/--to)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Resynchroniser même si déjà synchronisé",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simuler sans modifier la base de données",
        )

    def handle(self, *args, **options):
        organizer_slug = options["organizer"]
        event_slug = options.get("event")
        date_from_str = options.get("date_from")
        date_to_str = options.get("date_to")
        days_back = options.get("days")
        force = options.get("force", False)
        dry_run = options.get("dry_run", False)

        # Récupérer l'organisateur
        try:
            organizer = Organizer.objects.get(slug=organizer_slug)
        except Organizer.DoesNotExist:
            raise CommandError(f"Organisateur '{organizer_slug}' introuvable")

        # Parser les dates
        date_from = None
        date_to = None

        if date_from_str:
            try:
                date_from = parse_datetime(date_from_str)
                if not date_from:
                    # Si parse_datetime échoue, essayer juste la date
                    date_from = make_aware(
                        datetime.strptime(date_from_str, "%Y-%m-%d")
                    )
            except ValueError:
                raise CommandError(
                    f"Format de date invalide pour --from: {date_from_str}"
                )

        if date_to_str:
            try:
                date_to = parse_datetime(date_to_str)
                if not date_to:
                    date_to = make_aware(datetime.strptime(date_to_str, "%Y-%m-%d"))
            except ValueError:
                raise CommandError(
                    f"Format de date invalide pour --to: {date_to_str}"
                )

        # Initialiser le service
        sync_service = PSPSyncService(organizer=organizer)

        # Afficher les paramètres
        self.stdout.write(self.style.SUCCESS("=== Synchronisation des frais PSP ==="))
        self.stdout.write(f"Organisateur: {organizer.name} ({organizer.slug})")

        if event_slug:
            self.stdout.write(f"Événement: {event_slug}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("MODE DRY-RUN: Aucune modification ne sera faite")
            )

        if force:
            self.stdout.write(
                self.style.WARNING(
                    "MODE FORCE: Resynchronisation des paiements déjà synchronisés"
                )
            )

        # Synchroniser
        try:
            if event_slug:
                # Synchroniser un événement spécifique
                try:
                    event = Event.objects.get(slug=event_slug, organizer=organizer)
                except Event.DoesNotExist:
                    raise CommandError(
                        f"Événement '{event_slug}' introuvable pour l'organisateur '{organizer_slug}'"
                    )

                self.stdout.write(f"\nSynchronisation de l'événement {event.name}...")

                result = sync_service.sync_event_payments(
                    event=event,
                    date_from=date_from,
                    date_to=date_to,
                    days_back=days_back,
                    force=force,
                    dry_run=dry_run,
                )
            else:
                # Synchroniser tous les événements de l'organisateur
                self.stdout.write(
                    f"\nSynchronisation de tous les événements de {organizer.name}..."
                )

                result = sync_service.sync_organizer_payments(
                    date_from=date_from,
                    date_to=date_to,
                    days_back=days_back,
                    force=force,
                    dry_run=dry_run,
                )

            # Afficher les résultats
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write(self.style.SUCCESS("Résultats de la synchronisation:"))
            self.stdout.write(f"  Total des paiements traités: {result.total_payments}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Paiements synchronisés: {result.synced_payments}"
                )
            )
            self.stdout.write(
                self.style.WARNING(f"  Skipped payments: {result.skipped_payments}")
            )

            if result.failed_payments > 0:
                self.stdout.write(
                    self.style.ERROR(
                        f"  Failed payments: {result.failed_payments}"
                    )
                )

            self.stdout.write(
                f"  Total des frais synchronisés: {result.total_fees:.2f} EUR"
            )

            # Afficher les erreurs
            if result.errors:
                self.stdout.write("\n" + self.style.ERROR("Erreurs détaillées:"))
                for error in result.errors[:10]:  # Limiter à 10 erreurs
                    self.stdout.write(
                        f"  - Paiement {error['payment_id']}: {error['error']}"
                    )
                if len(result.errors) > 10:
                    self.stdout.write(
                        f"  ... et {len(result.errors) - 10} autres erreurs"
                    )

            self.stdout.write("=" * 60)

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        "\nDry-run mode: No changes were made"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS("\nSynchronisation terminée avec succès!")
                )

        except Exception as e:
            logger.exception("Erreur lors de la synchronisation")
            raise CommandError(f"Erreur lors de la synchronisation: {str(e)}")
