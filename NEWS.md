## 0.7.1 to 0.7.2

 * Events: Fix endpoints that use queries with mailgen tables to also
   include events that have not been sent yet.


## 0.7.0 to 0.7.1

 * Events: Fix `./stats?` to count events only once in case of
   `intelmq-cb-mailgen` setups. Note that several entries can be returned
   with the corresponding `./search?` call. See usage hint for the reason.


## 0.6.4 to 0.7.0

 * Tickets:
   * Change default parameters for `./stats?` to include the full last day
     (based on what is the timezone of the database.)
   * Cleanup code: Remove unused and broken `?id=` ability, change
     `/?ticketnumber=` ability to return mailgen tables like `events/search`.

 * Events:
   * Change `./search?` to return the columns from `mailgen_directives` and
     `mailgen_sent` tables as JSON values for easier handling in clients.
   * Remove `./export?`, as too similar to `./search?` and assumed unused.
   * Fix subquery for "EventID" (broken since 0.6.4).
   * Fix support for hug v==2.2.0 in three endpoints.


## 0.6.3.1 to 0.6.4

 * Events:
   * Enhance endpoints `./search?`, `./export?` to allow searching by
     columns from joined `directives` and `sent` tables for symmetry with the
     tickets backend. Add example for searching for `recipient_group` in
     `aggregate_identifier`.

 * Contactdb:
   * Enhance endpoint `./annotation/search?tag=` to additionally search for
     email tags and return organisations with those email addresses.

### Upgrade
 * Optional: Add an index for "`recipient_group` to directives (2019-10)", see
   https://github.com/Intevation/intelmq-mailgen/blob/master/sql/updates.txt


## 0.6.3 to 0.6.3.1

 * Contactdb:
   * Fix handling of email tags, by returing the correct default tags.


## 0.6.2 to 0.6.3

 * Contactdb:
  * Disallows creating CIDRs or FQDNs with the same value in a single contact;
    only the first will be inserted. If this happens it shows in loglevel INFO.
 * Events:
   * Additional configuration parameter `database table` to set the
     table name of the events table. Default is `events`.
 * Contacts: Add handling of email tags.

### Upgrade
 *  Requirements: intelmq-certbund-contact>=0.9.4 on the db server.


## 0.6.1 to 0.6.2
 * Contactdb:
   * Adds GET and PUT endpoints for ./email/ and an additional endpoint GET
    /searchdisabledcontact to support the separate email_status table.

### Upgrade
 * Requirements: Check that we have postgresql v>=9.5.


## 0.6.0 to 0.6.1

 * Checkticket:
   * Adds optional `limit` parameter to endpoint `./getEventsForTicket`.
   * Changes `getEventIDsForTicket` to returned a sorted list, to make
     the query result consistent for the same parameter.


## 0.5.3 to 0.6.0

 * Contactdb:
   * Fixes search by email address so it filters out duplicates.
   * Adds `tools/import_manual_contacts.py` to import manual contacts
     from a .csv file via TLS.
   * Adds sorting to some attribute lists when serving an org. Attributes
     sorted are contacts, asns, networks, fqdns, national_certs and tags.


## 0.5.2 to 0.5.3

 * Events: Changes /search endpoint to return complete events (similiar to
     checkticket's /getEvents)
 * Events: Enhances subqueries:
   * New subqueries can be added in the config file, see example configuration.
   * The given parameter can be used multiple times in an SQL query,
     for example: `("source.ip" = '%s' OR "destination.ip" = '%s')`

### Upgrade
 * Configuration: (optional) Add the example subquery `all_ips` to the
     eventsdb config file to get one more useful query.


## 0.5.1 to 0.5.2

 * Contactdb: Fixes annotation/search for organisation\_annotations.


## 0.5.0 to 0.5.1

 * Contactdb: Adds search for annotations by tag-name.
 * Contactdb: Allows to configure the list of common "tags".
 * Contactdb: Changes email search to be case-insensitive.

### Upgrade
 * Configuration: (optional) Add "common\_tags" to the contactdb config file,
     otherwise the default ones may be exposed to users by the frontend.


## 0.4.3.dev0 to 0.5.0
 * Contactdb: Allows tracking of db changes by user.
 * Contactdb: Adds example script for importing a manual whitelist.
 * Technical: Module called "intelmq-fody-backend" now
 * Technical: Compatible with psycopg2 coming with Ubuntu 16.04LTS now.

### Upgrade
 * To enable tracking of db changes by user follow instructions in README.md.
 * Technical: Must make sure that calling code uses the new module name.
