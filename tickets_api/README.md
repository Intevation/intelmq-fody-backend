Server side API of eventdb interface for intelmq-fody.

## Configuration
Uses environment variable ```TICKETS_SERVE_CONF_FILE``` to read
a configuration file, otherwise falls back to
reading `/etc/intelmq/tickets-serve.conf`.

**In most scenarios, this file can be the same file like the config from the eventdb-api**

Contents see
```sh
python3 -m tickets_api --example-conf
```
There must be a database user which can read from the eventdb.
If there is none yet, you can create one with something like:

```sh
createuser eventapiuser --pwprompt
psql -c "GRANT SELECT ON events TO eventapiuser;" intelmq-events

```

### LogLevel DDEBUG

There is an additional loglevel `DDEBUG`
for more details than `DEBUG`.

## Installation
For a production setup `intelmq_fody_api.py` has to be installed
with a webserver running `wsgi.multithread == False` and will try
to import the `tickets\_api` module.

The `tickets\_api` requires `python-dateutil` which can be installed from pypi.
`python-dateutil` is already a requirement of IntelMQ.
