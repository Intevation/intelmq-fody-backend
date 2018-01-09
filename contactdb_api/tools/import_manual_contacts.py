#!/usr/bin/env python3
"""Import manual contacts from .csv file into an intelmq-cb-mailgen contactdb.

Takes contacts from a special .csv file and a parameter for a tag.
Just imports, does **not** check if the data is in the contactdb already.

Example:
    {scriptname} example-contacts-1.csv "Targetgroup:CRITIS"

Details:
    All rows with the same value in `organization` will be added to the same
    organisation. It is assumed that the `contact` value is the same for all
    those rows: a list of plain email addresses, see example-contacts-1.csv.

    An "import_YYYYMMDD" comment is added to the organisation.

    The result of --dry-run --dump-json can be used to manually upload, e.g.
      curl http://localhost:8070/api/contactdb/org/manual/commit \
                --header "Content-Type:application/json" --data @z
     or with TLS and basic auth
      curl https://example.intevation.de:8000/api/contactdb/org/manual/commit \
              --cacert example.intevation-cert.pem --basic --user intevation
              --header "Content-Type:application/json" --data @z

Context:
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

import argparse
import csv
import datetime
from email.utils import getaddresses
import ipaddress
import json
import logging
import pprint
import sys

log = logging.getLogger(__name__)
logging.basicConfig(format='%(levelname)s:%(message)s',
                    level=logging.INFO)

import_comment = "import_" + datetime.date.today().strftime("%Y%m%d")


def add_info_from_row(orgs_by_name, line_number, row, tag):
    """Add info from one row to the orgs_by_name dictionary."""

    # email.utils.getaddresses calls parseaddr, but does not do much checking.
    email_addresses = getaddresses([row["contact"]])
    if len(email_addresses) < 1:
        log.error("No email addresses found in line %d", line_number)
        raise ValueError("is no list email addressses", row["contact"])

    contacts = []
    for realname, email_addr in email_addresses:
        # /!\ we assume no realnames
        contacts.append({
            "comment": "",
            "email": email_addr,
            "firstname": "",
            "lastname": "",
            "openpgp_fpr": "",
            "tel": "",
            })

    # find or add organization
    new_org = orgs_by_name.setdefault(row["organization"], {
        "annotations": [{"tag": tag}],
        "asns": [],
        "comment": import_comment,
        "contacts": contacts,
        "first_handle": "",
        "fqdns": [],
        "name": row["organization"],
        "national_certs": [],
        "networks": [],
        "ripe_org_hdl": "",
        "sector_id": None,
        "ti_handle": "",
        })

    if row["as_or_cidr"].startswith("AS"):
        try:
            asn = int(row["as_or_cidr"][2:])
        except ValueError:
            log.error("Problem parsing AS in line %d", line_number)
            raise

        new_org["asns"].append({"asn": asn,
                                "annotations": []})

        if row["comment"]:
            new_org["comment"] += ", AS{:d}:'{:s}'".format(
                                    asn, row["comment"])

    else:
        # use ipaddress module for a simple validation
        try:
            cidr = ipaddress.ip_network(row["as_or_cidr"]).compressed
        except ValueError:
            log.error("Problem parsing CIDR in line %d", line_number)
            raise

        new_org["networks"].append({"address": cidr,
                                    "annotations": [],
                                    "comment": row["comment"]})


def main():
    parser = argparse.ArgumentParser(epilog=__doc__.format(
                scriptname=sys.argv[0]),
                formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--debug", action="store_true",
                        help="set loglevel to DEBUG")
    parser.add_argument("--dry-run", action="store_true",
                        help="just print resulting org-objects")
    parser.add_argument("--dump-json", action="store_true",
                        help="output json commands when dry-running")
    parser.add_argument("filename", help="file to import")
    parser.add_argument("tag", help="tag to be used for importing")

    args = parser.parse_args()

    if args.debug:
        log.setLevel("DEBUG")

    with open(args.filename) as csvfile:
        # guess the csv file data format "dialect"
        dialect = csv.Sniffer().sniff(csvfile.read(1024))
        csvfile.seek(0)

        orgs_by_name = {}  # holds all objects to be created, indexed by name

        reader = csv.DictReader(csvfile, dialect=dialect)

        for line_number, row in enumerate(reader, 1):
            log.debug(row)
            add_info_from_row(orgs_by_name, line_number, row, args.tag)

    orgs = list(orgs_by_name.values())
    fody_backend_commands = ["create"] * len(orgs)

    if args.dry_run:
        if args.dump_json:
            print(json.dumps({"commands": fody_backend_commands,
                              "orgs": orgs}, sort_keys=True, indent=4))
        else:
            pprint.pprint(orgs_by_name)

    else:
        # TODO real import
        raise NotImplementedError

    # stats
    log.info("number_of_lines = {}".format(line_number))


main()
