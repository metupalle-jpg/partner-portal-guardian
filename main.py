"""HTTP server wrapper for Cloud Scheduler invocation.

Runs health checks directly (no ADK agent) when triggered by
Cloud Scheduler via POST /run.
"""

import json
import logging
import os
import traceback
from datetime import datetime, timezone

from flask import Flask, jsonify, request

# Import tool functions directly
from tools import (
    check_site_health,
    check_i18n_routes,
    check_api_endpoints,
    check_build_status,
    check_firebase_auth,
    send_report,
)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("guardian")


@app.get("/health")
def health():
    return jsonify(status="healthy", agent="partner_portal_guardian")


@app.post("/run")
def run_health_check():
    """Run all health checks directly and send report."""
    log.info("Starting partner portal health check run...")
    results = {}
    try:
        log.info("Checking site health...")
        results["site_health"] = check_site_health()
        log.info(f"Site health: {results['site_health']}")
    except Exception as e:
        results["site_health"] = f"ERROR: {e}"
        log.error(f"Site health check failed: {e}")

    try:
        log.info("Checking i18n routes...")
        results["i18n"] = check_i18n_routes()
        log.info(f"i18n: {results['i18n']}")
    except Exception as e:
        results["i18n"] = f"ERROR: {e}"
        log.error(f"i18n check failed: {e}")

    try:
        log.info("Checking API endpoints...")
        results["api"] = check_api_endpoints()
        log.info(f"API: {results['api']}")
    except Exception as e:
        results["api"] = f"ERROR: {e}"
        log.error(f"API check failed: {e}")

    try:
        log.info("Checking build status...")
        results["build"] = check_build_status()
        log.info(f"Build: {results['build']}")
    except Exception as e:
        results["build"] = f"ERROR: {e}"
        log.error(f"Build check failed: {e}")

    try:
        log.info("Checking Firebase auth...")
        results["firebase_auth"] = check_firebase_auth()
        log.info(f"Firebase: {results['firebase_auth']}")
    except Exception as e:
        results["firebase_auth"] = f"ERROR: {e}"
        log.error(f"Firebase auth check failed: {e}")

    # Build summary report
    timestamp = datetime.now(timezone.utc).isoformat()
    report = {
        "timestamp": timestamp,
        "service": "partner.resohealth.life",
        "checks": results,
    }

    # Determine overall status
    has_errors = any("ERROR" in str(v) for v in results.values())
    report["overall_status"] = "DEGRADED" if has_errors else "HEALTHY"

    log.info(f"Health check complete: {report['overall_status']}")
    log.info(f"Full report: {json.dumps(report, indent=2, default=str)}")

    try:
        send_report(json.dumps(report, indent=2, default=str))
        log.info("Report sent successfully")
    except Exception as e:
        log.error(f"Failed to send report: {e}")

    return jsonify(report), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
