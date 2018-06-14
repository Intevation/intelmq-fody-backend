## 0.6.1 to 0.6.2
 * Contactdb:
   * Adds GET and PUT endpoints for ./email/ and an additional endpointCGET
    /searchdisabledcontactto to support the seperate email_status table.

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
   * Adds sorting to some attribute list when serving an org. Attributes
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
