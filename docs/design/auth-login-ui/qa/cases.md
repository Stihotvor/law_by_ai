# QA cases: auth-login-ui

### QA-001 Admin role is accepted for admin check
- Covers: T2, Success Metric 1
- Type: functional
- Given a caller with role "admin"
- When the admin check runs
- Then the caller is accepted and no error is raised

### QA-002 Plain user is rejected by admin check
- Covers: T2, Failure Mode 2
- Type: failure
- Given a caller with role "user"
- When the admin check runs
- Then a PrivilegeEscalationError (a PermissionError) is raised

### QA-003 Empty role fails closed
- Covers: Edge Case 1
- Type: edge
- Given a caller with role "" (empty string)
- When the admin check runs
- Then access is denied and the caller is not treated as admin

### QA-004 None-like role fails closed
- Covers: Edge Case 1
- Type: edge
- Given a caller whose role is None
- When the admin check runs
- Then access is denied and the caller is not treated as admin

### QA-005 Upper case role fails closed
- Covers: Edge Case 1
- Type: edge
- Given a caller with role "ADMIN"
- When the admin check runs
- Then access is denied and the caller is not treated as admin

### QA-006 Unknown role fails closed
- Covers: Edge Case 1
- Type: edge
- Given a caller with role "superuser"
- When the admin check runs
- Then access is denied and the caller is not treated as admin

### QA-007 Unknown role in escalation check raises PrivilegeEscalationError
- Covers: Edge Case 4
- Type: edge
- Given a caller with role "superuser" and an admin-only action
- When the privilege escalation check runs
- Then PrivilegeEscalationError is raised, not InvalidRoleError

### QA-008 Escalation check rejects user on admin action
- Covers: Failure Mode 2, T2
- Type: failure
- Given a caller with role "user" and an admin-only action
- When the privilege escalation check runs
- Then PrivilegeEscalationError is raised and no data changes

### QA-009 Escalation check allows admin
- Covers: T2
- Type: functional
- Given a caller with role "admin" and an admin-only action
- When the privilege escalation check runs
- Then no error is raised

### QA-010 Escalation check repeated for denied user stays denied
- Covers: Failure Mode 1, repeated action
- Type: failure
- Given a caller with role "user" who was denied once
- When the same admin-only action is tried 3 more times
- Then each try raises PrivilegeEscalationError

### QA-011 Role requirement with non-standard role name
- Covers: T2, Decision (dead code kept)
- Type: failure
- Given a role requirement for the role name "root"
- When the role requirement check runs for a caller with role "admin"
- Then the check returns False and raises nothing (require_role is an equality predicate, see T2 spec)

### QA-012 Role requirement accepts matching role
- Covers: T2
- Type: functional
- Given a role requirement for "user" and a caller with role "user"
- When the role requirement check runs
- Then no error is raised

### QA-013 Rules removed from RBAC are detected
- Covers: Failure Mode 2, Business Goal test
- Type: security
- Given the admin check, the admin flag and the escalation check each changed to always allow (one at a time)
- When the RBAC test file runs
- Then at least one test fails for each of the 3 changes

### QA-014 RBAC coverage is 100 percent
- Covers: Success Metric 1
- Type: performance
- Given the new RBAC test file runs with line coverage on the RBAC module
- When the run ends
- Then coverage is 100% and every public name in the module has at least 1 test

### QA-015 Demoted admin loses admin pages
- Covers: Edge Case 2, Success Metric 2, T3
- Type: security
- Given admin "alice" has an open session and the login lookup now returns her with role "user"
- When the page reruns (auth check, then admin check)
- Then "Admin role required." is shown, the page stops and no data changes

### QA-016 Deactivated admin loses admin pages
- Covers: Edge Case 2, Success Metric 2, T3
- Type: security
- Given admin "bob" has an open session and the login lookup now returns him as inactive
- When the page reruns
- Then he does not reach the admin page and no admin data is shown

### QA-017 User on admin page is denied
- Covers: Failure Mode 1, Success Metric 2, T3
- Type: security
- Given logged-in user "carol" with role "user" in the database
- When she opens an admin-only page
- Then "Admin role required." is shown and the page stops

### QA-018 Session edit alone does not grant admin
- Covers: Edge Case 2, Decision
- Type: security
- Given user "carol" (role "user" in the database) whose session data is edited to say "admin"
- When the page reruns
- Then the database role "user" applies and the admin page is denied

### QA-019 Cookie claiming higher role gives database role
- Covers: Edge Case 3
- Type: security
- Given a cookie signed with the right key that claims role "admin" for user "carol" whose database role is "user"
- When she loads an admin page
- Then she gets role "user" and is denied

### QA-020 Current role fails closed for bad values
- Covers: Edge Case 1, T3
- Type: edge
- Given a logged-in session whose role is "", "ADMIN" or "superuser" (3 runs)
- When the current role is read
- Then each run gives a non-admin result and admin pages stay closed

### QA-021 No session gives no admin
- Covers: Edge Case 1
- Type: failure
- Given no logged-in user
- When the current role is read and an admin page is opened
- Then the result is non-admin and the admin page is denied

### QA-022 Admin principal check fails closed
- Covers: Decision (reviewer change 1), Failure Mode 2
- Type: security
- Given a principal with role "user"
- When the admin principal check runs
- Then access is denied with PrivilegeEscalationError

### QA-023 Admin principal check allows admin
- Covers: Decision (reviewer change 1)
- Type: functional
- Given a principal with role "admin"
- When the admin principal check runs
- Then it is accepted

### QA-024 Admin principal with unknown role denied
- Covers: Edge Case 1, Decision
- Type: edge
- Given a principal with role "ADMIN"
- When the admin principal check runs
- Then access is denied

### QA-025 Guard removal makes UI tests fail
- Covers: Success Metric 2, Decision consequence
- Type: security
- Given the admin guard is removed from the UI layer in a review branch
- When the 3 UI escalation tests run (QA-015, QA-016, QA-017)
- Then all 3 fail

### QA-026 At least 4 new T3 tests pass
- Covers: T3 done_when
- Type: functional
- Given the new UI and principal tests
- When the fast test suite runs with the filter demoted, deactivated, user_on_admin, current_role, require_admin_principal
- Then at least 4 tests run and all pass

### QA-027 No stale ADR-0004 text in core security
- Covers: Success Metric 3, T4
- Type: functional
- Given the repository after the task
- When searching the core security folder for "ADR-0004" and "token_store"
- Then 0 matches are found

### QA-028 No stale text in READMEs
- Covers: Success Metric 3, T4
- Type: functional
- Given the core, core security, UI and tests README files
- When searching them for "ADR-0004" and "token_store"
- Then 0 matches are found

### QA-029 Replaced text cites current ADRs
- Covers: Technical Constraints, T4
- Type: functional
- Given the edited security text
- When a reader checks the RBAC rules (admin manages data, user is read-only)
- Then the rules are still described and cite ADR-0013 and ADR-0003

### QA-030 pyjwt has an exact pin
- Covers: Success Metric 4, T1
- Type: functional
- Given the dependency file
- When searching for "pyjwt"
- Then one line shows "pyjwt==" with a full version, and no range operator

### QA-031 Install resolves with the pin
- Covers: Failure Mode 3, T1
- Type: failure
- Given the pinned pyjwt and streamlit-authenticator 0.4.2
- When the dev install runs
- Then the install exits 0 with no conflict

### QA-032 Dependency audit passes
- Covers: Failure Mode 3, Success Metric 4
- Type: security
- Given the pinned environment
- When pip-audit runs
- Then it exits 0

### QA-033 Pin conflict stops the task
- Covers: Failure Mode 3, Decision
- Type: failure
- Given a pyjwt pin that conflicts with streamlit-authenticator 0.4.2
- When the dev install runs
- Then the install fails and the task is reported as not done

### QA-034 Quality gate passes
- Covers: Success Metric 4
- Type: functional
- Given all 4 tasks done
- When ruff check, ruff format --check, pyright and pytest -m "not integration" run
- Then all 4 exit 0

### QA-035 Mutation gate does not drop
- Covers: Success Metric 4
- Type: performance
- Given the CI mutation score before the task is X percent
- When CI runs the mutation gate after the task
- Then the score is at least X percent

### QA-036 No change to public API, schema or settings
- Covers: Technical Constraints, Decision
- Type: functional
- Given the diff of the task
- When the diff is checked for runtime code, schema migrations and settings
- Then 0 behavior changes are found
