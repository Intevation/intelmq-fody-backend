#!/usr/bin/env python3
"""Serve IntelMQ - Mailgen Tickets

Requires hug (http://www.hug.rest/)

Copyright (C) 2017-2020 by Bundesamt für Sicherheit in der Informationstechnik

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
    * Dustin Demuth <dustin.demuth@intevation.de>

TODO:
    - To start, all queries will be AND concatenated. OR-Queries can be
      introduced later.
    - THIS SCRIPT CONTAINS A LOT OF DUPLICATED CODE FROM THE EVENTS-API!

"""

import json
import logging
import os
import sys
# FUTURE the typing module is part of Python's standard lib for v>=3.5
# try:
#    from typing import Tuple, Union, Sequence, List
# except:
#    pass

from falcon import HTTP_BAD_REQUEST, HTTP_INTERNAL_SERVER_ERROR
import hug
import psycopg2
import datetime
import dateutil.parser
import copy

from psycopg2.extras import RealDictCursor

from session import session

log = logging.getLogger(__name__)
# adding a custom log level for even more details when diagnosing
DD = logging.DEBUG-2
logging.addLevelName(DD, "DDEBUG")

EXAMPLE_CONF_FILE = r"""
{
  "libpg conninfo":
    "host=localhost dbname=eventdb user=apiuser password='USER\\'s DB PASSWORD'",
  "logging_level": "INFO"
}
""" # noqa

ENDPOINT_PREFIX = '/api/tickets'
ENDPOINT_NAME = 'Tickets'


def read_configuration() -> dict:
    """Read configuration file.

    If the environment variable EVENTDB_SERVE_CONF_FILE exist, use it
    for the file name. Otherwise uses a default.

    TODO:
        Move this to a lib which can be used as a common function
        for contact_db_api and other extensions.
        Maybe the Endpoint-Prefix can be a parameter for this.
        or intelmq_fody_backend....

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
                        "TICKETS_SERVE_CONF_FILE",
                        "/etc/intelmq/tickets-serve.conf")

    if os.path.isfile(config_file_name):
        with open(config_file_name) as config_handle:
                config = json.load(config_handle)

    return config if isinstance(config, dict) else {}


eventdb_conn = None
# Using a global object for the database connection
# must be initialised once


def open_db_connection(dsn: str):
    """ Open the Connection to the EventDB

    Args:
        dsn: a Connection - String

    Returns: a Database Connection

    """
    global eventdb_conn

    eventdb_conn = psycopg2.connect(dsn=dsn)
    return eventdb_conn


def __rollback_transaction():
    global eventdb_conn
    log.log(DD, "Calling rollback()")
    eventdb_conn.rollback()


QUERY_EVENT_SUBQUERY = {
    # TODO BEGINNING OF EVENTS-API COPY
    # queryname: ['sqlstatement', 'description', 'label', 'Expected-Type']
    'id': {
        'sql': 'events."id" = %s',
        'description': 'Query for an Event matching this ID.',
        'label': 'EventID',
        'exp_type': 'integer'
    },
    # Time
    'time-observation_before': {
        'sql': 'events."time.observation" < %s',
        'description': '',
        'label': 'Observation Time before',
        'exp_type': 'datetime'
    },
    'time-observation_after': {
        'sql': 'events."time.observation" > %s',
        'description': '',
        'label': 'Observation Time after',
        'exp_type': 'datetime'
    },
    'time-source_before': {
        'sql': 'events."time.source" < %s',
        'description': '',
        'label': 'Source Time before',
        'exp_type': 'datetime'
    },
    'time-source_after': {
        'sql': 'events."time.source" > %s',
        'description': '',
        'label': 'Source Time after',
        'exp_type': 'datetime'
    },
    # Source
    'source-ip_in_sn': {
        'sql': 'events."source.ip" <<= %s',
        'description': '',
        'label': 'Source IP-Network',
        'exp_type': 'cidr'
    },
    'source-ip_is': {
        'sql': 'events."source.ip" = %s',
        'description': '',
        'label': 'Source IP-Address',
        'exp_type': 'ip'
    },
    'source-asn_is': {
        'sql': 'events."source.asn" = %s',
        'description': '',
        'label': 'Source ASN',
        'exp_type': 'integer'
    },
    'source-fqdn_is': {
        'sql': 'events."source.fqdn" ILIKE %s',
        'description': '',
        'label': 'Source FQDN',
        'exp_type': 'string'
    },
    'source-fqdn_icontains': {
        'sql': 'events."source.fqdn" ILIKE concat(\'%%\', %s, \'%%\')',
        'description': '',
        'label': 'Source FQDN contains',
        'exp_type': 'string'
    },

    # Destinations
    'destination-ip_in_sn': {
        'sql': 'events."destination.ip" <<= %s',
        'description': '',
        'label': 'Destination IP-Network',
        'exp_type': 'cidr'
    },
    'destination-ip_is': {
        'sql': 'events."destination.ip" = %s',
        'description': '',
        'label': 'Destination IP-Address',
        'exp_type': 'ip'
    },
    'destination-asn_is': {
        'sql': 'events."destination.asn" = %s',
        'description': '',
        'label': 'Destination ASN',
        'exp_type': 'integer'
    },
    'destination-fqdn_is': {
        'sql': 'events."destination.fqdn" ILIKE %s',
        'description': '',
        'label': 'Destination FQDN',
        'exp_type': 'string'
    },
    'destination-fqdn_icontains': {
        'sql': 'events."destination.fqdn" ILIKE concat(\'%%\', %s, \'%%\')',
        'description': '',
        'label': 'Destination FQDN contains',
        'exp_type': 'string'
    },

    # Classification
    'classification-taxonomy_is': {
        'sql': 'events."classification.taxonomy" ILIKE %s',
        'description': '',
        'label': 'Classification Taxonomy',
        'exp_type': 'string'
    },
    'classification-taxonomy_icontains': {
        'sql': 'events."classification.taxonomy" '
               'ILIKE concat(\'%%\', %s, \'%%\')',
        'description': '',
        'label': 'Classification Taxonomy contains',
        'exp_type': 'string'
    },
    'classification-type_is': {
        'sql': 'events."classification.type" ILIKE %s',
        'description': '',
        'label': 'Classification Type',
        'exp_type': 'string'
    },
    'classification-type_icontains': {
        'sql': 'events."classification.type" ILIKE concat(\'%%\', %s, \'%%\')',
        'description': '',
        'label': 'Classification Type contains',
        'exp_type': 'string'
    },
    'classification-identifier_is': {
        'sql': 'events."classification.identifier" ILIKE %s',
        'description': '',
        'label': 'Classification Identifier',
        'exp_type': 'string'
    },
    'classification-identifier_icontains': {
        'sql': 'events."classification.identifier" '
               'ILIKE concat(\'%%\', %s, \'%%\')',
        'description': '',
        'label': 'Classification Identifier contains',
        'exp_type': 'string'
    },
    'malware-name_is': {
        'sql': 'events."malware.name" ILIKE %s',
        'description': '',
        'label': 'Malware Name',
        'exp_type': 'string'
    },
    'malware-name_icontains': {
        'sql': 'events."malware.name" ILIKE concat(\'%%\', %s, \'%%\')',
        'description': '',
        'label': 'Malware Name contains',
        'exp_type': 'string'
    },

    # Feed
    'feed-provider_is': {
        'sql': 'events."feed.provider" ILIKE %s',
        'description': '',
        'label': 'Feed Provider',
        'exp_type': 'string'
    },
    'feed-provider_icontains': {
        'sql': 'events."feed.provider" ILIKE concat(\'%%\', %s, \'%%\')',
        'description': '',
        'label': 'Feed Provider contains',
        'exp_type': 'string'
    },
    'feed-name_is': {
        'sql': 'events."feed.name" ILIKE %s',
        'description': '',
        'label': 'Feed Name',
        'exp_type': 'string'
    },
    'feed-name_icontains': {
        'sql': 'events."feed.name" ILIKE concat(\'%%\', %s, \'%%\')',
        'description': '',
        'label': 'Feed Name contains',
        'exp_type': 'string'
    },

    # queries that need the intelmq-cb-mailgen extra tables

    # Ticket-Related-Stuff
    'ticketnumber': {
        'sql': 'sent."intelmq_ticket" = %s',
        'description': '',
        'label': 'Ticketnumber',
        'exp_type': 'string'
    },
    'sent-at_before': {
        'sql': 'sent."sent_at" < %s',
        'description': '',
        'label': 'Sent before',
        'exp_type': 'datetime'
    },
    'sent-at_after': {
        'sql': 'sent."sent_at" > %s',
        'description': '',
        'label': 'Sent after',
        'exp_type': 'datetime'
    },

    # Directive-Related-Stuff
    'recipient_group': {
        'sql': 'json_object('
               '  directives."aggregate_identifier")->> \'recipient_group\' '
               'ILIKE %s',
        'description': 'Value for recipient_group tag'
                       'as set by the rule expert.',
        'label': 'Recipient Group',
        'exp_type': 'string',
    },
    'recipient_group_icontains': {
        'sql': 'json_object('
               '  directives."aggregate_identifier")->> \'recipient_group\' '
               'ILIKE concat(\'%%\', %s, \'%%\')',
        'description': 'Value for recipient_group tag'
                       'as set by the rule expert - substring match.',
        'label': 'Recipient Group contains',
        'exp_type': 'string',
    },
    'recipient-address_is': {
        'sql': 'directives."recipient_address" ILIKE %s',
        'description': '',
        'label': 'Recipient Email Address',
        'exp_type': 'email'
    },
    'recipient-address_icontains': {
        'sql':
            'directives."recipient_address" ILIKE concat(\'%%\', %s, \'%%\')',
        'description': '',
        'label': 'Recipient Email Address contains',
        'exp_type': 'string'
    },
}


# TODO DUPLICATE OF EVENTS-API
def query_get_subquery(q: str):
    """Return the query-Statement from the QUERY_EVENT_SUBQUERY

    Basically this is a getter for the dict...

    Args:
        q: A Key which can be found in QUERY_EVENT_SUBQUERY

    Returns: The subquery from QUERY_EVENT_SUBQUERY

    """
    r = QUERY_EVENT_SUBQUERY.get(q, '')
    s = None
    if r:
        s = r.get('sql', '')
    if s:
        return s
    else:
        raise ValueError('The query parameter you asked for is not supported.')


# TODO DUPLICATE OF EVENTS-API
def query_build_subquery(q: str, p: str):
    """Resolve Query-Operator and the Parameter into tuple of SQL and parameter.

    Args:
        q: the column which should match the search value
        p: the search value

    Returns: a tuple containing Query an Search Value

    """
    t = (query_get_subquery(q), p)
    return t


# TODO DUPLICATE OF EVENTS-API
def query_build_query(params):
    """

    Args:
        params:

    Returns: An Array of tuples

    """
    queries = []
    for key in params:
        queries.append(query_build_subquery(key, params[key]))
    return queries


def query_prepare_export(q):
    """Prepares a Query-string in order to export everything from the DB.

    Args:
        q: An array of Tuples created with query_build_query

    Returns: A Tuple consisting of a query string and an array of parameters.

    """
    q_string = "SELECT " \
               "       events.*, " \
               "       row_to_json(directives.*) AS mailgen_directives, " \
               "       row_to_json(sent.*) AS mailgen_sent " \
               "   FROM events" \
               " JOIN directives on directives.events_id = events.id " \
               " JOIN sent on sent.id = directives.sent_id "
    params = []
    # now iterate over q (which had to be created with query_build_query
    # previously) and should be a list of tuples
    # an concatenate the resulting query.
    # and a list of query parameters
    counter = 0
    for subquerytuple in q:
        if counter > 0:
            q_string = q_string + " AND " + subquerytuple[0]
            params.append(subquerytuple[1])
        else:
            q_string = q_string + " WHERE " + subquerytuple[0]
            params.append(subquerytuple[1])
        counter += 1
    return q_string, params


def query_prepare_search(q):
    """ Prepares a Query-string in order to Export Everything from the DB

    Args:
        q: An array of Tuples created with query_build_query

    Returns: A tuple consisting of a query string and an array of parameters.

    TODO: make more dynamic, equal to events' `/search` endpoint.

    """
    q_string = "SELECT events.id , " \
               " \"time.observation\", " \
               " \"time.source\", " \
               " \"source.ip\", " \
               " \"destination.ip\", " \
               " \"classification.taxonomy\", " \
               " \"classification.type\", " \
               " \"classification.identifier\", " \
               " \"malware.name\", " \
               " \"feed.provider\", "\
               " \"feed.name\", " \
               " sent_at, recipient_address, intelmq_ticket " \
               " FROM events " \
               " JOIN directives on directives.events_id = events.id " \
               " JOIN sent on sent.id = directives.sent_id "

    params = []
    # now iterate over q (which had to be created with query_build_query
    # previously) and should be a list of tuples
    # an concatenate the resulting query.
    # and a list of query parameters
    counter = 0
    for subquerytuple in q:
        if counter > 0:
            q_string = q_string + " AND " + subquerytuple[0]
            params.append(subquerytuple[1])
        else:
            q_string = q_string + " WHERE " + subquerytuple[0]
            params.append(subquerytuple[1])
        counter += 1
    return q_string, params


def query_prepare_stats(q, interval='day'):
    """ Prepares a Query-string for statistics

    Args:
        q: An array of Tuples created with query_build_query
        interval: 'month, 'day' or 'hour'

    Returns: A Tuple consisting of a query string and an array of parameters.

    """

    if interval not in ('month', 'week', 'day', 'hour'):
        raise ValueError

    trunc = "date_trunc('%s', \"sent_at\")" % (interval,)

    q_string = "SELECT %s, count(distinct(intelmq_ticket)) " \
               " FROM events " \
               " JOIN directives on directives.events_id = events.id " \
               " JOIN sent on sent.id = directives.sent_id " % (trunc, )

    # SELECT date_trunc('day', sent_at),
    #   count(intelmq_ticket) FROM sent GROUP BY date_trunc('day', sent_at);
    # Would be much faster, but do not just want to count the tickets, but also
    # might need to filter for certain attributes....

    params = []
    # now iterate over q (which had to be created with query_build_query
    # previously) and should be a list of tuples
    # an concatenate the resulting query.
    # and a list of query parameters
    counter = 0
    for subquerytuple in q:
        if counter > 0:
            q_string = q_string + " AND " + subquerytuple[0]
            params.append(subquerytuple[1])
        else:
            q_string = q_string + " WHERE " + subquerytuple[0]
            params.append(subquerytuple[1])
        counter += 1
    q_string = q_string + " GROUP BY %s" % (trunc, )
    return q_string, params


# TODO DUPLICATE OF EVENTS-API
def query(prepared_query):
    """ Queries the Database for Events

    Args:
        prepared_query: A QueryString, Parameter pair created
                        with query_prepare

    Returns: The results of the databasequery in JSON-Format.

    """
    global eventdb_conn

    # psycopgy2.4 does not offer 'with' for cursor()
    # FUTURE use with
    cur = eventdb_conn.cursor(cursor_factory=RealDictCursor)

    operation = prepared_query[0]
    parameters = prepared_query[1]
    log.info(cur.mogrify(operation, parameters))
    try:
        cur.execute(operation, parameters)
    except psycopg2.InterfaceError as err:
        if 'connection already closed' in str(err):
            log.error(repr(err))
            log.exception('Database Connection terminated unexectedly. Restoring the connection now.')
            eventdb_conn = open_db_connection(read_configuration()["libpg conninfo"])
            cur = eventdb_conn.cursor(cursor_factory=RealDictCursor)
        else:
            raise
    log.log(DD, "Ran query={}".format(repr(cur.query.decode('utf-8'))))
    # description = cur.description
    results = cur.fetchall()

    return results


@hug.startup()
def setup(api):
    config = read_configuration()
    if "logging_level" in config:
        log.setLevel(config["logging_level"])
    open_db_connection(config["libpg conninfo"])
    log.debug("Initialised DB connection for tickets_api.")

    # Copy of section in events_api/events_api/serve.py.
    # Change there there and update it here.
    global DB_TIMEZONE
    DB_TIMEZONE = _db_get_timezone()
    log.debug("Database says it operates in timezone =`" + DB_TIMEZONE + "`.")
    if DB_TIMEZONE == "localtime":
        # this means a postgresql db initialized before 9.5.19 [1] or a system
        # where initdb could not easily determine the system's full timezone.
        # But if postgres could not, we also shouldn't try.
        # [1] since https://www.postgresql.org/docs/9.5/release-9-5-19.html
        # initdb tries to determine the timezone (search for `TimeZone`).
        log.error("Could not determine database's timezone. Exiting.")
        sys.exit("""
Please set timezone of the database to a full timezone name explicitly.
Usually this is done in `postgresql.conf`. See PostgreSQL's docs.
On GNU/Linux systems you can try to replace the timezone= value with that of
    `timedatectl show --property=Timezone`
or use the last two elements of where `/etc/localtime` links to.
""")


def _db_get_timezone():
    """Query the database for its timezone setting."""
    # Copy of function in events_api/events_api/serve.py.
    # Change there there and update it here.
    global eventdb_conn

    # psycopgy2.4 does not offer 'with' for cursor()
    # FUTURE: use with
    cur = eventdb_conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SHOW timezone")
    return cur.fetchone()['TimeZone']


@hug.get(ENDPOINT_PREFIX, examples="ticketnumber=20191018-10000289", requires=session.token_authentication)
def getTicket(response,
              ticketnumber: hug.types.length(17, 18)):
    """Return events and directives associated with a ticketnumber.

    Args:
        response: A HUG response object...
        ticketnumber: the ticket number

    Returns: If existing one event of the EventDB

    """
    param = {}
    param["ticketnumber"] = ticketnumber
    querylist = query_build_query(param)
    prep = query_prepare_export(querylist)
    result = query(prep)

    # Hug v2.2.0 cannot serialize datetime.timedelta objects.
    # Therefore we need to do it on our own... until we have v2.3.0
    # See: https://github.com/timothycrosley/hug/issues/468
    for elem in result:
        if not elem.get("notification_interval") is None:
            td = elem.get("notification_interval")
            if (isinstance(td, datetime.timedelta)):
                elem["notification_interval"] = td.total_seconds()

    try:
        return result
    except psycopg2.Error as e:
        log.error(e)
        __rollback_transaction()
        response.status = HTTP_INTERNAL_SERVER_ERROR
        return {"error": "The query could not be processed."}


@hug.get(ENDPOINT_PREFIX + '/subqueries', requires=session.token_authentication)
def showSubqueries():
    """Return what's necessary to do queries, e.g subqueries and db timezone."""
    subquery_copy = copy.deepcopy(QUERY_EVENT_SUBQUERY)

    # Remove the SQL Statement from the SQ Object.
    for k, v in subquery_copy.items():
        if 'sql' in v:
            del(v['sql'])

    return {"subqueries": subquery_copy, "timezone": DB_TIMEZONE}


@hug.get(ENDPOINT_PREFIX + '/search',
         examples="sent-at_after=2017-03-01&sent-at_before=2017-03-01", requires=session.token_authentication)
def search(response, **params):
    """Search for events and tickets.

    Args:
        response: A HUG response object...
        **params: Queries from QUERY_EVENT_SUBQUERY

    Returns: A subset of the most likely most important fields
             of the events and their tickets which are matching the query.
    """
    for param in params:
        # Test if the parameters are sane....
        try:
            query_get_subquery(param)
        except ValueError:
            response.status = HTTP_BAD_REQUEST
            return {"error": "At least one of the queryparameters" +
                    " is not allowed: %s" % (param, )}

    if not params:
        response.status = HTTP_BAD_REQUEST
        return {"error": "Queries without parameters are not supported"}

    querylist = query_build_query(params)

    prep = query_prepare_search(querylist)

    try:
        return query(prep)
    except psycopg2.Error as e:
        log.error(e)
        __rollback_transaction()
        response.status = HTTP_INTERNAL_SERVER_ERROR
        return {"error": "The query could not be processed."}


@hug.get(ENDPOINT_PREFIX + '/stats',
         examples="malware-name_is=nymaim&" +
         "recipient-address_icontains=%telekom%&timeres=day", requires=session.token_authentication)
def stats(response, **params):
    """Return a statistic of all tickets matching the query parameters.

    Args:
        response: A HUG response object...
        **params: Queries from QUERY_EVENT_SUBQUERY

    Returns: If existing a statistical view on the amount of tickets
             per time-frame
    """
    now = datetime.datetime.now()

    DAY = datetime.timedelta(1, 0)
    WEEK = datetime.timedelta(7, 0)
    MONTH = datetime.timedelta(30, 0)

    # The Timebox of the resulting query. For which timeframe should an
    # evaluation take place? Based upon this timeframe a good timeresolution
    # will be suggested and used, if no other resolution was provided...

    # for the default: make sure the previous 24h are included
    # postgresl will interpret timestamps as being in the db wide TimeZone
    time_after = params.get(
        "sent-at_after",
        datetime.datetime(
            year=now.year, month=now.month, day=now.day
        ) - datetime.timedelta(days=1))

    # for the default: it is okay to go more in the future
    time_before = params.get(
        "sent-at_before", now + datetime.timedelta(days=1))

    if type(time_after) == list or type(time_before) == list:
        response.status = HTTP_BAD_REQUEST
        return {"reason":
                "Either time_after or time_before given more than once."}

    # Convert to datetime....
    if type(time_after) == str:
        time_after = dateutil.parser.parse(time_after)
    if type(time_before) == str:
        time_before = dateutil.parser.parse(time_before)

    suggested_timeres = 'day'

    if time_after and time_before:
        # Test end before start and correct that.
        if time_after > time_before:
            time_temp = time_after
            time_after = time_before
            time_before = time_temp
            time_temp = None

        delta_t = time_before - time_after
        # suggest a most likely sane timeframe:
        if delta_t > MONTH:
            suggested_timeres = 'month'

        elif delta_t <= MONTH and delta_t > WEEK:
            suggested_timeres = 'week'

        elif delta_t <= WEEK and delta_t > DAY:
            suggested_timeres = 'day'

        else:
            suggested_timeres = 'hour'

        params["sent-at_after"] = time_after
        params["sent-at_before"] = time_before

    else:
        response.status = HTTP_INTERNAL_SERVER_ERROR
        return {"error": "The query could not be processed."}

    # Read the Timeres parameter or use suggestion
    timeres = params.get("timeres", suggested_timeres)

    # Remove timeres from the params dict
    if params.get("timeres"):
        # skip the test for this parameter and remove it from params!
        del params["timeres"]

    # Check if this is a sane value. day, month, hour...
    if timeres not in ('month', 'week', 'day', 'hour'):
        # Default: suggested_timeres is a sane thing.
        timeres = suggested_timeres

    # remove other time-params which will be in conflict with this query
    if params.get("sent-at_after_encl"):
        del params["sent-at_after_encl"]
    if params.get("sent-at_before_encl"):
        del params["sent-at_before_encl"]

    for param in params:
        # Test if the parameters are sane....
        try:
            query_get_subquery(param)
        except ValueError:
            response.status = HTTP_BAD_REQUEST
            return {
                "error":
                "At least one of the queryparameters is not allowed: %s" %
                    (param, )
            }

    if not params:
        response.status = HTTP_BAD_REQUEST
        return {"error": "Queries without parameters are not supported"}

    querylist = query_build_query(params)

    prep = query_prepare_stats(querylist, timeres)

    try:
        results = query(prep)
        totalcount = 0
        for v in results:
            totalcount += v.get('count', 0)

    except psycopg2.Error as e:
        log.error(e)
        __rollback_transaction()
        response.status = HTTP_INTERNAL_SERVER_ERROR
        return {"error": "The query could not be processed."}

    except AttributeError as e:
        log.error(e)
        __rollback_transaction()
        response.status = HTTP_INTERNAL_SERVER_ERROR
        return {"error": "Something went wrong."}

    return {'timeres': timeres, 'total': totalcount, 'results': results}


@hug.get(ENDPOINT_PREFIX + '/getRecipient', requires=session.token_authentication)
def getDirective(response, ticketnumber: hug.types.length(17, 18)):

    result = None

    prep = ("SELECT * "
            " FROM directives"
            " JOIN sent ON sent_id = sent.id "
            " WHERE sent.intelmq_ticket = %s;", (ticketnumber,))

    try:
        result = query(prep)
    except psycopg2.Error as e:
        log.error(e)
        __rollback_transaction()
        response.status = HTTP_INTERNAL_SERVER_ERROR
        return {"error": "The query could not be processed."}

    # Hug v2.2.0 cannot serialize datetime.timedelta objects.
    # Therefore we need to do it on our own... until we have v2.3.0
    # See: https://github.com/timothycrosley/hug/issues/468
    for elem in result:
        if not elem.get("notification_interval") is None:
            td = elem.get("notification_interval")
            if isinstance(td, datetime.timedelta):
                elem["notification_interval"] = td.total_seconds()

    return result


def main():
    """ Main function of this module

    Returns: Nothing....

    """
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

    global eventdb_conn
    eventdb_conn = open_db_connection(config["libpg conninfo"])

    # TODO: Maybe add a search interface for the CLI
    # params={'t.o_after': '2017-03-01', 's.ip_in_sn': '31.25.41.74'}
    # prep = query_prepare(query_build_query(params))
    # return query(prep)
