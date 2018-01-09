#!/usr/bin/env python3
"""Import manual contacts from .csv file to an intelmq-cb-mailgen contactdb.

Takes contacts from a special .csv file and a parameter for a tag.
Just imports, does **not** check if the data is in the contactdb already.

Example input:
    example-contacts-1.csv

A tool to be used as part of an intelmq-cb-mailgen
(https://github.com/Intevation/intelmq-mailgen-release) setup.


Copyright (C) 2017,2018 by Bundesamt für Sicherheit in der Informationstechnik

Software engineering by Intevation GmbH

This program is Free Software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Author(s):
    * Bernhard E. Reiter <bernhard.reiter@intevation.de>
    * Bernhard Herzog <bernhard.herzog@intevation.de>
"""

import csv
import datetime
# from email.utils import parseaddr
import ipaddress
import logging
import pprint
import sys

log = logging.getLogger(__name__)
logging.basicConfig(format='%(levelname)s:%(message)s',
                    level=logging.INFO)
#                    level=logging.DEBUG)

# TODO get tag by command line parameter
tag = "Targetgroup:CRITIS"

import_comment = "import_" + datetime.date.today().strftime("%Y%m%d")


def main():
    with open(sys.argv[1]) as csvfile:
        # guess the csv file data format "dialect"
        dialect = csv.Sniffer().sniff(csvfile.read(1024))
        csvfile.seek(0)

        orgs_by_name = {}  # holds all objects to be created, indexed by name

        reader = csv.DictReader(csvfile, dialect=dialect)

        for line_number, row in enumerate(reader, 1):
            log.debug(row)

            # find or add organization
            new_org = orgs_by_name.setdefault(row["organization"], {
                "name": row["organization"],
                "comment": import_comment,
                "ripe_org_hdl": "",
                "ti_handle": "",
                "first_handle": "",
                "sector_id": None,
                "networks": [],
                "asns": [],
                "fqdns": [],
                "annotations": [{"tag": tag}],
                "national_certs": [],
                })

            # TODO add contact(s)

            if row["as_or_cidr"].startswith("AS"):
                asn = int(row["as_or_cidr"][2:])
                new_org["asns"].append({"asn": asn,
                                        "annotations": []})

                if row["comment"]:
                    new_org["comment"] += ", AS{:d}:'{:s}'".format(
                                            asn, row["comment"])

            else:
                # use ipaddress module for a simple validation
                cidr = ipaddress.ip_network(row["as_or_cidr"]).compressed
                new_org["networks"].append({"address": cidr,
                                            "comment": row["comment"]})

    # TODO do real import, until then just pretty print:
    pprint.pprint(orgs_by_name)

    # stats
    log.info("number_of_lines = {}".format(line_number))


main()
