from distutils.core import setup

setup(
    name='intelmq-fody-backend',
    # version shall be compatible with PEP440 and as close to
    # Semantic Versioning 2.0.0 as we can, to be similiar to fody's versioning
    version='0.6.4.dev0',
    packages=['tickets_api.tickets_api', 'events_api.events_api', 'contactdb_api.contactdb_api',
              'checkticket_api.checkticket_api', 'intelmq_fody_backend'],
    url='',
    license='AGPLv3',
    author='Dustin Demuth',
    author_email='dustin@intevation.de',
    description=''
)
