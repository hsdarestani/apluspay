# A+Pay Platform

A+Pay is a multi-tenant, closed-loop stored-value wallet platform for cafés, lounges and hospitality businesses. It is built as a product of **A+ Solution GmbH** and follows the dark, high-contrast, yellow-accented design language of `aplus-solution.de`.

This repository starts from the product logic of `apluscard`, but promotes it from a single-business application into a SaaS platform that can be sold to many independent businesses.

## Role model

| Role | Scope | Main capabilities |
|---|---|---|
| Platform Admin | Global | Create businesses and owners, inspect all tenants, plans, subscriptions, wallets and audit logs |
| Owner | One business | Manage staff, customers, wallets, balances and reports |
| Manager | One business | Operate customer wallets and team workflows without global access |
| Staff | One business | Look up a customer and charge purchases |
| Customer | Own wallets | View balance, loyalty points, QR token and digital receipts |

A user can own or staff multiple businesses through `Membership`. Customer wallets are explicitly scoped to a `Business`. Platform admins are Django staff/superusers and are the only users with global access.

## Multi-tenant boundaries

A+Pay uses shared-database logical tenancy in the MVP:

- Every operational entity contains a `business_id`.
- All owner and staff routes include a business slug and re-check membership server-side.
- Wallet lookups are always performed through `business.wallets`.
- Ledger idempotency keys are unique inside a tenant.
- Cross-tenant access is covered by automated tests.
- Immutable ledger entries and audit events preserve sensitive operations.

This approach is fast to ship and appropriate for the first customers. PostgreSQL Row Level Security or schema-based tenancy can be added later without changing the product model.

## Included now

- Branded German landing page and PWA shell
- Platform Admin dashboard
- One-step tenant provisioning: business, owner, location and trial subscription
- Owner dashboard with KPIs, customer creation and staff creation
- Staff checkout flow
- Customer multi-wallet portal
- Wallet top-up, purchase, refund, block and activation
- Immutable before/after balance ledger
- Digital transaction receipts
- Loyalty points foundation
- REST API for future mobile apps and POS integrations
- Docker, PostgreSQL and GitHub Actions tests

## Architecture

- Django 5.2 LTS
- Django REST Framework 3.16
- PostgreSQL in production, SQLite locally
- Gunicorn + WhiteNoise
- Server-rendered mobile-first PWA
- Shared database, tenant-scoped domain model

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Remove DATABASE_URL from .env to use SQLite locally.
export DJANGO_DEBUG=1
export DJANGO_SECURE_COOKIES=0
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Demo users:

- `platform / ChangeMe123!`
- `owner / ChangeMe123!`
- `staff / ChangeMe123!`
- `customer / ChangeMe123!`

Change all demo passwords immediately outside local development.

## API foundation

- `GET /api/v1/me/`
- `GET /api/v1/wallets/`
- `GET /api/v1/businesses/<slug>/wallets/`
- `POST /api/v1/businesses/<slug>/charge/`
- `POST /api/v1/businesses/<slug>/topup/`
- `POST /api/v1/businesses/<slug>/refund/`

Session and token authentication are enabled. Every business endpoint revalidates tenant membership.

## Deployment

```bash
cp .env.example .env
# Configure secrets, domain and PostgreSQL password.
docker compose up -d --build
curl http://127.0.0.1:8020/health/
```

Put Nginx or Caddy in front of port `127.0.0.1:8020`, provision HTTPS, then set secure cookies and HSTS.

## Product roadmap

1. Camera QR scanner and one-time payment intents
2. Customer self-onboarding and wallet claim links
3. Billing provider integration for A+Pay subscriptions
4. Per-tenant custom logo, domain and receipts
5. Multi-location permissions and location reports
6. Promotions, campaigns, rewards and push notifications
7. POS/TSE connector with external receipt references
8. Native iOS and Android apps on the same API
9. GDPR exports, retention policies and advanced fraud controls
10. Platform revenue analytics, support console and tenant impersonation with audited approval

## Legal and payment scope

The MVP models a **closed-loop balance** usable only at the issuing business. It should remain non-transferable and normally non-withdrawable until German payment-services, tax, VAT, fiscal receipt/TSE and accounting requirements are reviewed by qualified counsel. An A+Pay digital receipt is an application transaction record and not automatically a legally compliant fiscal receipt or invoice.
