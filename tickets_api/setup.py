"""A minimal setupfile for eventdb_api."""

from setuptools import setup, find_packages

setup(
    name='intelmq-tickets-api',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version='0.6.2',

    description='A hug based microservice api to intelmq-mailgen tickets.',

    packages=find_packages(),

    install_requires=['hug', 'psycopg2', 'python-dateutil'],

)
