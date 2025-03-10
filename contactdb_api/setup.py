"""A minimal setupfile for contactdb_api."""

from setuptools import setup, find_packages

setup(
    name='intelmq-certbund-contact-api',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version='0.10.1',

    description='A hug based microservice api to intelmq-certbund-contact.',

    packages=find_packages(),

    install_requires=['hug', 'psycopg2', 'typing', 'jsonschema'],
    python_requires='<3.13',  # Dependency falcon requires Python module cgi
)
