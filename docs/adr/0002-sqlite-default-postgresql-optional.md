# SQLite by default, PostgreSQL optional

## Context

The storage layer (`storage/database.py`, `storage/repositories.py`) must run with zero setup for the CLI, tests and local development, but the API service needs a server database in production.

## Decision

SQLite via `aiosqlite` is the default. `MOVIECON_DB_BACKEND=postgresql` selects PostgreSQL (`asyncpg`, optional `postgresql` extra), which reads its connection string from `MOVIECON_DATABASE_URL` or `DATABASE_URL`. Both schemas are defined side by side in `database.py` and all access goes through the `*Repository` classes with parameterized queries.

## Consequences

- Every schema change must be made in both the SQLite and PostgreSQL definitions.
- Tests run against SQLite only; the PostgreSQL path has no automated coverage.
