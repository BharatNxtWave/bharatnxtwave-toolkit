# BharatNXT Wave — Production Deployment Guide

---

## 1. Where should this be deployed?

This application was **built for an on-premise office LAN**, and that shapes
the answer. `accounts/network_security.OfficeNetworkMiddleware` rejects every
request whose client IP falls outside `BHARATNXT_OFFICE_NETWORKS`. The shipped
nginx config binds to a private address (`192.168.1.50`) with an internal TLS
certificate. The data involved — BharatNXT scheme sources, client collections,
scheme flyers — is confidential.

### Option A — On-premise LAN server ✅ recommended if the team works in office

One Ubuntu Server 24.04 LTS machine in the office with a **static LAN IP**,
running nginx + gunicorn + PostgreSQL together.

- Matches the security model the app already implements, with no changes.
- Confidential data never leaves the premises.
- One-time cost only — a mini PC (16 GB RAM / 512 GB SSD) is far more than
  enough for a team of this size. No monthly bill.
- **Trade-off:** nobody can use it from outside the office, and you own
  uptime, power, and backup verification.

### Option B — Cloud VM + VPN ✅ recommended if anyone works remotely

A small cloud VM with a mesh VPN (Tailscale or WireGuard) in front.

- Use **AWS Mumbai (`ap-south-1`)**, or Hetzner/DigitalOcean if cost matters
  more than data residency. For Indian customer data, keep it in India.
- 2 vCPU / 4 GB RAM is comfortable. Roughly ₹1,500–2,500/month.
- Install Tailscale, then set `BHARATNXT_OFFICE_NETWORKS=100.64.0.0/10`
  (the Tailscale CGNAT range). The IP allow-list keeps working — it now
  allow-lists *the VPN* instead of the office LAN, so the security model is
  preserved rather than abandoned.
- Bind gunicorn and nginx to the Tailscale interface only, **never** to the
  public IP. Keep the cloud firewall closed to everything except SSH.
- **Trade-off:** monthly cost, and every user needs the VPN client.

### Option C — Managed PaaS (Railway / Render / Fly.io) ❌ not recommended here

Fast to set up, but you would have to disable `OFFICE_NETWORK_ENFORCED`
because those platforms give you no stable client-IP boundary. That throws
away one of this app's two security layers and leaves only the login form
protecting confidential data on a public URL. It also puts the data on
infrastructure you cannot audit. Do not use this unless the security model is
formally revisited first.

**Short answer: Option A if everyone is in the office, Option B the moment
anyone needs remote access.** Both keep the app's design intact.

---

## 2. Server preparation (Ubuntu 24.04 LTS)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    postgresql postgresql-client nginx git

sudo adduser --system --group --home /opt/bharatnxt-toolkit bharatnxt
```

### PostgreSQL

```bash
sudo -u postgres psql
```

Then, at the `psql` prompt:

```sql
CREATE DATABASE bharatnxt_toolkit;
CREATE USER bharatnxt_app WITH PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';
ALTER ROLE bharatnxt_app SET client_encoding TO 'utf8';
ALTER ROLE bharatnxt_app SET default_transaction_isolation TO 'read committed';
ALTER ROLE bharatnxt_app SET timezone TO 'Asia/Kolkata';
GRANT ALL PRIVILEGES ON DATABASE bharatnxt_toolkit TO bharatnxt_app;
\q
```

---

## 3. Application install

```bash
sudo -u bharatnxt git clone <your-repo-url> /opt/bharatnxt-toolkit
cd /opt/bharatnxt-toolkit

sudo -u bharatnxt python3 -m venv .venv
sudo -u bharatnxt .venv/bin/pip install -r deployment/requirements-production.txt
```

---

## 4. Environment file

Generate a real secret key — **do not reuse the development one**:

```bash
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Copy the template and fill in real values:

```bash
sudo cp deployment/production.env.example /etc/bharatnxt-toolkit.env
sudo nano /etc/bharatnxt-toolkit.env

sudo chown root:bharatnxt /etc/bharatnxt-toolkit.env
sudo chmod 640 /etc/bharatnxt-toolkit.env
```

Every value that says `REPLACE_...` must actually be replaced.

| Variable | Notes |
|---|---|
| `BHARATNXT_ENVIRONMENT` | Must be exactly `production` — this is the switch that turns off `DEBUG` and turns on HTTPS enforcement and IP allow-listing |
| `BHARATNXT_SECRET_KEY` | The generated key. The app **refuses to start** without it |
| `BHARATNXT_ALLOWED_HOSTS` | The server's IP/hostname, comma-separated |
| `BHARATNXT_CSRF_TRUSTED_ORIGINS` | Same host **with the `https://` scheme** |
| `BHARATNXT_OFFICE_NETWORKS` | Real office subnet in CIDR, e.g. `192.168.1.0/24` (or the VPN range for Option B) |
| `BHARATNXT_DB_ENGINE` | `postgresql` |
| `BHARATNXT_DB_*` | Database name, user, password, host, port |
| `BHARATNXT_TRUSTED_PROXIES` | `127.0.0.1,::1` when nginx runs on the same box |
| `BHARATNXT_DJANGO_ADMIN_PATH` | Moves Django's built-in admin off `/admin/`; empty string removes it |
| `BHARATNXT_LOGIN_MAX_ATTEMPTS` | Failed sign-ins before lockout. Default `5` |
| `BHARATNXT_LOGIN_LOCKOUT_SECONDS` | Lockout duration in seconds. Default `900` |
| `BHARATNXT_LOG_DIR` | Optional. Defaults to `<project>/logs` |

> ⚠️ **Get `BHARATNXT_OFFICE_NETWORKS` right before you finish.** Set it to a
> subnet that does not include your own machine and you will lock everyone,
> including yourself, out of the web interface. You would then have to fix it
> over SSH and restart the service.

---

## 5. Migrate, collect static, create the first admin

```bash
cd /opt/bharatnxt-toolkit
set -a; source /etc/bharatnxt-toolkit.env; set +a

sudo -u bharatnxt -E .venv/bin/python manage.py migrate
sudo -u bharatnxt -E .venv/bin/python manage.py createcachetable
sudo -u bharatnxt -E .venv/bin/python manage.py collectstatic --noinput
sudo -u bharatnxt -E .venv/bin/python manage.py createsuperuser
```

`createcachetable` is required. The login lockout counters live in the
cache, and production uses the database cache backend so every gunicorn
worker shares one counter - a per-process cache would multiply the
effective attempt limit by the worker count.

Then log in and set that user's role to `SUPER_ADMIN` via **Admin Centre →
Employees**, so role-based screens behave correctly.

### Pre-import safety backups

Before applying any import the app takes a full database snapshot with
`pg_dump`, written to `confidential_source/audit/`. That is why
`postgresql-client` is installed above - without `pg_dump` on `PATH`
every import is refused.

```bash
sudo -u bharatnxt mkdir -p /opt/bharatnxt-toolkit/confidential_source/audit
sudo chmod 750 /opt/bharatnxt-toolkit/confidential_source
```

These snapshots contain the whole database. Include the directory in the
off-machine backup from section 8, and prune old snapshots - nothing
removes them automatically.

### Private flyer storage

Scheme flyers are stored **outside** the web root and are never served by
nginx. Create the directory with tight permissions:

```bash
sudo -u bharatnxt mkdir -p /opt/bharatnxt-toolkit/private_uploads
sudo chmod 750 /opt/bharatnxt-toolkit/private_uploads
```

---

## 6. Pre-flight check

```bash
sudo -u bharatnxt -E .venv/bin/python manage.py check --deploy
```

Expected output:

```
System check identified no issues (3 silenced).
```

The three silenced checks are deliberate and documented in `config/settings.py`:
`mail.E001` (this app sends no email), `security.W005` and `security.W021`
(HSTS subdomain/preload options that do not apply to a bare IP address).
Anything else appearing here is a real problem — fix it before going live.

---

## 7. nginx + gunicorn

```bash
sudo cp deployment/gunicorn.service.example \
        /etc/systemd/system/bharatnxt-toolkit.service

sudo cp deployment/nginx.internal.example \
        /etc/nginx/sites-available/bharatnxt-toolkit
sudo ln -s /etc/nginx/sites-available/bharatnxt-toolkit \
           /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
```

Edit both files and replace `192.168.1.50` with the real address, and the
`ssl_certificate` paths with your real internal certificate.

Generate an internal certificate if you do not have one (self-signed; browsers
will warn once until you distribute the CA to office machines):

```bash
sudo openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout /etc/ssl/private/bharatnxt-internal.key \
  -out    /etc/ssl/certs/bharatnxt-internal.crt \
  -subj "/CN=192.168.1.50"
```

Start everything:

```bash
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now bharatnxt-toolkit
sudo systemctl restart nginx

sudo systemctl status bharatnxt-toolkit
```

---

## 8. Backups

The app holds imported scheme data that is expensive to reconstruct. Set up
backups **on day one**, not later.

```bash
sudo cp deployment/backup-cron.example /etc/cron.d/bharatnxt-backup
sudo chmod 644 /etc/cron.d/bharatnxt-backup
```

`deployment/backup_database.sh` runs `pg_dump --format=custom` into
`$BHARATNXT_BACKUP_DIR` (default `<project>/backups`).

Two things the script does **not** do, which you must arrange yourself:

1. **Copy backups off the machine.** A backup on the same disk as the database
   does not survive a disk failure. Sync to a NAS or object storage.
2. **Back up `private_uploads/`.** The database stores flyer *metadata*; the
   files themselves live on disk and are not in `pg_dump`.

**Test a restore before you trust the backups.** An untested backup is not a
backup:

```bash
pg_restore --clean --no-owner -d bharatnxt_toolkit /path/to/backup.dump
```

---

## 9. Operating it

**Logs** — both journald and a rotating file (10 MB × 10):

```bash
sudo journalctl -u bharatnxt-toolkit -f
tail -f /opt/bharatnxt-toolkit/logs/bharatnxt.log
```

**Deploying an update:**

```bash
cd /opt/bharatnxt-toolkit
sudo -u bharatnxt git pull
sudo -u bharatnxt .venv/bin/pip install -r deployment/requirements-production.txt
set -a; source /etc/bharatnxt-toolkit.env; set +a
sudo -u bharatnxt -E .venv/bin/python manage.py migrate
sudo -u bharatnxt -E .venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart bharatnxt-toolkit
```

Take a database backup before any update that includes migrations.

---

## 10. Troubleshooting

| Symptom | Cause |
|---|---|
| `403 — available only from the authorised office network` | Client IP is outside `BHARATNXT_OFFICE_NETWORKS`, or nginx is not passing `X-Real-IP`, or the proxy address is missing from `BHARATNXT_TRUSTED_PROXIES` |
| Service will not start, `KeyError: 'BHARATNXT_SECRET_KEY'` | The env file is not being loaded — check `EnvironmentFile=` in the systemd unit |
| Pages load unstyled | `collectstatic` was not run, or the nginx `alias` path does not match `STATIC_ROOT` (`<project>/staticfiles/`) |
| CSRF failures on login | `BHARATNXT_CSRF_TRUSTED_ORIGINS` is missing the `https://` scheme |
| Blank 500 page | Check `logs/bharatnxt.log` — the traceback is recorded there |
| Upload rejected at ~20 MB | Intended. The limit is enforced in the app *and* in nginx |
| `pg_dump was not found on PATH` when applying an import | `postgresql-client` is not installed on the app server |
| "Too many failed sign-in attempts" | The login lockout. Wait it out, or clear the cache table. `LOGIN_FAILED` / `LOGIN_BLOCKED` rows in the activity log show who and from where |
| Lockout allows more attempts than configured | `createcachetable` was not run, so each gunicorn worker counts separately |

---

## 11. Known gaps — accepted, not blocking

Honest list of what this deployment does **not** have. None of these prevent
going live for an internal team, but you should know they are missing:

- **No CI pipeline.** Tests exist and pass, but nothing runs them
  automatically on push. Worth adding once more than one person commits.
- **No uptime monitoring or alerting.** If the service dies at night, nobody
  finds out until morning.
- **No staging environment.** Updates go straight from a developer machine to
  production. Take a backup first.
- **Backups are not verified automatically.** Schedule a manual restore test
  each quarter.
- **`toolkit/views.py` and `toolkit/models.py` are very large** and will
  slow future changes. A refactor is deferred, not forgotten.
- **Pre-import snapshots are never pruned.** `confidential_source/audit/` grows
  by one full database dump per applied import. Watch the disk.
- **The login lockout has no admin unlock screen.** Clearing an early lockout
  means clearing the cache table by hand.
