# QA cases: reject audit is append-only

### QA-001 App role cannot UPDATE an audit row
- Covers: Success Metric 3 of 3 denied statements
- Type: security
- Given the head schema, and one row in rejected_document with actor "admin@example.com"
- When the app role lawbyai_app runs UPDATE setting the actor to "other@example.com", in its own transaction
- Then PostgreSQL denies it with SQLSTATE 42501 and the row still shows "admin@example.com"

### QA-002 App role cannot DELETE an audit row
- Covers: Success Metric 3 of 3 denied statements
- Type: security
- Given the head schema, and one row in rejected_document
- When the app role lawbyai_app runs DELETE FROM rejected_document, in its own transaction
- Then PostgreSQL denies it with SQLSTATE 42501 and the table still holds 1 row

### QA-003 App role cannot TRUNCATE the audit table
- Covers: Success Metric 3 of 3 denied statements
- Type: security
- Given the head schema, and 3 rows in rejected_document
- When the app role lawbyai_app runs TRUNCATE rejected_document, in its own transaction
- Then PostgreSQL denies it with SQLSTATE 42501 and the table still holds 3 rows

### QA-004 App role can INSERT an audit row
- Covers: Success Metric 2 of 2 allowed statements
- Type: functional
- Given the head schema and an empty rejected_document
- When the app role lawbyai_app inserts 1 row with actor "admin@example.com"
- Then the INSERT succeeds and the table holds 1 row

### QA-005 App role can SELECT audit rows
- Covers: Success Metric 2 of 2 allowed statements
- Type: functional
- Given the head schema, and 2 rows in rejected_document
- When the app role lawbyai_app runs SELECT count(*) on rejected_document
- Then the result is 2 and no error occurs

### QA-006 Sequence grants stay after the revoke
- Covers: Technical Constraints (sequence grants stay)
- Type: edge
- Given the head schema and an empty rejected_document with a generated id column
- When the app role inserts 2 rows one after the other without giving an id
- Then both inserts succeed and the 2 rows get different ids

### QA-007 Owner keeps all rights
- Covers: Technical Constraints (owner keeps all rights); Business Goals (only owner can fix or purge)
- Type: functional
- Given the head schema, and 2 rows in rejected_document
- When the owner lawbyai_owner runs UPDATE on 1 row, then DELETE on it, then TRUNCATE
- Then each statement succeeds and the table is empty at the end

### QA-008 Schema guard: table privileges on head
- Covers: Failure Mode (later migration restores grants); Tests schema guard
- Type: security
- Given a database after upgrade to head, not to a fixed revision
- When the test asks if lawbyai_app has UPDATE, DELETE and TRUNCATE privilege on rejected_document
- Then all 3 answers are false

### QA-009 Schema guard: column-level UPDATE privilege
- Covers: Failure Mode (later migration restores grants); DBA fix F3
- Type: security
- Given a database after upgrade to head, and a column-level UPDATE grant on any column of rejected_document would be possible
- When the test asks if lawbyai_app has UPDATE on any column of rejected_document
- Then the answer is false

### QA-010 Schema guard: PUBLIC has no rights
- Covers: Failure Mode (later migration restores grants); Tests schema guard
- Type: security
- Given a database after upgrade to head
- When the test lists the privileges that PUBLIC holds on rejected_document
- Then the list is empty

### QA-011 Existing audit rows survive the migration
- Covers: Failure Mode (what must survive: every existing audit row)
- Type: failure
- Given a database at revision b7e2d41c9a30 with 5 rows in rejected_document
- When the owner runs the upgrade to head
- Then the table still holds the same 5 rows with the same values

### QA-012 Migration round trip as owner
- Covers: Success Metric upgrade, downgrade, upgrade with 0 failures; Failure Mode (owner can downgrade)
- Type: functional
- Given a database at head, and the owner connection
- When the owner runs upgrade to head, downgrade by 1 revision, and upgrade to head again
- Then all 3 steps finish with 0 errors and alembic shows exactly 1 head

### QA-013 Downgrade restores UPDATE and DELETE but not TRUNCATE
- Covers: Edge Case (migration downgrade); DBA fix F4
- Type: edge
- Given a database at head after the owner ran a downgrade by 1 revision
- When the test asks if lawbyai_app has UPDATE, DELETE and TRUNCATE on rejected_document
- Then UPDATE is true, DELETE is true and TRUNCATE is false

### QA-014 Upgrade fails fast when the table is locked
- Covers: Technical Constraints (migration safety); DBA fix F2 (lock timeout 5 s)
- Type: failure
- Given another session holds an ACCESS EXCLUSIVE lock on rejected_document for 30 s
- When the owner runs the upgrade
- Then the upgrade stops with a lock timeout error after about 5 s and does not wait 30 s
- OPEN: the requirements do not state the lock timeout; it comes from decision.md only

### QA-015 Repeated upgrade is safe
- Covers: Technical Constraints (one new revision); negative case, repeated action
- Type: edge
- Given a database already at head
- When the owner runs the upgrade to head a second time
- Then it finishes with 0 errors and the privileges are unchanged (no UPDATE, DELETE, TRUNCATE for lawbyai_app)

### QA-016 Reject with no actor raises and changes nothing
- Covers: Edge Case (no actor); Success Metric 1 test: reject() with no actor writes 0 rows
- Type: failure
- Given document "doc-001" in legal_document, an empty rejected_document and no actor set for the request
- When an admin flow rejects "doc-001"
- Then a permission error is raised, "doc-001" is still in legal_document and rejected_document has 0 rows

### QA-017 Reject with empty-string actor
- Covers: Edge Case (empty or blank actor)
- Type: failure
- Given document "doc-002" exists and the actor email is "" with role admin
- When an admin flow rejects "doc-002"
- Then a permission error is raised, "doc-002" stays and rejected_document has 0 rows

### QA-018 Reject with spaces-only actor
- Covers: Edge Case (blank actor)
- Type: failure
- Given document "doc-003" exists and the actor email is "   " (3 spaces) with role admin
- When an admin flow rejects "doc-003"
- Then a permission error is raised, "doc-003" stays and rejected_document has 0 rows

### QA-019 Reject by a non-admin role
- Covers: Decision (admin role check); Failure Mode (reject fails, document stays)
- Type: security
- Given document "doc-004" exists and the actor is "user@example.com" with role "user"
- When that actor rejects "doc-004"
- Then a permission error is raised, "doc-004" stays and rejected_document has 0 rows

### QA-020 Audit actor equals the context actor
- Covers: Business Goals (actor is the authenticated admin); Success Metric actor equals context actor
- Type: functional
- Given document "doc-005" exists and the actor is "admin@example.com" with role admin
- When that actor rejects "doc-005"
- Then rejected_document has 1 row with actor "admin@example.com" and "doc-005" is gone from legal_document

### QA-021 Caller cannot pass another actor
- Covers: Business Goals (caller cannot write another email); Technical Constraints (no free admin argument)
- Type: security
- Given document "doc-006" exists and the context actor is "admin@example.com"
- When a caller tries to reject "doc-006" and also passes the extra actor "boss@example.com"
- Then the call is refused as a bad call, and no row with "boss@example.com" exists in rejected_document

### QA-022 Actor with surrounding spaces is stored trimmed
- Covers: Decision (returns stripped email)
- Type: edge
- Given document "doc-007" exists and the actor email is "  admin@example.com  " with role admin
- When the actor rejects "doc-007"
- Then the audit row has actor "admin@example.com"

### QA-023 Concurrent rejects of one document
- Covers: Edge Case (two concurrent rejects)
- Type: edge
- Given document "doc-008" exists, and 2 threads each set actor "admin@example.com" with role admin
- When both threads reject "doc-008" at the same time
- Then exactly 1 thread succeeds, the other gets a not-found result, and rejected_document has 1 row for "doc-008"

### QA-024 Reject twice in a row
- Covers: Edge Case (repeated action); negative case
- Type: failure
- Given document "doc-009" was rejected once by "admin@example.com"
- When the same admin rejects "doc-009" again
- Then a not-found error is raised and rejected_document still has 1 row for "doc-009"

### QA-025 Reject of unknown document
- Covers: negative case, missing data
- Type: failure
- Given no document "doc-404" and an admin actor "admin@example.com"
- When the admin rejects "doc-404"
- Then a not-found error is raised and rejected_document has 0 rows

### QA-026 Reject is one transaction
- Covers: Failure Mode (reject transaction must survive)
- Type: failure
- Given document "doc-010" exists, an admin actor, and the audit insert is forced to fail
- When the admin rejects "doc-010"
- Then the error reaches the caller, "doc-010" is still in legal_document and rejected_document has 0 rows

### QA-027 Stale actor does not leak to a later request
- Covers: Failure Mode (actor never cleared)
- Type: failure
- Given an admin "admin@example.com" rejected "doc-011" inside a request scope, and the scope has ended
- When the same thread rejects "doc-012" with no new actor set
- Then a permission error is raised and "doc-012" stays

### QA-028 New thread does not inherit the actor
- Covers: Failure Mode (stale actor); Consequences (non-UI callers have no actor)
- Type: edge
- Given the main thread has actor "admin@example.com" with role admin, and document "doc-013" exists
- When a new background thread started without setting an actor rejects "doc-013"
- Then a permission error is raised in that thread and "doc-013" stays

### QA-029 Nested actor scope restores the previous actor
- Covers: Failure Mode (stale actor; context restore on exit)
- Type: edge
- Given actor "a@example.com" (admin) is set, then an inner scope sets "b@example.com" (admin)
- When the inner scope ends and the caller rejects "doc-014"
- Then the audit row has actor "a@example.com"

### QA-030 Login sets the actor for the request
- Covers: Technical Constraints (actor from the authenticated session); Tests Auth
- Type: functional
- Given user "admin@example.com" with role admin logged in through the app
- When a page run passes the authentication check
- Then the request actor is "admin@example.com" with role "admin"

### QA-031 Sign-out clears the actor
- Covers: Failure Mode (stale actor); Tests Auth
- Type: security
- Given user "admin@example.com" is logged in and the request actor is set
- When the user signs out
- Then the request actor is empty and a reject in that thread raises a permission error

### QA-032 Logout button clears the actor
- Covers: Failure Mode (stale actor); Tests Auth
- Type: security
- Given user "admin@example.com" is logged in and the request actor is set
- When the user presses the logout button
- Then the request actor is empty

### QA-033 Failed login sets no actor
- Covers: Technical Constraints (actor from authenticated session); negative case
- Type: security
- Given a visitor with a wrong password for "admin@example.com"
- When the page run checks authentication
- Then no actor is set and a reject in that run raises a permission error

### QA-034 UI shows an error when reject has no actor
- Covers: Failure Mode (UI shows an error, document stays)
- Type: failure
- Given a page run with no actor and document "doc-015" in the store
- When the page triggers a reject of "doc-015"
- Then the UI shows an error message and "doc-015" stays in the store
- OPEN: decision.md says the reject UI page and its error display are out of scope, so this case cannot run until that follow-up exists

### QA-035 Cleanup fixtures work with the owner role
- Covers: Tests DBA fix F1; Success Metric Docker suite 0 failures
- Type: functional
- Given the head schema, and the fetch rejection, worker pool and fetch task integration suites
- When the Docker suite runs these 3 suites plus the reject suite
- Then all of them pass with 0 failures and each cleanup leaves rejected_document empty

### QA-036 Later GRANT ALL migration is caught
- Covers: Failure Mode (GRANT ALL ON ALL TABLES restores UPDATE and DELETE)
- Type: security
- Given a test copy of the head schema where a new migration ran GRANT ALL ON ALL TABLES to lawbyai_app
- When the schema guard test runs
- Then the guard test fails because UPDATE and DELETE on rejected_document are true

### QA-037 Quality gate
- Covers: Success Metric quality gate
- Type: performance
- Given the finished change
- When ruff check, ruff format --check, pyright, the non-integration pytest run and the Docker suite run, then diff-cover runs
- Then all pass with 0 failures and diff-cover reports 90% or more on changed lines
