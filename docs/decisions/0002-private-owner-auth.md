# 0002 — Private owner login and opaque sessions

**Status:** Accepted
**Date:** 2026-11-21

## Context

Phase 1 adds a private single-owner login to the Flask skeleton. The original
Next.js app used scrypt, hashed opaque session tokens, a seven-day HttpOnly
cookie, a five-failure/15-minute lockout and a per-request guard. The Flask port
must preserve those properties on SQLite without `SELECT ... FOR UPDATE`.

## Decision

### Credentials

- Exactly one `users` row, fixed `id = 'owner'`.
- Usernames are trimmed, lowercased and limited to `[a-z0-9_.-]{3,64}`.
- Owner passwords are 12–128 characters; login input is 1–128.
- Passwords use `hashlib.scrypt` with `N=2^17, r=8, p=1`, a 16-byte random salt
  and a 64-byte key, stored as `scrypt-v1:<salt>:<key>`. Verification uses
  `hmac.compare_digest`. No plaintext is stored or logged.

### Sessions

- Tokens are 256-bit `secrets.token_urlsafe(32)` values (43 characters).
- Only the SHA-256 hex digest is stored in `sessions.token_hash`.
- The cookie is `amoja_session`, HttpOnly, SameSite=Lax, path `/`, seven days,
  and Secure outside development/testing.
- A successful login rotates any previous token, purges expired rows and resets
  the failure budget. Sign-out deletes the row and clears the cookie.

### CSRF

Flask-WTF protects every POST. Flask's session cookie is explicitly named
`amoja_csrf`, separate from `amoja_session`.

This separation is deliberate: an earlier implementation reused Flask's
`SESSION_COOKIE_NAME` for the auth cookie, so the CSRF session and auth token
overwrote each other. A regression test now asserts both cookies exist, differ,
and that the auth value hashes to a stored session.

### Lockout

- Five consecutive failures set `locked_until = now + 15 minutes`.
- While locked, even correct credentials are rejected.
- After the lock expires, the next failure restarts the budget at one.
- SQLite has no row-level `FOR UPDATE`. `authenticate` issues `BEGIN IMMEDIATE`
  before reading the owner row, taking the database write lock so concurrent
  attempts cannot share one failure slot. On PostgreSQL this should become
  `SELECT ... FOR UPDATE`.

### Guarding and redirects

- The private `web_bp` blueprint has a `before_request` guard, so new pages are
  protected by default.
- Unauthenticated HTML requests redirect to `/login?next=…`; HTMX requests get
  `401` plus `HX-Redirect`, which makes the browser perform a full navigation.
- `next` must be a local path. Scheme, host, `//` and backslashes are rejected.
- Authenticated responses and auth pages send `Cache-Control: no-store`.

### Provisioning

`flask --app src.app create-owner` (wrapped by `make owner`) creates the owner.
It is idempotent and refuses to overwrite existing credentials. `AUTH_USERNAME`
and `AUTH_PASSWORD` support non-interactive provisioning.

## Consequences

- Login verification is intentionally CPU- and memory-expensive and runs while
  holding SQLite's write lock. This is acceptable for one owner and a single
  web worker, and it makes the failure budget deterministic.
- There is no password-reset UI. Rotating a forgotten password requires a
  deliberate operator step; adding a safe reset path is future work.
- There is no MFA or "remember me" option; the session lifetime is fixed at
  seven days.
- Moving to PostgreSQL requires replacing `BEGIN IMMEDIATE` with a row lock while
  preserving the same failure-budget semantics.
