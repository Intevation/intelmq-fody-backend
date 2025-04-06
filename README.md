# Documentation
A backend to serve
[intelmq-mailgen](https://github.com/Intevation/intelmq-mailgen)
data or just events from an IntelMQ PostgreSQL database
for the webapp [Fody](https://github.com/intevation/intelmq-fody).


Each contained module has an additional `README.md` to follow.

# Requirements
 * Python < 3.13
 * hug
 * psycopg2 >=2.4.5
 * intelmq-mailgen
 * python-dateutil
 * typing
 * postgresql v>=9.5

## Locale

The encoding of the locale must be UTF-8.
To do this, run `dpkg-reconfigure locales` and select, for example, `en_US.UTF-8`.

# License
This software is Free Software available under the terms of
the AGPL v3 or later versions of this license.
See the file `agpl-3.0.txt` or https://www.gnu.org/licenses/agpl-3.0.en.html
for details.

# Operating manual

See [events_api/README.md](events_api/README.md) for usage hints for statistics.

Because of https://github.com/Intevation/intelmq-fody-backend/issues/12
make sure to restart the serving process(es) each time you have
restarted postgresql.

## Run with hug interactively

For development purposes it is possible to run the backend interactively. The intelmq-fody frontend expects the backend at port 8002.

```bash
hug -f intelmq_fody_backend/serve.py -p 8002
```

It is also possible to only run a single backend, for example the events API:
```bash
hug -f events_api/events_api/serve.py -p 8002
```

## Run with Apache and WSGI
```
#as root
apt-get install libapache2-mod-wsgi-py3
```

You might want to use an Apache-Config similar to the example included as
[config/apache-example/001-fody.conf](config/apache-example/001-fody.conf)

# Authentication
Authentication for the endpoints exposed by the fody-backend is configured in a json formatted file. The fody-backend tires to load the configuration file `/etc/intelmq/fody-session.conf` and `${PREFIX}/etc/intelmq/fody-session.conf`. To override these paths set the environment variable `FODY_SESSION_CONFIG` to the path pointing to the config file.

If the config file is not found in the given locations the authentication is disabled.

## Example configuration

```
{
	"session_store": "/etc/intelmq/fody-session.sqlite",
	"session_duration": 86400
}
```

* `session_store`: the location of the sqlite database that contains users and sessions.
* `session_duration`: the maximal duration of a session.

If you enable the session_store you will have to create user accounts to be able to access the API functionality. You can do this using fody-adduser:
```
fody-adduser --user <username> --password <password>
```

## Same authentication as IntelMQ Manager

You can use the same authentication for IntelMQ Fody as for the IntelMQ Manager.

1. From `/etc/intelmq/api-config.json` copy the value of the field `session_store` (on Debian/Ubuntu it is likely `/var/lib/dbconfig-common/sqlite3/intelmq-api/intelmqapi`). Short command: `jq -r .session_store /etc/intelmq/api-config.json`
2. In `/etc/intelmq/fody-session.conf` set this value for the field `session_store`.
3. Run `sudo systemctl restart apache2` to make the change effective, restarting IntelMQ Fody's Backend.

# Track db changes by user
Only the module `contactdb_api` exposes the ability to write changes to the db.

If you want to be able to find out which user (see section above) did which particular change:
 1. Set the logging level to at least INFO.
 2. Keep the error logs of the wsgi application. In the default Apache configuration for fody, the file is `/var/log/apache2/fody-backend-error.log`

Log entries will show the requested change
together with the username, search for
`user =`. Example for Apache2:

```sh
pushd /var/log/apache2/
zgrep 'user =' fody-backend-error.log*
fody-backend-error.log:[Fri May 05 14:19:26.882299 2017] [:error] [pid 2075] 2017-05-05 14:19:26,882 contactdb_api.contactdb_api.serve INFO - Got commit_object = {'orgs': [{'comment': 'Testing', 'first_handle': '', 'name': 'Intevation', 'sector_id': None, 'contacts': [], 'ti_handle': '', 'ripe_org_hdl': '', 'asns': []}], 'commands': ['create']}; user = 'bernhard.reiter'
fody-backend-error.log:[Fri May 05 14:19:26.882299 2017] [:error] [pid 2075] 2017-05-05 14:19274,179 contactdb_api.contactdb_api.serve INFO - Commit successful, results = [('create', 126)]; user = 'bernhard.reiter'
```

# Links
* [python-imqfody](https://github.com/3c7/python-imqfody) a python3 module
  to ease accessing the Fody backend.

# History
Most of the files within this repository originated from:
https://github.com/Intevation/intelmq-mailgen/tree/master/extras
