"""Service diagnostic, connection testing, and on-demand intake sync endpoints."""

from flask import Blueprint, jsonify, current_app
from src.web.auth import login_required, admin_required
from src.service import EmailParserService

service_bp = Blueprint("service", __name__)


@service_bp.route("/api/service/status", methods=["GET"])
@login_required
def service_status():
    service: EmailParserService = current_app.config["SERVICE_INSTANCE"]
    preflight_ok = service.pre_flight_checks()
    return jsonify({
        "status": "RUNNING" if preflight_ok else "ERROR",
        "preflight_passed": preflight_ok,
        "database_connected": True
    })


@service_bp.route("/api/service/test-imap", methods=["POST"])
@admin_required
def test_imap_connection():
    service: EmailParserService = current_app.config["SERVICE_INSTANCE"]
    connected = service.imap_client.connect()
    if connected:
        emails = service.imap_client.fetch_unread_emails()
        service.imap_client.close()
        return jsonify({
            "success": True,
            "message": f"Connection successful! Detected {len(emails)} unread email(s)."
        })
    else:
        return jsonify({
            "success": False,
            "message": "Failed to connect or authenticate to IMAP server."
        }), 502


@service_bp.route("/api/service/sync-now", methods=["POST"])
@login_required
def trigger_manual_sync():
    """Triggers an on-demand intake pass."""
    service: EmailParserService = current_app.config["SERVICE_INSTANCE"]
    try:
        created_count = service.process_once()
        return jsonify({
            "success": True,
            "jobs_created": created_count,
            "message": f"Sync complete. Created {created_count} new job(s)."
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
