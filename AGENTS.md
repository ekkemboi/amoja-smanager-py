# Amoja Social Manager — Agent Guidelines

A private social media scheduler ported from `../amoja-smanager` (Next.js) to
Flask, following the conventions of `../amoja-desk`. Read `PLAN.md` before
changing code.

## Current scope

The repository has a **foundation plus private login**. It has an app factory,
SQLite schema, Alembic migrations, single-owner sign-in with session guards, a
Jinja/HTMX dashboard shell and tests. It does **not** have a composer, media
uploads, a scheduler, a publisher or analytics. Do not describe those as
implemented.

## Build & development

```bash
cp .env.example .env          # optional in development
make init                     # uv sync + alembic upgrade head
make owner                    # create the single owner account
make dev                      # http://127.0.0.1:5000
make test                     # pytest on in-memory SQLite
make check                    # compile + tests
make lint                     # ruff check
make format                   # ruff format
```

Run a single test:

```bash
uv run pytest tests/test_pages.py::test_healthz_reports_ok -v
```

## Project structure

```
src/
  app.py         # Flask app factory, security headers, /healthz
  cli.py         # create-owner command
  config.py      # Development / Testing / Production configs
  models.py      # SQLAlchemy models + SQLite pragmas
  services/      # Business logic; auth.py holds passwords and sessions
web/
  navigation.py  # Sidebar items
  routes/        # web is guarded; auth.py handles login/logout
  templates/     # login.html, base.html + one template per page
  static/        # css/app.css and js/app.js
migrations/     # Alembic env and versions
tests/          # pytest fixtures and tests
```

## Code style

- Python 3.12, 88-column lines, Ruff rules `E,F,I,N,W,UP`.
- Absolute imports: `from src.models import Post`.
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE` constants.
- Blueprints use the `_bp` suffix: `web_bp`.
- Public functions get a one-line docstring.
- Routes handle HTTP; business logic belongs in `src/services/`.
- Keep SQLite-specific behaviour out of services so a PostgreSQL move stays possible.

## Database

- SQLite is intentional. Do not add a database server or Docker dependency.
- Migrations are the only schema source. Never use `db.create_all()` outside tests.
- SQLite runs with `foreign_keys=ON`, WAL, `synchronous=NORMAL` and a 5s busy timeout.
- SQLite is single-writer: keep one web worker and one publishing worker.
- Authentication serializes failed attempts with `BEGIN IMMEDIATE`. Do not
  replace it with a plain read-then-write without preserving that guarantee.
- Run `make db-backup` before destructive schema work.

## Non-negotiable product rules

- Mock-first: all flows must work offline. Simulated output is always labelled.
- Ports and adapters: services depend on `Publisher` / `AnalyticsProvider`
  interfaces, never platform SDKs.
- Per-account mode is `mock | api | browser | manual`, snapshotted per attempt.
- Never silently fall back from API to browser automation.
- Never make real social platform requests during tests.
- Browser automation is optional and only for authorized, platform-permitted work.
- Publishing jobs must be safe under restarts, concurrency and uncertain outcomes.
- Secrets come from environment variables. Never commit `.env` or credentials.
- Passwords use salted scrypt. Session tokens are random, stored only as
  SHA-256 hashes, and carried in the HttpOnly `amoja_session` cookie.
- Keep the auth cookie and the Flask CSRF cookie (`amoja_csrf`) separate.
- Every POST is CSRF protected. Every private route is guarded at request time.
- Five failed sign-ins lock the owner for 15 minutes. Never log credentials.
- Present times in `APP_TIMEZONE`; store UTC.

## Work discipline

1. Read `PLAN.md` and this file first.
2. Work on one unchecked task at a time and inspect what already exists.
3. Explain intended changes before implementing.
4. Add focused tests, run `make check` (and `make lint`), and report exact results.
5. Update `PLAN.md` checkboxes only after verification.
6. Ask before changing architecture, adding services, or implementing live integrations.
