# Contributing to Pretix Payment Fees

First off, thank you for considering contributing to Pretix Payment Fees! 🎉

The following is a set of guidelines for contributing to this plugin. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Pull Requests](#pull-requests)
- [Development Setup](#development-setup)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing Guidelines](#testing-guidelines)
- [Commit Guidelines](#commit-guidelines)

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the [existing issues](https://github.com/valentin-gosselin/pretix-payment-fees/issues) to avoid duplicates.

When creating a bug report, please include:

- **Clear and descriptive title**
- **Detailed description** of the issue
- **Steps to reproduce** the behavior
- **Expected vs actual behavior**
- **Environment details**:
  - Pretix version
  - Plugin version
  - Python version
  - OS and browser (if relevant)
- **Screenshots or error logs** (if applicable)

**Example bug report:**

```markdown
### Bug: Settlement date not extracted for Mollie payments

**Description:**
Settlement dates are always null in exports, even when Mollie settlements exist.

**Steps to reproduce:**
1. Configure Mollie with OAuth
2. Sync payments with settlements
3. Export to PDF
4. Check settlement date column

**Expected:** Settlement date from Mollie API
**Actual:** Always null

**Environment:**
- Pretix 2024.10.0
- pretix-payment-fees 0.9.0
- Python 3.11

**Logs:**
```
[2025-10-04 10:15:23] WARNING: Could not extract settlement date for stl_xxxxx
```
```

### Suggesting Enhancements

Enhancement suggestions are tracked as [GitHub issues](https://github.com/valentin-gosselin/pretix-payment-fees/issues).

When creating an enhancement suggestion, please include:

- **Clear and descriptive title**
- **Detailed description** of the proposed feature
- **Use cases** and motivation
- **Possible implementation** (if you have ideas)
- **Alternatives considered**

### Pull Requests

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/my-awesome-feature
   # or
   git checkout -b fix/issue-123
   ```
3. **Make your changes** following our [code style](#code-style-guidelines)
4. **Write tests** for your changes
5. **Update documentation** if needed
6. **Commit your changes** following our [commit guidelines](#commit-guidelines)
7. **Push** to your fork
8. **Create a Pull Request**

**PR Checklist:**

- [ ] Code follows the project style guidelines
- [ ] Self-review of code completed
- [ ] Comments added for complex logic
- [ ] Documentation updated (if applicable)
- [ ] Tests added/updated and passing
- [ ] No new warnings generated
- [ ] Changelog updated in `CHANGELOG.md`

## Development Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (for local Pretix instance)
- Git

### Local Development

1. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR-USERNAME/pretix-payment-fees.git
   cd pretix-payment-fees
   ```

2. **Install development dependencies:**
   ```bash
   pip install -e ".[dev]"  # Future: will include black, flake8, pytest, etc.
   ```

3. **Run in Docker (recommended):**
   ```bash
   # See main project README for Docker setup
   docker-compose up -d
   ```

4. **Run migrations:**
   ```bash
   docker exec pretix-dev python -m pretix migrate
   ```

5. **Collect static files:**
   ```bash
   docker exec pretix-dev python -m pretix rebuild
   ```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=pretix_payment_fees

# Run specific test file
pytest tests/test_models.py

# Run in Docker
docker exec pretix-dev pytest /path/to/pretix-payment-fees/tests/
```

### Building Translations

```bash
# Extract strings for translation
django-admin makemessages -l fr

# Compile translations
django-admin compilemessages

# Or use the Docker script
bash compile_translations.sh
```

## Code Style Guidelines

### Python

We follow **PEP 8** with some modifications:

- **Line length**: 100 characters (not 79)
- **Indentation**: 4 spaces
- **Imports**: Grouped and sorted (stdlib, third-party, local)
- **Docstrings**: Google style

**Example:**

```python
import logging
from datetime import datetime
from typing import Optional, Dict

from django.db import models
import requests

from pretix_payment_fees.models import PSPConfig

logger = logging.getLogger(__name__)


class MollieClient:
    """
    Client for Mollie API interactions.

    This class handles authentication and API calls to Mollie's
    payment service provider.

    Attributes:
        api_key: Mollie API key (live_ or test_)
        test_mode: Whether to use test API endpoints
    """

    API_BASE_URL = "https://api.mollie.com/v2"

    def __init__(self, api_key: str, test_mode: bool = False):
        """
        Initialize Mollie client.

        Args:
            api_key: Mollie API key starting with 'live_' or 'test_'
            test_mode: Enable test mode for sandbox API
        """
        self.api_key = api_key
        self.test_mode = test_mode

    def get_payment(self, payment_id: str) -> Optional[Dict]:
        """
        Retrieve payment details from Mollie.

        Args:
            payment_id: Mollie payment ID (tr_xxxxx)

        Returns:
            Payment data dict or None if not found

        Raises:
            requests.HTTPError: If API returns 4xx/5xx
        """
        url = f"{self.API_BASE_URL}/payments/{payment_id}"
        response = requests.get(url, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def _headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
```

### HTML/Templates

- **Indentation**: 2 spaces
- **Django template tags**: Proper spacing
- **Accessibility**: ARIA labels, semantic HTML

### JavaScript

- **Modern ES6+** syntax
- **Const/let** instead of var
- **Arrow functions** where appropriate
- **Semicolons** required

## Testing Guidelines

### Writing Tests

- **Unit tests**: For individual functions/methods
- **Integration tests**: For API interactions
- **E2E tests**: For critical user flows

**Example test:**

```python
import pytest
from decimal import Decimal
from pretix_payment_fees.psp.mollie_client import MollieClient


class TestMollieClient:
    """Tests for Mollie API client."""

    @pytest.fixture
    def mollie_client(self):
        """Create a test Mollie client."""
        return MollieClient(api_key="test_xxxxx", test_mode=True)

    def test_get_payment_success(self, mollie_client, requests_mock):
        """Test successful payment retrieval."""
        # Arrange
        payment_id = "tr_test123"
        mock_response = {
            "id": payment_id,
            "amount": {"value": "10.00", "currency": "EUR"},
            "status": "paid"
        }
        requests_mock.get(
            f"{mollie_client.API_BASE_URL}/payments/{payment_id}",
            json=mock_response
        )

        # Act
        result = mollie_client.get_payment(payment_id)

        # Assert
        assert result["id"] == payment_id
        assert result["status"] == "paid"

    def test_get_payment_not_found(self, mollie_client, requests_mock):
        """Test payment not found returns None."""
        payment_id = "tr_notfound"
        requests_mock.get(
            f"{mollie_client.API_BASE_URL}/payments/{payment_id}",
            status_code=404
        )

        result = mollie_client.get_payment(payment_id)
        assert result is None
```

### Test Coverage

- **Minimum**: 70% overall coverage
- **Goal**: 80%+ coverage
- **Critical paths**: 100% coverage (payment sync, fee calculation)

## Commit Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/):

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, missing semicolons, etc
- `refactor`: Code restructuring
- `perf`: Performance improvements
- `test`: Adding tests
- `chore`: Maintenance tasks

### Examples

```bash
feat(mollie): add settlement date extraction

Implement _extract_settlement_date() method to retrieve
settlement dates from Mollie settlements API.

Closes #123

---

fix(oauth): handle token refresh edge case

Fix issue where expired tokens were not refreshed properly
when the refresh token was also expired.

Fixes #456

---

docs(readme): update installation instructions

Add Docker Compose setup steps and clarify
environment variable configuration.
```

### Commit Message Rules

- Use imperative mood ("add", not "added" or "adds")
- First line max 72 characters
- Reference issues/PRs in footer
- Include breaking changes in footer

## Questions?

- 📧 Email: valentin@gosselin.pro
- 💬 GitHub Issues: [Open an issue](https://github.com/valentin-gosselin/pretix-payment-fees/issues/new)

Thank you for contributing! 🙏
