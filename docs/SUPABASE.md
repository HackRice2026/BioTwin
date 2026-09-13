# Supabase database

BioTwin can use hosted Supabase Postgres through its existing SQLAlchemy
storage layer. The FastAPI server remains the only data API: browser code must
not receive a database password, service-role key, or direct access to health
tables.

## Data ownership

- `users.email` is unique and identifies the login account.
- Internal `users.id` values are the stable foreign keys. Email addresses are
  not copied into every health row, so an email change does not orphan data.
- `measurements.user_id` owns every normalized Garmin, Fitbit, replay,
  Bluetooth, Influx-backfill, or synthetic frame.
- `measurements.dedupe_key` makes repeated Garmin deliveries idempotent per
  account.
- Derived baselines, readiness results, plans, predictions, provider tokens,
  and calendar caches live in `documents` under the same user ID.
- Sessions and conversations are also account-scoped and are deleted with the
  owning account.

## Provision with Supabase MCP

Use the official project-scoped MCP server. Substitute the project reference;
do not commit it if the repository will be public.

```sh
codex mcp remove supabase
codex mcp add supabase \
  --url "https://mcp.supabase.com/mcp?project_ref=PROJECT_REF&features=database%2Cdocs"
codex mcp login supabase \
  --scopes "projects:read,database:read,database:write"
```

Apply `supabase/migrations/202609120001_biotwin_schema.sql` through the MCP
database migration tool. The migration enables row-level security and revokes
the Supabase `anon` and `authenticated` browser roles because BioTwin uses its
own server-managed sessions. Do not add permissive RLS policies unless the app
is deliberately migrated to Supabase Auth in a separate change.

## Connect the server

Copy the Supabase **direct/session-mode** PostgreSQL connection string from the
project's Connect panel and adapt its scheme for the installed psycopg driver:

```env
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@HOST:5432/postgres?sslmode=require
```

Use the direct connection on an IPv6-capable host. On an IPv4-only network,
select **Session pooler** in the Connect panel and use the displayed pooler
host plus the `postgres.PROJECT_REF` username. A direct hostname that fails to
resolve locally is an IPv4/IPv6 routing issue; it is not evidence of a bad
database password.

Keep this only in `.env` or the deployment secret store. Never put the database
password in Git, frontend variables, screenshots, or chat. If the password has
special URL characters, URL-encode it.

Start BioTwin normally. All current storage operations then use Supabase:

```sh
uv run uvicorn core.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Garmin data enters through the existing ingestion adapters and is written to
`measurements` after normalization. The API resolves the signed-in session to
one internal user ID, so reads and writes remain isolated by account.

To transfer one existing local SQLite account, including its password hash,
measurements, derived documents, active sessions, and conversations:

```sh
PYTHONPATH=. uv run scripts/migrate_sqlite_account.py --email user@example.com
```

The command reads the target from `DATABASE_URL`, copies only the requested
account's rows, and is safe to repeat because it uses the schema's stable keys.

## Verification

After the MCP migration and `DATABASE_URL` update:

1. Register two temporary accounts with different emails.
2. Ingest or sync Garmin data into only the first account.
3. Confirm the first account can read its measurements and the second cannot.
4. Repeat the same Garmin delivery and confirm the dedupe constraint prevents
   a duplicate.
5. Export and delete the first account; confirm all dependent rows are gone.
6. Run `uv run pytest -q` and the PostgreSQL contract tests with a dedicated
   `TEST_POSTGRES_URL`.
