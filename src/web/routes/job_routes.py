"""Job and enquiry explorer API endpoints with safe attachment streaming and path traversal checks."""

import os
import json
import shutil
from flask import Blueprint, request, jsonify, send_file, current_app, abort
from src.web.auth import login_required
from src.security.sanitizer import sanitize_filename
from src.storage.state_db import StateDatabase

job_bp = Blueprint("jobs", __name__)


@job_bp.route("/api/stats", methods=["GET"])
@login_required
def get_stats():
    state_db: StateDatabase = current_app.config["STATE_DB"]
    config = current_app.config["APP_CONFIG"]
    
    stats = state_db.get_stats()
    
    # Check quarantine count
    quarantine_dir = os.path.abspath(config.storage.quarantine_dir)
    quarantine_count = len(os.listdir(quarantine_dir)) if os.path.exists(quarantine_dir) else 0
    stats["QUARANTINED"] = quarantine_count

    # Disk health check
    base_dir = os.path.abspath(config.storage.base_dir)
    try:
        total, used, free = shutil.disk_usage(base_dir)
        stats["DISK_FREE_MB"] = round(free / (1024 * 1024), 1)
        stats["DISK_TOTAL_MB"] = round(total / (1024 * 1024), 1)
    except Exception:
        stats["DISK_FREE_MB"] = 0
        stats["DISK_TOTAL_MB"] = 0

    return jsonify(stats)


@job_bp.route("/api/jobs", methods=["GET"])
@login_required
def list_jobs():
    state_db: StateDatabase = current_app.config["STATE_DB"]
    
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = max(int(request.args.get("offset", 0)), 0)
    search = request.args.get("search")
    status = request.args.get("status")

    jobs = state_db.get_recent_jobs(limit=limit, offset=offset, search=search, status=status)
    return jsonify({
        "jobs": jobs,
        "count": len(jobs),
        "limit": limit,
        "offset": offset
    })


@job_bp.route("/api/jobs/<job_id>", methods=["GET"])
@login_required
def get_job_details(job_id: str):
    state_db: StateDatabase = current_app.config["STATE_DB"]
    job_record = state_db.get_job_by_id(job_id)
    if not job_record:
        return jsonify({"error": "Not Found", "message": f"Job '{job_id}' not found."}), 404

    manifest_data = None
    manifest_path = job_record.get("manifest_path")
    if manifest_path and os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception:
            manifest_data = None

    return jsonify({
        "job": job_record,
        "manifest": manifest_data
    })


@job_bp.route("/api/jobs/<job_id>/markdown", methods=["GET"])
@login_required
def get_job_markdown(job_id: str):
    state_db: StateDatabase = current_app.config["STATE_DB"]
    job_record = state_db.get_job_by_id(job_id)
    if not job_record:
        return jsonify({"error": "Not Found", "message": f"Job '{job_id}' not found."}), 404

    manifest_path = job_record.get("manifest_path")
    if not manifest_path or not os.path.exists(manifest_path):
        return jsonify({"error": "Not Found", "message": "Job directory or manifest missing."}), 404

    job_dir = os.path.dirname(os.path.abspath(manifest_path))
    md_file_path = os.path.join(job_dir, "email_content.md")

    if not os.path.exists(md_file_path):
        return jsonify({"error": "Not Found", "message": "email_content.md not found in job directory."}), 404

    try:
        with open(md_file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"job_id": job_id, "content": content})
    except Exception as e:
        return jsonify({"error": "Read Error", "message": str(e)}), 500


@job_bp.route("/api/jobs/<job_id>/attachments/<filename>", methods=["GET"])
@login_required
def download_attachment(job_id: str, filename: str):
    """
    Safely serves an attachment file for download with strict security headers:
    1. Validates path traversal.
    2. Enforces Content-Disposition: attachment.
    3. Blocks MIME sniffing via nosniff.
    """
    state_db: StateDatabase = current_app.config["STATE_DB"]
    job_record = state_db.get_job_by_id(job_id)
    if not job_record or not job_record.get("manifest_path"):
        abort(404)

    # Sanitize requested filename
    clean_filename = sanitize_filename(filename)
    job_dir = os.path.dirname(os.path.abspath(job_record["manifest_path"]))
    attachments_dir = os.path.join(job_dir, "attachments")
    target_file = os.path.abspath(os.path.join(attachments_dir, clean_filename))

    # Path traversal validation: ensure resolved path is strictly inside attachments_dir
    if not target_file.startswith(os.path.abspath(attachments_dir) + os.sep):
        abort(403)

    if not os.path.exists(target_file) or not os.path.isfile(target_file):
        abort(404)

    response = send_file(
        target_file,
        as_attachment=True,
        download_name=clean_filename,
        mimetype="application/octet-stream"
    )
    # Strict security headers on served attachments
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    response.headers["X-Download-Options"] = "noopen"
    return response
