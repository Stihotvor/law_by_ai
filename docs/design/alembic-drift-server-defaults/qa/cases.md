# QA cases: Alembic drift test compares server defaults

### QA-001 Changed status default is detected
- Covers: Success Metric 1, T2
- Type: functional
- Given a database migrated to head, and a copy of all model tables where the `legal_document.status` server default is changed from 'needs_review' to 'published'
- When the drift comparison runs on the copy with server default comparison on
- Then the flattened diff has exactly 1 `modify_default` entry, for `legal_document.status`

### QA-002 Clean tree gives zero diff
- Covers: Success Metric 2, T1
- Type: functional
- Given a database migrated to head with the current migrations and the unchanged models
- When the drift comparison runs with server default comparison on
- Then the diff has 0 entries

### QA-003 CHECK name pinned under a naming convention
- Covers: Success Metric 3, Failure Mode 2, Edge Case 2, T3
- Type: failure
- Given a new metadata with naming convention `ck_%(table_name)s_%(constraint_name)s` and the `legal_document` table copied into it
- When the CHECK constraint name is read from the copy
- Then the name is exactly `ck_legal_document_status`, and the test fails with a clear message if it is `ck_legal_document_ck_legal_document_status`

### QA-004 Migration files unchanged
- Covers: Success Metric 4, T1
- Type: functional
- Given the branch with all 3 tasks done
- When the git diff of the migration versions folder against main is listed
- Then it shows 0 changed files

### QA-005 Cast rendering is not drift
- Covers: Edge Case 1
- Type: edge
- Given a database where the status default is stored as 'needs_review'::character varying and the model default is 'needs_review'
- When the drift comparison runs with server default comparison on
- Then no `modify_default` entry appears for `legal_document.status`

### QA-006 Integer default matches
- Covers: Edge Case 1, Business Goal 1
- Type: edge
- Given a database where `users.session_version` has default 0 and the model default is 0
- When the drift comparison runs with server default comparison on
- Then no `modify_default` entry appears for `users.session_version`

### QA-007 No default on both sides
- Covers: Edge Case 3
- Type: edge
- Given a model column with no server default and a database column with no default
- When the drift comparison runs with server default comparison on
- Then the diff has 0 entries for that column

### QA-008 Changed integer default is detected
- Covers: Business Goal 1
- Type: functional
- Given a copy of the model tables where `users.session_version` server default is changed from 0 to 5
- When the drift comparison runs with server default comparison on
- Then the diff has exactly 1 `modify_default` entry for `users.session_version`

### QA-009 Default removed from model is detected
- Covers: Business Goal 1, Failure Mode 1
- Type: failure
- Given a copy of the model tables where the `legal_document.status` server default is removed
- When the drift comparison runs with server default comparison on
- Then the diff has exactly 1 `modify_default` entry for `legal_document.status`

### QA-010 Copy does not change shared metadata
- Covers: T2
- Type: edge
- Given the status default changed on the copy as in QA-001
- When the drift comparison on the unchanged shared metadata runs afterward in the same session
- Then the diff has 0 entries and the shared status default is still 'needs_review'

### QA-011 Copy gives no unrelated entries
- Covers: T2
- Type: edge
- Given the copy of all tables with only the status default changed
- When the drift comparison runs
- Then the diff has no `remove_table` entry and no missing foreign key target error

### QA-012 Repeated drift run is stable
- Covers: Failure Mode 1
- Type: edge
- Given a database migrated to head and unchanged models
- When the drift comparison runs 2 times in a row
- Then both runs give 0 diff entries

### QA-013 Revision tool and test use the same options
- Covers: Failure Mode 3, Technical Constraints
- Type: functional
- Given the shared options dict has server default comparison on
- When the options used by the migration environment (online and offline) and by the drift test are compared
- Then both read the same dict, with server default comparison on in all 3 places

### QA-014 Autogenerate on clean tree makes no change
- Covers: Technical Constraints, Failure Mode 1
- Type: functional
- Given a database migrated to head and unchanged models
- When `alembic revision --autogenerate` runs
- Then the new revision has an empty upgrade body, and no schema change is proposed

### QA-015 Offline mode still runs
- Covers: Technical Constraints
- Type: functional
- Given the migration environment in offline mode
- When `alembic upgrade head --sql` runs
- Then SQL is printed with exit code 0

### QA-016 Hand-edited CHECK text is caught
- Covers: Technical Constraints (CHECK text guard)
- Type: failure
- Given the model CHECK on `legal_document.status` has a changed allowed value list, with the same name
- When the existing CHECK text test runs against the migrated database
- Then the test fails, because the drift comparison alone does not see CHECK text

### QA-017 CHECK name in database unchanged
- Covers: Business Goal 2
- Type: functional
- Given a fresh database created by migrations to head
- When the constraint names of `legal_document` are listed
- Then `ck_legal_document_status` is present exactly once, with the same name as before the change

### QA-018 Plain metadata without convention keeps name
- Covers: Edge Case 2, Business Goal 2
- Type: edge
- Given the shared metadata with no naming convention
- When the CHECK constraint name is read
- Then the name is exactly `ck_legal_document_status`

### QA-019 Shared options dict has no Alembic import
- Covers: T1
- Type: edge
- Given the shared options module
- When it is imported in a process where Alembic is not installed
- Then the import works and the dict equals `{"compare_server_default": True}`
