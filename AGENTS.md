# AGENTS.md

## Cursor Cloud specific instructions

EduOS Backend is a single Django 5 + DRF product (a multi-tenant School ERP JSON API). There is no frontend in this repo. Standard commands live in `README.md` and the `Makefile`; only the non-obvious caveats are captured below.

### Environment
- Python deps are installed into a virtualenv at `.venv/` (gitignored). Run tools via `.venv/bin/<tool>` or `source .venv/bin/activate` first. `make`/`manage.py` commands assume the venv is active.
- Dev defaults require **no external services**: `config.settings.dev` uses SQLite (`db.sqlite3`), local-memory cache, eager (synchronous) Celery, and sandbox/stub integrations (S3/R2, Razorpay, MSG91, Anthropic). Postgres/Redis are only needed if you opt in via `USE_POSTGRES=true` / `USE_REDIS=true` or `make docker-up`.
- `.env` is gitignored. Local/cloud secrets (Neon `DB_*`, R2 keys, `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY`) belong in `.env` and/or Cursor secrets — never commit them. `config/env.py` loads `.env` at startup and **overwrites** matching process env vars.
- `DATABASE_URL` in `.env` is **not** read by Django settings. Postgres is selected only when `USE_POSTGRES=true` (or `USE_SQLITE=false`); otherwise the `DB_*` Neon credentials are ignored and SQLite is used. With `S3_MODE=live` + R2 keys, gallery uploads hit the real Cloudflare R2 bucket (not the in-memory sandbox).
- WeasyPrint (PDF generation) needs system libs (`libpango-1.0-0`, `libpangocairo-1.0-0`, `libgdk-pixbuf-2.0-0`, `libffi`, `shared-mime-info`) and `libpq-dev`; these are baked into the VM image, not the update script.

### Running the app
- `make dev` (i.e. `python manage.py runserver`) serves on port 8000. Run `make migrate` first on a fresh database (the update script does NOT run migrations).
- There is no bundled UI or OpenAPI/Swagger route — test via HTTP clients (curl/httpx) against `/api/v1/...`.
- The `/health/` route is a stub with no endpoints registered (`apps/core/urls.py`), so it returns 404 — do not use it as a readiness check.

### Tests (important gotcha)
- The committed `pytest.ini` is empty, which causes pytest to ignore the `[tool.pytest.ini_options]` config in `pyproject.toml` (including `DJANGO_SETTINGS_MODULE`). Plain `pytest` / `make test` therefore fail with `ImproperlyConfigured: Requested setting AUTH_USER_MODEL`.
- Run tests with the settings module set explicitly: `DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/pytest`. The test settings use in-memory SQLite and are fully hermetic.
- A subset of tests currently fail/error on `main` (pre-existing test-data/fixture issues, e.g. `UNIQUE constraint` in `academics_academic_period`), independent of environment setup. `ruff check` also reports many pre-existing lint errors.

### Seeding & auth (for manual API testing)
- `make seed` is broken (it calls a nonexistent `seed_demo_data` command). Seed demo tenants instead with `.venv/bin/python seed_db.py` (idempotent). It creates tenants `greenfield`, `horizon`, `riverside`, each with super_admin/admin/faculty/student, all password `Password123!` (platform owner: `Platform@123`).
- Login (`POST /api/v1/auth/login/`) requires `identifier`, `password`, `role`, and `tenant_id` (a UUID). Also send the `X-Tenant-ID` header so tenant middleware scopes the request.
- Identifier is the **phone number** for `admin`/`parent` roles and the **custom login id** (e.g. `FAC-001`, `STU-001`) for `faculty`/`student`.
- `admin`/`super_admin`/`platform_owner` are passwordless (email OTP / MFA) — password login is rejected for them. For simple end-to-end auth testing use `faculty` or `student`, which use password login and return a JWT access/refresh pair.
