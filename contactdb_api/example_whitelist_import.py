#!/usr/bin/env python3
"""Example how to import a whitelist csv file.

Will create manual orgs to be imported via fody_backend from lines like::


asn;ip_or_cidr;type;identifier;comment;contact
49234;;malware;;"BSI, meist False-Positives";"<abuse@bsi.bund.de>"
;2001:638:81e::/48;malware;;"Malware-Research";"Max Musterfrau <abuse@cert-bund.de>"
;194.94.208.10;opendns;;"Rate-Limiting für DNS implementiert";Max Musterfrau <abuse@cert-bund.de>"


Copyright (C) 2017 by Bundesamt für Sicherheit in der Informationstechnik

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
        * Bernhard E. Reiter <bernhard@intevation.de>
"""  # noqa

import csv
from email.utils import parseaddr
import logging
import sys

log = logging.getLogger(__name__)
logging.basicConfig(format='%(levelname)s:%(message)s',
                    level=logging.INFO)
#                    level=logging.DEBUG)

with open(sys.argv[1]) as csvfile:
    # guess the csv file data format "dialect"
    dialect = csv.Sniffer().sniff(csvfile.read(1024))
    csvfile.seek(0)

    new_org_names = {}

    types = {}
    identifiers = {}
    number_of_lines = 0

    reader = csv.DictReader(csvfile, dialect=dialect)
    for row in reader:
        log.debug(row)

        # counting for stats
        number_of_lines += 1

        if row['type'] != '':
            if row['type'] in types:
                types[row['type']] += 1
            else:
                types[row['type']] = 1

        if row['identifier'] != '':
            if row['identifier'] in identifiers:
                identifiers[row['identifier']] += 1
            else:
                identifiers[row['identifier']] = 1

        potential_new_org = {}
        # let us use the domain part of the contact email address as org name
        log.debug(parseaddr(row["contact"]))

        realname, email_addr = parseaddr(row["contact"])
        r = realname.split(" ")
        realname_lastname = r[-1]
        if len(r) > 1:
            realname_firstname = " ".join(r[0:-1])
        else:
            realname_firstname = ''

        potential_new_org["name"] = email_addr.split("@", 1)[1]

        # unless we have some common email providers
        if potential_new_org["name"] in ("gmail.com", "gmx.de"):
            potential_new_org["name"] = email_addr

        potential_new_org["contacts"] = [{
                "email": email_addr,
                "firstname": realname_firstname,
                "lastname": realname_lastname
                }]

        while (potential_new_org["name"] in new_org_names):
            # check if we already have an organisation where we should
            # add additional networks to

            if (potential_new_org["contacts"][0] ==
                    new_org_names[potential_new_org["name"]]["contacts"][0]):

                new_org = new_org_names[potential_new_org["name"]]
                break
            else:
                # try the next generated name
                # /!\ needs a more clever algorithm if happens more often
                potential_new_org["name"] += " (n)"
                continue
        else:
            # add new org
            new_org = potential_new_org
            new_org_names[new_org["name"]] = new_org

        if row["asn"] != '':
            # /!\ there are only asns with 'malware' and each org is singular
            asn_inhib = {'asn': int(row["asn"]),
                         'annotations': [{"tag": "no-malware"}]}

            new_org["asns"] = asn_inhib
            new_org["comment"] = "ASN inhibition comment: " + row["comment"]

        else:
            # must be id_or_cidr
            network_inhib = {'address': row["ip_or_cidr"],
                             'comment': row["comment"]}
            if row["type"] == 'malware':
                network_inhib["annotations"] = [{"tag": "no-malware"}]
            else:
                network_inhib["annotations"] = [{
                    "tag": "inhibition",
                    "condition": [
                        "eq", ["event_field", "classification.identifier"],
                        row["identifier"]
                        ]
                    }]

            if 'networks' in new_org:
                new_org["networks"].append(network_inhib)
            else:
                new_org["networks"] = [network_inhib]

        log.debug(new_org)

    # TODO create structure to be send to the endpoint
    #   /api/contactdb/org/manual/commit
    import pprint
    for name, org in new_org_names.items():
        pprint.pprint(org)

    log.info("number_of_lines = {}".format(number_of_lines))
    log.info("types_count = {}".format(types))
    log.info("identifier_count = {}".format(identifiers))
    log.info("number_of_resulting_orgs = {}".format(len(new_org_names)))
