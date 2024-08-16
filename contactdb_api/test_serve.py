"""Serve intelmq-certbund-contact db api via wsgi.

Requires hug (http://www.hug.rest/)


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
    Bernhard E. Reiter <bernhard@intevation.de>
"""
import json
import os
import tempfile
import unittest

from psycopg2.extras import RealDictRow
from copy import deepcopy

from contactdb_api import serve


class Tests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir_obj = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp_dir_obj.cleanup()

    def test_reading_config(self):
        self.conf_file_name = os.path.join(self._tmp_dir_obj.name, 'a.conf')

        test_config = {"a": "value", "b": 123}

        with open(self.conf_file_name, mode="wt") as file_object:
            json.dump(test_config, file_object)

        os.environ["CONTACTDB_SERVE_CONF_FILE"] = self.conf_file_name

        self.assertEqual = (serve.read_configuration(), test_config)

    def test_default_config(self):
        self.conf_file_name = os.path.join(self._tmp_dir_obj.name, 'a.conf')

        with open(self.conf_file_name, mode="wt") as file_object:
            file_object.write(serve.EXAMPLE_CONF_FILE)

        os.environ["CONTACTDB_SERVE_CONF_FILE"] = self.conf_file_name

        self.assertIsInstance(serve.read_configuration(), dict)


class AnnotationsTests(unittest.TestCase):
    maxDiff = None
    TAG_1 = {"tag": "1"}
    TAG_2 = {"tag": "2"}
    TAG_1_NEVER = {"tag": "1", "expires": ""}
    TAG_2_NEVER = {"tag": "2", "expires": ""}
    TAG_1_EXPIRE = {"tag": "1", "expires": "2024-01-01"}

    def setUp(self):
        self.addTypeEqualityFunc(list, self.assertCountEqual)

    def test_annotation_diff_simple(self):
        for mode in (False, True):
            # mode is not relevant for these checks
            self.assertEqual(serve._annotation_diff([], [], mode),
                             {'add': [], 'remove': [], 'change': []})
            self.assertEqual(serve._annotation_diff([], [self.TAG_1], mode),
                             {'add': [{"data": self.TAG_1, 'log': True}], 'remove': [], 'change': []})
            self.assertEqual(serve._annotation_diff([self.TAG_1], [], mode),
                             {'add': [], 'remove': [{"data": self.TAG_1, 'log': True}], 'change': []})
            self.assertEqual(serve._annotation_diff([self.TAG_1], [self.TAG_1], mode),
                             {'add': [], 'remove': [], 'change': []})
            self.assertEqual(serve._annotation_diff([self.TAG_1, self.TAG_2], [self.TAG_2], mode),
                             {'add': [], 'remove': [{"data": self.TAG_1, 'log': True}], 'change': []})
            self.assertEqual(serve._annotation_diff([self.TAG_1_NEVER], [self.TAG_1_NEVER, self.TAG_2_NEVER], mode),
                             {'add': [{"data": self.TAG_2_NEVER, 'log': True}], 'remove': [], 'change': []})
        self.assertEqual(serve._annotation_diff([self.TAG_1_NEVER], [self.TAG_1_EXPIRE], False),
                         {'add': [{"data": self.TAG_1_EXPIRE, 'log': True}], 'remove': [{"data": self.TAG_1_NEVER, 'log': True}], 'change': []})

    def test_annotation_diff_change(self):
        self.assertEqual(serve._annotation_diff([self.TAG_1_NEVER], [self.TAG_1_EXPIRE], True),
                         {'add': [{"data": self.TAG_1_EXPIRE, 'log': False}], 'remove': [{"data": self.TAG_1_NEVER, 'log': False}],
                          'change': [{"before": self.TAG_1_NEVER, "after": self.TAG_1_EXPIRE}]})
        self.assertEqual(serve._annotation_diff([self.TAG_1_NEVER, self.TAG_2_NEVER], [self.TAG_1_EXPIRE, self.TAG_2_NEVER], True),
                         {'add': [{"data": self.TAG_1_EXPIRE, 'log': False}], 'remove': [{"data": self.TAG_1_NEVER, 'log': False}],
                          'change': [{"before": self.TAG_1_NEVER, "after": self.TAG_1_EXPIRE}]})
        self.assertEqual(serve._annotation_diff([{"tag": "inhibition", "expires": "", "condition": ["eq", ["event_field", "foo"], "bar"]}, self.TAG_2_NEVER],
                                                [{"tag": "inhibition", "expires": "2024-01-01", "condition": ["eq", ["event_field", "foo"], "bar"]},
                                                 {"tag": "3", "expires": "2024-02-01"}], True),
                         {'add': [{"data": {"tag": "inhibition", "expires": "2024-01-01", "condition": ["eq", ["event_field", "foo"], "bar"]}, 'log': False},
                                  {"data": {"tag": "3", "expires": "2024-02-01"}, 'log': True}],
                          'remove': [{"data": self.TAG_2_NEVER, 'log': True},
                                     {"data": {"tag": "inhibition", "expires": "", "condition": ["eq", ["event_field", "foo"], "bar"]}, 'log': False}],
                          'change': [{"before": {"tag": "inhibition", "expires": "", "condition": ["eq", ["event_field", "foo"], "bar"]},
                                      "after": {"tag": "inhibition", "expires": "2024-01-01", "condition": ["eq", ["event_field", "foo"], "bar"]}}]})
        self.assertEqual(serve._annotation_diff([{"tag": "1", "expires": "2024-10-29"},
                                                 {"tag": "1", "expires": "2024-10-28"}],
                                                [{"tag": "1", "expires": "2024-10-31"}]),
                         {'add': [{'data': {"tag": "1", "expires": "2024-10-31"}, 'log': False}],
                          'remove': [
                             {'data': {"tag": "1", "expires": "2024-10-28"}, 'log': False},
                             {'data': {"tag": "1", "expires": "2024-10-29"}, 'log': True}],
                          'change': [
                             {'before': {"tag": "1", "expires": "2024-10-28"},
                              'after': {"tag": "1", "expires": "2024-10-31"}}
                         ]})
        self.assertEqual(serve._annotation_diff([{'tag': 'de-provider-xarf', 'expires': ''}],
                                                [{'tag': 'de-provider-xarf', 'expires': '2024-08-30'}, {'tag': 'de-provider-xarf', 'expires': '2024-10-29'}]),
                         {'add': [{'data': {'tag': 'de-provider-xarf', 'expires': '2024-08-30'}, 'log': False},
                                  {'data': {'tag': 'de-provider-xarf', 'expires': '2024-10-29'}, 'log': True}],
                          'change': [{'before': {'tag': 'de-provider-xarf', 'expires': ''},
                                      'after': {'tag': 'de-provider-xarf', 'expires': '2024-08-30'}}],
                          'remove': [{'data': {'tag': 'de-provider-xarf', 'expires': ''}, 'log': False}]})

    def test_annotation_diff_warn(self):
        with self.assertWarnsRegex(UserWarning, '^_annotation_diff: Modification detection disabled for performance reasons'):
            serve._annotation_diff([self.TAG_1] * 30, [], False)


ORG_DB_SIMPLE = RealDictRow([('organisation_id', 11), ('name', 'delete me'), ('sector_id', None), ('comment', ''), ('ripe_org_hdl', ''), ('ti_handle', ''), ('first_handle', ''), ('asns', []), ('contacts', []), ('national_certs', []), ('networks', []), ('fqdns', []), ('annotations', [])])
ORG_PY_SIMPLE = {'organisation_id': 11, 'name': 'delete me', 'sector_id': None, 'comment': '', 'ripe_org_hdl': '', 'ti_handle': '', 'first_handle': '', 'asns': [], 'contacts': [], 'national_certs': [], 'networks': [], 'fqdns': [], 'annotations': []}

ORG_DB_CONTACT = RealDictRow([('organisation_id', 12), ('name', 'delete me'), ('sector_id', None), ('comment', ''), ('ripe_org_hdl', ''), ('ti_handle', ''), ('first_handle', ''), ('asns', []), ('contacts', [RealDictRow([('contact_id', 58), ('firstname', ''), ('lastname', ''), ('tel', ''), ('openpgp_fpr', ''), ('email', 'abuse@example.com'), ('comment', ''), ('organisation_id', 12)])]), ('national_certs', []), ('networks', []), ('fqdns', []), ('annotations', [])])
ORG_PY_CONTACT = {'organisation_id': 12, 'name': 'delete me', 'sector_id': None, 'comment': '', 'ripe_org_hdl': '', 'ti_handle': '', 'first_handle': '', 'asns': [], 'contacts': [{'contact_id': 58, 'firstname': '', 'lastname': '', 'tel': '', 'openpgp_fpr': '', 'email': 'abuse@example.com', 'comment': '', 'organisation_id': 12}], 'national_certs': [], 'networks': [], 'fqdns': [], 'annotations': []}

ORG_DB_NETWORK_TAG = RealDictRow([('organisation_id', 13), ('name', 'delete me'), ('sector_id', None), ('comment', ''), ('ripe_org_hdl', ''), ('ti_handle', ''), ('first_handle', ''), ('asns', []), ('contacts', []), ('national_certs', []), ('networks', [RealDictRow([('network_id', 10), ('address', '10.0.0.1/32'), ('comment', ''), ('annotations', [{'tag': 'example_tag', 'expires': ''}])])]), ('fqdns', []), ('annotations', [])])
ORG_PY_NETWORK_TAG = {'organisation_id': 13, 'name': 'delete me', 'sector_id': None, 'comment': '', 'ripe_org_hdl': '', 'ti_handle': '', 'first_handle': '', 'asns': [], 'contacts': [], 'national_certs': [], 'networks': [{'network_id': 10, 'address': '10.0.0.1/32', 'comment': '', 'annotations': [{'tag': 'example_tag', 'expires': ''}]}], 'fqdns': [], 'annotations': []}
ORG_DB_NETWORK_TAG_EXPIRES = RealDictRow([('organisation_id', 13), ('name', 'delete me'), ('sector_id', None), ('comment', ''), ('ripe_org_hdl', ''), ('ti_handle', ''), ('first_handle', ''), ('asns', []), ('contacts', []), ('national_certs', []), ('networks', [RealDictRow([('network_id', 10), ('address', '10.0.0.1/32'), ('comment', ''), ('annotations', [{'tag': 'example_tag', 'expires': '2024-01-01'}])])]), ('fqdns', []), ('annotations', [])])
ORG_PY_NETWORK_TAG_EXPIRES = {'organisation_id': 13, 'name': 'delete me', 'sector_id': None, 'comment': '', 'ripe_org_hdl': '', 'ti_handle': '', 'first_handle': '', 'asns': [], 'contacts': [], 'national_certs': [], 'networks': [{'network_id': 10, 'address': '10.0.0.1/32', 'comment': '', 'annotations': [{'tag': 'example_tag', 'expires': '2024-01-01'}]}], 'fqdns': [], 'annotations': []}

ORG_DB = RealDictRow([('organisation_id', 14), ('name', 'delete me'), ('sector_id', None), ('comment', ''), ('ripe_org_hdl', ''), ('ti_handle', ''), ('first_handle', ''), ('asns', []), ('contacts', []), ('national_certs', []),
                      ('asns', [RealDictRow([('asn', 1), ('annotations', [{'tag': 'else'}])])]),
                      ('networks', [RealDictRow([('network_id', 11), ('address', '10.0.0.1/32'), ('comment', 'because'), ('annotations', [{'tag': 'Whitelist:Malware'}])])]),
                      ('fqdns', [RealDictRow([('fqdn_id', 4), ('fqdn', 'example.com'), ('comment', ''), ('annotations', [{'tag': 'inhibition', 'condition': ['eq', ['event_field', 'foo'], 'bar']}])])]),
                      ('annotations', [{'tag': 'Whitelist:All'}])])
ORG_PY = {'organisation_id': 14, 'name': 'delete me', 'sector_id': None, 'comment': '', 'ripe_org_hdl': '', 'ti_handle': '', 'first_handle': '',
          'asns': [{'annotations': [{'tag': 'else'}], 'asn': 1}],
          'contacts': [],
          'national_certs': [],
          'networks': [{'network_id': 11, 'address': '10.0.0.1/32', 'comment': 'because', 'annotations': [{'tag': 'Whitelist:Malware'}]}],
          'fqdns': [{'fqdn_id': 4, 'fqdn': 'example.com', 'comment': '', 'annotations': [{'tag': 'inhibition', 'condition': ['eq', ['event_field', 'foo'], 'bar']}]}],
          'annotations': [{'tag': 'Whitelist:All'}]}

ORG_PY_ASN_EXPIRES = deepcopy(ORG_PY)
ORG_PY_ASN_EXPIRES['asns'][0]['annotations'][0]['expires'] = ''
ORG_PY_FQDN_EXPIRES = deepcopy(ORG_PY)
ORG_PY_FQDN_EXPIRES['fqdns'][0]['annotations'][0]['expires'] = ''
ORG_PY_NET_EXPIRES = deepcopy(ORG_PY)
ORG_PY_NET_EXPIRES['networks'][0]['annotations'][0]['expires'] = ''
ORG_PY_ORG_EXPIRES = deepcopy(ORG_PY)
ORG_PY_ORG_EXPIRES['annotations'][0]['expires'] = ''


class TestOrgComparison(unittest.TestCase):
    maxDiff = None

    def test_org_equal(self):
        "Simple comparisons, nothing special"
        self.assertTrue(serve._compare_org(ORG_DB_SIMPLE, ORG_PY_SIMPLE))
        self.assertTrue(serve._compare_org(ORG_DB_CONTACT, ORG_PY_CONTACT))
        self.assertTrue(serve._compare_org(ORG_DB_NETWORK_TAG, ORG_PY_NETWORK_TAG))
        self.assertTrue(serve._compare_org(ORG_DB_NETWORK_TAG_EXPIRES, ORG_PY_NETWORK_TAG_EXPIRES))
        self.assertTrue(serve._compare_org(ORG_DB, ORG_PY))

    def test_org_equal_expires(self):
        "Tests with empty expire fields in each category"
        self.assertTrue(serve._compare_org(ORG_DB, ORG_PY_ASN_EXPIRES))
        self.assertTrue(serve._compare_org(ORG_DB, ORG_PY_FQDN_EXPIRES))
        self.assertTrue(serve._compare_org(ORG_DB, ORG_PY_NET_EXPIRES))
        self.assertTrue(serve._compare_org(ORG_DB, ORG_PY_ORG_EXPIRES))
