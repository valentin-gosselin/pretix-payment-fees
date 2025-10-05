# Pretix Payment Fees Tracker

[![Version](https://img.shields.io/badge/version-0.9.0--beta-blue.svg)](https://github.com/valentin-gosselin/pretix-payment-fees/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Pretix](https://img.shields.io/badge/pretix-2024.0.0+-purple.svg)](https://pretix.eu/)
[![Multilingual](https://img.shields.io/badge/languages-8-brightgreen.svg)](#supported-languages)

A Pretix plugin that automatically tracks, synchronizes and reports payment provider fees from Mollie and SumUp, providing comprehensive accounting reports with fee breakdowns.

## Supported Languages

🌍 This plugin is available in 8 languages with 100% translation coverage:

- 🇬🇧 **English** (Base)
- 🇫🇷 **Français** (French)
- 🇩🇪 **Deutsch** (German)
- 🇪🇸 **Español** (Spanish)
- 🇳🇱 **Nederlands** (Dutch)
- 🇮🇹 **Italiano** (Italian)
- 🇵🇹 **Português** (Portuguese)
- 🇵🇱 **Polski** (Polish)

## Features

- **Automatic Fee Synchronization**: Automatically fetch and sync payment fees from Mollie and SumUp APIs
- **Comprehensive Reporting**: Generate detailed accounting reports including:
  - PDF accounting reports with payment provider fee sections
  - Payment and refund lists with fee columns
  - CSV/Excel exports with complete fee data
- **Multi-Provider Support**: Currently supports:
  - Mollie (including OAuth integration)
  - SumUp
- **Real-time Fee Display**: View payment fees directly in Pretix order details
- **Bulk Operations**: Synchronize fees for multiple events at once
- **Smart Caching**: Reduces API calls with intelligent Django caching
- **Diagnostic Tools**: Monitor cache status and API errors

## Installation

### Prerequisites

- Pretix >= 2024.0.0 fre
- Python >= 3.11
- Access to Mollie and/or SumUp APIs

### Docker Installation (Recommended)

The plugin should be integrated into the Pretix Docker image:

```dockerfile
FROM pretix/standalone:stable

USER root

# System dependencies for WeasyPrint
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 \
    libharfbuzz0b libffi-dev libjpeg-dev \
    libopenjp2-7-dev libcairo2 libgdk-pixbuf2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install the plugin
RUN pip3 install pretix-payment-fees

USER pretixuser
RUN cd /pretix/src && make production
```

### Run Migrations

After deployment, execute migrations:

```bash
docker exec pretix-dev python -m pretix migrate
```

## Configuration

### PSP Configuration (Organizer Level)

1. Login as administrator
2. Navigate to **Organizer → PSP Configuration**
3. Configure your API keys:

#### Mollie Setup
- **API Key**: Get from [Mollie Dashboard](https://www.mollie.com/dashboard/developers/api-keys)
- Format: `live_...` (production) or `test_...` (sandbox)
- **Test Mode**: Check if using test key
- **Enable Mollie**: Check to activate integration

#### SumUp Setup
- **API Key**: Create OAuth app on [SumUp Developer Portal](https://developer.sumup.com/)
- Request `payments` scope from SumUp
- **Merchant Code**: Your SumUp merchant identifier
- **Test Mode**: Check if using sandbox environment
- **Enable SumUp**: Check to activate integration

#### Advanced Options
- **Cache Duration**: Default 3600 seconds (1h). Increase for high transaction volumes.

## Usage

### PSP Synchronization

1. Go to **Organizer → PSP Synchronization**
2. Select events to synchronize
3. Choose dry run or full sync
4. Click **Synchronize Fees**

### Generating Reports

#### Accounting Report with Fees
1. Navigate to **Event → Data exports**
2. Select **Accounting Report (with banking fees)**
3. Configure date range and options
4. Export as PDF

#### Payment List with Fees
1. Navigate to **Event → Data exports**
2. Select **Payments and refunds with banking fees**
3. Export in CSV or Excel format

## Export Formats

### CSV/Excel Columns

| Column | Description |
|--------|-------------|
| Payment Date | Payment date and time |
| Order ID | Pretix order code |
| Payment Method | Provider (mollie, sumup, etc.) |
| Gross Amount | Total amount paid |
| PSP Fees | Provider transaction fees |
| Net Amount | Gross - Fees |
| Currency | EUR, USD, etc. |
| PSP Transaction ID | Provider transaction ID |
| Settlement ID | Settlement ID (Mollie only) |
| Status | confirmed, refunded, etc. |

### Report Sections

1. **Main Table**: Transaction list
2. **Global Totals**: All payment aggregations
3. **PSP Totals**: Aggregation by payment method
4. **Accounting Control**: Verification that Gross - Fees = Net

## Management Commands

```bash
# Sync fees for all events of an organizer
python manage.py sync_psp_fees --organizer=your-org

# Sync specific event
python manage.py sync_psp_fees --organizer=your-org --event=your-event

# Dry run mode
python manage.py sync_psp_fees --organizer=your-org --dry-run
```

## API Integrations

### Mollie APIs
- **Balances API**: `/v2/balances/{id}/transactions`
- **Settlements API**: `/v2/settlements/{id}`
- **Payments API**: `/v2/payments/{id}`
- [Mollie Documentation](https://docs.mollie.com/reference/v2/balances-api/overview)

### SumUp APIs
- **Transactions API**: `/v0.1/me/transactions`
- **Transaction History**: `/v0.1/me/transactions/history`
- [SumUp Documentation](https://developer.sumup.com/api/transactions)

## Known Limitations

### Mollie
- Fees only available if settlement exists
- Fallback: 2.1% + 0.25 EUR estimation (standard EU card rate)
- Historical data limited (from July 2022)

### SumUp
- API may require manual approval for `payments` scope
- Fees not always directly provided
- Fallback: 1.95% + 0.15 EUR estimation

### General
- PSP transaction ↔ Pretix payment matching done by stored ID
- If ID unavailable, matching by amount/date (may be imprecise)
- Partial refunds may require manual verification

## Diagnostics

Diagnostic page available at **Organizer → PSP Diagnostics**:
- Configuration status
- Cache statistics (count, by provider, age)
- Recent errors tracking

## Development

### Project Structure

```
pretix_payment_fees/
├── __init__.py               # Plugin metadata
├── signals.py                # Signal receivers
├── models.py                 # PSPConfig, PSPTransactionCache
├── forms.py                  # PSP configuration forms
├── views.py                  # Configuration views
├── admin_views.py            # Diagnostic views
├── urls.py                   # Plugin URLs
├── services/
│   └── psp_sync.py           # Sync orchestration
├── psp/
│   ├── mollie_client.py      # Mollie API client
│   ├── mollie_oauth_client.py # Mollie OAuth
│   └── sumup_client.py       # SumUp API client
├── exporters/
│   ├── accounting_report_psp.py  # PDF accounting report
│   └── payment_list_psp.py       # Payment list with fees
└── templates/
    └── pretix_payment_fees/
        ├── settings.html      # PSP config page
        ├── psp_sync.html      # Sync page
        └── diagnostic.html    # Diagnostic page
```

### Development & Testing

This plugin is designed to run within a Pretix environment. Testing should be done in a development Pretix instance:

1. **Install in development mode**:
   ```bash
   docker exec pretix-dev pip install -e /path/to/pretix-payment-fees
   ```

2. **Test the plugin**:
   - Create test events in your Pretix instance
   - Configure PSP credentials (use test/sandbox keys)
   - Process test payments through Mollie/SumUp
   - Use the sync functionality to fetch fees
   - Verify reports and exports

3. **Code quality** (optional):
   ```bash
   # Format code
   black pretix_payment_fees/ --line-length=100

   # Sort imports
   isort pretix_payment_fees/ --profile=black

   # Check translations
   python manage.py makemessages
   python manage.py compilemessages
   ```

**Note**: This plugin requires a full Pretix environment to function. Automated testing via CI/CD is not implemented as the plugin is tightly integrated with Pretix core.

## Support

For issues and feature requests:
1. Check logs: `docker logs pretix-dev`
2. Review diagnostic page
3. Verify API keys are valid
4. Open a GitHub issue

## License

Apache License 2.0

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Changelog

### 0.9.0 (2025-10-04) - Beta Release
- Initial public beta release
- Mollie integration with OAuth2 support (tested in production)
- SumUp integration (⚠️ **not yet tested in production**, awaiting real merchant account)
- Multilingual support (EN, FR, DE, ES, NL, IT, PT, PL)
- CSV, Excel, PDF exports with fee breakdowns
- Accounting reports with PSP fees section
- Smart caching system
- Diagnostic and monitoring tools

**Note**: Version 1.0.0 will be released after successful SumUp production testing.