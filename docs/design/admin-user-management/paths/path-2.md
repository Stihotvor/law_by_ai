# Path 2: hexagonal service layer
New `src/core/users/` with `service.py`, `ports.py` (`UserRepository`) and `errors.py`. The service owns the admin check, validation, hashing, error mapping and audit. `PostgreSQLStore` implements the port. The page maps form fields to service calls and errors to messages.
- Deactivate: the service refuses self by email. The store takes `FOR UPDATE` on active admin rows, recounts, then updates. An inactive target returns early.
- Tests: a fake port gives cheap unit tests and a zero-call assertion for role `user`. Real Postgres covers integration.
- Effort: M.
- Risks: self-match by email. The lock needs a two-session test. The port and the store can drift, so a conformance test is needed. `create_user` cannot be reused as is.
