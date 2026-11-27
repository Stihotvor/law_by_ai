# QA cases: procedure-kb

Specs under `specs/` could not be listed (tool limits). Cases come from requirements, decision and tasks.

### QA-001 Empty source_url is rejected
- Covers: Edge Cases (empty source_url)
- Type: failure
- Given an admin and YAML "pesel-test" with step "register-at-office" whose source_url is ""
- When the admin imports the YAML
- Then the import fails with an error that names the upload and step "register-at-office", and the procedures table still has 0 rows

### QA-002 Missing last_checked is rejected
- Covers: Edge Cases (missing last_checked)
- Type: failure
- Given an admin and YAML "tax-id-test" with step "apply-online" that has no last_checked
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online", and nothing is stored

### QA-003 Invalid date is rejected
- Covers: Edge Cases, tasks T1 (bad date)
- Type: failure
- Given an admin and YAML where step "apply-online" has last_checked "2026-13-45"
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online", and nothing is stored

### QA-004 Future date is rejected
- Covers: Edge Cases (date in the future)
- Type: failure
- Given today is 2026-11-27 and YAML where step "apply-online" has last_checked "2026-11-28"
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online", and nothing is stored

### QA-005 Today's date is accepted
- Covers: Edge Cases (date boundary)
- Type: edge
- Given today is 2026-11-27 and a YAML step with last_checked "2026-11-27", https source_url, and a verify line
- When the admin imports the YAML
- Then the import succeeds as revision 1

### QA-006 Missing verify line is rejected
- Covers: Edge Cases (no verify line)
- Type: failure
- Given YAML where step "apply-online" has no verify-with-office line
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online", and nothing is stored

### QA-007 Blank verify line is rejected
- Covers: Edge Cases (no verify line)
- Type: failure
- Given YAML where step "apply-online" has a verify line of "   " (3 spaces)
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online", and nothing is stored

### QA-008 Empty step text is rejected
- Covers: Technical Constraints (step fields)
- Type: failure
- Given YAML where step "apply-online" has text ""
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online", and nothing is stored

### QA-009 Zero steps is rejected
- Covers: Edge Cases (zero steps)
- Type: failure
- Given YAML for slug "empty-proc" with title "Empty" and "steps: []"
- When the admin imports the YAML
- Then the import fails with a validation error and nothing is stored

### QA-010 http source_url is rejected
- Covers: Edge Cases (scheme other than https)
- Type: failure
- Given YAML where step "apply-online" has source_url "http://example.gov.pl/pesel"
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online", and nothing is stored

### QA-011 ftp source_url is rejected
- Covers: Edge Cases (scheme other than https)
- Type: failure
- Given YAML where step "apply-online" has source_url "ftp://example.gov.pl/pesel"
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online"

### QA-012 URL with credentials is rejected
- Covers: Edge Cases (credentials in URL)
- Type: security
- Given YAML where step "apply-online" has source_url "https://user:secret@example.gov.pl/pesel"
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online", and the error text does not contain "secret"

### QA-013 Malformed YAML names the file
- Covers: Edge Cases (malformed YAML)
- Type: failure
- Given a seed file "broken.yaml" with content "slug: [unclosed"
- When the seed loads the file
- Then loading fails with an error that names "broken.yaml"

### QA-014 Unknown key is rejected
- Covers: Edge Cases (unknown key)
- Type: failure
- Given a seed file "extra.yaml" with a valid procedure plus the top-level key "priority: 1"
- When the seed loads the file
- Then loading fails with an error that names "extra.yaml"

### QA-015 Unknown key inside a step is rejected
- Covers: Edge Cases (unknown key)
- Type: failure
- Given YAML where step "apply-online" has the extra key "cost: 17 PLN"
- When the admin imports the YAML
- Then the import fails with an error that names step "apply-online"

### QA-016 Bad slug in YAML is rejected
- Covers: Technical Constraints (slug rule)
- Type: failure
- Given YAML with slug "PESEL_Test" (upper case and underscore)
- When the admin imports the YAML
- Then the import fails with a validation error and nothing is stored

### QA-017 Duplicate step key is rejected
- Covers: Technical Constraints (unique key)
- Type: failure
- Given YAML with two steps that both have key "apply-online"
- When the admin imports the YAML
- Then the import fails with a validation error and nothing is stored

### QA-018 Blank title is rejected
- Covers: Technical Constraints (title check)
- Type: failure
- Given YAML with slug "pesel-test" and title "  "
- When the admin imports the YAML
- Then the import fails with a validation error and nothing is stored

### QA-019 Step key not kebab-case is rejected
- Covers: Technical Constraints (key rule)
- Type: failure
- Given YAML where a step has key "Apply Online"
- When the admin imports the YAML
- Then the import fails with an error that names that step

### QA-020 Empty YAML text is rejected
- Covers: Edge Cases (bad input)
- Type: failure
- Given an admin and an empty text ""
- When the admin imports it
- Then the import fails with a validation error and nothing is stored

### QA-021 Failed import keeps old data
- Covers: Failure Modes (validate before write, one transaction)
- Type: failure
- Given procedure "pesel" stored at revision 2 with 4 steps
- When an admin imports YAML for "pesel" with 3 valid steps and a 4th step with an empty source_url
- Then the import fails, "pesel" is still revision 2 with its 4 old steps, and the revision rows for "pesel" number 2

### QA-022 Database failure mid-import rolls back
- Covers: Failure Modes (one transaction), tasks T4
- Type: failure
- Given procedure "pesel" at revision 1 with 3 steps and a database that fails while the new steps are inserted
- When an admin imports changed content for "pesel"
- Then the caller gets a store error with no content in its message, "pesel" is still revision 1 with 3 old steps, and no revision 2 row exists

### QA-023 First import is revision 1
- Covers: Success Metrics (one revision row per import)
- Type: functional
- Given an empty database and admin "admin@example.com"
- When the admin imports valid YAML for slug "pesel" with 3 steps
- Then the result shows slug "pesel", revision 1, changed true, and one revision row exists with actor "admin@example.com" and a creation time

### QA-024 Changed content adds revision 2 and replaces steps
- Covers: Edge Cases (existing slug), Success Metrics
- Type: functional
- Given "pesel" at revision 1 with 3 steps
- When an admin imports YAML for "pesel" with 4 steps and a new title "PESEL number"
- Then the result is revision 2 with changed true, get returns title "PESEL number" with exactly 4 steps, and 2 revision rows exist

### QA-025 Identical content adds no revision
- Covers: Edge Cases (identical content)
- Type: functional
- Given "pesel" at revision 1
- When an admin imports the exact same YAML again
- Then the result is revision 1 with changed false and only 1 revision row exists

### QA-026 Identical content by another admin adds no revision
- Covers: Edge Cases (actor does not count)
- Type: edge
- Given "pesel" at revision 1 imported by "a@example.com"
- When admin "b@example.com" imports the same content
- Then the result is changed false and no revision row for "b@example.com" exists

### QA-027 Identical content keeps updated_at
- Covers: Decision (import order step 2)
- Type: edge
- Given "pesel" at revision 1 with a known update time
- When an admin imports the same content
- Then the update time of "pesel" is unchanged

### QA-028 Whitespace-only YAML change does not add a revision
- Covers: Edge Cases (identical content)
- Type: edge
- Given "pesel" at revision 1
- When an admin imports the same data with different key order and added comments
- Then the result is changed false

### QA-029 Change of one date adds a revision
- Covers: Edge Cases (identical content)
- Type: edge
- Given "pesel" at revision 1 with step "apply-online" last_checked 2026-10-01
- When an admin imports the same content with last_checked 2026-11-01 for that step
- Then the result is revision 2 with changed true

### QA-030 Non-admin import is refused
- Covers: Edge Cases (non-admin)
- Type: security
- Given a caller with role user, email "user@example.com", and valid YAML for "pesel"
- When the caller imports the YAML
- Then a principal-required error is raised and the procedures table has 0 rows

### QA-031 Caller with no principal is refused
- Covers: Edge Cases (non-admin)
- Type: security
- Given no signed-in principal and valid YAML
- When the caller imports the YAML
- Then a principal-required error is raised and no database session is opened

### QA-032 Non-admin with invalid YAML gets the refusal first
- Covers: Edge Cases (non-admin), Decision (admin check first)
- Type: security
- Given a user-role caller and YAML with an empty source_url
- When the caller imports the YAML
- Then a principal-required error is raised, not a validation error

### QA-033 Non-admin cannot add a revision to an existing procedure
- Covers: Edge Cases (non-admin)
- Type: security
- Given "pesel" at revision 1 and a user-role caller with changed YAML
- When the caller imports it
- Then a principal-required error is raised and "pesel" is still revision 1

### QA-034 Actor comes from the principal
- Covers: Decision (actor from principal)
- Type: functional
- Given admin "owner@example.com" signed in
- When the admin imports valid YAML
- Then the revision row has actor "owner@example.com"

### QA-035 App role cannot UPDATE a revision row
- Covers: Failure Modes (history survives), Success Metrics (privilege test)
- Type: security
- Given the migrated database, one revision row for "pesel", and a connection as lawbyai_app
- When the connection runs UPDATE on the actor of that revision row
- Then the database returns permission denied and the row is unchanged

### QA-036 App role cannot DELETE a revision row
- Covers: Failure Modes (history survives)
- Type: security
- Given the same database and connection as lawbyai_app
- When the connection runs DELETE on that revision row
- Then the database returns permission denied and the row still exists

### QA-037 App role cannot TRUNCATE the revision table
- Covers: Decision (TRUNCATE revoked)
- Type: security
- Given a connection as lawbyai_app
- When the connection runs TRUNCATE on the revision table
- Then the database returns permission denied

### QA-038 App role cannot DELETE a procedure
- Covers: Decision (grants), tasks T3
- Type: security
- Given a connection as lawbyai_app and procedure "pesel"
- When the connection runs DELETE on "pesel"
- Then the database returns permission denied and "pesel" still exists

### QA-039 App role can INSERT and SELECT revisions
- Covers: Decision (grants)
- Type: functional
- Given a connection as lawbyai_app
- When the connection inserts a revision row and reads it back
- Then both statements succeed

### QA-040 App role can replace steps
- Covers: Decision (grants)
- Type: functional
- Given a connection as lawbyai_app and procedure "pesel" with 3 steps
- When the connection deletes the steps and inserts 4 new steps
- Then both succeed and 4 steps exist

### QA-041 Deleting a procedure with revisions is restricted
- Covers: Decision (RESTRICT cascade)
- Type: failure
- Given a database owner connection, "pesel" with 1 revision row
- When the owner runs DELETE on "pesel"
- Then the database refuses with a foreign key error and the revision row still exists

### QA-042 Deleting a procedure without revisions cascades steps
- Covers: Decision (step FK cascade)
- Type: edge
- Given a database owner connection and a procedure with 3 steps and no revision row
- When the owner deletes the procedure
- Then the 3 steps are deleted

### QA-043 Revision row with empty actor is rejected
- Covers: Decision (actor non-empty)
- Type: failure
- Given the migrated database
- When a revision row is inserted with actor ""
- Then the database rejects it with a CHECK error

### QA-044 Revision content must be an object
- Covers: Decision (jsonb_typeof check)
- Type: failure
- Given the migrated database
- When a revision row is inserted with content `[1,2]`
- Then the database rejects it with a CHECK error

### QA-045 Duplicate revision number is rejected
- Covers: Decision (UNIQUE procedure_id, revision)
- Type: failure
- Given "pesel" with revision row 1
- When a second row with revision 1 is inserted for "pesel"
- Then the database rejects it with a unique error

### QA-046 Database rejects bad slug
- Covers: Decision (slug CHECK)
- Type: failure
- Given the migrated database
- When a procedure with slug "Bad_Slug" is inserted
- Then the database rejects it with a CHECK error

### QA-047 Database rejects revision 0
- Covers: Decision (revision >= 1)
- Type: failure
- Given the migrated database
- When a procedure with revision 0 is inserted
- Then the database rejects it with a CHECK error

### QA-048 Database rejects http step URL
- Covers: Decision (source_url LIKE https)
- Type: failure
- Given "pesel" and the migrated database
- When a step with source_url "http://example.gov.pl" is inserted
- Then the database rejects it with a CHECK error

### QA-049 Database rejects negative position and empty text
- Covers: Decision (step CHECKs)
- Type: failure
- Given "pesel" and the migrated database
- When a step with position -1 is inserted, and then a step with text "" is inserted
- Then the database rejects both with CHECK errors

### QA-050 Database rejects duplicate step key and position
- Covers: Decision (step unique rules)
- Type: failure
- Given "pesel" with a step at position 0 and key "apply-online"
- When a second step with position 0, and then one with key "apply-online" at position 1, are inserted
- Then the database rejects both with unique errors

### QA-051 Database rejects blank title and schema_version 0
- Covers: Decision (procedure CHECKs)
- Type: failure
- Given the migrated database
- When a procedure with title "  " is inserted, and then one with schema_version 0
- Then the database rejects both with CHECK errors

### QA-052 Migration upgrade and downgrade on empty history
- Covers: Decision (Data), tasks T3
- Type: functional
- Given a database at head c4a91e7f2b58
- When the migration is upgraded and then downgraded
- Then the 3 tables exist after upgrade and are gone after downgrade

### QA-053 Downgrade stops when history exists
- Covers: Decision (downgrade guard)
- Type: failure
- Given the migration applied and 1 revision row
- When the migration is downgraded
- Then the downgrade stops with an error and the revision row still exists

### QA-054 Upgrade is not blocked forever by a lock
- Covers: Decision (lock_timeout 5s)
- Type: failure
- Given another session holds a lock on a table the migration touches for 30 seconds
- When the migration is upgraded
- Then it fails after about 5 seconds with a lock timeout error

### QA-055 Concurrent imports of one new slug
- Covers: Edge Cases (same slug), Failure Modes, tasks T4
- Type: edge
- Given an empty database and two admins who import different content for slug "pesel" at the same moment
- When both imports run
- Then the stored revisions are 1 and 2 with no duplicates, "pesel" is revision 2, and its steps match the content of revision 2

### QA-056 Concurrent imports of one existing slug
- Covers: Edge Cases (same slug), tasks T4
- Type: edge
- Given "pesel" at revision 1 and two admins who import two different changes at the same moment
- When both imports run
- Then revisions 2 and 3 exist once each and no import fails

### QA-057 Concurrent imports of identical content
- Covers: Edge Cases (same slug, identical content)
- Type: edge
- Given an empty database and two admins who import the same YAML for "pesel" at the same moment
- When both imports run
- Then exactly 1 revision row exists, and one result is changed true and one is changed false

### QA-058 Reader sees no mixed state during import
- Covers: Decision (reads in one statement)
- Type: edge
- Given "pesel" at revision 1 with title "PESEL" and 3 steps, and an import that sets title "PESEL number" with 4 steps
- When get_procedure runs repeatedly 100 times while the import runs
- Then each result is either title "PESEL" with 3 steps or title "PESEL number" with 4 steps

### QA-059 Find existing procedure
- Covers: Business Goals (find by slug)
- Type: functional
- Given "pesel" stored at revision 1 with 3 steps
- When get_procedure("pesel") is called
- Then it returns slug "pesel", revision 1, and 3 steps in position order, each with source_url, last_checked, and verify line

### QA-060 Unknown slug returns not found
- Covers: Edge Cases (unknown slug)
- Type: failure
- Given 3 stored procedures
- When get_procedure("no-such-procedure") is called
- Then it returns None and raises no KeyError

### QA-061 Malformed slug returns not found
- Covers: Decision (malformed slug)
- Type: failure
- Given 3 stored procedures
- When get_procedure is called with "PESEL; DROP TABLE procedure"
- Then it returns None, and all 3 procedures still exist

### QA-062 Empty and oversized slug return not found
- Covers: Decision (malformed slug)
- Type: failure
- Given 3 stored procedures
- When get_procedure is called with "" and then with a slug of 10000 "a" characters
- Then both return None

### QA-063 Slug with trailing hyphen returns not found
- Covers: Decision (malformed slug)
- Type: edge
- Given 3 stored procedures
- When get_procedure("pesel-") is called
- Then it returns None

### QA-064 List is sorted by slug
- Covers: Decision (list sorted)
- Type: functional
- Given procedures imported in the order "tax-id", "pesel", "residence-card"
- When list_procedures is called
- Then it returns slugs in the order "pesel", "residence-card", "tax-id", each with a title

### QA-065 List on empty table
- Covers: Edge Cases (empty table)
- Type: edge
- Given an empty procedure table
- When list_procedures is called
- Then it returns an empty list

### QA-066 Read after caller session closed
- Covers: Decision (frozen objects)
- Type: edge
- Given "pesel" stored
- When the caller reads steps of the returned procedure after the call ends
- Then the steps are available with no database error

### QA-067 Returned procedure cannot be changed
- Covers: Decision (frozen models)
- Type: edge
- Given a procedure returned by get_procedure
- When the caller sets its title to "X"
- Then the assignment is refused

### QA-068 Stale date is shown unchanged
- Covers: Failure Modes (stale last_checked)
- Type: functional
- Given "pesel" with step "apply-online" last_checked 2020-01-01
- When get_procedure("pesel") is called in 2026
- Then the step shows last_checked 2020-01-01 with no hiding or change

### QA-069 Store error has no content
- Covers: Decision (error rules)
- Type: security
- Given a database that is down and YAML with title "Secret title"
- When an admin imports the YAML
- Then a store error is raised whose message does not contain "Secret title" and whose cause is chained

### QA-070 Step schema is pinned
- Covers: Failure Modes (schema change), Success Metrics
- Type: functional
- Given the current step model
- When its field names and the schema_version are listed
- Then they equal key, text, source_url, last_checked, verify_with_office and schema_version 1

### QA-071 YAML without schema_version is rejected
- Covers: Failure Modes (schema version)
- Type: failure
- Given YAML with no schema_version field
- When the admin imports the YAML
- Then the import fails with a validation error

### QA-072 Unsupported schema_version is rejected
- Covers: Failure Modes (schema version)
- Type: failure
- Given YAML with schema_version 99
- When the admin imports the YAML
- Then the import fails with a validation error and nothing is stored
- OPEN: the supported version set is not stated in the requirements

### QA-073 Seed loads exactly 3 procedures
- Covers: Success Metrics (3 of 3, 4 scenarios)
- Type: functional
- Given an empty migrated database
- When the seed runs
- Then list_procedures returns exactly 3 slugs for PESEL, residence card, and tax ID, and the seed directory holds exactly 3 files

### QA-074 Seed procedures have at least 3 steps with sources
- Covers: Success Metrics (3 steps, source link)
- Type: functional
- Given the seeded database
- When each of the 3 procedures is read
- Then each has at least 3 steps and every step has an https source_url, a last_checked date, and a verify line

### QA-075 Seed run twice adds no revision
- Covers: Success Metrics (second run)
- Type: functional
- Given a database seeded once with 3 revision rows
- When the seed runs a second time
- Then it exits with 0 errors and the revision rows still number 3

### QA-076 Seed actor is system:seed
- Covers: Decision (seed actor)
- Type: functional
- Given an empty migrated database
- When the seed runs
- Then each of the 3 revision rows has actor "system:seed"

### QA-077 Seed with duplicate slug stops
- Covers: Edge Cases (same slug in two files)
- Type: failure
- Given seed files "pesel.yaml" and "pesel-copy.yaml" with slug "pesel"
- When the seed runs
- Then it stops with an error that names both files, and nothing is written

### QA-078 Seed with one bad file writes nothing
- Covers: Edge Cases, Failure Modes (bad data)
- Type: failure
- Given 3 seed files where "tax-id.yaml" has an empty source_url
- When the seed runs
- Then it fails with an error that names "tax-id.yaml" and the step, and the user sees that bad data was rejected
- OPEN: it is not stated whether valid files import before the bad file or nothing is imported

### QA-079 Seed edit adds a revision
- Covers: Edge Cases (existing slug)
- Type: functional
- Given a seeded database and "pesel.yaml" with one changed last_checked date
- When the seed runs again
- Then "pesel" is revision 2 and the other 2 procedures stay revision 1

### QA-080 Seed without a database
- Covers: Failure Modes (store error)
- Type: failure
- Given POSTGRES_URL points to a stopped server
- When the seed runs
- Then it exits with a non-zero code and an error with no URL password in the text

### QA-081 Seed runs as the app role
- Covers: Decision (Seed)
- Type: security
- Given the seed started with the lawbyai_app connection
- When the seed runs
- Then it completes with no permission error

### QA-082 Seed content has no advice wording
- Covers: Technical Constraints (ADR-0015)
- Type: functional
- Given the 3 seed files
- When the owner reads every step text
- Then each step states information with a source, and the verify-with-office line is present on every step

### QA-083 get_procedure read time
- Covers: Success Metrics (under 100 ms)
- Type: performance
- Given the seeded database with 3 procedures
- When get_procedure("pesel") is called 20 times
- Then each call returns in under 100 ms

### QA-084 list_procedures read time
- Covers: Success Metrics (under 100 ms)
- Type: performance
- Given the seeded database with 3 procedures
- When list_procedures is called 20 times
- Then each call returns in under 100 ms

### QA-085 Unknown slug read time
- Covers: Success Metrics (under 100 ms)
- Type: performance
- Given the seeded database with 3 procedures
- When get_procedure("no-such-procedure") is called
- Then it returns None in under 100 ms

### QA-086 Docs state run order
- Covers: tasks T5 (docs)
- Type: functional
- Given the migrations guide
- When a reader looks for the seed step
- Then the guide states to migrate first and then seed

### QA-087 Owner gate in PR text
- Covers: Failure Modes (owner gate)
- Type: functional
- Given the PR text for this task
- When the reviewer reads it
- Then it states that an approving owner review is required before merge
- OPEN: a test cannot prove the owner gate, so this is a manual check

### QA-088 Import of large content
- Covers: Technical Constraints (budget)
- Type: performance
- Given YAML for "big-proc" with 200 valid steps
- When an admin imports it
- Then the import succeeds as revision 1 and get returns 200 steps in position order
- OPEN: no maximum step count or file size is stated

### QA-089 Import of oversized upload
- Covers: Edge Cases (bad input)
- Type: security
- Given a 50 MB text upload
- When an admin imports it
- Then the import fails with a clear error and does not exhaust memory
- OPEN: no size limit is stated in the requirements
