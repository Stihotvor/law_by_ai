# QA cases: migration lock deadline

### QA-001 Timeout when the key is held
- Covers: Success Metrics (timeout test), T3
- Type: performance
- Given a second database connection holds advisory key 0x6C61775F6D6967 and MIGRATION_LOCK_TIMEOUT_S is 2
- When the operator runs `alembic upgrade head`
- Then the run fails after at least 2 s and at most 5 s

### QA-002 Timeout message content
- Covers: Failure Modes (error message), T3
- Type: failure
- Given a second connection with backend pid 4321 (read from the database) holds key 0x6C61775F6D6967 and MIGRATION_LOCK_TIMEOUT_S is 2
- When the operator runs `alembic upgrade head` and it times out
- Then the error text contains 0x6C61775F6D6967, the deadline 2, and the pid 4321

### QA-003 No revision applied on timeout
- Covers: Edge Cases (held past deadline), Success Metrics (0 changed rows)
- Type: failure
- Given a database at revision X with the key held by a second connection and MIGRATION_LOCK_TIMEOUT_S is 2
- When the operator runs `alembic upgrade head` and it times out
- Then `alembic_version` has 0 changed rows and still shows revision X

### QA-004 Non-zero exit on timeout
- Covers: Failure Modes (exit code)
- Type: failure
- Given the key is held by a second connection and MIGRATION_LOCK_TIMEOUT_S is 2
- When the one-shot init service runs the upgrade
- Then the process exits with a non-zero code and dependent services do not start

### QA-005 Error is a RuntimeError subclass
- Covers: Failure Modes (error type)
- Type: failure
- Given a fake connection where every lock try returns false and a fake clock that passes 300 s
- When the lock helper waits for the key
- Then it raises an error that is an instance of RuntimeError

### QA-006 Lock free on first try
- Covers: Edge Cases (lock is free)
- Type: functional
- Given no session holds key 0x6C61775F6D6967 and the database is at an older revision
- When the operator runs `alembic upgrade head`
- Then the run logs no wait line and applies all missing revisions

### QA-007 Wait line when first try fails
- Covers: Failure Modes (wait log line)
- Type: functional
- Given a second connection holds the key and MIGRATION_LOCK_TIMEOUT_S is 5
- When the operator runs `alembic upgrade head`
- Then the log has exactly 1 wait line that names the key and the deadline 5 s

### QA-008 Lock freed before deadline
- Covers: Edge Cases (freed before deadline)
- Type: functional
- Given a second connection holds the key, MIGRATION_LOCK_TIMEOUT_S is 10, and the holder releases it after 3 s
- When the operator runs `alembic upgrade head`
- Then the run takes the lock at the next 1 s poll, finishes before 10 s, and applies only the missing revisions

### QA-009 Poll interval is 1 s
- Covers: Technical Constraints (1 s poll)
- Type: functional
- Given a fake clock, a fake sleep, and a fake connection whose lock try returns false 3 times and then true
- When the lock helper waits for the key
- Then the fake sleep was called 3 times with 1 s each and the body runs once

### QA-010 Body never runs on timeout
- Covers: Failure Modes (no revision on timeout), T2
- Type: failure
- Given a fake connection whose lock try always returns false and a deadline of 2 s on a fake clock
- When the lock helper waits and the deadline passes
- Then the protected body does not run

### QA-011 Holder unknown
- Covers: Edge Cases (holder ended before pg_locks query)
- Type: edge
- Given a fake connection whose lock try always returns false and whose holder query returns no row, deadline 2 s
- When the deadline passes
- Then the error names key 0x6C61775F6D6967, the deadline 2, and the word "unknown" in place of the pid

### QA-012 Poll query fails
- Covers: Failure Modes (connection lost)
- Type: failure
- Given a fake connection whose lock try raises a database error on the 2nd call
- When the lock helper waits for the key
- Then the same database error is raised and it is not a timeout error

### QA-013 Holder query fails
- Covers: Failure Modes (connection lost), T2
- Type: failure
- Given a fake connection whose lock try returns false until the deadline and whose holder query raises a database error
- When the deadline passes
- Then the database error is raised unchanged and not a timeout error

### QA-014 Release failure is logged
- Covers: T2 (release failure)
- Type: failure
- Given the lock is taken and the release query raises a database error after the body finishes
- When the lock helper leaves the protected block
- Then the failure is logged and no error is raised

### QA-015 Setting default
- Covers: Success Metrics (setting default 300), T1
- Type: functional
- Given MIGRATION_LOCK_TIMEOUT_S is not set
- When settings load
- Then the migration lock deadline is 300

### QA-016 Setting valid value
- Covers: Success Metrics (valid value), T1
- Type: functional
- Given MIGRATION_LOCK_TIMEOUT_S is 12.5
- When settings load
- Then the migration lock deadline is 12.5

### QA-017 Setting zero
- Covers: Edge Cases (value 0), Success Metrics, T1
- Type: edge
- Given MIGRATION_LOCK_TIMEOUT_S is 0
- When settings load
- Then loading fails with an error that names MIGRATION_LOCK_TIMEOUT_S

### QA-018 Setting negative
- Covers: Edge Cases (value -5), Success Metrics, T1
- Type: edge
- Given MIGRATION_LOCK_TIMEOUT_S is -5
- When settings load
- Then loading fails with an error that names MIGRATION_LOCK_TIMEOUT_S

### QA-019 Setting non-numeric
- Covers: Edge Cases (value abc), Success Metrics, T1
- Type: edge
- Given MIGRATION_LOCK_TIMEOUT_S is abc
- When settings load
- Then loading fails with an error that names MIGRATION_LOCK_TIMEOUT_S

### QA-020 Invalid value fails before connect
- Covers: Edge Cases (fails before it connects), T3
- Type: failure
- Given MIGRATION_LOCK_TIMEOUT_S is 0 and the database is stopped
- When the operator runs `alembic upgrade head`
- Then the run exits non-zero with an error that names MIGRATION_LOCK_TIMEOUT_S and no connection error appears

### QA-021 Invalid value fails before connect, -5 and abc
- Covers: Edge Cases (-5, abc), T3
- Type: failure
- Given MIGRATION_LOCK_TIMEOUT_S is abc and the database is stopped
- When the operator runs `alembic upgrade head`
- Then the run exits non-zero with an error that names MIGRATION_LOCK_TIMEOUT_S and no connection error appears

### QA-022 Negative value on a live database
- Covers: Edge Cases (value -5), T3
- Type: failure
- Given MIGRATION_LOCK_TIMEOUT_S is -5 and the database is at revision X
- When the operator runs `alembic upgrade head`
- Then the run exits non-zero naming MIGRATION_LOCK_TIMEOUT_S and `alembic_version` still shows revision X

### QA-023 Offline mode takes no lock
- Covers: Edge Cases (offline mode)
- Type: edge
- Given a second connection holds key 0x6C61775F6D6967 and MIGRATION_LOCK_TIMEOUT_S is 2
- When the operator runs `alembic upgrade head --sql`
- Then the SQL script prints at once with no wait and no lock error

### QA-024 Offline mode ignores invalid deadline
- Covers: Edge Cases (offline reads no deadline)
- Type: edge
- Given MIGRATION_LOCK_TIMEOUT_S is abc
- When the operator runs `alembic upgrade head --sql`
- Then the SQL script prints and the exit code is 0

### QA-025 Existing lock tests pass (one adapted to polling)
- Covers: Success Metrics (4 existing tests)
- Type: functional
- Given the 4 existing tests in the migration lock integration test file, with no edit
- When the Docker integration suite runs them
- Then all 4 pass

### QA-026 Repeated run after timeout
- Covers: Failure Modes, negative (repeated action)
- Type: failure
- Given a first run timed out because the key was held, and the holder then releases the key
- When the operator runs `alembic upgrade head` again
- Then the second run takes the lock without wait and applies all missing revisions

### QA-027 Timeout does not leave a stuck lock
- Covers: Business Goals (later upgrades blocked)
- Type: failure
- Given a run timed out on a held key and the holder released it
- When a third connection tries the key with a non-blocking try
- Then the try succeeds, so the timed-out run did not take or keep the key

### QA-028 Fractional deadline
- Covers: Technical Constraints (positive number)
- Type: edge
- Given MIGRATION_LOCK_TIMEOUT_S is 0.5 and the key is held
- When the operator runs `alembic upgrade head`
- Then the run fails with a timeout error that shows the deadline 0.5 and it does not wait for a full 1 s poll cycle beyond the deadline
- Resolved: the run always makes at least one try. It stops at the first poll at or after the deadline, so it overshoots by at most one poll interval (1 s).

### QA-029 Empty value
- Covers: Technical Constraints (non-numeric fails)
- Type: edge
- Given MIGRATION_LOCK_TIMEOUT_S is set to an empty string
- When settings load
- Then loading fails naming MIGRATION_LOCK_TIMEOUT_S
- Resolved: an empty value is invalid. `_positive` raises "must be a number" for an empty string.

### QA-030 Non-finite value
- Covers: Technical Constraints (positive number)
- Type: edge
- Given MIGRATION_LOCK_TIMEOUT_S is inf
- When settings load
- Then loading fails naming MIGRATION_LOCK_TIMEOUT_S
- Resolved: `inf` and `nan` are invalid. `_positive` accepts only positive, finite values.

### QA-031 Doc update
- Covers: T4
- Type: functional
- Given the migration guide after the change
- When a reader opens the section "Overlapping upgrade runs"
- Then it names MIGRATION_LOCK_TIMEOUT_S, the 300 s default, the 1 s poll, key 0x6C61775F6D6967 and the holder pid in the error

### QA-032 Quality gate
- Covers: Success Metrics (quality gate)
- Type: functional
- Given the finished change on the branch
- When ruff check, ruff format --check, pyright and pytest run, with the coverage and mutation gates
- Then all of them pass with exit code 0
