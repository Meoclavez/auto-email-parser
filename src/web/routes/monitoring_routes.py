"""Daemon monitoring controller routes (Start / Pause / Resume / Immediate Sync)."""

from flask import Blueprint, jsonify, current_app, g, request
from src.web.auth import login_required, admin_required
from src.service import EmailParserService

monitoring_bp = Blueprint("monitoring", __name__)


@monitoring_bp.route("/api/monitoring/status", methods=["GET"])
@login_required
def get_monitoring_status():
    service: EmailParserService = current_app.config["SERVICE_INSTANCE"]
    return jsonify(service.get_monitoring_status())


@monitoring_bp.route("/api/monitoring/start", methods=["POST"])
@admin_required
def start_monitoring():
    service: EmailParserService = current_app.config["SERVICE_INSTANCE"]
    service.start_background_monitoring()
    current_app.config["STATE_DB"].record_audit_log(
        user_id=g.current_user["user_id"],
        username=g.current_user["username"],
        action="START_MONITORING",
        ip_address=request.remote_addr
    )
    return jsonify({"success": True, "message": "Email monitoring daemon started."})


@monitoring_bp.route("/api/monitoring/pause", methods=["POST"])
@admin_required
def pause_monitoring():
    service: EmailParserService = current_app.config["SERVICE_INSTANCE"]
    service.pause_monitoring()
    current_app.config["STATE_DB"].record_audit_log(
        user_id=g.current_user["user_id"],
        username=g.current_user["username"],
        action="PAUSE_MONITORING",
        ip_address=request.remote_addr
    )
    return jsonify({"success": True, "message": "Email monitoring paused."})


@monitoring_bp.route("/api/monitoring/resume", methods=["POST"])
@admin_required
def resume_monitoring():
    service: EmailParserService = current_app.config["SERVICE_INSTANCE"]
    service.resume_monitoring()
    current_app.config["STATE_DB"].record_audit_log(
        user_id=g.current_user["user_id"],
        username=g.current_user["username"],
        action="RESUME_MONITORING",
        ip_address=request.remote_addr
    )
    return jsonify({"success": True, "message": "Email monitoring resumed."})


@monitoring_bp.route("/api/monitoring/sync", methods=["POST"])
@login_required
def trigger_immediate_sync():
    service: EmailParserService = current_app.config["SERVICE_INSTANCE"]
    try:
        created_count = service.process_once()
        current_app.config["STATE_DB"].record_audit_log(
            user_id=g.current_user["user_id"],
            username=g.current_user["username"],
            action="MANUAL_SYNC",
            target=f"{created_count} jobs created",
            ip_address=request.remote_addr
        )
        return jsonify({
            "success": True,
            "jobs_created": created_count,
            "message": f"Sync completed across all active mailboxes. Created {created_count} new job(s)."
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
