import os
import re
from distutils.command.build import build

from django.core import management
from setuptools import find_packages, setup

# Read version without importing the module to avoid circular imports
with open(os.path.join(os.path.dirname(__file__), "pretix_payment_fees", "__init__.py")) as f:
    __version__ = re.search(r'__version__ = "(.*?)"', f.read()).group(1)


try:
    with open(
        os.path.join(os.path.dirname(__file__), "README.md"), encoding="utf-8"
    ) as f:
        long_description = f.read()
except Exception:
    long_description = ""


class CustomBuild(build):
    def run(self):
        management.call_command("compilemessages", verbosity=1)
        build.run(self)


cmdclass = {"build": CustomBuild}


setup(
    name="pretix-payment-fees",
    version=__version__,
    description="Pretix plugin for tracking and reporting payment provider fees (Mollie, SumUp)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/valentin-gosselin/pretix-payment-fees",
    author="Valentin Gosselin",
    author_email="valentin@gosselin.pro",
    license="Apache",
    install_requires=[
        "weasyprint>=62.0",
        "openpyxl>=3.1.0",
        "requests>=2.28.0",
    ],
    packages=find_packages(exclude=["tests", "tests.*"]),
    include_package_data=True,
    cmdclass=cmdclass,
    entry_points="""
[pretix.plugin]
pretix_payment_fees=pretix_payment_fees:PluginApp
""",
)