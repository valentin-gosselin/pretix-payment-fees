import os
from distutils.command.build import build

from setuptools import setup


class CustomBuild(build):
    def run(self):
        # Only run compilemessages if Django settings are available
        # (not during Docker build or pip install without pretix)
        try:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")
            import django
            django.setup()
            from django.core import management
            management.call_command("compilemessages", verbosity=1)
        except Exception:
            # Skip compilemessages if Django is not properly configured
            # The .mo files should already be compiled in the source
            pass
        build.run(self)


cmdclass = {"build": CustomBuild}

# Configuration is now in pyproject.toml
setup(cmdclass=cmdclass)