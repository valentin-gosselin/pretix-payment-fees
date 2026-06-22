# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Order-level detail export (one row per order with categories and fee detail)
- Venue-occupancy export for partners (ticket counts per category, no amounts)
- Full 8-language i18n of the new export (.po extraction)

## [1.1.0] - 2026-06-22

### Added
- **New export "Recettes détaillées"**: detailed revenue report by sales channel
  and session, in PDF, CSV and Excel.
  - Aggregation by Sales channel > Session (subevent) > Product (Item) >
    Nature (Variation), with per-category subtotals and grand total.
  - **Dynamic fee columns, one per PSP** (Mollie, SumUp...), derived from the
    `OrderFee` types present in the data; humanised fallback for unknown types.
  - **Per-line fee allocation** via intra-order pro rata: a fee is spread only
    over the positions of its own order, so products paid outside any PSP show
    0.00; the per-line sum reconciles exactly with the Pretix `OrderFee` total.
  - Net revenue (gross minus fees) at line, session and channel level.
  - Single-channel filter, cross view (Category x Session), ticketing block
    (paid vs invitations), VAT rate per session from the tax rule.
  - Sober editorial PDF design (A4 portrait, OpenSans, indigo accent).
- Test suite covering builder, renderers and exporter (54 tests).

### Changed
- Renamed the plugin's accounting export surface around the new report.

### Removed
- Legacy exporters `accounting_report_psp` and `payment_list_psp` and their
  renderers, replaced by the new "Recettes détaillées" export.

## [1.0.1] - 2026-04-22

### Fixed
- **Critical**: `order_paid` signal receiver used the wrong calling convention
  (treated `sender` as the `Order` instead of the `Event`), causing every paid
  order to raise `AttributeError: 'Event' object has no attribute 'event'`
  inside the `perform_order` Celery task. The error was surfaced to buyers as
  "An unexpected error occurred, please try again later" and blocked all
  checkouts while the plugin was enabled.
- Wrapped the whole `on_order_paid` receiver in a defensive `try/except` so
  that any future failure in the auto-sync path is logged and never propagates
  to the order creation pipeline.

## [0.9.0] - 2025-10-04

### Added
- **Mollie Integration**
  - OAuth2 authentication with Mollie Connect
  - Real-time fee synchronization via Balance and Settlement APIs
  - Settlement date extraction from Mollie API
  - Smart caching system with configurable TTL
  - Automatic token refresh mechanism

- **SumUp Integration** (⚠️ Beta - not tested in production)
  - API integration for transaction history
  - Fee calculation and caching
  - Test mode support

- **Multilingual Support** (8 languages at 100% coverage)
  - English (base language)
  - French (Français)
  - German (Deutsch)
  - Spanish (Español)
  - Dutch (Nederlands)
  - Italian (Italiano)
  - Portuguese (Português)
  - Polish (Polski)

- **Export Capabilities**
  - PDF accounting reports with PSP fee breakdowns
  - CSV export with detailed fee information
  - Excel (XLSX) export with formatted data
  - Payment and refund lists with fee columns

- **Admin Interface**
  - PSP configuration page (organizer-level)
  - Manual fee synchronization dashboard
  - Automatic synchronization with configurable frequency
  - Diagnostic tools (cache stats, error tracking)
  - Multi-event bulk operations

- **Data Management**
  - PSPConfig model for API credentials storage
  - PSPTransactionCache for fee data caching
  - SettlementRateCache for Mollie settlement rates
  - Django migrations for schema management

- **Developer Tools**
  - Management command: `sync_psp_fees`
  - Dry-run mode for testing
  - Comprehensive logging system
  - Error tracking in admin interface

### Fixed
- Settlement date extraction from Mollie settlements API
- API error logging system implementation
- CSRF protection in all forms
- Proper timezone handling for datetime fields

### Security
- API credentials encrypted in database
- CSRF tokens in all POST forms
- Input validation and sanitization
- OAuth token secure storage

## [0.1.0] - 2025-09-30

### Added
- Initial project structure
- Basic Mollie API integration (API key based)
- Simple fee estimation fallback (2.1% + €0.25)
- CSV export prototype
- French translations only

### Known Issues
- OAuth not implemented
- No SumUp support
- Limited language support
- Manual installation only

---

## Migration Guide

### From 0.1.0 to 0.9.0

**Breaking Changes:**
- OAuth2 is now the recommended authentication method for Mollie
- Database schema changes require migrations: `python -m pretix migrate`
- Configuration moved to organizer-level settings

**Migration Steps:**
1. Backup your database
2. Update plugin: `pip install --upgrade pretix-payment-fees`
3. Run migrations: `python -m pretix migrate`
4. Rebuild static files: `python -m pretix rebuild`
5. Configure OAuth credentials in PSP settings
6. Restart services: `systemctl restart pretix-web pretix-worker`

---

## Deprecation Notice

### v0.9.0
- **API Key Authentication**: While still supported, OAuth2 is now the recommended method for Mollie
- **Old Cache Format**: Will be automatically migrated on first sync

---

## Links

- [Repository](https://github.com/valentin-gosselin/pretix-payment-fees)
- [Issues](https://github.com/valentin-gosselin/pretix-payment-fees/issues)
- [Pull Requests](https://github.com/valentin-gosselin/pretix-payment-fees/pulls)

[Unreleased]: https://github.com/valentin-gosselin/pretix-payment-fees/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/valentin-gosselin/pretix-payment-fees/releases/tag/v0.9.0
[0.1.0]: https://github.com/valentin-gosselin/pretix-payment-fees/releases/tag/v0.1.0
