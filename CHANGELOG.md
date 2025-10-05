# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for v1.0.0
- Full SumUp integration testing in production environment
- Performance optimizations for bulk exports
- Extended test coverage (>80%)
- API rate limiting and circuit breaker patterns

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
