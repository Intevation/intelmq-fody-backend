
# Requirements
 * hug
 * psycopg2 2.4.5 (HIGHER Versions are not supported!)
 * intelmq-mailgen
 * python-dateutil
 * typing

# License
This software is Free Software available under the terms of
the AGPL v3 or later versions of this license.
See the file `agpl-3.0.txt` or https://www.gnu.org/licenses/agpl-3.0.en.html
for details.

# Run with hug
```
hug -f intelmq_fody_backend/serve.py -p 8002
```


# Run with Apache and WSGI
```
#as root
apt-get install libapache2-mod-wsgi-py3
```

You might want to use an Apache-Config similar to the example included as 
[config/apache-example/001-fody.conf](config/apache-example/001-fody.conf)


# Development
## Version number
Originally fody-backend had been designed with sub-modules
that could potentially also be used separately.
Example how to change all version numbers:
```sh
grep -rl version= . | xargs sed -i 's/0.4.4.dev0/0.5.0.dev0/'
```

## Origin
Most of the files within this repository originated from:
https://github.com/Intevation/intelmq-mailgen/tree/master/extras
