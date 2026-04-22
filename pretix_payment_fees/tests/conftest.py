"""
Configure Django before tests import the plugin modules.

The plugin's signal handlers use ``gettext_lazy`` and Pretix ORM models, so
Django must be fully initialized at import time. We rely on Pretix's own
test settings when available (they're shipped inside the pretix container
as ``pretix.testutils.settings``).
"""
import os


def pytest_configure(config):  # noqa: ARG001
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.testutils.settings")
    import django

    django.setup()
