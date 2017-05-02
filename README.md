
# Requirements
 * hug
 * psycopg2 2.4.5 (HIGHER Versions are not supported!)
 * intelmq-mailgen
 * python-dateutil

# License
This software is available under the terms of the AGPL v3 or later versions of this license.
See the file `agpl-3.0.txt` or https://www.gnu.org/licenses/agpl-3.0.en.html
for details.

# Run with hug
```
hug -f intelmq_fody_api/serve.py -p 8002
```


# Run with Apache and WSGI



```
#as root
apt-get install libapache2-mod-wsgi-py3
```

You might want to use an Apache-Config similar to the example included as 
[config/apache-example/001-fody.conf](config/apache-example/001-fody.conf)


## Origin
Most of the files within this repository originated from:
https://github.com/Intevation/intelmq-mailgen/tree/master/extras
