# QA cases: admin-user-management

Tenant A has admins admin1@a.example and admin2@a.example, and user bob@a.example. Tenant B has admin admin@b.example and user eve@b.example.

### QA-001 Admin creates a user who then logs in
- Covers: Business Goals test, T6
- Type: functional
- Given admin1@a.example is logged in to tenant A
- When admin1 creates carol@a.example, role user, name "Carol Nowak", password "correct-horse-12"
- Then carol@a.example logs in with that password and lands in tenant A

### QA-002 Admin deactivates a user who then cannot log in
- Covers: Business Goals test, T3, T6
- Type: functional
- Given bob@a.example is active and can log in
- When admin1 deactivates bob@a.example
- Then a new login by bob@a.example with the correct password is refused

### QA-003 Old cookie of a deactivated user fails
- Covers: Success Metric 1, T3
- Type: security
- Given bob@a.example holds a valid session cookie
- When admin1 deactivates bob and bob sends the old cookie on the next request
- Then the request is refused because the session version differs from the stored one

### QA-004 New user joins the admin's tenant, not a form tenant
- Covers: Business Goals (tenant from context), T4
- Type: security
- Given admin1@a.example is logged in to tenant A and the form has no tenant field
- When admin1 creates dave@a.example
- Then the user list of tenant A shows dave@a.example and the list of tenant B does not

### QA-005 List shows own tenant users only, ordered by email
- Covers: Success Metric 2, T2
- Type: functional
- Given tenant A has admin1, admin2, bob and tenant B has admin@b.example and eve@b.example
- When admin1 opens the users page
- Then the page shows admin1@a.example, admin2@a.example, bob@a.example in that order and 0 tenant B rows

### QA-006 List never shows hash or session version
- Covers: Failure Mode (never show password), T2
- Type: security
- Given tenant A has 3 users
- When admin1 views the list
- Then no row shows a password, a hash or a session version

### QA-007 Duplicate email in own tenant
- Covers: Edge Case 1, T2, T7
- Type: edge
- Given bob@a.example exists in tenant A
- When admin1 creates bob@a.example with password "correct-horse-12"
- Then the page shows "Cannot create this user." and the list still holds one bob@a.example

### QA-008 Duplicate email in another tenant
- Covers: Edge Case 1, T2, T7
- Type: edge
- Given eve@b.example exists in tenant B
- When admin1 creates eve@b.example
- Then the page shows exactly "Cannot create this user." and the text is identical to the own tenant duplicate

### QA-009 Duplicate email differs only by case and spaces
- Covers: Edge Case 2, T4
- Type: edge
- Given bob@a.example exists
- When admin1 submits "  BOB@A.Example " as the email
- Then the page shows "Cannot create this user." and no second row exists

### QA-010 Email is trimmed and lowercased
- Covers: Edge Case 2, T4
- Type: functional
- Given no user frank@a.example exists
- When admin1 creates a user with email "  Frank@A.Example "
- Then the list shows frank@a.example

### QA-011 Blank email refused
- Covers: Edge Case 2, T4
- Type: failure
- Given admin1 is logged in
- When admin1 submits an email of 3 spaces
- Then the page shows a clear input error and no user is created

### QA-012 Malformed email refused
- Covers: Edge Case 2, T4
- Type: failure
- Given admin1 is logged in
- When admin1 submits "no-at-sign.example" and then "a@@b.example"
- Then both attempts show an input error and create 0 users

### QA-013 Email length limit
- Covers: Technical Constraints (email max 256), T4
- Type: edge
- Given admin1 is logged in
- When admin1 submits an email of 257 characters, then one of exactly 256 characters
- Then the 257 character email is refused and the 256 character email is created

### QA-014 Name length limit
- Covers: Technical Constraints (name max 256), T4
- Type: edge
- Given admin1 is logged in
- When admin1 submits a name of 257 characters, then one of 256 characters
- Then the 257 character name is refused and the 256 character name is created

### QA-015 Password shorter than 12 characters
- Covers: Technical Constraints (password), T4
- Type: failure
- Given admin1 is logged in
- When admin1 creates a user with password "short-pw-11" (11 characters)
- Then the page shows an input error and no user is created

### QA-016 Password of exactly 12 characters
- Covers: Technical Constraints (password), T4
- Type: edge
- Given admin1 is logged in
- When admin1 creates grace@a.example with password "abcdefghijkl"
- Then the user is created and logs in with that password

### QA-017 Password of 72 bytes and 73 bytes
- Covers: Technical Constraints (72 UTF-8 bytes), T4
- Type: edge
- Given admin1 is logged in
- When admin1 submits a 72 byte ASCII password, then a 73 byte ASCII password
- Then the 72 byte password is accepted and the 73 byte password is refused

### QA-018 Multibyte password over 72 bytes
- Covers: Technical Constraints (UTF-8 bytes), T4
- Type: edge
- Given admin1 is logged in
- When admin1 submits a password of 37 characters "ł" (74 bytes)
- Then the password is refused although it has fewer than 72 characters

### QA-019 Role outside the valid set refused
- Covers: Edge Case 3, T4
- Type: failure
- Given admin1 is logged in
- When a create call arrives with role "superadmin"
- Then it is refused and no user is created

### QA-020 Admin creates an admin
- Covers: Technical Constraints (both roles), T4
- Type: functional
- Given admin1 is logged in
- When admin1 creates henry@a.example with role admin
- Then henry logs in and sees the users page

### QA-021 Deactivate is idempotent
- Covers: Edge Case 4, T3
- Type: edge
- Given bob@a.example is inactive and has session version 5
- When admin1 deactivates bob again
- Then no error shows and bob's session version stays 5

### QA-022 Deactivate an id from another tenant
- Covers: Edge Case 5, T3
- Type: security
- Given eve@b.example has a known id in tenant B
- When admin1 deactivates that id
- Then the result equals the result for a missing row and eve stays active

### QA-023 Deactivate an unknown id
- Covers: Edge Case 5, T3
- Type: failure
- Given no user has id 00000000-0000-4000-8000-000000000000
- When admin1 deactivates that id
- Then the page shows a not found message and no row changes

### QA-024 Self-deactivation refused
- Covers: Technical Constraints (self), T3
- Type: failure
- Given admin1 and admin2 are active admins
- When admin1 deactivates admin1
- Then the call is refused and admin1 stays active

### QA-025 Last active admin cannot be deactivated
- Covers: Technical Constraints (last admin), T3
- Type: failure
- Given tenant A has exactly 2 active admins, admin1 and admin2, in two separate DB sessions
- When admin1 deactivates admin2 and admin2 deactivates admin1 at the same time
- Then exactly one call succeeds, the other raises LastAdminError, and exactly 1 admin stays active
- Note: a single admin that deactivates itself gets SelfDeactivationError, because self is checked first. LastAdminError is reachable by the race above, or by a store-level call whose actor id is not an admin of the tenant.

### QA-026 Deactivating one of two admins succeeds
- Covers: Technical Constraints (last admin), T3
- Type: functional
- Given tenant A has exactly 2 active admins, admin1 and admin2
- When admin1 deactivates admin2
- Then admin2 is inactive and admin1 remains the single active admin

### QA-027 Self check comes before last-admin check
- Covers: Decision (self before last admin), T3
- Type: edge
- Given admin1 is the only active admin of tenant A
- When admin1 deactivates admin1
- Then the refusal is the self-deactivation error, not the last admin error

### QA-028 Concurrent deactivation of the last two admins
- Covers: Edge Case 6, T3
- Type: edge
- Given tenant A has exactly 2 active admins, admin1 and admin2, in two sessions
- When admin1 deactivates admin2 and admin2 deactivates admin1 at the same time
- Then exactly 1 admin stays active and no deadlock error reaches the admin

### QA-029 Role user opens the page URL directly
- Covers: Edge Case 7, T7
- Type: security
- Given bob@a.example (role user) is logged in
- When bob opens the users page URL
- Then the page shows "Admin role required." and loads 0 user rows

### QA-030 Role user calls create at service level
- Covers: Success Metric 3, T4, T6
- Type: security
- Given bob@a.example (role user) is the current principal in tenant A
- When bob calls create for zed@a.example
- Then the call is refused and 0 users are created

### QA-031 Role user calls deactivate at service level
- Covers: Success Metric 3, T4, T6
- Type: security
- Given bob is the current principal and admin2 is active
- When bob calls deactivate for admin2
- Then the call is refused and admin2 stays active

### QA-032 Demoted or deactivated admin loses the page
- Covers: Edge Case 8, T7
- Type: security
- Given admin2 is logged in and admin1 then deactivates admin2
- When admin2 sends the next request to the users page
- Then admin2 gets no page and no data

### QA-033 Admin principal not found in tenant refused
- Covers: Decision (actor row check), T4
- Type: security
- Given a principal with admin role and email ghost@a.example that has no row in tenant A
- When it calls create
- Then the call is refused and 0 users are created

### QA-034 Admin of tenant B cannot act on tenant A
- Covers: Success Metric 2, T2, T3
- Type: security
- Given admin@b.example is logged in to tenant B
- When admin@b.example deactivates the id of bob@a.example
- Then the result is not found and bob stays active

### QA-035 No tenant set at service level
- Covers: Technical Constraints (empty tenant), T4
- Type: security
- Given an admin principal with no tenant set
- When it calls create, list and deactivate
- Then each call is refused and no SQL changes any row

### QA-036 Leak test with no tenant at store level
- Covers: Success Metric 2, T2, T3
- Type: security
- Given tenants A and B hold 5 users in total and no tenant is set
- When list, insert and deactivate run at store level
- Then list returns 0 rows, insert raises an error and deactivate changes 0 rows

### QA-037 Leak test with tenant set
- Covers: Success Metric 2, T2
- Type: security
- Given tenant A is set and tenant B holds 2 users
- When list runs and insert runs
- Then 0 tenant B rows are read and the new row has tenant A

### QA-038 DB error on create is generic and creates nothing
- Covers: Failure Mode 1, T7
- Type: failure
- Given the database raises a connection error during create
- When admin1 creates ivan@a.example
- Then the page shows a generic error without a stack trace. When the rollback is confirmed, ivan does not exist
- And if the commit outcome is unknown (the connection failed after the commit), the message tells the admin to check the user list, and a retry gives the duplicate message, not a second user

### QA-039 DB error on deactivate changes nothing
- Covers: Failure Mode 1, T3
- Type: failure
- Given the database fails during deactivation of bob
- When admin1 deactivates bob
- Then the page shows a generic error and tells the admin to check the user list. When the rollback is confirmed, bob stays active. A retry after an unknown outcome is an idempotent no-op

### QA-040 Non-duplicate integrity error is not shown as duplicate
- Covers: Failure Mode 1, T2
- Type: failure
- Given a database constraint other than the unique email fails on create
- When admin1 creates judy@a.example
- Then the page shows the generic error, not "Cannot create this user."

### QA-041 Logs hold no password or hash
- Covers: Failure Mode 2, T4
- Type: security
- Given logs are captured and admin1 creates kim@a.example with password "Sup3r-secret-pw!"
- When create succeeds and then fails on a duplicate
- Then the captured logs hold neither "Sup3r-secret-pw!" nor any bcrypt hash starting with "$2"

### QA-042 Audit event on create and deactivate
- Covers: Failure Mode 3, T4
- Type: functional
- Given logs are captured
- When admin1 deactivates bob
- Then one audit event holds admin1's id, bob's id, action deactivate and a changed flag of true

### QA-043 Audit event on idempotent deactivate
- Covers: Failure Mode 3, T4
- Type: edge
- Given bob is already inactive and logs are captured
- When admin1 deactivates bob
- Then the audit event shows a changed flag of false

### QA-044 Login lookup down keeps login behaviour
- Covers: Failure Mode 4
- Type: failure
- Given the redis or login lookup is down
- When any user logs in
- Then the login behaviour equals the behaviour before this change

### QA-045 Invalid input shows no stack trace
- Covers: Failure Mode 5, T7
- Type: failure
- Given admin1 is logged in
- When admin1 submits every invalid input from QA-011 to QA-019
- Then each time the page shows a fixed message and no stack trace

### QA-046 Page action time
- Covers: Success Metric 6, T6
- Type: performance
- Given local Postgres holds tenant A with 100 users
- When admin1 creates a user, lists users and deactivates a user
- Then each action returns in under 1 second

### QA-047 Repeated create submit
- Covers: Edge Case 1, T7
- Type: edge
- Given admin1 submits the form for lena@a.example and the first call succeeded
- When admin1 submits the same form again
- Then the page shows "Cannot create this user." and one lena exists

### QA-048 Privilege escalation refused
- Covers: Success Metric 4, T6
- Type: security
- Given bob (role user) tries to create an admin account for himself
- When the call runs at service level
- Then it is refused and bob stays role user

### QA-049 Port and store stay in step
- Covers: Success Metric 4, T5
- Type: functional
- Given the user repository contract has 4 methods
- When the conformance test compares the real store with the contract
- Then the 4 method names and parameters match

### QA-050 Coverage and mutation gates
- Covers: Success Metric 5, T8
- Type: functional
- Given all new code is in place
- When the repo coverage and mutation gates run on the user service code
- Then both gates pass at the thresholds in CONTRIBUTING.md

### QA-051 Seed script still creates users
- Covers: Decision (create_user signature kept)
- Type: functional
- Given an empty database
- When the seed script runs
- Then it creates its users with the same fields as before
