# 0001 — Flask + SQLite foundation skeleton

**Status:** Accepted
**Date:** 2026-11-21

## Context

`amoja-smanager` is an ~8,300-line TypeScript/Next.js social media manager. The
owner wants a Python/Flask implementation, using `amoja-desk` as the reference
for stack and conventions. The first pass is intentionally a skeleton, not a
feature port.

## Decision

- New sibling repository `amoja-smanager-py`; the Next.js app is untouched.
- Flask 3 application factory with Development/Testing/Production configs.
- Flask-SQLAlchemy models and Alembic migrations.
- SQLite for storage: WAL, foreign keys, `synchronous=NORMAL`, 5s busy timeout.
- Jinja2 templates with HTMX fragment navigation, Tailwind CDN and shared CSS
  design tokens copied from Amoja desk. Chart.js is loaded for later analytics.
- pytest with an in-memory SQLite database per test.
- `uv` + Makefile for setup, migrations, tests, lint and formatting.

## Why SQLite

The app is single-owner and self-hosted. Amoja desk proves the pattern: one
writer, one Gunicorn worker, one scheduled worker. SQLite removes Docker and a
database server from the setup. WAL keeps readers responsive.

Trade-off: SQLite has no `SELECT ... FOR UPDATE SKIP LOCKED`. Job claiming will
use `BEGIN IMMEDIATE` transactions and conditional updates instead. If the app
ever needs multi-writer concurrency or live analytics volume, move the same
schema to PostgreSQL; enum values, checks and indexes were kept portable.

## Consequences

- The initial migration is hand-written so CHECK constraints and the functional
  analytics index match the models exactly. Alembic autogenerate does not
  reliably detect CHECK constraints or expression indexes.
- The `analytics_snapshots_observation_unique` index uses
  `coalesce(account_id, '')` / `coalesce(target_id, '')` to emulate
  `NULLS NOT DISTINCT`, which SQLite lacks.
- No authentication, publishing or analytics behaviour exists yet. The shell
  labels itself as a skeleton and makes no platform requests.
