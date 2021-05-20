from distutils.core import setup

setup(
    name='intelmq-fody-backend',
    # version shall be compatible with PEP440 and as close to
    # Semantic Versioning 2.0.0 as we can, to be similiar to fody's versioning
    version='0.9.1.dev0',
    packages=[
        'checkticket_api.checkticket_api',
        'contactdb_api.contactdb_api',
        'events_api.events_api',
        'intelmq_fody_backend',
        'session',
        'tickets_api.tickets_api',
        ],
    url='',
    license='AGPLv3',
    author='Intevation GmbH',
    author_email='info@intevation.de',
    description=''
)
