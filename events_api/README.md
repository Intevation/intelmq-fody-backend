Server side API of eventdb interface for intelmq-fody.

The module can be used on an events table created by an
`intelmq/bots/outputs/postgresql/`.

If there are additional tables from running a `intelmq-cb-mailgen` setup,
additional features are offered.


## Configuration
Uses environment variable ```EVENTDB_SERVE_CONF_FILE``` to read
a configuration file, otherwise falls back to
reading `/etc/intelmq/eventdb-serve.conf`.

Contents see
```sh
python3 -m events_api.events_api --example-conf
```
There must be a database user which can read from the eventdb.
If there is none yet, you can create one with something like:

```sh
createuser eventapiuser --pwprompt
psql -c "GRANT SELECT ON  ALL TABLES IN SCHEMA public TO eventapiuser;" \
    intelmq-events
```

### LogLevel DDEBUG

There is an additional loglevel `DDEBUG`
for more details than `DEBUG`.

## Installation
For a production setup `intelmq-fody-backend` has to be installed
with a webserver running `wsgi.multithread == False` and will try
to import the `eventdb\_api` module.

The `eventdb\_api` requires `python-dateutil` which can be installed from pypi.
`python-dateutil` is already a requirement of IntelMQ.
