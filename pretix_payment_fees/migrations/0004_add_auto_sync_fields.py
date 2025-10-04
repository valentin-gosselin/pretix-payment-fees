# Generated migration for auto-sync fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretix_payment_fees', '0003_settlement_rate_cache'),
    ]

    operations = [
        migrations.AddField(
            model_name='pspconfig',
            name='auto_sync_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Activer la synchronisation automatique des frais PSP',
                verbose_name='Synchronisation automatique'
            ),
        ),
        migrations.AddField(
            model_name='pspconfig',
            name='auto_sync_interval',
            field=models.CharField(
                choices=[
                    ('hourly', 'Toutes les heures'),
                    ('6hours', 'Toutes les 6 heures'),
                    ('daily', 'Une fois par jour')
                ],
                default='6hours',
                help_text='Fréquence de la synchronisation automatique',
                max_length=20,
                verbose_name='Fréquence de synchronisation'
            ),
        ),
        migrations.AddField(
            model_name='pspconfig',
            name='last_auto_sync',
            field=models.DateTimeField(
                blank=True,
                help_text='Date et heure de la dernière synchronisation automatique',
                null=True,
                verbose_name='Dernière synchronisation automatique'
            ),
        ),
    ]
