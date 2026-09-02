# BharatNXT Wave — Internal Toolkit

Django application for the BharatNXT BDE team: scheme/service search, call
workspace, saved client collections, scheme flyers, and an admin centre for
data import, reconciliation and activity auditing.

This is an **internal, office-network-only** tool. Access is restricted by an
IP allow-list on top of the login.

Two supported deployments:

- **[deployment/DEPLOYMENT.md](deployment/DEPLOYMENT.md)** — on-premise LAN
  server (nginx + gunicorn + PostgreSQL). The model the app was designed for.
- **[deployment/DEPLOY_RENDER.md](deployment/DEPLOY_RENDER.md)** — Render, via
  the `Dockerfile` and `render.yaml` blueprint. Read its section 0 first: the
  app gets a public URL, and the allow-list moves from the office LAN range to
  the office's public IP.

---

## Stack

| | |
|---|---|
| Python | 3.13 (verified on 3.13.14) |
| Django | 6.1 |
| Database | SQLite (development) · PostgreSQL (production) |
| Server | gunicorn behind nginx |
| Excel I/O | openpyxl |

No JavaScript build step — static assets are plain CSS/JS under `static/`.

---

## Local development setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

A superuser can reach the Admin Centre immediately. To create ordinary staff,
use **Admin Centre → Employees**, or set the `role` field directly
(`BDE`, `DATA_ADMIN`, `SECURITY_ADMIN`, `IT_ADMIN`, `SUPER_ADMIN`).

In development `OFFICE_NETWORK_ENFORCED` is `False`, so localhost works
normally. In production it is forced on — see the deployment guide.

---

## Running the tests

```bash
python manage.py test
```

86 tests across `accounts`, `dashboard` and `toolkit`. They cover login,
session/CSRF handling and brute-force lockout, admin access control, import
safety and finalisation, the pre-import backup on both database engines, and
the scheme-flyer upload/restore lifecycle.

One test deliberately triggers a flyer integrity failure — an `IntegrityError`
traceback in the output is **expected** and does not mean the run failed. Look
at the final `OK` line.

---

## Apps

| App | Responsibility |
|---|---|
| `accounts` | Custom `User` model, roles, login, session tracking, activity log, office-network and admin-portal middleware |
| `dashboard` | Landing dashboard, BDE analytics, admin overview (no models of its own) |
| `toolkit` | The domain core — services/schemes, search intelligence, matcher, workbook import pipeline, reconciliation, saved collections, scheme flyers |

---

## Things worth knowing before you change code

- **`toolkit/models.py` is ~2,100 lines and `toolkit/views.py` is ~4,500.**
  Both are due for a split, but nothing depends on that split happening.
- **Some tests assert on source text** (`getsource` + `assertIn`) rather than
  behaviour. That style once let a `NameError` ship in a guarded code path,
  because the assertion only checked that the guard's text existed. Prefer a
  test that drives the view; see `toolkit/test_changed_information_approval.py`.
- **Login failures are counted in the cache** by `accounts/login_throttle.py`.
  Production must use a cache shared across gunicorn workers, or the limit is
  effectively multiplied by the worker count.
- **Applying an import first snapshots the whole database** via
  `toolkit.intelligence.final_import.backup_database`. It needs `pg_dump` on
  `PATH` under PostgreSQL.
- **Client IP resolution has two modes** (`BHARATNXT_PROXY_MODE`), because it
  feeds the IP allow-list: `xrealip` behind your own nginx, `forwarded` behind
  a managed platform. Read the docstrings in `accounts/network_security.py`
  before touching it — getting it wrong makes the allow-list spoofable.
- **Scheme flyers are stored outside the web root** via
  `toolkit/flyer_storage.PrivateFlyerStorage`. That storage class raises on
  `.url()` by design — flyers are only ever served through the authenticated
  preview/download views. Do not "fix" it by giving it a base URL.
- **`accounts/network_security.py` trusts `X-Real-IP` only from
  `TRUSTED_PROXY_IPS`.** If you put another proxy in front, add its address
  there or IP allow-listing silently becomes spoofable.
- **Uploads are capped at 20 MB** in three places that must stay in agreement:
  `toolkit/flyer_validation.MAX_FLYER_BYTES`, `ToolkitImportUploadForm`, and
  `client_max_body_size` in the nginx config.

---

## Configuration

All production configuration is environment-driven. Nothing secret lives in
the repository. See `deployment/production.env.example` for the full list and
[deployment/DEPLOYMENT.md](deployment/DEPLOYMENT.md) for what each value should be.

Development runs entirely on defaults — no `.env` file is required.
