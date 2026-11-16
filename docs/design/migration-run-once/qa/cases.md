# QA cases: migration run once

### QA-001 Two concurrent upgrades on an empty database
- Covers: Success Metric 1, Edge Case "Empty database", T1, T2
- Type: functional
- Given an empty scratch PostgreSQL database and two `alembic upgrade head` processes started at the same moment
- When both processes run to the end
- Then both exit with code 0 and `alembic_version` holds exactly 1 row equal to head

### QA-002 Second run blocks while the lock key is held
- Covers: Success Metric 2, T1, T2
- Type: functional
- Given a separate session holds the advisory lock key 0x6C61775F6D6967 on a scratch database
- When a run of `alembic upgrade head` starts and 2 s pass
- Then the run is still running and has not exited

### QA-003 Blocked run completes after release
- Covers: Success Metric 2, T2
- Type: functional
- Given the run from QA-002 is waiting while the separate session holds the key
- When the separate session releases the lock
- Then the run exits with code 0 and the database is at head

### QA-004 No lock left after a run at head
- Covers: Success Metric 3, Edge Case "Database already at head", T2
- Type: functional
- Given a scratch database already at head
- When `alembic upgrade head` runs and exits
- Then the exit code is 0, no migration is applied, and `pg_locks` shows 0 advisory locks

### QA-005 Third concurrent run waits
- Covers: Edge Case "A third concurrent run"
- Type: edge
- Given an empty scratch database and 3 `alembic upgrade head` processes started at the same moment
- When all 3 processes run to the end
- Then all 3 exit with code 0 and `alembic_version` holds exactly 1 row equal to head

### QA-006 Second run on an empty database does nothing after waiting
- Covers: Edge Case "Empty database"
- Type: edge
- Given an empty scratch database where run A holds the lock and creates `alembic_version`, and run B waits
- When run A finishes
- Then run B applies no migration, exits with code 0, and the log shows no "already exists" error

### QA-007 Failed migration frees the lock
- Covers: Failure Mode "A migration fails"
- Type: failure
- Given a scratch database and a run whose migration raises an error on its first statement
- When the run exits
- Then the exit code is not 0, the original error is shown, the changes of that migration are rolled back, and `pg_locks` shows 0 advisory locks

### QA-008 Waiting run retries after a failed run
- Covers: Failure Mode "A migration fails"
- Type: failure
- Given run A holds the lock and then fails in a migration, and run B waits on the lock
- When run A fails and releases the lock
- Then run B takes the lock, starts again from the same revision that run A started from, and exits with code 0 if its migrations succeed

### QA-009 Unlock error does not hide the migration error
- Covers: Failure Mode "A migration fails", Decision "finally"
- Type: failure
- Given a migration fails and the connection is already broken when the run tries to unlock
- When the run exits
- Then the error shown is the migration error, not the unlock error

### QA-010 Killed process frees the lock
- Covers: Failure Mode "A process dies while it holds the lock"
- Type: failure
- Given run A holds the lock in the middle of a slow migration and run B waits
- When run A is killed with SIGKILL
- Then PostgreSQL ends the session of run A, run B takes the lock within 5 s, and `pg_locks` shows only one advisory lock owner, run B
- Note: the 5 s bound is a test tolerance. A killed client closes its socket, and PostgreSQL ends the session at once.

### QA-011 Wait has no time limit
- Covers: Failure Mode "A run waits with no time limit"
- Type: edge
- Given a separate session holds the lock key and no `lock_timeout` is set
- When a run waits for 30 s
- Then the run is still waiting, shows no timeout error, and `pg_locks` shows the run as waiting for the key

### QA-012 Timeout setting makes the waiting run fail
- Covers: Failure Mode "lock_timeout or statement_timeout"
- Type: failure
- Given the role has `lock_timeout` set to 1000 ms and a separate session holds the lock key
- When a run of `alembic upgrade head` starts
- Then the run exits with a non-zero code and a timeout error after about 1 s, and applies no migration

### QA-013 Repeated run is idempotent
- Covers: Business Goals, repeated actions
- Type: edge
- Given a scratch database at head after one successful run
- When `alembic upgrade head` runs 3 times one after another
- Then each run exits with code 0, `alembic_version` still holds 1 row, and `pg_locks` shows 0 advisory locks

### QA-014 Offline SQL output takes no lock
- Covers: Technical Constraint "Offline mode", T2
- Type: functional
- Given no database is reachable and the connection URL points to a closed port
- When `alembic upgrade <first revision> --sql` runs
- Then it prints the SQL script, exits with code 0, and the script has no `pg_advisory_lock` statement

### QA-015 Offline run does not wait on a held lock
- Covers: Technical Constraint "Offline mode"
- Type: edge
- Given a separate session holds the lock key on a scratch database
- When `alembic upgrade <first revision> --sql` runs
- Then it exits with code 0 within 2 s

### QA-016 Different key does not block
- Covers: Decision "Lock key", negative case
- Type: negative
- Given a separate session holds the advisory lock key 12345, not the migration key
- When `alembic upgrade head` runs on a scratch database
- Then the run exits with code 0 without waiting

### QA-017 Lock role needs no extra grant
- Covers: Technical Constraint "owner role"
- Type: security
- Given a scratch database where the role `lawbyai_owner` has no extra grant
- When `alembic upgrade head` runs as `lawbyai_owner`
- Then the run exits with code 0 and shows no permission error

### QA-018 No schema change from the lock
- Covers: Technical Constraint "No new migration, no schema change"
- Type: functional
- Given a scratch database upgraded with the lock in place
- When the schema is compared with a database upgraded before this change
- Then both schemas are the same and the list of revisions has no new entry

### QA-019 Docs note on the advisory lock
- Covers: T3
- Type: functional
- Given the file `docs/migrations.md` after the change
- When a reader searches it for "advisory"
- Then a section is found that names the key 0x6C61775F6D6967, says the wait has no limit, and warns that a `lock_timeout` makes the waiting run fail

### QA-020 Quality gate
- Covers: Success Metric 4, T4
- Type: functional
- Given the finished change
- When ruff check, ruff format --check, pyright, the fast tests and the Docker suite run
- Then there are 0 failures and the migration lock tests show 3 PASSED
