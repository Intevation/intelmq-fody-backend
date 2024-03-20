"""Session support for intelmq-fody-backend.

Requires hug (http://www.hug.rest/)

Copyright (C) 2017, 2018, 2019, 2021 by
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
    * Raimund Renkert <raimund.renkert@intevation.de>


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
import os
import sys
import threading
import hashlib
from typing import List, Tuple, Union, Optional
from contextlib import contextmanager

from falcon import HTTP_BAD_REQUEST, HTTP_NOT_FOUND
import hug
import sqlite3

import session.config
import session.files as files

INIT_DB_SQL = """
BEGIN;
CREATE TABLE version (version INTEGER);
INSERT INTO version (version) VALUES (1);
CREATE TABLE session (
    session_id TEXT PRIMARY KEY,
    modified TIMESTAMP,
    data BLOB
);
CREATE TABLE user(
    username TEXT PRIMARY KEY,
    password TEXT,
    salt TEXT
);
COMMIT;
"""

LOOKUP_SESSION_SQL = """
SELECT data FROM session WHERE session_id = ?;
"""

STORE_SESSION_SQL = """
INSERT OR REPLACE INTO session (session_id, modified, data)
VALUES (?, CURRENT_TIMESTAMP, ?);
"""

EXPIRATION_SQL = """
DELETE FROM session
 WHERE strftime('%s', 'now') - strftime('%s', modified) > ?;
"""

TOUCH_SESSION_SQL = """
UPDATE session SET modified = CURRENT_TIMESTAMP WHERE session_id = ?;
"""

ADD_USER_SQL = """
INSERT OR REPLACE INTO user (username, password, salt) VALUES (?, ?, ?);
"""

LOOKUP_USER_SQL = """
SELECT username, password, salt FROM user WHERE username = ?;
"""

config = session.config.Config

file_access = files.FileAccess

session_store = None

def verify_token(token):
    if session_store is not None:
        return session_store.verify_token(token)
    else:
        return None

hug_token_authentication = hug.authentication.token(verify_token)

def token_authentication(*args, **kw):
    if session_store is not None:
        return hug_token_authentication(*args, **kw)
    else:
        return True

def initialize_sessions(c: session.config.Config):
    global config, file_access, session_store
    config = c
    file_access = files.FileAccess(config)

    session_file = config.session_store
    if session_file is not None:
        session_store = session.session.SessionStore(str(session_file),
                                             config.session_duration)

class SessionStore:
    """Session store based on SQLite
    The SQLite database is used in autocommit mode avoid blocking
    connections to the same database from other processes. This ensures
    that no transactions are open for very long. The transactions this
    class needs to do are all single statements anyway, so autocommit is
    no problem.
    Instances of this class can be used by multiple threads
    simultaneously. Use of the underlying sqlite connection object is
    serialized between threads with a lock.
    """

    def __init__(self, dbname: str, max_duration: int):
        self.dbname = dbname
        self.max_duration = max_duration
        if not os.path.isfile(self.dbname):
            self.init_sqlite_db()
        self.lock = threading.Lock()
        self.connection = self.connect()

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.dbname, check_same_thread=False,
                               isolation_level=None)

    @contextmanager
    def get_con(self):
        with self.lock:
            yield self.connection

    def init_sqlite_db(self):
        with self.connect() as con:
            con.executescript(INIT_DB_SQL)

    def execute(self, stmt: str, params: tuple) -> Optional[tuple]:
        try:
            with self.get_con() as con:
                return con.execute(stmt, params).fetchone()
        except sqlite3.OperationalError as exc:
            print(f"SQLite3-Error ({exc}): Possibly missing write permissions to session file (or the folder it is located in).")
            return None


    #
    # Methods for session data
    #

    def expire_sessions(self):
        self.execute(EXPIRATION_SQL, (self.max_duration,))

    def get(self, session_id: str) -> Optional[dict]:
        self.expire_sessions()
        row = self.execute(LOOKUP_SESSION_SQL, (session_id,))
        if row is not None:
            return json.loads(row[0])
        return None

    def set(self, session_id: str, session_data: dict):
        self.execute(STORE_SESSION_SQL,
                     (session_id, json.dumps(session_data)))

    def new_session(self, session_data: dict) -> str:
        token = os.urandom(16).hex()
        self.set(token, session_data)
        return token

    def verify_token(self, token: str) -> Union[bool, dict]:
        session_data = self.get(token)
        if session_data is not None:
            self.execute(TOUCH_SESSION_SQL, (token,))
            return session_data
        return False

    #
    # User account methods
    #

    def add_user(self, username: str, password: str):
        hashed, salt = self.hash_password(password)
        self.execute(ADD_USER_SQL, (username, hashed, salt))

    def verify_user(self, username: str, password: str) -> Optional[dict]:
        row = self.execute(LOOKUP_USER_SQL, (username,))
        if row is not None:
            username, stored_hash, salt = row
            hashed = self.hash_password(password, bytes.fromhex(salt))[0]
            if hashed == stored_hash:
                return {"username": username}
        return None

    def hash_password(self, password: str,
                      salt: Optional[bytes] = None) -> Tuple[str, str]:
        if salt is None:
            salt = os.urandom(16)
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf8"), salt,
                                     100000)
        return (hashed.hex(), salt.hex())