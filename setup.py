from distutils.core import setup

setup(
    name='intelmq-fody-api',
    version='0.4.2.dev0',
    packages=['tickets_api.tickets_api', 'events_api.events_api', 'contactdb_api.contactdb_api',
              'checkticket_api.checkticket_api', 'intelmq_fody_api'],
    url='',
    license='AGPLv3',
    author='Dustin Demuth',
    author_email='dustin@intevation.de',
    description=''
)
