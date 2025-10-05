"""
Pytest configuration for pretix-payment-fees tests.
"""
import sys
from unittest.mock import MagicMock

# Mock pretix modules to avoid import errors during CI
sys.modules['pretix'] = MagicMock()
sys.modules['pretix.base'] = MagicMock()
sys.modules['pretix.base.models'] = MagicMock()
sys.modules['pretix.base.signals'] = MagicMock()
sys.modules['pretix.base.i18n'] = MagicMock()
sys.modules['pretix.base.exporter'] = MagicMock()
sys.modules['pretix.base.decimal'] = MagicMock()
sys.modules['pretix.base.services'] = MagicMock()
sys.modules['pretix.control'] = MagicMock()
sys.modules['pretix.control.signals'] = MagicMock()
sys.modules['pretix.multidomain'] = MagicMock()
sys.modules['pretix.multidomain.urlreverse'] = MagicMock()
sys.modules['pretix.base.payment'] = MagicMock()
sys.modules['pretix.helpers'] = MagicMock()
sys.modules['pretix.helpers.database'] = MagicMock()
sys.modules['pretixhelpers.pagination'] = MagicMock()

# Skip pytest-django if Pretix is not available
def pytest_configure(config):
    """Configure pytest to skip Django tests if needed."""
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.test_settings')