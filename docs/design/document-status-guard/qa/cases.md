# QA cases: document status guard

### QA-001 Update cannot approve a document
- Covers: Success Metrics (update test), Edge Cases (update with status), T2
- Type: functional
- Given a stored document id "doc-100" with status needs_review and title "Old"
- When a caller updates "doc-100" with status "approved" and title "x"
- Then the stored status is still needs_review and the stored title is "x"

### QA-002 Insert with approved is stored as needs_review
- Covers: Success Metrics (insert test), Edge Cases (insert with approved), T2
- Type: functional
- Given no stored document with id "doc-200"
- When a caller saves a new document with id "doc-200", title "Act A" and status "approved"
- Then the stored row has status needs_review and the call returns without error

### QA-003 Insert without status
- Covers: Edge Cases (insert with no status), T2
- Type: functional
- Given a new payload with id "doc-201", title "Act B" and no status key
- When a caller saves it
- Then the stored status is needs_review and 0 status warnings are logged

### QA-004 Upsert keeps approved when needs_review is sent
- Covers: Success Metrics (upsert test), Edge Cases (upsert), T2
- Type: functional
- Given a stored document "doc-300" with status approved and title "Old"
- When a caller saves the same id "doc-300" with status needs_review and title "New"
- Then the stored status is still approved and the title is "New"

### QA-005 Upsert keeps approved when approved is sent
- Covers: Edge Cases (upsert), T2
- Type: functional
- Given a stored document "doc-301" with status approved
- When a caller saves the same id "doc-301" with status approved
- Then the stored status is approved and the row count for "doc-301" is 1

### QA-006 Upsert cannot approve a needs_review row
- Covers: Business Goals (no skip of review), Edge Cases (upsert), T2
- Type: security
- Given a stored document "doc-302" with status needs_review
- When a caller saves the same id "doc-302" with status "approved"
- Then the stored status is still needs_review

### QA-007 Unknown status "bogus" does not raise
- Covers: Edge Cases (unknown status), T2
- Type: edge
- Given a stored document "doc-400" with status needs_review
- When a caller updates "doc-400" with status "bogus"
- Then no error is raised and the stored status is needs_review

### QA-008 Unknown status "rejected" does not raise
- Covers: Edge Cases (unknown status), T2
- Type: edge
- Given a stored document "doc-401" with status needs_review
- When a caller updates "doc-401" with status "rejected"
- Then no error is raised and the stored status is needs_review

### QA-009 Empty status does not raise
- Covers: Edge Cases (unknown status), T2
- Type: edge
- Given a stored document "doc-402" with status needs_review
- When a caller updates "doc-402" with status "" (empty string)
- Then no error is raised and the stored status is needs_review

### QA-010 None status does not raise
- Covers: Edge Cases (unknown status), T2
- Type: edge
- Given a stored document "doc-403" with status needs_review
- When a caller updates "doc-403" with status None
- Then no error is raised and the stored status is needs_review

### QA-011 Insert with unknown status is stored as needs_review
- Covers: Edge Cases (unknown status), T2
- Type: negative
- Given no stored document with id "doc-404"
- When a caller saves a new document "doc-404" with status "bogus"
- Then no error is raised and the stored status is needs_review

### QA-012 Warning names keys and hides values
- Covers: Failure Modes (ignore design, no secret in log), T2
- Type: security
- Given a stored document "doc-500"
- When a caller updates "doc-500" with status "approved-secret" and an unknown key "foo" with value 1
- Then exactly 1 warning is logged, it contains "status" and "foo", and it does not contain "approved-secret"

### QA-013 Insert warning names the key only
- Covers: Failure Modes (ignore design), T2
- Type: security
- Given no stored document with id "doc-501"
- When a caller saves a new document "doc-501" with status "approved"
- Then exactly 1 warning is logged, it contains "status", and it does not contain "approved"

### QA-014 Upsert warning lists dropped keys
- Covers: Failure Modes (ignore design), T2
- Type: functional
- Given a stored document "doc-502" with status approved
- When a caller saves id "doc-502" with status "needs_review" and title "T"
- Then exactly 1 warning is logged for the call and it contains "status"

### QA-015 Update without dropped keys logs no warning
- Covers: Failure Modes (ignore design), T2
- Type: negative
- Given a stored document "doc-503"
- When a caller updates "doc-503" with title "Only title"
- Then 0 warnings are logged

### QA-016 Update cannot change tenant_id
- Covers: Decision Consequences (tenant move closed), T1, T2
- Type: security
- Given a stored document "doc-600" with tenant_id "t1"
- When a caller updates "doc-600" with tenant_id "t2" and title "x"
- Then the stored tenant_id is still "t1", the title is "x", and the warning names "tenant_id"

### QA-017 Upsert cannot move a document to another tenant
- Covers: Decision Consequences (tenant move closed), T1, T2
- Type: security
- Given a stored document "doc-601" with tenant_id "t1"
- When a caller saves id "doc-601" with tenant_id "t2"
- Then the stored tenant_id is still "t1" and no row exists for "doc-601" under "t2"

### QA-018 Update cannot change id
- Covers: Decision Consequences (id not changed), T1
- Type: negative
- Given a stored document "d1"
- When a caller updates "d1" with id "d2" and title "x"
- Then the document is still found under "d1", no document "d2" exists, and the warning does not name "id"

### QA-019 Insert still reads tenant_id
- Covers: Decision (insert reads tenant_id as today), T2
- Type: functional
- Given no stored document "doc-602" and a tenant "t1" passed by the caller
- When a caller saves "doc-602" with status "approved"
- Then the stored row has tenant_id "t1" and status needs_review

### QA-020 Metadata is stored and read back
- Covers: Decision (metadata maps to metadata_), T1
- Type: functional
- Given a stored document "doc-700"
- When a caller updates "doc-700" with metadata {"court": "SN", "year": 2024}
- Then reading "doc-700" returns metadata {"court": "SN", "year": 2024}

### QA-021 Metadata does not break the model
- Covers: Decision (metadata vs Base.metadata), T1
- Type: negative
- Given a row object and a payload with metadata {"k": "v"}
- When the payload is applied to the row
- Then the row metadata_ JSON value equals {"k": "v"} and the row metadata attribute is still the model table registry (Base.metadata)

### QA-022 All allowed keys are copied
- Covers: Decision (allowlist), T1
- Type: functional
- Given a row object
- When a payload with title "T", content "C", source "S", source_url "https://example.eu/a", is_processed true, metadata {"a": 1} and last_updated "2026-01-15T10:00:00" is applied
- Then each value is set on the row and the list of dropped keys is empty

### QA-023 Status dropped at row level with return value
- Covers: Decision (returns dropped names), T1
- Type: functional
- Given a row with status needs_review
- When the payload {"status": "approved", "title": "x"} is applied
- Then the row status is needs_review, the title is "x", and the dropped list is ["status"]

### QA-024 Dropped names are sorted
- Covers: Decision (sorted dropped names), T1
- Type: edge
- Given a row with tenant_id "t1"
- When the payload {"tenant_id": "t2", "foo": 1} is applied
- Then tenant_id is "t1" and the dropped list is ["foo", "tenant_id"]

### QA-025 id is ignored and not reported
- Covers: Decision (id excluded from dropped list), T1
- Type: edge
- Given a row with id "d1"
- When the payload {"id": "d2"} is applied
- Then the row id is "d1" and the dropped list is []

### QA-026 Row-level status values never raise
- Covers: Edge Cases (unknown status), T1
- Type: negative
- Given a row with status needs_review
- When payloads with status "approved", "bogus", "rejected", "" and None are applied one at a time
- Then no error is raised, the row status stays needs_review, and each dropped list is ["status"]

### QA-027 Caller dict unchanged by update
- Covers: Edge Cases (input dict unchanged), T1
- Type: edge
- Given a payload {"status": "approved", "title": "x"} and a copy of it
- When a caller updates a stored document with the payload
- Then the payload equals the copy

### QA-028 Save writes only the generated id back
- Covers: Edge Cases (input dict, id write-back), T2
- Type: edge
- Given a payload {"title": "No id", "status": "approved"} with no id and a copy of it
- When a caller saves the payload
- Then the payload has a new generated id and otherwise equals the copy, including status "approved"

### QA-029 Reads return status
- Covers: Failure Modes (read paths), T2
- Type: functional
- Given a stored document "doc-800" with status needs_review
- When a caller reads "doc-800"
- Then the result has status needs_review

### QA-030 Missing document update
- Covers: Failure Modes (no row changes), T2
- Type: failure
- Given no stored document "missing-1"
- When a caller updates "missing-1" with status "approved"
- Then no row is created and no status is stored for "missing-1"

### QA-031 Repeated approve attempts
- Covers: Business Goals (no skip of review), T2
- Type: negative
- Given a stored document "doc-801" with status needs_review
- When a caller updates "doc-801" with status "approved" 3 times in a row
- Then the stored status is needs_review after each call and 3 warnings are logged

### QA-032 Fetch stores needs_review
- Covers: Success Metrics (fetch test), Failure Modes (fetch keeps working), T3
- Type: functional
- Given a fetch of a new document "Act 2026/12" with the network mocked
- When the fetch task runs
- Then the task returns status "saved" and the stored row has status needs_review

### QA-033 Fetch logs no status warning
- Covers: Success Metrics (fetch test, no warning), T3
- Type: functional
- Given a fetch of a new document "Act 2026/13" with the network mocked
- When the fetch task runs
- Then 0 warnings that name "status" are logged

### QA-034 Fetch payload has no status
- Covers: Decision (fetch stops sending status), T3
- Type: functional
- Given a fetched document with title "Act 2026/14" and text "Body"
- When the task builds the document payload
- Then the payload has no "status" key

### QA-035 Repeated fetch inserts a new row
- Covers: Decision Consequences (each fetch inserts), T3
- Type: edge
- Given a document "Act 2026/15" already fetched once and approved by direct database edit
- When the fetch task runs again for the same source
- Then a new row with status needs_review is added and the approved row keeps status approved

### QA-036 No new migration
- Covers: Success Metrics (0 new migrations), T2
- Type: functional
- Given the change is applied and the migration folder listing from before the change
- When the folder listing is compared
- Then 0 new files exist

### QA-037 validate_status is gone
- Covers: Decision (validate_status removed), T2
- Type: functional
- Given the change is applied
- When a text search for "validate_status" runs over the application code
- Then the output is empty

### QA-038 Quality gate
- Covers: Success Metrics (quality gate)
- Type: functional
- Given the change is applied
- When ruff check, ruff format --check, pyright and pytest run
- Then all 4 pass, and the coverage and mutation gates of CONTRIBUTING.md pass

### QA-039 Direct database write is not blocked
- Covers: Decision Consequences (raw SQL can set approved)
- Type: edge
- Given a stored document "doc-900" with status needs_review
- When an operator sets status to approved by SQL outside the store
- Then the write succeeds. OPEN: the database-level guard is a follow-up, so this is a known gap and not a defect.
