from distutils.core import setup

setup(
    name='intelmq-fody-backend',
    version='0.5.4.dev0',
    packages=['tickets_api.tickets_api', 'events_api.events_api', 'contactdb_api.contactdb_api',
              'checkticket_api.checkticket_api', 'intelmq_fody_backend'],
    url='',
    license='AGPLv3',
    author='Dustin Demuth',
    author_email='dustin@intevation.de',
    description=''
)
