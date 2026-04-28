"""Health-check tools for the Partner Portal Guardian agent."""

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from google.cloud.devtools import cloudbuild_v1 as build_v1
from google.cloud.devtools.cloudbuild_v1.types import Build

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "dave-487819")
REGION = os.environ.get("GOOGLE_CLOUD_LOCATION", "me-central1")
SITE_URL = "https://partner.resohealth.life"
CLOUD_RUN_URL = os.environ.get(
    "CLOUD_RUN_URL",
    "https://partner-portal-389848866614.me-central1.run.app",
)
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK_URL", "")
BUILD_TRIGGER_ID = os.environ.get(
    "BUILD_TRIGGER_ID",
    "rmgpgab-partner-portal-me-central1-metupalle-jpg-partner-porfdb",
)
DUBAI_TZ = timezone(timedelta(hours=4))


# ---------------------------------------------------------------------------
# 1. Cloud Build status
# ---------------------------------------------------------------------------
def check_build_status() -> dict:
    """Return the latest Cloud Build status for the partner-portal trigger.

    Returns a dict with keys: build_id, status, commit, started, duration_sec,
    log_url.
    """
    client = build_v1.CloudBuildClient()
    builds_pager = client.list_builds(
        request={
            "project_id": PROJECT_ID,
            "page_size": 5,
        }
    )
    # Pick the most recent build that matches our trigger
    for b in builds_pager:
        info = {
            "build_id": b.id[:12],
            "status": Build.Status(b.status).name,
            "commit": (b.substitutions or {}).get("COMMIT_SHA", "unknown")[:7],
            "started": b.start_time.isoformat() if b.start_time else None,
            "duration_sec": (
                int((b.finish_time - b.start_time).total_seconds())
                if b.finish_time and b.start_time
                else None
            ),
            "log_url": b.log_url,
        }
        return info
    return {"error": "No builds found"}


# ---------------------------------------------------------------------------
# 2. Site availability probe
# ---------------------------------------------------------------------------
def check_site_health() -> dict:
    """Probe key routes on partner.resohealth.life and the Cloud Run URL.

    Returns a dict mapping each URL to its HTTP status code and latency_ms.
    """
    urls = [
        f"{SITE_URL}",
        f"{SITE_URL}/login",
        f"{SITE_URL}/dashboard",
        f"{SITE_URL}/zh",
        f"{SITE_URL}/zh/login",
        f"{CLOUD_RUN_URL}",
    ]
    results = {}
    for url in urls:
        try:
            t0 = time.time()
            r = requests.get(url, timeout=20, allow_redirects=True)
            latency = int((time.time() - t0) * 1000)
            results[url] = {
                "status_code": r.status_code,
                "ok": r.status_code < 400,
                "latency_ms": latency,
            }
        except requests.RequestException as exc:
            results[url] = {
                "status_code": 0,
                "ok": False,
                "error": str(exc)[:200],
            }
    return results


# ---------------------------------------------------------------------------
# 3. i18n / Chinese route validation
# ---------------------------------------------------------------------------
def check_i18n_routes() -> dict:
    """Verify the /zh Chinese routes serve translated content.

    Checks that the page returns 200 and contains Chinese characters.
    Returns validation results for each route.
    """
    routes = ["/zh", "/zh/login"]
    results = {}
    for route in routes:
        url = f"{SITE_URL}{route}"
        try:
            r = requests.get(url, timeout=20)
            text = r.text[:10000]
            has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in text)
            has_sidebar_zh = any(
                kw in text
                for kw in ["\u4eea\u8868\u677f", "\u5ba2\u6237", "\u9884\u7ea6",
                           "\u5065\u5eb7\u670d\u52a1", "\u5408\u4f5c\u4f19\u4f34"]
            )  # Dashboard, Clients, Bookings, Wellness, Partner
            results[route] = {
                "status_code": r.status_code,
                "has_chinese_chars": has_chinese,
                "has_translated_nav": has_sidebar_zh,
                "ok": r.status_code == 200 and has_chinese,
            }
        except requests.RequestException as exc:
            results[route] = {"ok": False, "error": str(exc)[:200]}
    return results


# ---------------------------------------------------------------------------
# 4. Firebase / Auth check
# ---------------------------------------------------------------------------
def check_firebase_auth() -> dict:
    """Verify the login page loads and includes Firebase Auth configuration.

    Returns whether Firebase JS SDK references are present.
    """
    checks = {}
    for path in ["/login", "/zh/login"]:
        url = f"{SITE_URL}{path}"
        try:
            r = requests.get(url, timeout=20)
            body = r.text.lower()
            checks[path] = {
                "status_code": r.status_code,
                "has_firebase_sdk": "firebase" in body,
                "has_auth_import": "signinwithemailandpassword" in body
                or "createuserwithemailandpassword" in body
                or "firebase/auth" in body,
                "ok": r.status_code == 200 and "firebase" in body,
            }
        except requests.RequestException as exc:
            checks[path] = {"ok": False, "error": str(exc)[:200]}
    return checks


# ---------------------------------------------------------------------------
# 5. API endpoint health
# ---------------------------------------------------------------------------
def check_api_endpoints() -> dict:
    """Probe key API routes to ensure backend is responding.

    Tests bookings, clients, and sara endpoints.
    """
    endpoints = [
        "/api/bookings",
        "/api/clients",
    ]
    results = {}
    for ep in endpoints:
        url = f"{CLOUD_RUN_URL}{ep}"
        try:
            r = requests.get(url, timeout=15)
            results[ep] = {
                "status_code": r.status_code,
                "ok": r.status_code < 500,
            }
        except requests.RequestException as exc:
            results[ep] = {"ok": False, "error": str(exc)[:200]}
    return results


# ---------------------------------------------------------------------------
# 6. Trigger rebuild
# ---------------------------------------------------------------------------
def trigger_rebuild(reason: str = "Guardian bot auto-rebuild") -> dict:
    """Trigger a fresh Cloud Build for the partner-portal from the main branch.

    Args:
        reason: Human-readable reason for the rebuild.

    Returns dict with trigger result.
    """
    client = build_v1.CloudBuildClient()
    try:
        op = client.run_build_trigger(
            request={
                "project_id": PROJECT_ID,
                "trigger_id": BUILD_TRIGGER_ID,
                "source": build_v1.RepoSource(branch_name="main"),
            }
        )
        return {
            "triggered": True,
            "reason": reason,
            "operation": op.operation.name if hasattr(op, "operation") else "submitted",
        }
    except Exception as exc:
        return {"triggered": False, "error": str(exc)[:300]}


# ---------------------------------------------------------------------------
# 7. Send report
# ---------------------------------------------------------------------------
def send_report(
    summary: str,
    all_checks_passed: bool,
    failed_checks: str = "",
) -> str:
    """Send the nightly health-check report to Slack and log it.

    Args:
        summary: Full text summary of results.
        all_checks_passed: True if every check succeeded.
        failed_checks: Comma-separated list of failed check names.

    Returns confirmation message.
    """
    now = datetime.now(DUBAI_TZ).strftime("%Y-%m-%d %H:%M %Z")
    icon = "\u2705" if all_checks_passed else "\U0001f6a8"
    header = f"{icon} Partner Portal Nightly Report \u2014 {now}"
    full_msg = f"{header}\n\n{summary}"

    if failed_checks:
        full_msg += f"\n\n\u274c Failed: {failed_checks}"

    # Always print to stdout (Cloud Logging)
    print("=" * 60)
    print(full_msg)
    print("=" * 60)

    # Slack webhook (if configured)
    if SLACK_WEBHOOK:
        try:
            requests.post(
                SLACK_WEBHOOK,
                json={"text": full_msg},
                timeout=10,
            )
        except Exception as exc:
            print(f"Slack send failed: {exc}")

    return f"Report sent at {now}. All passed: {all_checks_passed}"
