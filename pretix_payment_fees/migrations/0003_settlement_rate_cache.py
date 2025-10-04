# Generated migration for Settlement Rate Cache

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pretix_payment_fees', '0002_add_mollie_oauth_fields'),
        ('pretixbase', '0001_initial'),
    ]

    operations = [
        # Add last_known_settlement_rates to PSPConfig
        migrations.AddField(
            model_name='pspconfig',
            name='last_known_settlement_rates',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Derniers rates de settlement récupérés (backup pour paiements récents)',
                verbose_name='Derniers rates connus'
            ),
        ),

        # Create SettlementRateCache model
        migrations.CreateModel(
            name='SettlementRateCache',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('settlement_id', models.CharField(
                    db_index=True,
                    help_text='ID du settlement Mollie (stl_xxx)',
                    max_length=255,
                    unique=True,
                    verbose_name='Settlement ID'
                )),
                ('period_year', models.IntegerField(verbose_name='Année')),
                ('period_month', models.IntegerField(verbose_name='Mois')),
                ('rates_data', models.JSONField(
                    help_text='Rates de frais par type de carte pour ce settlement',
                    verbose_name='Rates'
                )),
                ('settled_at', models.DateTimeField(
                    blank=True,
                    null=True,
                    verbose_name='Date settlement'
                )),
                ('fetched_at', models.DateTimeField(
                    auto_now_add=True,
                    verbose_name='Date récupération'
                )),
                ('organizer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='pretixbase.organizer'
                )),
            ],
            options={
                'verbose_name': 'Cache Settlement Rate',
                'verbose_name_plural': 'Cache Settlement Rates',
            },
        ),

        # Create indexes
        migrations.AddIndex(
            model_name='settlementratecache',
            index=models.Index(
                fields=['organizer', 'period_year', 'period_month'],
                name='pretix_expo_organiz_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='settlementratecache',
            index=models.Index(
                fields=['settlement_id'],
                name='pretix_expo_settlem_idx'
            ),
        ),
    ]
