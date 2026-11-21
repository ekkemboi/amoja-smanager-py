# Amoja Social Manager (Flask)

A private, self-hosted social media scheduler for Instagram, Facebook Pages,
TikTok, X and YouTube. This is the **Python/Flask port** of
[`amoja-smanager`](../amoja-smanager), built on the conventions used by
[`amoja-desk`](../amoja-desk).

> **Current state: foundation + private login.** The app factory, SQLite schema,
> migrations, single-owner sign-in, session guards and dashboard shell exist.
> There is no composer, scheduler, publisher or analytics provider yet. Nothing
> contacts a social platform.

## Stack

| Concern | Choice |
| --- | --- |
| Language | Python 3.12+ |
| Web framework | Flask 3 app factory |
| Database | SQLite (WAL, foreign keys, busy timeout) |
| ORM | SQLAlchemy + Flask-SQLAlchemy |
| Migrations | Alembic |
| UI | Jinja2 server-rendered templates |
| Interactivity | HTMX (fragment navigation) |
| Styling | Tailwind CDN + shared CSS design tokens |
| Charts | Chart.js (loaded, unused until analytics) |
| Tests | pytest on in-memory SQLite |
| Tooling | `uv`, Make, Ruff |

SQLite is deliberate for a single-user app. Writes are serialized, so run a
single Gunicorn worker and a single scheduled publishing worker. The schema and
enum values are kept portable so PostgreSQL can replace SQLite later.

## Quick start

```sh
cp .env.example .env      # optional; development has safe defaults
make init                 # uv sync + alembic upgrade head
make owner                # create the single owner account (prompts)
make dev                  # http://127.0.0.1:5000
```

Health check: `GET /healthz`.

## Commands

```sh
make help                 # list tasks
make owner                # create the owner account (or AUTH_USERNAME/AUTH_PASSWORD)
make test                 # pytest on in-memory SQLite
make check                # compile sources + tests
make lint                 # ruff check
make format               # ruff format
make migrate              # apply migrations
make migration m="..."    # autogenerate a revision
make downgrade            # roll back one revision
make db-shell             # sqlite3 prompt
make db-backup            # consistent copy in backups/
make db-reset CONFIRM=yes # destructive reset
```

## Structure

```
src/
  app.py                  # Flask app factory, headers, health check
  cli.py                  # `create-owner` provisioning command
  config.py               # Dev/Test/Prod configuration
  models.py               # SQLAlchemy models and SQLite pragmas
  services/auth.py        # passwords, sessions, lockout, provisioning
web/
  navigation.py           # shared sidebar metadata
  routes/__init__.py      # private page blueprint + session guard
  routes/auth.py          # sign-in and sign-out
  templates/              # login, Jinja2 shell and placeholder pages
  static/                 # CSS design tokens and shell JS
migrations/               # Alembic environment and revisions
tests/                    # pytest fixtures and smoke tests
docs/decisions/           # architecture decision records
```

## Data model

The initial schema mirrors the TypeScript implementation:

- `users`, `sessions` — private owner login and hashed session tokens
- `social_accounts` — platform, handle, mode and encrypted credentials
- `posts`, `post_targets`, `media` — drafts, per-account variants and uploads
- `publish_jobs`, `publish_attempts` — durable jobs with leases and history
- `analytics_snapshots` — metric observations with explicit provenance

Checks, unique constraints and indexes are in the models and the initial
migration. Only `users` and `sessions` are queried so far, by authentication.

## Authentication

- One owner account, created with `make owner` (idempotent; existing credentials
  are never overwritten).
- Passwords use salted scrypt (`N=2^17, r=8, p=1`) and are stored as
  `scrypt-v1:<salt>:<key>`; plaintext is never stored or logged.
- Sign-in issues a random 256-bit opaque token. The cookie carries the token;
  only its SHA-256 hash is stored in `sessions`.
- The `amoja_session` cookie is HttpOnly, SameSite=Lax, path `/`, valid for
  seven days, and Secure in production.
- A separate `amoja_csrf` Flask session cookie holds the CSRF token. Every POST
  (sign-in, sign-out) is CSRF protected.
- Five failed attempts lock sign-in for 15 minutes. Attempts are serialized with
  SQLite `BEGIN IMMEDIATE`, so concurrent workers cannot share one failure slot.
- Successful sign-in rotates the previous token, clears expired sessions and
  resets the failure budget. Sign-out deletes the session row and clears the
  cookie.
- Every page in the private blueprint is guarded by a request-time check.
  Open redirects in `?next=` are rejected. Authenticated responses use
  `Cache-Control: no-store`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `FLASK_ENV` | `development`, `testing` or `production` |
| `SECRET_KEY` | Flask session signing key; required in production |
| `DATABASE_URL` | SQLite location, default `instance/amoja-smanager.db` |
| `APP_TIMEZONE` | Presentation timezone, default `UTC` |
| `MEDIA_ROOT` | Private upload directory, default `instance/media` |
| `MAX_CONTENT_LENGTH` | Upload ceiling in bytes, default 100 MiB |
| `AUTH_USERNAME` | Optional non-interactive owner username for `make owner` |
| `AUTH_PASSWORD` | Optional non-interactive owner password for `make owner` |

Never commit `.env` or credentials. Production refuses to start without
`SECRET_KEY`.

## Production

```sh
SECRET_KEY=... uv run gunicorn --bind 0.0.0.0:5000 --workers 1 --timeout 120 "src.app:create_app()"
```

Set `SECRET_KEY`, then create the owner once with `make owner` or by setting
`AUTH_USERNAME`/`AUTH_PASSWORD` for the command. Put a reverse proxy with HTTPS
in front, back up `instance/` regularly, and run the publishing worker as a
single scheduled process once it exists.

## Port roadmap

See [`PLAN.md`](PLAN.md). Next: the publishing contract and deterministic mock
adapter, then draft CRUD, media uploads and platform variants, scheduling, manual
fallback, analytics, and hardening. Live platform integrations remain post-MVP
and require explicit approval.

## License

Released under the [MIT License](LICENSE). Third-party dependencies remain under
their respective licenses.
