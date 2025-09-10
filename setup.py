from setuptools import setup

setup(
    name='intelmq-fody-backend',
    # version shall be compatible with PEP440 and as close to
    # Semantic Versioning 2.0.0 as we can, to be similar to fody's versioning
    version='0.11.1',
    packages=[
        'checkticket_api.checkticket_api',
        'contactdb_api.contactdb_api',
        'events_api.events_api',
        'intelmq_fody_backend',
        'session',
        'tickets_api.tickets_api',
        ],
    url='https://github.com/Intevation/intelmq-fody-backend',
    license='AGPLv3',
    author='Intevation GmbH',
    author_email='info@intevation.de',
    description=' A backend to serve intelmq-cb-mailgen data for the webapp fody. ',
    scripts = ['fody-adduser'],
    python_requires='<3.13',  # Dependency falcon requires Python module cgi
)
