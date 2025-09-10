#!/usr/bin/env python3
"""Serve intelmq-certbund-contact db api via wsgi.

Requires hug (http://www.hug.rest/)

Copyright (C) 2017, 2018, 2019 by
Bundesamt für Sicherheit in der Informationstechnik

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
    * Bernhard Herzog <bernhard.herzog@intevation.de>


Design rationale:
    Our services shall be accessed by
    https://github.com/Intevation/intelmq-fody
    so our "endpoints" should be reachable from the same ip:port as
    the checkticket endpoints.

    We need location and credentials for the database holding the contactdb.
    The checkticket_api module [1] solves this problem by reusing
    the intelmq-mailgen configuration to access the 'intelmq-events' database.
    This serving part need to access a different database 'contactdb', thus
    we start with our on configuration.

    [1] https://github.com/Intevation/intelmq-fody-backend/tree/master/checkticket_api # noqa

"""
import json
import logging
import os
import sys
from copy import deepcopy
from typing import List, Tuple, Union
from operator import attrgetter
from warnings import warn

from falcon import HTTP_BAD_REQUEST, HTTP_NOT_FOUND, HTTP_UNPROCESSABLE_ENTITY
import hug
import psycopg2
from psycopg2.extras import RealDictCursor, RealDictRow
import jsonschema

from session import session

from contextlib import contextmanager
from psycopg2.extras import Json
from psycopg2.extensions import register_adapter
from psycopg2 import pool

register_adapter(dict, Json)
# The Json adaption will automatically convert to objects when reading


log = logging.getLogger(__name__)
# adding a custom log level for even more details when diagnosing
DD = logging.DEBUG-2
logging.addLevelName(DD, "DDEBUG")

# Using a global config variable, to be initialised once
config = None


def read_configuration() -> dict:
    """Read configuration file.

    If the environment variable CONTACTDB_SERVE_CONF_FILE exist, use it
    for the file name. Otherwise uses a default.

    Returns:
        The configuration values, possibly containing more dicts.

    Notes:
      Design rationale:
        * Provies an "okay" separation from config and code.
        * Better than intelmq-mailgen which has two hard-coded places
          and merge code for the config.
        * (Inspired by https://12factor.net/config.) But it is not a good
          idea to put credential information in the commandline or environment.
        * We are using json for the configuration file format and not
          Python's configparser module to stay more in line with intelmq's
          overall design philosophy to use json for configuration files.
    """
    config = None
    config_file_name = os.environ.get(
                        "CONTACTDB_SERVE_CONF_FILE",
                        "/etc/intelmq/contactdb-serve.conf")

    if os.path.isfile(config_file_name):
        with open(config_file_name) as config_handle:
                config = json.load(config_handle)

    return config if isinstance(config, dict) else {}


EXAMPLE_CONF_FILE = r"""
{
  "common_tags": [ "Whitelist:Malware",
                   "Whitelist:DNS-Open-Resolver",
                   "Whitelist:Open-Telnet",
                   "Whitelist:Shadowserver",
                   "Whitelist:All"
                   ],
  "libpg conninfo":
    "host=localhost dbname=contactdb user=apiuser password='USER\\'s DB PASSWORD'",
  "logging_level": "INFO"
}
"""  # noqa

ENDPOINT_PREFIX = '/api/contactdb'
ENDPOINT_NAME = 'ContactDB'
ANNOTATION_DIFF_MAX = 20


class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class CommitError(Error):
    """Exception raises if a commit action fails.
    """
    pass


class UnknownTagError(Error):
    """Exception raised when the client supplies an unknown tag."""
    pass


class ValidationError(Error):
    def __init__(self, errors):
        self.errors = errors

contactdb_pool = None
# Using a global object for the database connection
# must be initialised once
MAX_POOL_CONNECTIONS = 4

def open_db_pool(dsn: str):
    """Open the Connection pool to the ContactDB and saves in global obj

    Args:
        dsn: a Connection - String
    """
    global contactdb_pool

    contactdb_pool = pool.ThreadedConnectionPool(1, MAX_POOL_CONNECTIONS, dsn=dsn)
    return contactdb_pool


@contextmanager
def db_connection():

    # Pool doesn't check the connection automatically
    # Iterate max_connection+1 ensures that we either get a refreshed connection,
    # or the problem isn't solvable that way
    for _ in range(MAX_POOL_CONNECTIONS + 1):
        connection = contactdb_pool.getconn()
        try:
            connection.cursor().execute("SELECT 1;")
            break
        except psycopg2.Error as exc:
            log.info("Healthcheck connection failed: %s", repr(exc))
            contactdb_pool.putconn(connection, close=True)
    else:
        raise RuntimeError(f"Cannot get a healthy connection")

    try:
        yield connection
    finally:
        contactdb_pool.putconn(connection)


def _db_query(operation: str,
              parameters: Union[dict, list] = None) -> Tuple[list, list]:
    """Does an database query.

    Creates a cursor from the global database connection, runs
    the query or command the fetches all results.

    | By default, the first time a command is sent to the database [..]
    | a new transaction is created. The following database commands will
    | be executed in the context of the same transaction – not only the
    | commands issued by the first cursor, but the ones issued by all
    | the cursors created by the same connection.
    from psycopg2 docs section: Basic module usage->Transaction control
    http://initd.org/psycopg/docs/usage.html?#transactions-control

    Thus each endpoint must make sure explicitly call __commit_transaction()
    or __rollback_transaction() when done with all db operations.
    In case of a command failure __rollback_transaction() must be called
    until new commands will be executed.

    Parameters:
        operation: The query to be used by psycopg2.cursor.execute()
        parameters: for the sql query

    Returns:
        Tuple[list, List[psycopg2.extras.RealDictRow]]:
            description and results.
    """
    with db_connection() as conn:
        # psycopgy2.4 does not offer 'with' for cursor()
        # FUTURE: use with
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute(operation, parameters)
            results = cur.fetchall()
        except (psycopg2.Error, AttributeError):
            log.log(DD, "Calling rollback()")
            conn.rollback()
            raise
        else:
            conn.commit()

        log.log(DD, "Ran query={}".format(repr(cur.query.decode('utf-8'))))
        description = cur.description
        cur.close()

        return (description, results)


def _db_manipulate(operation: str, parameters=None) -> int:
    """Manipulates the database.

    Creates a cursor from the global database connection, runs the command.
    Has the same requirements regarding transactions as _db_query().

    Parameters:
        operation: The query to be used by psycopg2.cursor.execute()
        parameters: for the sql query

    Returns:
        Number of affected rows.
    """
    #  log.log(DD, "_db_manipulate({}, {})"
    #          "".format(operation, parameters))

    with db_connection() as conn:
        # pscopgy2.4 does not offer 'with' for cursor()
        # FUTURE use with
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(operation, parameters)
        log.log(DD, "Ran query={}".format(cur.query.decode('utf-8')))
        conn.commit()

        return cur.rowcount


def __db_query_organisation_ids(operation_str: str,  parameters=None):
    """Inquires organisation_ids for a specific query.

    Parameters:
        operation(str): must be a psycopg2 execute operation string that
            only returns an array of ids "AS organisation_ids" or nothing
            it has to contain '{0}' format placeholders for the table variants

    Returns:
        Dict("auto":list, "manual":list): lists of organisation_ids that
            where manually entered or imported automatically
    """
    orgs = {}

    description, results = _db_query(operation_str.format(""), parameters)
    if len(results) == 1 and results[0]["organisation_ids"] is not None:
        orgs["manual"] = results[0]["organisation_ids"]
    else:
        orgs["manual"] = []

    description, results = _db_query(operation_str.format("_automatic"),
                                     parameters)
    if len(results) == 1 and results[0]["organisation_ids"] is not None:
        orgs["auto"] = results[0]["organisation_ids"]
    else:
        orgs["auto"] = []

    return orgs


def __db_query_org(org_id: int, table_variant: str) -> dict:
    """Returns details for an organisation.

    Parameters:
        org_id:int: the organisation id to be queried
        table_variant: either "" or "_automatic"

    Returns:
        containing the organisation and additional keys
            'annotations', 'asns' (with 'annotations') and 'contacts'
    """

    operation_str = """
        SELECT * FROM organisation{0} WHERE organisation{0}_id = %s
        """.format(table_variant)

    description, results = _db_query(operation_str, (org_id,))

    if not len(results) == 1:
            return {}
    else:
        org = results[0]
        if table_variant != '':  # keep plain id name for all table variants
            org["organisation_id"] = org.pop(
                    "organisation{0}_id".format(table_variant)
                    )

        # insert asns.
        # HINT: we are not using __db_query_asn() because we don't know the
        #   asns yet, so we'll have to do another query anyway and using
        #   the function to encapsulate adding of the annotations would make
        #   the code here less elegant.
        operation_str = """
            SELECT * FROM organisation_to_asn{0}
                WHERE organisation{0}_id = %s
                ORDER BY asn
            """.format(table_variant)

        description, results = _db_query(operation_str, (org_id,))
        org["asns"] = results

        # insert contacts
        operation_str = """
            SELECT * FROM contact{0}
                WHERE organisation{0}_id = %s
                ORDER BY lower(email)
            """.format(table_variant)

        description, results = _db_query(operation_str, (org_id,))
        org["contacts"] = results

        # insert national certs
        operation_str = """
            SELECT * FROM national_cert{0}
                WHERE organisation{0}_id = %s
                ORDER BY lower(country_code)
            """.format(table_variant)

        description, results = _db_query(operation_str, (org_id,))
        org["national_certs"] = results

        # insert networks
        # we need the `network_id`s to query annotations.
        # According to the postgresql 9.5:
        #   "IPv4 addresses will always sort before IPv6 addresses"
        operation_str = """
            SELECT n.network{0}_id AS network_id, address, comment
                FROM network{0} AS n
                JOIN organisation_to_network{0} AS otn
                    ON n.network{0}_id = otn.network{0}_id
                WHERE otn.organisation{0}_id = %s
                ORDER BY n.address
            """.format(table_variant)

        description, results = _db_query(operation_str, (org_id,))
        org["networks"] = results

        # insert fqdns
        # we need the `fqdn_id`s to query annotations.
        operation_str = """
            SELECT f.fqdn{0}_id AS fqdn_id, fqdn, comment
                FROM fqdn{0} AS f
                JOIN organisation_to_fqdn{0} AS of
                    ON f.fqdn{0}_id = of.fqdn{0}_id
                WHERE of.organisation{0}_id = %s
                ORDER BY lower(fqdn)
            """.format(table_variant)

        description, results = _db_query(operation_str, (org_id,))
        org["fqdns"] = results

        # add existing annotations to the result
        # they can only be there for manual tables
        if table_variant == '':
            # insert annotations for the org
            org["annotations"] = __db_query_annotations(
                    "organisation", "organisation_id", org_id)

            # query annotations for each asn
            for index, asn in enumerate(org["asns"][:]):
                org["asns"][index]["annotations"] = \
                    __db_query_annotations("autonomous_system", "asn",
                                           asn["asn"])

            # query annotations for each network
            for index, network in enumerate(org["networks"][:]):
                org["networks"][index]["annotations"] = \
                    __db_query_annotations("network", "network_id",
                                           network["network_id"])

            # query annotations for each fqdn
            for index, fqdn in enumerate(org["fqdns"][:]):
                org["fqdns"][index]["annotations"] = \
                    __db_query_annotations("fqdn", "fqdn_id",
                                           fqdn["fqdn_id"])

        return org


def __db_query_annotations(table: str, column_name: str,
                           column_value: Union[str, int]) -> list:
    """Queries annotations.

    Parameters:
        table: the table name to which `_annotation` is added
        column_name: which has to match for the WHERE clause
        column_value: which we want

    Returns:
        all annotations, even if one occurs several times
    """
    operation_str = """
        SELECT json_agg(annotation ORDER BY annotation->>'tag')
            FROM {0}_annotation
            WHERE {1} = %s
    """.format(table, column_name)
    description, results = _db_query(operation_str, (column_value,))
    annos = results[0]["json_agg"]
    return annos if annos is not None else []


def __db_query_asn(asn: int, table_variant: str) -> dict:
    """Returns details for an asn."""

    operation_str = """
                SELECT * FROM organisation_to_asn{0}
                    WHERE asn = %s
                """.format(table_variant)
    description, results = _db_query(operation_str, (asn,))

    if len(results) > 0:
        if table_variant == '':  # insert annotations for manual tables
            results[0]['annotations'] = \
                __db_query_annotations("autonomous_system", "asn", asn)
        return results[0]
    else:
        return None


TABLE_TO_NAME_COLUMN = {
    'organisation': 'name',
    'fqdn': 'fqdn',
    'network': 'address'
}


def __get_name_to_object(object_type: str, object_value: int) -> str:
    if object_type == 'autonomous_system':
        return object_value
    return _db_query("""SELECT {0} FROM {1} WHERE {1}_id = %s""".format(TABLE_TO_NAME_COLUMN[object_type], object_type),
                     (object_value, ))[1][0][TABLE_TO_NAME_COLUMN[object_type]]


class Hashabledict(dict):
    """ Required for using dicts in a set"""

    def __hash__(self):
        return hash((frozenset(self.items())))

    def __lt__(self, other):
        """Make comparisons & sorting possible in a consistent way by using the annotation content in a specific order"""
        return f"{self.get('tag')}{self.get('expires')}{self.get('inhibtion')}" < f"{other.get('tag')}{other.get('expires')}{other.get('inhibtion')}"

    def __setitem__(self, key, value) -> None:
        raise RuntimeError('Unhashabledict cannot be changed')


def hashable_annotation(anno: dict) -> Hashabledict:
    """ Convert a annotation to a hashable annotation with tuples """
    anno_c = anno.copy()
    if 'condition' in anno_c:
        anno_c['condition'][1] = tuple(anno_c['condition'][1])
        anno_c['condition'] = tuple(anno_c['condition'])
    return Hashabledict(anno_c)


def unhashable_annotation(anno: dict) -> Hashabledict:
    """ Convert a hashable annotation to a normal annotation with lists """
    anno_c = anno.copy()
    if 'condition' in anno_c:
        anno_c['condition'] = list(anno_c['condition'])
        anno_c['condition'][1] = list(anno_c['condition'][1])
    return dict(anno_c)


def _annotation_diff(annos_are: List[dict], annos_should: List[dict],
                     detect_modifications: bool = True) -> List[dict]:
    """
    Compare two lists of annotations. Identify new and removed annotations.
    Main feature is to optionally detect modifications. Only changed expiry dates are detected at the moment.

    The speed implications are low, as the number of annotations are usually < 5 and annotation changes don't happen that often.
    For more than ANNOTATION_DIFF_MAX annotations, modification detection is disabled.
    """
    total_annotations = len(annos_are) + len(annos_should)
    if total_annotations >= ANNOTATION_DIFF_MAX:
        detect_modifications = False
        warn(f"_annotation_diff: Modification detection disabled for performance reasons, "
             f"got {total_annotations} annotations in total (>= {ANNOTATION_DIFF_MAX})")

    if detect_modifications:
        add = []
        remove = []
        change = []

        are = set([hashable_annotation(e) for e in annos_are])
        should = set([hashable_annotation(e) for e in annos_should])
        to_remove = sorted(are - should)
        to_add = sorted(should - are)

        for anno in to_remove.copy():
            anno_never = dict(anno)
            anno_never.pop('expires', None)
            for compare_anno in to_add.copy():  # compare with annos to add ignoring the expiry date
                compare_anno_never = dict(compare_anno)
                compare_anno_never.pop('expires', None)
                if anno_never == compare_anno_never:
                    remove.append({'data': unhashable_annotation(anno), 'log': False})
                    add.append({'data': unhashable_annotation(compare_anno), 'log': False})
                    change.append({'before': unhashable_annotation(anno), 'after': unhashable_annotation(compare_anno)})
                    to_add.remove(compare_anno)  # remove the processed annos from the two lists
                    to_remove.remove(anno)
                    break
            else:
                remove.append({'data': unhashable_annotation(anno), 'log': True})

        for anno in to_add:
            anno_never = dict(anno)
            anno_never.pop('expires', None)
            for compare_anno in to_remove.copy():
                compare_anno_never = dict(compare_anno)
                compare_anno_never.pop('expires', None)
                if anno_never == compare_anno_never:
                    add.append({'data': unhashable_annotation(anno), 'log': False})
                    remove.append({'data': unhashable_annotation(compare_anno), 'log': False})
                    change.append({'after': unhashable_annotation(anno), 'before': unhashable_annotation(compare_anno)})
                    to_remove.remove(compare_anno)
                    break
            else:
                add.append({'data': unhashable_annotation(anno), 'log': True})

        return {'add': add, 'remove': remove, 'change': change}
    else:
        return {'add': [{'data': a, 'log': True} for a in annos_should if a not in annos_are],
                'remove': [{'data': a, 'log': True} for a in annos_are if a not in annos_should],
                'change': []}


def __fix_annotations_to_table(
        annos_should: list, mode: str,
        table_pre: str, column_name: str, column_value: int,
        username: str) -> None:
    """Make sure that only these annotations exist to the given table.

    Parameters:
        annos: annotations that shall exist afterwards
        mode: how to deal with existing annos not in annos_should
            values 'cut' or 'add'
        table_pre: the prefix for `_annotation`
        column_name: of the FK to be set
        column_value: of the FK to be set
    """

    annos_are = __db_query_annotations(table_pre, column_name, column_value)
    anno_diff = _annotation_diff(annos_are, annos_should, detect_modifications=mode == 'cut')
    log.debug('Annotation Diff for %s is %r', table_pre, anno_diff)
    log.log(DD, "annos_should = {}; annos_are = {}"
                "".format(annos_should, annos_are))

    # Query the name of the affected object (organisation name, fqdn, domain or AS number)
    affected_object = __get_name_to_object(table_pre, column_value)

    # add missing annotations
    for anno in anno_diff['add']:
        operation_str = """
            INSERT INTO {0}_annotation
                ({1}, annotation) VALUES (%s, %s::json)
        """.format(table_pre, column_name)
        if anno['log']:
            _db_manipulate(f"""
                        INSERT INTO audit_log ("table", "user", "operation", "object_type", "object_value", "after")
                        VALUES ('{table_pre}_annotation', %s, 'add', %s, %s, %s::jsonb)
                        """, (username, table_pre, affected_object, anno['data'],))
        _db_manipulate(operation_str, (column_value, anno['data']))

    if mode == "cut":
        # remove superfluous annotations
        for anno in anno_diff['remove']:
            op_str = """
                DELETE FROM {0}_annotation
                    WHERE {1} = %s
                    AND annotation = %s::jsonb
                """.format(table_pre, column_name)
            _db_manipulate(op_str, (column_value, anno['data']))
            if anno['log']:
                _db_manipulate(f"""
                                INSERT INTO audit_log ("table", "user", "operation", "object_type", "object_value", "before")
                                VALUES ('{table_pre}_annotation', %s, 'remove', %s, %s, %s::jsonb)
                                """, (username, table_pre, affected_object, anno['data']))

    # add audit_log entries for all annotations with changed expiry date
    for anno in anno_diff['change']:
        _db_manipulate(f"""
                    INSERT INTO audit_log ("table", "user", "operation", "object_type", "object_value", "before", "after")
                    VALUES ('{table_pre}_annotation', %s, 'change', %s, %s, %s::jsonb, %s::jsonb)
                    """, (username, table_pre, affected_object, anno['before'], anno['after']))


def __fix_asns_to_org(asns: list, mode: str, org_id: int, username: str) -> None:
    """Make sure that exactly this asns with annotations exits and are linked.

    For each asn:
        Add missing annotations
        Remove superfluous ones

        Check the link to the org and create if necessary

    Parameters:
        asns: that should be exist afterwards
        mode: how to deal with annotation differences 'cut' or 'add'
        org_id: the org for the asns
    """
    for asn in asns:
        asn_id = asn["asn"]

        annos_should = asn["annotations"] if "annotations" in asn else []
        __fix_annotations_to_table(annos_should, mode,
                                   "autonomous_system", "asn", asn_id, username=username)

        # check linking to the org
        operation_str = """
            SELECT * FROM organisation_to_asn
                WHERE organisation_id = %s AND asn = %s
            """
        description, results = _db_query(operation_str, (org_id, asn_id,))
        if len(results) == 0:
            # add link
            operation_str = """
                INSERT INTO organisation_to_asn
                    (organisation_id, asn) VALUES (%s, %s)
                """
            _db_manipulate(operation_str, (org_id, asn_id,))

    # remove links between asns and org that should not be there anymore
    operation_str = """
        DELETE FROM organisation_to_asn
            WHERE organisation_id = %s
            AND asn != ALL(%s)
    """
    _db_manipulate(operation_str, (org_id, [int(asn["asn"]) for asn in asns]))

    # remove all annotations that are not linked to anymore
    operation_str = """
        DELETE FROM autonomous_system_annotation as asa
            WHERE asa.asn NOT IN (SELECT asn FROM organisation_to_asn)
        """
    _db_manipulate(operation_str)


def __fix_ntms_to_org(ntms_should: list, ntms_are: list,
                      table_name: str, column_name: str,
                      org_id: int, username: str) -> None:
    """Make sure that these ntm entries are there and linked from the org.

    In the certbund_contact db schema useful for entries that are linked
    via n-to-m tables and have annotations like 'network' and 'fqdn'.

    We implement way 2 from the https://github.com/Intevation/intelmq-fody/blob/master/docs/DesignConsiderations.md

    Parameters:
        ntms_should : .. exist and be linked from the org afterwards
        ntms_are: .. already linked to the org
        table_name: of the ntm table, also used to calculate the id_column_name
        org_id: to be linked by the ntms_should
    """  # noqa
    id_column_name = table_name + "_id"

    log.log(DD, "__fix_ntms_to_org({}, {},{}, {}, {})"
                "".format(ntms_should, ntms_are,
                          table_name, column_name, org_id))

    values_should = [n[column_name] for n in ntms_should]
    values_are = [n[column_name] for n in ntms_are]

    # remove links to orgs that we do not want anymore
    superfluous = [n for n in ntms_are
                   if n[column_name] not in values_should]
    for entry_shouldnt in superfluous:
        __fix_annotations_to_table([], "cut", table_name,
                                   id_column_name,
                                   entry_shouldnt[id_column_name],
                                   username=username)
        operation_str = """
            DELETE FROM organisation_to_{0}
                WHERE organisation_id = %s
                    AND {1} = %s
            """.format(table_name, id_column_name)
        _db_manipulate(operation_str,
                       (org_id, entry_shouldnt[id_column_name]))

    # create and link missing entries
    missing = [n for n in ntms_should
               if n[column_name] not in values_are]

    values_already_added = []
    for entry in missing:
        if entry[column_name] in values_already_added:
            # do not add a value twice,
            # let the first one win throw away the others.
            # TODO once better error reporting is implemented: throw error
            log.info("%s already exits, throwing away %s.", column_name, entry)
            continue

        # we have to freshly create an entry
        operation_str = """
            INSERT INTO {0} ({1}, comment)
                VALUES (%({1})s, %(comment)s)
            RETURNING {2}
            """.format(table_name, column_name, id_column_name)
        desc, results = _db_query(operation_str, entry)
        new_entry_id = results[0][id_column_name]

        __fix_annotations_to_table(entry["annotations"], "add",
                                   table_name, id_column_name, new_entry_id, username=username)

        # link it to the org
        operation_str = """
            INSERT INTO organisation_to_{0}
                (organisation_id, {1}) VALUES (%s, %s)
            """.format(table_name, id_column_name)
        _db_manipulate(operation_str, (org_id, new_entry_id))

        values_already_added.append(entry[column_name])

    # update and link existing entries
    existing = [n for n in ntms_are if n[column_name] in values_should]
    for entry_is in existing:
        # find entry_should
        for entry in ntms_should:
            if entry_is[column_name] == entry[column_name]:
                entry_should = entry
                break

        # update comment (as the column is already the one we wanted)
        op_str = """
            UPDATE {0}
                SET (comment) = row(%s)
                WHERE {1} = %s
            """.format(table_name, id_column_name)
        _db_manipulate(op_str,
                       (entry_should['comment'], entry_is[id_column_name],))

        # update annotations
        __fix_annotations_to_table(entry_should["annotations"], "cut",
                                   table_name, id_column_name,
                                   entry_is[id_column_name], username=username)

    # delete entries that are not linked anymore
    operation_str = """
        DELETE FROM {0} AS t
            WHERE NOT EXISTS (
                SELECT * FROM organisation_to_{0} AS ott
                    WHERE ott.{1} = t.{1}
                )
        """.format(table_name, id_column_name)
    _db_manipulate(operation_str, "")


def __fix_leafnodes_to_org(leafs: List[dict], table: str,
                           needed_attributes: List[str], org_id: int) -> None:
    """Make sure that exactly the list of leafnotes exist and link to the org.

    (In the certbund-contact db this is useful for 'national_cert' and
    'contact').

    Parameters:
        leafs: entries that shall be linked to the org
        table: name of the entry table
        needed_attributes: that have to be keys in each entry to be inserted
            in the database 'table'
    """

    # first delete all leafnotes for the org
    op_str = "DELETE FROM {0} WHERE organisation_id = %s".format(table)
    _db_manipulate(op_str, (org_id,))

    # next (re)create all entries we want to have now
    for leaf in leafs:
        # make sure that all attributes are there and at least ''
        # (As None would we translated to = NULL' which always fails in SQL)
        for attribute in needed_attributes:
            if (attribute not in leaf) or leaf[attribute] is None:
                raise CommitError("{} not set".format(attribute))

        # add the org_id to the dict so it holds all parameters for the query
        leaf["organisation_id"] = org_id

        op_str = """
            INSERT INTO {0} ({1}, organisation_id)
            VALUES (%({2})s, %(organisation_id)s)
        """.format(table,
                   ", ".join(needed_attributes),
                   ")s, %(".join(needed_attributes))

        _db_manipulate(op_str, leaf)


org_schema = {
    "definitions": {
        "annotations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "minLength": 1},
                    "condition": {"type": ["array", "boolean"], "minItems": 2, "maxItems": 3}
                },
                "required": ["tag"]
            }
        }
    },
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "comment": {"type": "string"},
        "ripe_org_hdl": {"type": "string"},
        "ti_handle": {"type": "string"},
        "first_handle": {"type": "string"},
        "annotations": {"$ref": "#/definitions/annotations"},
        "asns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "asn": {"type": "integer", "minimum": 0},
                    "annotations": {"$ref": "#/definitions/annotations"}
                },
                "required": ["asn"]
            }
        },
        "contacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "firstname": {"type": "string"},
                    "lastname": {"type": "string"},
                    "email": {"type": "string", "pattern": "^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"},
                    "tel": {"type": "string"},
                    "comment": {"type": "string"},
                    "openpgp_fpr": {"type": "string"}
                },
                "required": ["firstname", "lastname", "email", "tel", "comment", "openpgp_fpr"]
            }
        },
        "fqdns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fqdn": {"type": "string", "pattern": "^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\\.)*(?:[0-9]*[a-z](?:[a-z0-9-]*[a-z0-9])?|[0-9]+-+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)$"},
                    "comment": {"type": "string"},
                    "annotations": {"$ref": "#/definitions/annotations"}
                },
                "required": ["fqdn"]
            }
        },
        "networks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "minLength": 1, "format": "cidr"},
                    "comment": {"type": "string"},
                    "annotations": {"$ref": "#/definitions/annotations"}
                },
                "required": ["address"]
            }
        },
        "national_certs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "country_code": {"type": "string", "pattern": "^[a-zA-Z]{2}$"},
                    "comment": {"type": "string"}
                },
                "required": ["country_code"]
            }
        }
    },
    "required": ["name"]
}


org_checker = jsonschema.FormatChecker()


@org_checker.checks('cidr')
def validate_cidr(cidr):
    # Currently only validated in front-end
    return True


org_validator = jsonschema.Draft7Validator(org_schema, format_checker=org_checker)


def validate_org(org: dict) -> None:
    """Validate org, raise if invalid

    Validate the org against the schema. If it is invalid, raise
    ValidationError.
    """
    error_list = []
    errors = sorted(org_validator.iter_errors(org), key=attrgetter("path"))
    for error in errors:
        error_list.append((list(error.absolute_path), error.message))
    if error_list:
        raise ValidationError(error_list)


def _create_org(org: dict, username: str) -> int:
    """Insert an new contactdb entry.

    Makes sure that the contactdb entry expressed by the org dict
    is in the tables for manual entries.

    Creates it anyway, even if there are entries with the same
    values in organisation, because there may be differences in the
    entries that are attached for a purpose.

    Returns:
        Database ID of the organisation that was created.
    """
    # log.debug("_create_org called with " + repr(org))

    validate_org(org)

    needed_attribs = ['name', 'comment', 'ripe_org_hdl',
                      'ti_handle', 'first_handle']

    for attrib in needed_attribs:
        if attrib in org:
            if org[attrib] is None:
                org[attrib] = ''
        else:
            raise CommitError("{} not set".format(attrib))

    if org['name'] == '':
        raise CommitError("Name of the organisation must be provided.")

    operation_str = """
        INSERT INTO organisation
            (name, sector_id, comment, ripe_org_hdl,
             ti_handle, first_handle)
            VALUES (%(name)s, %(sector_id)s, %(comment)s, %(ripe_org_hdl)s,
                    %(ti_handle)s, %(first_handle)s)
            RETURNING organisation_id
        """
    description, results = _db_query(operation_str, org)
    new_org_id = results[0]["organisation_id"]

    __fix_annotations_to_table(org["annotations"], "add",
                               "organisation", "organisation_id", new_org_id,
                               username=username)

    __fix_asns_to_org(org['asns'], "add", new_org_id, username=username)

    __fix_leafnodes_to_org(org['contacts'], 'contact',
                           ['firstname', 'lastname', 'tel',
                            'openpgp_fpr', 'email', 'comment'], new_org_id)

    __fix_leafnodes_to_org(org["national_certs"], "national_cert",
                           ["country_code", "comment"], new_org_id)

    # as this is a new org object, there is nothing linked to it yet
    __fix_ntms_to_org(org["networks"], [], "network", "address", new_org_id, username=username)
    __fix_ntms_to_org(org["fqdns"], [], "fqdn", "fqdn", new_org_id, username=username)

    return new_org_id


def _update_org(org, username: str):
    """Update a contactdb entry.

    First updates or creates the linked entries.
    There is no need to check if other linked entries are similar,
    because we use the contactdb in a way that each org as its own
    linked entries.

    Last update the values of the org itself.

    Returns:
        Database ID of the updated organisation.
    """
    # log.debug("_update_org called with " + repr(org))

    validate_org(org)

    org_id = org["organisation_id"]
    org_in_db = __db_query_org(org_id, "")

    if ("organisation_id" not in org_in_db) \
            or org_in_db["organisation_id"] != org_id:
        raise CommitError("Org {} to be updated not in db.".format(org_id))

    if 'name' not in org or org['name'] is None or org['name'] == '':
        raise CommitError("Name of the organisation must be provided.")

    if org["sector_id"] == '':
        org["sector_id"] = None

    __fix_annotations_to_table(org["annotations"], "cut",
                               "organisation", "organisation_id", org_id, username=username)

    __fix_asns_to_org(org["asns"], "cut", org_id, username=username)
    __fix_leafnodes_to_org(org['contacts'], 'contact',
                           ['firstname', 'lastname', 'tel',
                            'openpgp_fpr', 'email', 'comment'], org_id)
    __fix_leafnodes_to_org(org["national_certs"], "national_cert",
                           ["country_code", "comment"], org_id)

    org_so_far = __db_query_org(org_id, "")
    networks_are = org_so_far["networks"] if "networks" in org_so_far else []
    __fix_ntms_to_org(org["networks"], networks_are,
                      "network", "address", org_id, username=username)

    fqdns_are = org_so_far["fqdns"] if "fqdns" in org_so_far else []
    __fix_ntms_to_org(org["fqdns"], fqdns_are, "fqdn", "fqdn", org_id, username=username)

    # linking other tables has been done, only update is left to do
    operation_str = """
        UPDATE organisation
            SET (name, sector_id, comment, ripe_org_hdl,
                 ti_handle, first_handle)
              = (%(name)s, %(sector_id)s, %(comment)s, %(ripe_org_hdl)s,
                 %(ti_handle)s, %(first_handle)s)
            WHERE organisation_id = %(organisation_id)s
        """
    _db_manipulate(operation_str, org)

    return org_id


def _compare_org(org_a: dict, org_b: dict) -> bool:
    """ Compare two organisation objects for equality.

    Ignores empty expire fields.
    Can be extended to other fields (emtpy conditions of inhibitions, empty network objects etc)

    Returns True if both organisation objects are equal,
        False otherwise"""
    a = deepcopy(org_a)
    b = deepcopy(org_b)
    for org in (a, b):
        if isinstance(org, RealDictRow):
            org = dict(org)
        for obj_type in ('asns', 'fqdns', 'networks'):
            for obj_id, obj in enumerate(org[obj_type]):
                for anno_id, anno in enumerate(org[obj_type][obj_id]['annotations']):
                    if anno.get('expires', None) == '':
                        print(f'{obj_type} anno empty expires')
                        del org[obj_type][obj_id]['annotations'][anno_id]['expires']
        for anno_id, anno in enumerate(org['annotations']):
            if anno.get('expires', None) == '':
                print('org anno empty expires')
                del org['annotations'][anno_id]['expires']

    return a == b


def _delete_org(org, username: str) -> int:
    """Delete an manual org from the contactdb.

    Also delete the attached entries, if they are not used elsewhere.

    Returns:
        Database ID of the organisation that has been deleted.
    """
    # log.debug("_delete_org called with " + repr(org))

    validate_org(org)

    org_id_rm = org["organisation_id"]

    org_in_db = __db_query_org(org_id_rm, "")

    if not _compare_org(org_in_db, org):
        log.warn("org_in_db = %r; org = %r", org_in_db, org)
        raise CommitError("Org to be deleted differs from db entry.")

    __fix_asns_to_org([], "cut", org_id_rm, username=username)
    __fix_leafnodes_to_org([], "contact", [], org_id_rm)

    org_is = __db_query_org(org_id_rm, "")

    networks_are = org_is["networks"] if "networks" in org_is else []
    __fix_ntms_to_org([], networks_are, "network", "address", org_id_rm, username=username)

    fqdns_are = org_is["fqdns"] if "fqdns" in org_is else []
    __fix_ntms_to_org([], fqdns_are, "fqdn", "fqdn", org_id_rm, username=username)

    __fix_leafnodes_to_org([], "national_cert", [], org_id_rm)

    __fix_annotations_to_table([], "cut",
                               "organisation", "organisation_id", org_id_rm, username=username)

    # remove org itself
    operation_str = "DELETE FROM organisation WHERE organisation_id = %s"
    affected_rows = _db_manipulate(operation_str, (org["organisation_id"],))

    if affected_rows == 1:
        return org["organisation_id"]


@hug.startup()
def setup(api):
    global config
    config = read_configuration()
    if "logging_level" in config:
        log.setLevel(config["logging_level"])
    open_db_pool(config["libpg conninfo"])
    log.debug("Initialised DB connection for contactdb_api.")


@hug.get(ENDPOINT_PREFIX + '/ping', requires=session.token_authentication)
def pong():
    return ["pong"]


@hug.get(ENDPOINT_PREFIX + '/searchasn', requires=session.token_authentication)
def searchasn(asn: int):
    # as an asn can only be associated once with an org_id,
    # we do not need DISTINCT
    query_results = __db_query_organisation_ids("""
        SELECT array_agg(organisation{0}_id) as organisation_ids
            FROM organisation_to_asn{0}
            WHERE asn=%s
        """, (asn,))
    return query_results


@hug.get(ENDPOINT_PREFIX + '/searchorg', requires=session.token_authentication)
def searchorg(name: str):
    """Search for an entry with the given name.

    Search is an case-insensitive substring search.
    """
    # each org_id only has one name, so we do not need DISTINCT
    return __db_query_organisation_ids("""
        SELECT array_agg(o.organisation{0}_id) AS organisation_ids
            FROM organisation{0} AS o
            WHERE name ILIKE %s
        """, ("%"+name+"%",))


@hug.get(ENDPOINT_PREFIX + '/searchcontact', requires=session.token_authentication)
def searchcontact(email: str):
    """Search for an entry with the given email address.

    Uses a case-insensitive substring search.
    """
    query_results = __db_query_organisation_ids("""
        SELECT array_agg(DISTINCT c.organisation{0}_id) AS organisation_ids
            FROM contact{0} AS c
            WHERE c.email ILIKE %s
        """, ("%"+email+"%",))
    return query_results


@hug.get(ENDPOINT_PREFIX + '/searchdisabledcontact', requires=session.token_authentication)
def searchdisabledcontact(email: str):
    """Search for entries where string is part of a disabled email address.

    Uses a case-insensitive substring search.
    """
    query_results = __db_query_organisation_ids("""
        SELECT array_agg(DISTINCT c.organisation{0}_id) AS organisation_ids
            FROM contact{0} AS c
            LEFT OUTER JOIN email_status es ON c.email = es.email
            WHERE c.email ILIKE %s AND es.enabled = false
        """, ("%"+email+"%",))
    return query_results


@hug.get(ENDPOINT_PREFIX + '/searchcidr', requires=session.token_authentication)
def searchcidr(address: str, response):
    """Search for orgs related to the cidr.

    Finds orgs that either are responsible for the network or ip
    or that are contained in the given network.

    Strips leading and trailing whitespace.
    """
    address = address.strip()
    try:
        # postgresql 9.3/docs/9.12:
        #   '<<=   is contained within or equals'
        #   '>>    contains'
        query_results = __db_query_organisation_ids("""
            SELECT array_agg(DISTINCT otn.organisation{0}_id)
                    AS organisation_ids
                FROM organisation_to_network{0} AS otn
                JOIN network{0} AS n
                    ON n.network{0}_id = otn.network{0}_id
                WHERE n.address <<= %s OR n.address >> %s
            """, (address, address))
    except psycopg2.DataError:
        # catching psycopg2.DataError: invalid input syntax for type inet
        log.info("searchcidr?address=%s failed with DataError", address)
        response.status = HTTP_BAD_REQUEST
        return {"reason": "DataError, probably not in cidr style."}

    return query_results


@hug.get(ENDPOINT_PREFIX + '/searchfqdn', requires=session.token_authentication)
def searchfqdn(domain: str):
    """Search orgs that are responsible for a hostname in the domain.

    Strips whitespace.
    """
    domain = domain.strip()
    query_results = __db_query_organisation_ids("""
        SELECT array_agg(DISTINCT otf.organisation{0}_id)
                AS organisation_ids
            FROM organisation_to_fqdn{0} AS otf
            JOIN fqdn{0} AS f ON f.fqdn{0}_id = otf.fqdn{0}_id
            WHERE f.fqdn ILIKE %s OR f.fqdn ILIKE %s
        """, (domain, "%."+domain))
    return query_results


@hug.get(ENDPOINT_PREFIX + '/searchnational', requires=session.token_authentication)
def searchnational(countrycode: hug.types.length(2, 3)):
    """Search for orgs that are responsible for the given country.
    """
    query_results = __db_query_organisation_ids("""
        SELECT array_agg(DISTINCT organisation{0}_id) AS organisation_ids
            FROM national_cert{0}
            WHERE country_code ILIKE %s
        """, (countrycode,))
    return query_results


def join_org_ids(q1: list, q2: list):
    """Merge two query_results with `manual` and `auto` lists.

    Returning a new object where org_ids are unique and numerically ordered.
    """

    new_query_results = {}
    new_query_results["auto"] = list(set(q1["auto"] + q2["auto"]))
    new_query_results["auto"].sort(key=int)
    new_query_results["manual"] = list(set(q1["manual"] + q2["manual"]))
    new_query_results["manual"].sort(key=int)

    return new_query_results


@hug.get(ENDPOINT_PREFIX + '/annotation/search', requires=session.token_authentication)
def search_annotation(tag: str):
    """Search for orgs that are attached to a matching annotation.

    Searches both annotations in manual entries and email 'tags'.
    """
    # we only have the manual tables with annotations, thus we
    # cannot use  __db_query_organisation_ids() and do it manually
    query_results = {"auto": [], "manual": []}

    op_str = """
        SELECT array_agg(organisation_id) AS organisation_ids FROM (

            -- 1. orgs
            SELECT organisation_id FROM organisation_annotation
                WHERE annotation::json->>'tag' ILIKE %s

            UNION DISTINCT

            -- 2. asns
            SELECT organisation_id FROM organisation_to_asn AS ota
                JOIN autonomous_system_annotation AS asa
                    ON ota.asn = asa.asn
                WHERE asa.annotation->>'tag' ILIKE %s

            UNION DISTINCT

            -- 3. networks
            SELECT organisation_id FROM organisation_to_network AS otn
                JOIN network AS n
                    ON otn.network_id = n.network_id
                JOIN network_annotation AS na
                    ON n.network_id = na.network_id
                WHERE na.annotation->>'tag' ILIKE %s

            UNION DISTINCT

            -- 4. fqdns
            SELECT organisation_id FROM organisation_to_fqdn AS otf
                JOIN fqdn AS f
                    ON otf.fqdn_id = f.fqdn_id
                JOIN fqdn_annotation AS fa
                    ON f.fqdn_id = fa.fqdn_id
                WHERE fa.annotation->>'tag' ILIKE %s

            ) AS foo
        """
    desc, results = _db_query(op_str, ("%" + tag + "%",)*4)

    if len(results) == 1 and results[0]["organisation_ids"] is not None:
        query_results["manual"] = results[0]["organisation_ids"]

    # search for email tags
    op_str = """
        SELECT email from email_tag
            WHERE tag_id IN (
                SELECT tag_id from tag where tag_description ILIKE %s
                )
        """
    desc, results = _db_query(op_str, ("%" + tag + "%",))

    # find org ids for each email address and join them
    for result in results:
        additional_org_ids = searchcontact(result["email"])
        query_results = join_org_ids(query_results, additional_org_ids)
    return query_results


@hug.get(ENDPOINT_PREFIX + '/org/manual/{id}', requires=session.token_authentication)
def get_manual_org_details(id: int):
    return __db_query_org(id, "")


@hug.get(ENDPOINT_PREFIX + '/org/auto/{id}', requires=session.token_authentication)
def get_auto_org_details(id: int):
    return __db_query_org(id, "_automatic")


@hug.get(ENDPOINT_PREFIX + '/org/schema.json')
def get_org_schema():
    return org_schema


@hug.get(ENDPOINT_PREFIX + '/asn/manual/{number}', requires=session.token_authentication)
def get_manual_asn_details(number: int, response):
    asn = __db_query_asn(number, "")

    if asn is None:
        response.status = HTTP_NOT_FOUND
        return {"reason": "ASN not found"}
    else:
        return asn


def _load_known_email_tags():
    # Note: we determine the name of the default tag with min as the
    # aggregation function because due to the filter and the constraint
    # that there is only one default tag per tag_name there will be only
    # one value.
    all_tags = _db_query("""
        SELECT tag_name,
               json_object_agg(tag_value,
                               CASE WHEN tag_description = '' THEN tag_value
                                    ELSE tag_description
                               END) AS tags,
               coalesce(min(tag_value) FILTER (WHERE is_default), '')
               AS default_tag
          FROM tag_name JOIN tag ON tag.tag_name_id = tag_name.tag_name_id
      GROUP BY tag_name, tag_name_order
      ORDER BY tag_name_order""")[1]
    return [(row["tag_name"], dict(tags=row["tags"],
                                   default_tag=row["default_tag"]))
            for row in all_tags]


@hug.get(ENDPOINT_PREFIX + '/annotation/hints', requires=session.token_authentication)
def get_annotation_hints():
    """Return all hints helpful to build a good interface to annotations.
    """
    global config
    # TODO ask the database or inquire what the rules have registered

    # the following hints are hints for all table types,
    # in the future, if needed, we could have a dict for each
    # `autonomous_system`, `organisation`, `network` and `fqdn` separately
    hints = {'tags': ['daily',
                      'hourly',
                      'XY-provider-xarf',
                      'certXY-realtime-xmpp'],
             'conditions': {'binary_operators': {'eq': '=='},
                            'fields': {'event_field': [
                                'classification.identifier',
                                'destination.asn'
                                ]}}}

    if 'common_tags' in config:
        hints['tags'] = config['common_tags']
    hints['email_tags'] = _load_known_email_tags()

    return hints


# a way to test this is similar to
#   import requests
#   requests.post('http://localhost:8000/api/contactdb/org/manual/commit', json={'one': 'two'}, auth=('user', 'pass')).json() # noqa
@hug.post(ENDPOINT_PREFIX + '/org/manual/commit', requires=session.token_authentication)
def commit_pending_org_changes(body, request, response, user: hug.directives.user):
    log.info("Got commit_object = %r; user = %r.", body, user['username'])
    if not (body
            and 'commands' in body
            and len(body['commands']) > 0
            and 'orgs' in body
            and len(body['orgs']) > 0
            and len(body['commands']) == len(body['orgs'])):
        response.status = HTTP_BAD_REQUEST
        return {'reason': "Needs commands and orgs arrays of same length."}

    commands = body['commands']
    orgs = body['orgs']

    known_commands = {  # list of commands and function table
        'create': _create_org,
        'update': _update_org,
        'delete': _delete_org
        }

    for command in commands:
        if command not in known_commands:
            response.status = HTTP_BAD_REQUEST
            return {'reason':
                    "Unknown command. Not in " + str(known_commands.keys())}

    results = []
    try:
        for i, (command, org) in enumerate(zip(commands, orgs)):
            results.append((command, known_commands[command](org, username = user['username'])))
    except ValidationError as e:
        response.status = HTTP_UNPROCESSABLE_ENTITY
        return {
            "reason": "JSON validation failed",
            "details": {"create": [(i, e.errors)]}
        }
    except Exception as exc:
        log.info("Commit failed %r with %r by username = %r",
                 command, org, user['username'], exc_info=exc)
        response.status = HTTP_BAD_REQUEST
        return {
            "reason": "Commit failed",
            "details": "{}".format(repr(exc).replace('\n', ' '))
        }

    log.info("Commit successful, results = %r; username = %r",
             results, user['username'])
    return results


@hug.get(ENDPOINT_PREFIX + '/email/{email}', requires=session.token_authentication)
def get_email_details(email: str):
    """Lookup status/tags of an email address.

    Returns:

        A single email_status object, which has the following key/value
        pairs:

           enabled: Boolean, indicating whether notifications should be
                    sent to that address.

           tags: Object with tag categories as keys and one tag for each
                 key.

        If the email address is not known, enabled will be true and tags
        will have an empty object.
    """
    op_str = """SELECT * FROM email_status WHERE email = %s"""

    tags_query = """SELECT tag_name, tag_value
                      FROM email_tag
                      JOIN tag USING (tag_id)
                      JOIN tag_name USING (tag_name_id)
                     WHERE email = %s"""

    statuses = _db_query(op_str, (email,))[1]
    tags = _db_query(tags_query, (email,))[1]

    if len(statuses) > 0:
        result = statuses[0]
    else:
        result = {"email": email, "enabled": True}

    result["tags"] = dict((row["tag_name"], row["tag_value"])
                          for row in tags)

    return result


def _set_email_status(email, enabled):
    # using an "upsert" feature that is available since postgresql 9.5
    # because it is cleanest, e.g.
    # see https://hashrocket.com/blog/posts/upsert-records-with-postgresql-9-5
    op_str = """INSERT INTO email_status (email, enabled)
                    VALUES (%s, %s)
                ON CONFLICT (email)
                    DO UPDATE SET (email, enabled, added) = (%s, %s, now())
             """
    return _db_manipulate(op_str, (email, enabled, email, enabled))


def _set_email_tags(email, tags):
    _db_manipulate("DELETE FROM email_tag WHERE email = %s", (email,))
    total_rows_changed = 0
    for tag_name, tag_value in tags.items():
        num_rows = _db_manipulate("""INSERT INTO email_tag (email, tag_id)
                                     SELECT %s, tag_id
                                       FROM tag
                                       JOIN tag_name USING (tag_name_id)
                                      WHERE tag_name = %s
                                        AND tag_value = %s""",
                                  (email, tag_name, tag_value))
        if num_rows < 1:
            raise UnknownTagError("Unknown Tag: tag_name: %r, tag_value: %r"
                                  % (tag_name, tag_value))
        total_rows_changed += num_rows
    return total_rows_changed


@hug.put(ENDPOINT_PREFIX + '/email/{email}', requires=session.token_authentication)
def put_email(email: str, body, request, response, user: hug.directives.user):
    """Updates status and/or tags of email.

    The body should be a JSON object with one or both of the following
    key/value pairs:

       enabled: Boolean

       tags: Object mapping tag categories to tags. Each category has
             one tag. All categories/tags not mentioned in this object
             will be removed from set of tags associated with the email
             address.
    """
    log.info("Got new status for email = %r; body = %r; username = %r",
             email, body, user['username'])

    if not body:
        response.status = HTTP_BAD_REQUEST
        return

    status = body.get("enabled")
    if status is not None and status not in [True, False]:
        response.status = HTTP_BAD_REQUEST
        return

    tags = body.get("tags")
    if tags is not None:
        # the actual tag values are checked by _set_email_tags, but we
        # can check that tags is a dictionary mapping strings to
        # strings.
        for category, tag in tags.items():
            if not isinstance(category, str) or not isinstance(tag, str):
                response.status = HTTP_BAD_REQUEST
                return

    try:
        n_rows_changed = 0
        if status is not None:
            n_rows_changed += _set_email_status(email, status)
        if tags is not None:
            n_rows_changed += _set_email_tags(email, tags)
    except UnknownTagError:
        response.status = HTTP_BAD_REQUEST
        return

    return n_rows_changed


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--example-conf':
        print(EXAMPLE_CONF_FILE)
        sys.exit()

    config = read_configuration()
    print("config = {}".format(config,))
    if "logging_level" in config:
        log.setLevel(config["logging_level"])

    print("log.name = \"{}\"".format(log.name))
    print("log effective level = \"{}\"".format(
        logging.getLevelName(log.getEffectiveLevel())))

    open_db_pool(config["libpg conninfo"])

    with db_connection() as conn:
        cur = conn.cursor()

        for count in [
                "organisation_automatic",
                "organisation",
                "contact_automatic",
                "contact",
                "organisation_to_asn_automatic",
                "organisation_to_asn",
                "national_cert_automatic",
                "national_cert",
                "network_automatic",
                "network",
                "fqdn_automatic",
                "fqdn",
                ]:
            cur.execute("SELECT count(*) FROM {}".format(count))
            result = cur.fetchone()
            print("count_{} = {}".format(count, result[0]))

        cur.connection.commit()  # end transaction
