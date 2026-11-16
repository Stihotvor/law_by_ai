# QA cases: worker DB pool size

### QA-001 App pool size default
- Covers: Success Metric app engine 5 + 10; POSTGRES_POOL_SIZE default 5
- Type: functional
- Given POSTGRES_POOL_SIZE is not set
- When the app builds its database engine
- Then the engine pool size is 5

### QA-002 App overflow default
- Covers: Success Metric app engine 5 + 10; POSTGRES_MAX_OVERFLOW default 10
- Type: functional
- Given POSTGRES_MAX_OVERFLOW is not set
- When the app builds its database engine
- Then the engine overflow limit is 10

### QA-003 Worker pool size default
- Covers: Success Metric worker engine 1 + 1; WORKER_POSTGRES_POOL_SIZE default 1
- Type: functional
- Given WORKER_POSTGRES_POOL_SIZE is not set
- When the worker builds its database engine
- Then the engine pool size is 1

### QA-004 Worker overflow default
- Covers: Success Metric worker engine 1 + 1; WORKER_POSTGRES_MAX_OVERFLOW default 1
- Type: functional
- Given WORKER_POSTGRES_MAX_OVERFLOW is not set
- When the worker builds its database engine
- Then the engine overflow limit is 1

### QA-005 App pool size override
- Covers: POSTGRES_POOL_SIZE valid override
- Type: functional
- Given POSTGRES_POOL_SIZE is "3"
- When the app builds its database engine
- Then the engine pool size is 3

### QA-006 App overflow override
- Covers: POSTGRES_MAX_OVERFLOW valid override
- Type: functional
- Given POSTGRES_MAX_OVERFLOW is "2"
- When the app builds its database engine
- Then the engine overflow limit is 2

### QA-007 Worker pool size override
- Covers: WORKER_POSTGRES_POOL_SIZE valid override
- Type: functional
- Given WORKER_POSTGRES_POOL_SIZE is "2"
- When the worker builds its database engine
- Then the engine pool size is 2

### QA-008 Worker overflow override
- Covers: WORKER_POSTGRES_MAX_OVERFLOW valid override
- Type: functional
- Given WORKER_POSTGRES_MAX_OVERFLOW is "0"
- When the worker builds its database engine
- Then the engine overflow limit is 0 (zero is accepted)

### QA-009 App pool size 0 rejected
- Covers: Edge Case pool_size=0 is unlimited; POSTGRES_POOL_SIZE rejected value
- Type: edge
- Given POSTGRES_POOL_SIZE is "0"
- When the app reads the pool settings
- Then a ValueError is raised and its message contains "POSTGRES_POOL_SIZE"

### QA-010 App overflow -1 rejected
- Covers: Edge Case max_overflow=-1 is unlimited; POSTGRES_MAX_OVERFLOW rejected value
- Type: edge
- Given POSTGRES_MAX_OVERFLOW is "-1"
- When the app reads the pool settings
- Then a ValueError is raised and its message contains "POSTGRES_MAX_OVERFLOW"

### QA-011 Worker pool size 0 rejected
- Covers: Edge Case pool_size=0; WORKER_POSTGRES_POOL_SIZE rejected value
- Type: edge
- Given WORKER_POSTGRES_POOL_SIZE is "0"
- When the worker reads the pool settings
- Then a ValueError is raised and its message contains "WORKER_POSTGRES_POOL_SIZE"

### QA-012 Worker overflow -1 rejected
- Covers: Edge Case max_overflow=-1; WORKER_POSTGRES_MAX_OVERFLOW rejected value
- Type: edge
- Given WORKER_POSTGRES_MAX_OVERFLOW is "-1"
- When the worker reads the pool settings
- Then a ValueError is raised and its message contains "WORKER_POSTGRES_MAX_OVERFLOW"

### QA-013 Negative pool size rejected
- Covers: Edge Case reject value lower than 1
- Type: failure
- Given WORKER_POSTGRES_POOL_SIZE is "-5"
- When the worker reads the pool settings
- Then a ValueError is raised and its message contains "WORKER_POSTGRES_POOL_SIZE"

### QA-014 Non-integer value names the variable
- Covers: Edge Case "abc" gives ValueError that names the variable
- Type: failure
- Given POSTGRES_POOL_SIZE is "abc"
- When the app reads the pool settings
- Then a ValueError is raised and its message contains "POSTGRES_POOL_SIZE"

### QA-015 Float string rejected
- Covers: Edge Case non-integer value
- Type: failure
- Given WORKER_POSTGRES_MAX_OVERFLOW is "1.5"
- When the worker reads the pool settings
- Then a ValueError is raised and its message contains "WORKER_POSTGRES_MAX_OVERFLOW"

### QA-016 Empty value uses default
- Covers: Edge Case empty variable uses the default
- Type: edge
- Given POSTGRES_POOL_SIZE is "" (empty string)
- When the app reads the pool settings
- Then no error is raised and the pool size is 5

### QA-017 Empty worker value uses default
- Covers: Edge Case empty variable uses the default
- Type: edge
- Given WORKER_POSTGRES_POOL_SIZE is "" and WORKER_POSTGRES_MAX_OVERFLOW is ""
- When the worker reads the pool settings
- Then the pool size is 1 and the overflow is 1

### QA-018 Minimum boundary accepted
- Covers: Edge Case bounds (size 1, overflow 0 are valid)
- Type: edge
- Given POSTGRES_POOL_SIZE is "1" and POSTGRES_MAX_OVERFLOW is "0"
- When the app reads the pool settings
- Then no error is raised and the pool is 1 + 0

### QA-019 Pool config guard rejects size below 1
- Covers: Design point 2, PoolConfig size < 1
- Type: failure
- Given a caller creates a pool config with size 0 and overflow 1
- When the pool config is built
- Then a ValueError is raised

### QA-020 Pool config guard rejects negative overflow
- Covers: Design point 2, PoolConfig max_overflow < 0
- Type: failure
- Given a caller creates a pool config with size 1 and overflow -1
- When the pool config is built
- Then a ValueError is raised

### QA-021 Pool config is immutable
- Covers: Design point 2, frozen PoolConfig
- Type: failure
- Given a pool config with size 1 and overflow 1
- When a caller sets its size to 0
- Then the assignment is refused and the config still has size 1

### QA-022 Store without pool argument uses app pool
- Covers: Design point 3, app vs worker pool
- Type: functional
- Given a store is built with no pool argument and default settings
- When the store is initialized
- Then the engine pool size is 5 and the overflow limit is 10

### QA-023 Store with explicit pool uses it
- Covers: Success Metric worker engine 1 + 1; Design point 3
- Type: functional
- Given a store is built with a 1 + 1 pool and POSTGRES_POOL_SIZE is "7"
- When the store is initialized
- Then the engine pool size is 1 and the overflow limit is 1

### QA-024 Worker settings do not change the app pool
- Covers: Failure Mode app not affected by worker settings
- Type: functional
- Given WORKER_POSTGRES_POOL_SIZE is "1" and POSTGRES_POOL_SIZE is "5"
- When the app builds its engine
- Then the pool size is 5

### QA-025 App settings do not change the worker pool
- Covers: Design point 8, worker reads only WORKER_* pair
- Type: functional
- Given POSTGRES_POOL_SIZE is "9" and POSTGRES_MAX_OVERFLOW is "9", and the WORKER_* variables are unset
- When the worker builds its engine
- Then the pool is 1 + 1

### QA-026 Bad app setting fails before any engine exists
- Covers: Failure Mode bad pool value fails at build time; Design point 9
- Type: failure
- Given POSTGRES_POOL_SIZE is "0" and the store has no pool argument
- When the store is initialized
- Then a ValueError naming "POSTGRES_POOL_SIZE" is raised and no engine was created

### QA-027 Bad value never gives an unlimited pool
- Covers: Failure Mode no silent fallback to unlimited pool
- Type: security
- Given POSTGRES_MAX_OVERFLOW is "-1"
- When the app builds its engine
- Then a ValueError is raised and no engine with an unlimited overflow exists

### QA-028 Connection health check on checkout
- Covers: Consequences pool_pre_ping
- Type: functional
- Given a worker engine built with default settings
- When the engine settings are inspected
- Then connection health check before use (pre-ping) is on

### QA-029 Pool timeout is 30 seconds
- Covers: Failure Mode pool timeout 30 s default; Design point 3
- Type: functional
- Given an engine built with default settings
- When the engine settings are inspected
- Then the pool timeout is 30 seconds

### QA-030 Worker child survives a Postgres restart
- Covers: Consequences pre-ping survives restart
- Type: failure
- Given a worker child holds 1 idle pooled connection and Postgres restarts
- When the child runs the next task
- Then the task gets a working connection and does not fail with a closed-connection error

### QA-031 Busy worker pool times out
- Covers: Failure Mode all worker connections busy
- Type: failure
- Given a 1 + 1 worker pool with 2 connections checked out
- When a third task asks for a connection
- Then it waits 30 seconds and then fails with a pool timeout error

### QA-032 Timed-out task is persisted as failed
- Covers: Failure Mode failed task persisted (ADR-0006)
- Type: failure
- Given the pool timeout case of QA-031 for document fetch "doc-1"
- When the task fails
- Then a failed-task record for "doc-1" exists and can be re-run from the UI

### QA-033 Bad worker setting fails in store creation
- Covers: Contract _make_store raises ValueError
- Type: failure
- Given WORKER_POSTGRES_POOL_SIZE is "abc"
- When the fetch task asks for its store
- Then a ValueError naming "WORKER_POSTGRES_POOL_SIZE" is raised before the store is initialized

### QA-034 Failed store creation keeps cached store empty
- Covers: Contract _store stays None
- Type: failure
- Given WORKER_POSTGRES_MAX_OVERFLOW is "-1"
- When the fetch task asks for its store and it fails
- Then the cached store is still None

### QA-035 Next task retries after a failed store creation
- Covers: Contract next task tries again
- Type: failure
- Given QA-034 happened, then the operator sets WORKER_POSTGRES_MAX_OVERFLOW to "1"
- When the next fetch task runs in the same child
- Then the store is built with a 1 + 1 pool and the task proceeds

### QA-036 Repeated store requests reuse one store
- Covers: Technical Constraint lazy store per child
- Type: edge
- Given valid worker settings
- When the fetch task asks for its store 3 times in one child
- Then the same store is returned and only one engine was built

### QA-037 Fetch task gets store only from the shared builder
- Covers: Consequences risk of new direct store callers
- Type: security
- Given the fetch task module
- When a test replaces the shared store builder with a recording stub and runs a fetch
- Then the stub is called and no other store is built

### QA-038 Fetch document with 1 + 1 pool
- Covers: Design point 10 integration test; Success Metric at most 4 connections
- Type: functional
- Given a real Postgres and a worker pool of 1 + 1
- When the fetch task runs document fetch for one document
- Then the task succeeds and the child holds at most 2 connections

### QA-039 Worker connection cap with concurrency 2
- Covers: Success Metric at most 4 connections (down from 30)
- Type: performance
- Given a worker started with --concurrency=2 and default settings, and 10 fetch tasks queued
- When all tasks run and the open connections of the worker are counted on Postgres
- Then the peak count is 4 or fewer

### QA-040 Compose passes app pool variables
- Covers: Design point 5, x-app-env
- Type: functional
- Given POSTGRES_POOL_SIZE "3" and POSTGRES_MAX_OVERFLOW "2" are exported
- When the compose config is rendered
- Then the app service shows both values

### QA-041 Compose passes worker pool variables to the worker
- Covers: Design point 5, celery-worker
- Type: functional
- Given WORKER_POSTGRES_POOL_SIZE "1" and WORKER_POSTGRES_MAX_OVERFLOW "1" are exported
- When the compose config is rendered
- Then the celery-worker service shows both values

### QA-042 Compose with variables unset
- Covers: Design point 8, bare keys; init gets code defaults
- Type: edge
- Given none of the four variables is set
- When the stack starts
- Then the stack starts, the worker pool is 1 + 1 and the app pool is 5 + 10

### QA-043 Env example lists four variables
- Covers: Design point 5, .env.example
- Type: functional
- Given the example env file
- When a reader lists its lines
- Then POSTGRES_POOL_SIZE=5, POSTGRES_MAX_OVERFLOW=10, WORKER_POSTGRES_POOL_SIZE=1 and WORKER_POSTGRES_MAX_OVERFLOW=1 appear commented out

### QA-044 Settings docs table lists four variables
- Covers: Design point 7
- Type: functional
- Given the settings module documentation
- When a reader looks at the variable table
- Then all four variable names appear with their defaults

### QA-045 Init service uses default pool
- Covers: Consequences init uses app pool
- Type: edge
- Given the init bootstrap service has no pool variables
- When it runs
- Then it opens its connections with the 5 + 10 pool and exits normally

### QA-046 Quality gate
- Covers: Success Metric gate (diff-cover 90%)
- Type: performance
- Given the finished change
- When the lint, type check, fast tests and diff-cover run
- Then all exit 0 and diff-cover reports 90% or more on changed lines
