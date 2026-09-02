#!/usr/bin/env python3
"""Load test for BharatNXT Wave.

Answers one question with evidence instead of arithmetic: how many BDEs can
use this deployment at once before it gets slow or starts failing.

Standard library only - no pip install on the machine you run it from.

    python deployment/loadtest.py --url https://toolkit.example.com \\
        --users 50 --duration 60

    # ramp until it breaks
    python deployment/loadtest.py --url ... --ramp 10,25,50,100,200

Each simulated BDE loops through a realistic session - dashboard, browse the
library, search, open a scheme - pausing between actions the way a person on
a client call would.

BEFORE YOU RUN IT
-----------------
1. Point it at staging, or at production out of hours. It generates real
   searches, real ActivityLog rows and real load.

2. Create the test accounts first (they must be BDE role, not admin):

       python manage.py shell -c "
       from django.contrib.auth import get_user_model
       U = get_user_model()
       for i in range(200):
           u, _ = U.objects.get_or_create(
               username=f'loadtest{i:03d}', defaults={'role': 'BDE'})
           u.role = 'BDE'; u.set_password('loadtest-password-1234'); u.save()
       "

3. The office IP allow-list applies. Run this from inside the office network
   (or from wherever BHARATNXT_OFFICE_NETWORKS permits), or every request
   comes back 403.

4. Delete the accounts afterwards:

       python manage.py shell -c "
       from django.contrib.auth import get_user_model
       get_user_model().objects.filter(username__startswith='loadtest').delete()"

READING THE RESULT
------------------
p95 is the number that matters - it is what the slowest 1 in 20 clicks feels
like. Under about 1s the app feels responsive; past 3s people think it has
hung. Watch for the concurrency level where p95 turns sharply upward: that is
the real capacity of the deployment, and it will be well below the level
where errors start.
"""

import argparse
import http.cookiejar
import random
import re
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor


CSRF_RE = re.compile(
    r'name="csrfmiddlewaretoken"\s+value="([^"]+)"'
)

SEARCH_TERMS = [
    "credit", "working capital", "msme", "export finance",
    "term loan", "invoice discounting", "supply chain",
    "msme working capital loan", "export credit guarantee scheme",
    "collateral free business loan",
]

_print_lock = threading.Lock()


class Result:
    def __init__(self):
        self.latencies = []
        self.errors = 0
        self.statuses = {}
        self.lock = threading.Lock()

    def record(self, seconds, status):
        with self.lock:
            self.latencies.append(seconds)
            self.statuses[status] = self.statuses.get(status, 0) + 1
            if status >= 400 or status == 0:
                self.errors += 1


class Session:
    """One simulated BDE, with its own cookie jar."""

    def __init__(self, base_url, username, password):
        self.base = base_url.rstrip("/")
        self.username = username
        self.password = password

        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar)
        )

    def get(self, path, result=None):
        url = f"{self.base}{path}"
        started = time.perf_counter()
        status = 0
        body = ""

        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "bharatnxt-loadtest/1.0"},
            )
            with self.opener.open(request, timeout=30) as response:
                body = response.read().decode("utf-8", "replace")
                status = response.status

        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read().decode("utf-8", "replace")

        except Exception:
            status = 0

        elapsed = time.perf_counter() - started

        if result is not None:
            result.record(elapsed, status)

        return status, body

    def login(self):
        status, body = self.get("/login/")

        if status != 200:
            return False, f"login page returned {status}"

        match = CSRF_RE.search(body)

        if not match:
            return False, "no CSRF token on the login page"

        data = urllib.parse.urlencode({
            "csrfmiddlewaretoken": match.group(1),
            "username": self.username,
            "password": self.password,
        }).encode()

        request = urllib.request.Request(
            f"{self.base}/login/",
            data=data,
            headers={
                "Referer": f"{self.base}/login/",
                "User-Agent": "bharatnxt-loadtest/1.0",
            },
        )

        try:
            with self.opener.open(request, timeout=30) as response:
                # A successful sign-in redirects away from /login/.
                if response.url.rstrip("/").endswith("/login"):
                    return False, "credentials rejected"
                return True, ""

        except urllib.error.HTTPError as exc:
            return False, f"login POST returned {exc.code}"

        except Exception as exc:
            return False, f"login failed: {exc}"

    def work(self, result, deadline, think):
        """Loop a realistic BDE session until the deadline."""

        while time.time() < deadline:
            self.get("/", result)
            time.sleep(think * random.uniform(0.5, 1.5))

            if time.time() >= deadline:
                break

            self.get("/toolkit/library/", result)
            time.sleep(think * random.uniform(0.5, 1.5))

            if time.time() >= deadline:
                break

            term = urllib.parse.quote_plus(random.choice(SEARCH_TERMS))
            self.get(f"/toolkit/library/?q={term}", result)
            time.sleep(think * random.uniform(0.5, 1.5))


def percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(len(ordered) * pct / 100), len(ordered) - 1)
    return ordered[index]


def run_level(base_url, users, duration, think, password, prefix):
    result = Result()

    sessions = []
    failures = []

    for i in range(users):
        session = Session(base_url, f"{prefix}{i:03d}", password)
        ok, reason = session.login()

        if ok:
            sessions.append(session)
        else:
            failures.append(reason)

    if not sessions:
        with _print_lock:
            print(f"  could not sign in any user: {failures[:1]}")
        return None

    if failures:
        with _print_lock:
            print(f"  warning: {len(failures)} of {users} could not sign in "
                  f"({failures[0]})")

    deadline = time.time() + duration
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
        for session in sessions:
            pool.submit(session.work, result, deadline, think)

    wall = time.perf_counter() - started
    total = len(result.latencies)

    if not total:
        return None

    return {
        "users": len(sessions),
        "requests": total,
        "rps": total / wall,
        "p50": percentile(result.latencies, 50),
        "p95": percentile(result.latencies, 95),
        "p99": percentile(result.latencies, 99),
        "mean": statistics.fmean(result.latencies),
        "errors": result.errors,
        "error_pct": 100.0 * result.errors / total,
        "statuses": result.statuses,
    }


def report(rows):
    print()
    print(f"{'USERS':>6} {'REQS':>7} {'REQ/S':>7} "
          f"{'p50':>8} {'p95':>8} {'p99':>8} {'ERR%':>7}")
    print("-" * 60)

    for r in rows:
        print(f"{r['users']:6} {r['requests']:7} {r['rps']:7.1f} "
              f"{r['p50']*1000:7.0f}m {r['p95']*1000:7.0f}m "
              f"{r['p99']*1000:7.0f}m {r['error_pct']:6.1f}%")

    print()

    healthy = [r for r in rows if r["p95"] < 1.0 and r["error_pct"] < 1.0]

    if healthy:
        best = max(healthy, key=lambda r: r["users"])
        print(f"Comfortable at {best['users']} concurrent users "
              f"(p95 {best['p95']*1000:.0f} ms, "
              f"{best['error_pct']:.1f}% errors).")
    else:
        print("No level stayed under a 1s p95 with under 1% errors.")

    degraded = [r for r in rows if r["p95"] >= 3.0 or r["error_pct"] >= 5.0]

    if degraded:
        first = min(degraded, key=lambda r: r["users"])
        print(f"Degraded by {first['users']} concurrent users "
              f"(p95 {first['p95']*1000:.0f} ms, "
              f"{first['error_pct']:.1f}% errors).")

    statuses = {}
    for r in rows:
        for code, n in r["statuses"].items():
            statuses[code] = statuses.get(code, 0) + n

    print(f"\nHTTP status totals: {dict(sorted(statuses.items()))}")

    if statuses.get(403):
        print("  403s usually mean the office IP allow-list is rejecting the "
              "machine this test runs from.")
    if statuses.get(0):
        print("  status 0 means the connection failed or timed out - the "
              "server was saturated or the request exceeded 30s.")


def main():
    parser = argparse.ArgumentParser(
        description="Load test BharatNXT Wave."
    )
    parser.add_argument("--url", required=True,
                        help="Base URL, e.g. https://toolkit.example.com")
    parser.add_argument("--users", type=int, default=25,
                        help="Concurrent simulated BDEs (default 25).")
    parser.add_argument("--ramp", default="",
                        help="Comma-separated levels, e.g. 10,25,50,100. "
                             "Overrides --users.")
    parser.add_argument("--duration", type=int, default=60,
                        help="Seconds per level (default 60).")
    parser.add_argument("--think", type=float, default=5.0,
                        help="Seconds a BDE pauses between actions "
                             "(default 5).")
    parser.add_argument("--password", default="loadtest-password-1234")
    parser.add_argument("--prefix", default="loadtest",
                        help="Test account username prefix.")

    args = parser.parse_args()

    levels = (
        [int(x) for x in args.ramp.split(",") if x.strip()]
        if args.ramp else [args.users]
    )

    print(f"Target      : {args.url}")
    print(f"Levels      : {levels}")
    print(f"Duration    : {args.duration}s per level")
    print(f"Think time  : {args.think}s between actions")
    print()

    rows = []

    for users in levels:
        print(f"running {users} concurrent users...")
        row = run_level(
            args.url, users, args.duration,
            args.think, args.password, args.prefix,
        )

        if row is None:
            print(f"  level {users} produced no results - stopping.")
            break

        print(f"  {row['requests']} requests, "
              f"p95 {row['p95']*1000:.0f} ms, "
              f"{row['error_pct']:.1f}% errors")

        rows.append(row)

    if rows:
        report(rows)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
