#!/usr/bin/env python3
"""Example how to import a whitelist csv file.

Creates a python script that can be inspected and later
run as contactdb_api backend user (with the same configuration file)
to write data into the intelmq-cb-mailgen contactdb.

Will create manual orgs to be imported via fody_backend from lines like::


asn;ip_or_cidr;type;identifier;comment;contact
49234;;malware;;"BSI, meist False-Positives";"<abuse@bsi.bund.de>"
;2001:638:81e::/48;malware;;"Malware-Research";"Max Musterfrau <abuse@cert-bund.de>"
;194.94.208.10;opendns;;"Rate-Limiting für DNS implementiert";Max Musterfrau <abuse@cert-bund.de>"


Makes several assumptions, see /!\ in the code.

Use like
    python3 $basename whitelist-20170505.csv >import-wlist-1.py
    vim import-wlist-1.py  # optional

Transfer to the machine (and user) where the fody-backend runs
(check the contactdb_api docs if you want to configure it differently)
    python3 import-wlist-1.py  # and redirect logs according to your needs


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
import pprint
import sys

log = logging.getLogger(__name__)
logging.basicConfig(format='%(levelname)s:%(message)s',
                    level=logging.INFO)
#                    level=logging.DEBUG)

TAG_WHITELIST_MALWARE = "Whitelist:Malware"

with open(sys.argv[1]) as csvfile:
    # guess the csv file data format "dialect"
    dialect = csv.Sniffer().sniff(csvfile.read(1024))
    csvfile.seek(0)

    new_org_names = {}  # holds all objects to be created, hashed by name

    # counters for stats
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

        potential_new_org = {
                "name": None,
                "comment": "",
                "ripe_org_hdl": '',
                "ti_handle": '',
                "first_handle": '',
                "sector_id": None,
                "networks": [],
                "asns": [],
                "fqdns": [],
                "annotations": [],
                "national_certs": []
                }
        # /!\ let us use the domain part of the contact email addr as org name
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
        # /!\ we assume it is enough to deal with the following email providers
        if potential_new_org["name"] in ("gmail.com", "gmx.de"):
            potential_new_org["name"] = email_addr

        potential_new_org["contacts"] = [{
                "email": email_addr,
                "firstname": realname_firstname,
                "lastname": realname_lastname,
                "tel": "",
                "openpgp_fpr": "",
                "comment": ""
                }]

        while (potential_new_org["name"] in new_org_names):
            # check if we already have an organisation where we should
            # add additional networks to

            if (potential_new_org["contacts"][0] ==
                    new_org_names[potential_new_org["name"]]["contacts"][0]):
                # use existing org
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

        # /!\ we assume that either asn or id_or_cidr are filled
        if row["asn"] != '':
            # /!\ there are only asns with 'malware' and each org is singular
            asn_inhib = {'asn': int(row["asn"]),
                         'annotations': [{"tag": TAG_WHITELIST_MALWARE}]}

            new_org["asns"] = [asn_inhib]
            new_org["comment"] = "ASN inhibition comment: " + row["comment"]

        else:
            # must be id_or_cidr
            network_inhib = {'address': row["ip_or_cidr"],
                             'comment': row["comment"]}
            if row["type"] == 'malware':
                network_inhib["annotations"] = [{"tag": TAG_WHITELIST_MALWARE}]
            else:
                # /!\ we assume that we have an identifier instead
                if row["identifier"] == 'opendns':
                    network_inhib["annotations"] = [
                        {"tag": "Whitelist:DNS-Open-Resolver"}]
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

    # create a python skript
    print("""\
import logging
import types

from contactdb_api.contactdb_api import serve

logging.basicConfig(format='%(levelname)s:%(message)s')

# objects with some wsgi-like properties for serve.commit_pending_org_changes()
simple_request = types.SimpleNamespace(env = {'REMOTE_USER':'local_script'})
simple_response = types.SimpleNamespace()

""")

    output_strings = [pprint.pformat(org) for org in new_org_names.values()]
    print('orgs = [')
    print(',\n'.join(output_strings))
    print(']')

    output_commands = ["create"] * len(output_strings)

    print("body = { 'commands' : " + repr(output_commands) + ",")
    print("         'orgs' : orgs }")

    print("""\
serve.setup(None)
result = serve.commit_pending_org_changes(
    body, simple_request, simple_response)

print(result, simple_response)
""")

    # output some stats
    log.info("number_of_lines = {}".format(number_of_lines))
    log.info("types_count = {}".format(types))
    log.info("identifier_count = {}".format(identifiers))
    log.info("number_of_resulting_orgs = {}".format(len(new_org_names)))
