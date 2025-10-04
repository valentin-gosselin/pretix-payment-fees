# Generated migration for pretix_payment_fees

from django.db import migrations, models
import django.db.models.deletion
import pretix_payment_fees.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('pretixbase', '0001_initial'),  # Dépend de Pretix core
    ]

    operations = [
        migrations.CreateModel(
            name='PSPConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('mollie_enabled', models.BooleanField(default=False, verbose_name='Activer Mollie')),
                ('mollie_api_key', models.CharField(blank=True, help_text="Clé API Mollie (live_ ou test_)", max_length=255, verbose_name='Clé API Mollie')),
                ('mollie_test_mode', models.BooleanField(default=False, verbose_name='Mode test Mollie')),
                ('sumup_enabled', models.BooleanField(default=False, verbose_name='Activer SumUp')),
                ('sumup_api_key', models.CharField(blank=True, help_text='API Key ou Access Token SumUp', max_length=255, verbose_name='Clé API SumUp')),
                ('sumup_test_mode', models.BooleanField(default=False, verbose_name='Mode test SumUp')),
                ('cache_duration', models.IntegerField(default=3600, help_text='Durée de cache des transactions PSP', verbose_name='Durée cache (secondes)')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('organizer', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='psp_config', to='pretixbase.organizer')),
            ],
            options={
                'verbose_name': 'Configuration PSP',
                'verbose_name_plural': 'Configurations PSP',
            },
        ),
        migrations.CreateModel(
            name='PSPTransactionCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('psp_provider', models.CharField(choices=[('mollie', 'Mollie'), ('sumup', 'SumUp')], max_length=20)),
                ('transaction_id', models.CharField(db_index=True, max_length=255, verbose_name='ID Transaction PSP')),
                ('amount_gross', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Montant brut')),
                ('amount_fee', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Frais PSP')),
                ('amount_net', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Montant net')),
                ('currency', models.CharField(default='EUR', max_length=3)),
                ('settlement_id', models.CharField(blank=True, max_length=255, null=True, verbose_name='ID Settlement (Mollie uniquement)')),
                ('status', models.CharField(help_text='paid, refunded, chargeback, etc.', max_length=50, verbose_name='Statut')),
                ('fee_details', models.JSONField(default=dict, help_text='Détails des différents types de frais', verbose_name='Détails frais')),
                ('transaction_date', models.DateTimeField(verbose_name='Date transaction')),
                ('settlement_date', models.DateTimeField(blank=True, null=True, verbose_name='Date règlement')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('organizer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pretixbase.organizer')),
            ],
            options={
                'verbose_name': 'Cache Transaction PSP',
                'verbose_name_plural': 'Cache Transactions PSP',
            },
        ),
        migrations.AddIndex(
            model_name='psptransactioncache',
            index=models.Index(fields=['organizer', 'psp_provider', 'transaction_date'], name='pretix_expo_organiz_e5f2c3_idx'),
        ),
        migrations.AddIndex(
            model_name='psptransactioncache',
            index=models.Index(fields=['transaction_id'], name='pretix_expo_transac_a1b2c3_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='psptransactioncache',
            unique_together={('psp_provider', 'transaction_id')},
        ),
    ]