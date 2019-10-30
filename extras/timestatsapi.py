"""Measure the duration of HTTP requests repeatedly.

This program calls a given URL in intervals, logging how long the
request took. The code assumes that you need to authenticate with
username and password. The username can be given as a command line
argument and the password will be prompted for interactively.
"""

import sys
import time
import argparse
import logging
import logging.config
import getpass

import requests


def configure_logging(logfilename, log_level):
    if logfilename is not None:
        handler = {"class": "logging.FileHandler",
                   "formatter": "generic",
                   "filename": logfilename}
    else:
        handler = {"class": "logging.StreamHandler",
                   "formatter": "generic",
                   "stream": sys.stderr}

    logging.config.dictConfig(
        dict(version=1,
             formatters=dict(generic=dict(format=("%(asctime)s"
                                                  " %(levelname)-5.5s"
                                                  " [%(name)s] %(message)s"))),
             handlers=dict(root_handler=handler),
             root=dict(handlers=["root_handler"],
                       level=log_level)))


def time_stats_api_call(url, user, password):
    start_time = time.monotonic()
    log.debug("Sending request at %f", start_time)
    result = requests.get(url, auth=(user, password))
    # Useful for debugging:
    # print(repr(result.content))
    end_time = time.monotonic()
    log.debug("Finished request at %f", end_time)
    return (result.status_code, end_time - start_time)


def gather_stats_api_times(url, user, password, sleep_duration):
    log.info("Every %ds GET %r", sleep_duration, url)
    while True:
        try:
            status, duration = time_stats_api_call(url, user, password)
            log.info("Response: %r, Duration: %f", status, duration)
        except Exception:
            log.exception("Exception while timing API call")
        time.sleep(sleep_duration)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="intevation")
    parser.add_argument("--url",
                        default=("http://localhost:8000/api/events/stats"
                                 "?time-observation_after=2017-04-01 00:00"
                                 "&time-observation_before=2017-05-01 00:00"
                                 "&timeres=hour"))
    parser.add_argument("--sleep", type=int,
                        help="How long to sleep after an attempt (in seconds)")
    parser.add_argument("--log-file")
    parser.add_argument("--log-level", default="INFO")

    args = parser.parse_args()

    configure_logging(args.log_file, args.log_level)

    global log
    log = logging.getLogger("timestatsapi")

    password = getpass.getpass("password for user %s: " % args.user)

    gather_stats_api_times(args.url, args.user, password, args.sleep)


main()
