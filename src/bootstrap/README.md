# Bootstrap

This package is the init program. Run it with `python -m bootstrap`.

It does these steps in this order:

1. It checks the configuration. It makes no network call in this step.
2. It runs the database migrations.
3. It creates the S3 bucket if the bucket is missing.
4. It creates the first tenant if the tenant is missing.
5. It creates the first admin if the user is missing.

Each step checks the state first. A second run creates nothing.
The program never changes an existing user. It never resets a password or a role.

The program tries to connect to Postgres and S3 up to 5 times. The wait doubles after each try.

| Exit code | Meaning |
|---|---|
| 0 | All steps are done or were done before |
| 2 | The configuration is not valid |
| 3 | Postgres or S3 did not answer after all tries |
| 4 | A step failed. The log names the step |

The log has one line for each step: `step=<name> result=created|exists|failed`.
The log never shows a password, a key, or a URL.

- `init_stack.py`: the steps and the exit codes.
- `__main__.py`: the entry point.
