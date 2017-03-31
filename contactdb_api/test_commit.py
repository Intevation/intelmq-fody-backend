"""Tests exercising the contactdb_api via HTTP.

TODO: Add code to setup a authed server for testing automatically.

Until we do not have an server automatically setup,
the functions in here must be run manually.
"""

import json
import os
import urllib.error
import urllib.request

BASEURL = 'http://localhost:' + os.getenv('TESTPORT', '8000')
ENDPOINT = '/api/contactdb/org/manual/commit'

DATA_BAD = json.dumps({'spam': 1, 'eggs': 2, 'bacon': 0})

# ATTENTION, the following testing data contains database IDs
# which may or may not make them usable with a different database

# Hint: the python object formatting comes from pprint.pprint()

DATA = json.dumps({
    'commands': ['create'],
    'orgs': [{'annotations': [{"tag": "Guten"}],
              'asns': [{'annotations': [{"tag": "daily"}, {"tag": "X"}],
                        'asn': 49234,
                        'import_source': 'ripe',
                        'import_time': '2017-03-29T15:40:34.357995',
                        'organisation_automatic_id': 861}],
              'comment': 'This is a second manual entry to test writing the '
                         'details',
              'contacts': [{'comment': 'First command to a contact',
                            'contact_automatic_id': 1536,
                            'email': 'abuse@bund.de',
                            'firstname': 'Abkus',
                            'organisation_automatic_id': 861,
                            'import_source': 'ripe',
                            'import_time': '2017-03-29T15:40:34.357995',
                            'lastname': 'Adler',
                            'openpgp_fpr': 'abcdef12',
                            'tel': '+49 00000000001'}],
              'first_handle': '',
              'fqdns': [{"annotations": [{"tag": "yeah"}],
                         "fqdn": "www.bsi.bund.de",
                         "comment": ""}],
              'import_source': 'ripe',
              'import_time': '2017-03-29T15:40:34.357995',
              'name': 'Bundesamt fuer Sicherheit in der Informationstechnik',
              'nationalcerts': [],
              'networks': [{'address': '77.87.224.0/21',
                            'annotations': [{"tag": "monthly"},
                                            {"tag": "no-way"}],
                            'comment': '',
                            'import_source': 'ripe',
                            'import_time': '2017-03-29T15:40:34.357995',
                            'network_automatic_id': 13653,
                            'organisation_automatic_id': 861}],
              'organisation_id': 861,
              'ripe_org_hdl': 'ORG-BA202-RIPE',
              'sector_id': None,
              'ti_handle': ''}]}
)

DATA_UPDATE = json.dumps({
    'commands': ['update'],
    'orgs': [{'asns': [{'asn_id': 49234,
                        'comment': '',
                        'notification_interval': 0,
                        'number': 49234,
                        'organisation_id': 3698,
                        'ripe_aut_num': None}],
              'comment': 'Example manual contact entry.',
              'contacts': [{'comment': 'This is the same contact as '
                                       'officially given.',
                            'contact_id': 3580,
                            'email': 'abuse@bund.de',
                            'firstname': '',
                            'format_id': 2,
                            'id': 3698,
                            'is_primary_contact': False,
                            'lastname': '',
                            'openpgp_fpr': '',
                            'organisation_id': 3698,
                            'role_type': 'abuse-c',
                            'tel': ''}],
              'first_handle': '',
              'id': 3698,
              'name': 'Bundesamt fuer Sicherheit in der Informationstechnik',
              'ripe_org_hdl': '',
              'sector_id': None,
              'ti_handle': ''}]}
)

DATA_DELETE = json.dumps({
    'commands': ['delete'],
    'orgs': [{'asns': [{'asn_id': 49234,
                        'comment': '',
                        'notification_interval': 0,
                        'number': 49234,
                        'organisation_id': 3698,
                        'ripe_aut_num': None}],
              'comment': 'Example manual contact entr.',
              'contacts': [{'comment': 'This is the same contact as '
                                       'officially given.',
                            'contact_id': 3580,
                            'email': 'abuse@bund.de',
                            'firstname': '',
                            'format_id': 2,
                            'id': 3698,
                            'is_primary_contact': False,
                            'lastname': '',
                            'openpgp_fpr': '',
                            'organisation_id': 3698,
                            'role_type': 'abuse-c',
                            'tel': ''}],
              'first_handle': '',
              'id': 3698,
              'name': 'Bundesamt fuer Sicherheit in der Informationstechnik',
              'ripe_org_hdl': '',
              'sector_id': None,
              'ti_handle': ''}]}
)


def semi_automatic():
    # generic code for an Basic Auth connection
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(realm=None, uri=BASEURL,
                              user='intelmq', passwd='intelmq')
    auth_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
    opener = urllib.request.build_opener(auth_handler)
    urllib.request.install_opener(opener)

    # generic code for a POST request
    request = urllib.request.Request(BASEURL + ENDPOINT)
    request.add_header("Content-Type", "application/json")

    # test1
    f = urllib.request.urlopen(request, DATA.encode('utf-8'))
    result = f.read().decode('utf-8')
    print(result)
    new_org_id = json.loads(result)[0]

    f = urllib.request.urlopen(request, DATA.encode('utf-8'))
    result = f.read().decode('utf-8')

    if not json.loads(result)[0] == new_org_id:
        print('Not idempotent!')
    else:
        print('test1 was idempotent.')

    # test2 no commands
    try:
        f = urllib.request.urlopen(request, DATA_BAD.encode('utf-8'))
    except urllib.error.HTTPError as err:
        print(err.code, err.reason)
        print(err.read().decode('utf-8'))

    # test3 not even json
    try:
        f = urllib.request.urlopen(request, 'not even json}'.encode('utf-8'))
    except urllib.error.HTTPError as err:
        print(err.code, err.reason)
        print(err.read().decode('utf-8'))

    # test4 unknown command
    try:
        data = json.dumps({'commands': ['mangle'], 'orgs': [1]})
        f = urllib.request.urlopen(request, data.encode('utf-8'))
    except urllib.error.HTTPError as err:
        print(err.code, err.reason)
        print(err.read().decode('utf-8'))

    # test5 update
    f = urllib.request.urlopen(request, DATA_UPDATE.encode('utf-8'))
    print(f.read().decode('utf-8'))

    # test5 delete
    f = urllib.request.urlopen(request, DATA_DELETE.encode('utf-8'))
    print(f.read().decode('utf-8'))


if __name__ == '__main__':
    semi_automatic()
