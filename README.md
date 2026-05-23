# EduOS Backend

Multi-tenant, role-based Education Management Platform API built with **Django 5 + DRF**.

## Quick Start

```bash
# 1. Clone and enter
cd eduOS-backend

# 2. Create virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements-dev.txt

# 4. Set up environment
cp .env.example .env  # Edit with your DB credentials

# 5. Start services (PostgreSQL + Redis)
make docker-up  # or start them manually

# 6. Run migrations
make migrate

# 7. Start development server
make dev
```

## Architecture

```
URL → View → Serializer (validate) → Service or Selector → Model → Serializer (response) → View
```

- **Views**: Thin controllers — auth, permissions, call service/selector, return response
- **Services**: Write / business logic — create, update, delete, workflows, external APIs
- **Selectors**: Read logic — optimized queries, filters, lists, detail fetches
- **Serializers**: Input validation and output shape for the API

## Project Structure

```
eduOS-backend/
├── manage.py
├── config/                     # Project configuration
│   ├── __init__.py             # Celery app import
│   ├── settings/
│   │   ├── base.py             # Shared settings
│   │   ├── dev.py              # Development overrides
│   │   └── prod.py             # Production overrides
│   ├── urls.py                 # Root URL config
│   ├── celery.py               # Celery app
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/                   # Shared: base models, permissions, pagination, middleware
│   ├── accounts/               # Users, auth, JWT, MFA, invites, sessions
│   ├── organizations/          # Institutions (tenants), branches, plans, feature flags
│   ├── academics/              # Academic years, departments, courses, timetable
│   ├── admissions/             # Enquiries, applications, enrollments
│   ├── attendance/             # Attendance sessions, records, leave requests
│   ├── examinations/           # Exams, marks, results, hall tickets, assignments
│   ├── fees/                   # Fee structures, invoices, payments, receipts, refunds
│   ├── hr/                     # Employees, leave, payroll, salary slips
│   ├── communications/         # Announcements, notifications, SMS, email
│   ├── analytics/              # Audit logs, reports, data exports, job tracking
│   └── integrations/           # Razorpay, MSG91, S3, AI adapters, webhooks, outbox
├── requirements.txt
├── requirements-dev.txt
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── pyproject.toml
```

Each app follows:
```
apps/<app>/
├── models/           # Database schema
├── serializers/      # Input validation & output shape
├── views/            # Thin controllers
├── services/         # Write / business logic
├── selectors/        # Read / query logic
├── tests/            # Tests + factories
├── migrations/
├── management/commands/
├── urls.py
├── admin.py
├── apps.py
├── tasks.py          # Celery async jobs
├── permissions.py
├── enums.py
├── constants.py
├── signals.py
└── filters.py
```

## API Routes

All endpoints are under `/api/v1/`:

| Prefix | App |
|--------|-----|
| `/api/v1/auth/` | accounts |
| `/api/v1/organizations/` | organizations |
| `/api/v1/academics/` | academics |
| `/api/v1/admissions/` | admissions |
| `/api/v1/attendance/` | attendance |
| `/api/v1/examinations/` | examinations |
| `/api/v1/fees/` | fees |
| `/api/v1/hr/` | hr |
| `/api/v1/communications/` | communications |
| `/api/v1/analytics/` | analytics |
| `/api/v1/integrations/` | integrations |
| `/health/` | core (liveness/readiness) |

## Commands

```bash
make dev              # Run dev server
make migrate          # Run migrations
make makemigrations   # Create migrations
make test             # Run tests
make lint             # Run linter
make format           # Format code
make docker-up        # Start PostgreSQL + Redis
make celery           # Start Celery worker
make beat             # Start Celery beat
make seed             # Seed demo data
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 5 + DRF |
| Database | PostgreSQL 16 |
| Cache/Queue | Redis 7 + Celery |
| Auth | JWT (access + refresh) |
| Payments | Razorpay |
| SMS | MSG91 |
| Storage | AWS S3 |
| AI | Anthropic API |
| WebSocket | Django Channels |
