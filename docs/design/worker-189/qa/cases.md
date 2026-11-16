# worker-189 QA cases

### QA-001 Child with no store closes nothing
- Covers: Edge Case 1, Success Metric 3, T1
- Type: edge
- Given a Celery prefork child that has run 0 tasks and holds no database store
- When the child receives the worker process shutdown signal
- Then 0 new database stores are created and 0 database connections are opened

### QA-002 Child with one store closes it once
- Covers: Edge Case 2, Success Metric 4, T1
- Type: functional
- Given a child that ran 50 fetch tasks and holds 1 store
- When the child receives the worker process shutdown signal
- Then the store is closed exactly 1 time

### QA-003 Store is rebuilt after close
- Covers: Edge Case 3, T2
- Type: functional
- Given a child whose store was closed by the shutdown signal
- When the same process runs one more fetch task
- Then a second, new store is built (2 builds in total) and it is not the closed one

### QA-004 Close failure is logged and does not escape
- Covers: Failure Mode 1, T1
- Type: failure
- Given a child whose store raises RuntimeError("socket gone") on close
- When the child receives the worker process shutdown signal
- Then 1 warning with the traceback is logged, no error reaches the caller, and the child exits normally

### QA-005 Store is dropped even when close fails
- Covers: Failure Mode 1, Edge Case 3
- Type: failure
- Given a child whose store raises RuntimeError("socket gone") on close
- When the shutdown signal is sent and then 1 new fetch task runs
- Then the new task builds a fresh store (1 new build)

### QA-006 Hard kill skips the signal
- Covers: Failure Mode 2
- Type: failure
- Given a child that holds 1 store with 2 idle connections
- When the child is killed with SIGKILL, so the signal never fires
- Then the operating system closes the sockets at process exit and the database shows 0 connections from that child within 30 seconds. OPEN: the requirement gives no time limit, so 30 seconds is assumed.

### QA-007 Schema behind head fails on first task
- Covers: Failure Mode 3
- Type: failure
- Given a database whose schema is 1 revision behind head
- When a child runs its first fetch task
- Then the task fails with a schema-not-at-head error and no migration runs

### QA-008 Failed build is retried by the next task
- Covers: Failure Mode 3, T1
- Type: failure
- Given the first store build fails with a schema-not-at-head error and the schema is then upgraded to head
- When the same child runs a second fetch task
- Then the second task builds a store and completes, and no failed store stays cached

### QA-009 Shutdown after failed build closes nothing
- Covers: Failure Mode 3, T1
- Type: edge
- Given a child whose only store build failed
- When the child receives the worker process shutdown signal
- Then 0 close calls happen and no error is raised

### QA-010 Live pool is released
- Covers: Success Metric 2, T3
- Type: functional
- Given a child that built a store on live PostgreSQL and ran 1 query, so the pool shows more than 0 checked-in connections
- When the worker process shutdown signal is sent
- Then the saved old pool shows 0 checked-in connections, the store has no engine, and the cached store is empty

### QA-011 Unit tests need no database or network
- Covers: Success Metric 1, T2
- Type: performance
- Given the 6 handler unit tests and a machine with no PostgreSQL and no network
- When the tests run with the non-integration marker
- Then 6 of 6 pass (100%) and 0 connections are attempted

### QA-012 Shutdown signal reaches the handler
- Covers: T2, Technical Constraints
- Type: functional
- Given the task module is imported and 1 store is cached
- When the worker process shutdown signal is sent with no sender
- Then the store is closed exactly 1 time

### QA-013 Repeated shutdown signal is safe
- Covers: Edge Case 1, Edge Case 2
- Type: edge
- Given a child with 1 store that already received the shutdown signal once
- When the shutdown signal is sent a second time
- Then no second close happens (1 close in total) and no error is raised

### QA-014 Importing the module opens no connection
- Covers: Technical Constraints (lazy store)
- Type: edge
- Given a parent worker process and an unreachable database
- When the task module is imported
- Then 0 stores are built and 0 connections are attempted

### QA-015 Handler tolerates extra signal arguments
- Covers: T1
- Type: edge
- Given a child with 1 store
- When the shutdown signal is sent with pid=4242, exitcode=0 and sender="ForkPoolWorker-3"
- Then the store is closed exactly 1 time and no argument error occurs

### QA-016 Stale migration claim removed
- Covers: Business Goal 2, T1
- Type: functional
- Given the fetch task module after the change
- When a reviewer searches it for the word "migrat"
- Then 0 lines claim that the store migrates, and any match says the init service migrates

### QA-017 Worker never migrates
- Covers: Business Goal 2, Technical Constraints
- Type: security
- Given a database at head and a worker started with the application role
- When the worker runs 1 fetch task
- Then 0 schema change statements run and the application role is not given owner rights

### QA-018 Solo pool does not fire the signal
- Covers: Technical Constraints, decision Consequences
- Type: edge
- Given a worker started with the solo pool that built 1 store
- When the worker runs a task and stops
- Then the signal does not fire and the store is not closed by the handler. This is an accepted risk.

### QA-019 Child recycle closes the store
- Covers: Business Goal 1, decision Consequences
- Type: functional
- Given a prefork worker with a limit of 10 tasks per child and 1 child that ran 10 tasks
- When the child is recycled
- Then its old store is closed 1 time and the new child holds 0 stores until its first task

### QA-020 Autoscale shrink releases connections
- Covers: Business Goal 1
- Type: performance
- Given a worker with autoscale 4 to 1 and 4 children that each hold 3 idle connections (12 in total)
- When autoscale stops 3 children
- Then the database shows 3 connections from the remaining child and 0 from the stopped children

### QA-021 Coverage and mutation gate
- Covers: Success Metric 5, T2
- Type: performance
- Given the change to the fetch task module and its 7 new tests
- When the diff coverage and mutation checks run
- Then diff coverage on changed lines is at least 90% and the mutation score meets the CONTRIBUTING.md gate
