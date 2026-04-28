"""HTTP server wrapper for Cloud Scheduler invocation.

This runs the ADK agent as a one-shot task when triggered by
Cloud Scheduler via POST /run, and also exposes the ADK web UI
for interactive debugging on GET /.
"""

import asyncio
import json
import os
import traceback

from flask import Flask, jsonify, request
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import the agent
from partner_portal_guardian.agent import root_agent

app = Flask(__name__)

ASK_MSG = "Run the full nightly health check now. Execute every check and send the report."


async def run_agent_once():
    """Execute the guardian agent for a single health-check run."""
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name="partner_portal_guardian",
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name="partner_portal_guardian",
        user_id="scheduler",
    )

    user_msg = types.Content(
        role="user",
        parts=[types.Part.from_text(ASK_MSG)],
    )

    final_response = None
    async for event in runner.run_async(
        user_id="scheduler",
        session_id=session.id,
        new_message=user_msg,
    ):
        if event.is_final_response():
            final_response = event.content.parts[0].text
            break

    return final_response or "Agent completed but no final response captured."


@app.route("/run", methods=["POST"])
def run_health_check():
    """Cloud Scheduler hits this endpoint nightly."""
    try:
        result = asyncio.run(run_agent_once())
        return jsonify({"status": "ok", "result": result}), 200
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "agent": "partner_portal_guardian"}), 200


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "name": "Partner Portal Guardian",
        "description": "Nightly health-check bot for partner.resohealth.life",
        "endpoints": {
            "POST /run": "Trigger a full health check (used by Cloud Scheduler)",
            "GET /health": "Liveness check",
        },
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
