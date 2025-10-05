from distutils.command.build import build

from django.core import management
from setuptools import setup


class CustomBuild(build):
    def run(self):
        management.call_command("compilemessages", verbosity=1)
        build.run(self)


cmdclass = {"build": CustomBuild}

# Configuration is now in pyproject.toml
setup(cmdclass=cmdclass)