"""Job and enquiry explorer API endpoints with safe attachment streaming, notes, status pipeline, and manual file upload."""

import os
import json
import shutil
from flask import Blueprint, request, jsonify, send_file, current_app, abort, g
from src.web.auth import login_required
from src.security.sanitizer import sanitize_filename
from src.storage.state_db import StateDatabase
from src.service import EmailParserService

job_bp = Blueprint("jobs", __name__)


@job_bp.route("/api/stats", methods=["GET"])
@login_required
def get_stats():
    state_db: StateDatabase = current_app.config["STATE_DB"]
    config = current_app.config["APP_CONFIG"]
    
    stats = state_db.get_stats()
    
    quarantine_dir = os.path.abspath(config.storage.quarantine_dir)
    quarantine_count = len(os.listdir(quarantine_dir)) if os.path.exists(quarantine_dir) else 0
    stats["QUARANTINED"] = quarantine_count

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

    notes = state_db.get_job_notes(job_id)

    return jsonify({
        "job": job_record,
        "manifest": manifest_data,
        "notes": notes
    })


@job_bp.route("/api/jobs/<job_id>/status", methods=["POST"])
@login_required
def update_job_status(job_id: str):
    data = request.get_json() or {}
    new_status = str(data.get("status", "")).strip().upper()
    valid_statuses = ("NEW", "IN_REVIEW", "QUOTED", "ARCHIVED", "REJECTED", "PROCESSED")

    if new_status not in valid_statuses:
        return jsonify({"error": "Bad Request", "message": f"Invalid status. Must be one of {valid_statuses}."}), 400

    state_db: StateDatabase = current_app.config["STATE_DB"]
    updated = state_db.update_job_status(job_id, new_status)
    if not updated:
        return jsonify({"error": "Not Found", "message": "Job not found."}), 404

    state_db.record_audit_log(
        user_id=g.current_user["user_id"],
        username=g.current_user["username"],
        action="UPDATE_STATUS",
        target=f"{job_id} -> {new_status}",
        ip_address=request.remote_addr
    )

    return jsonify({"success": True, "status": new_status, "message": f"Job status updated to {new_status}."})


@job_bp.route("/api/jobs/<job_id>/notes", methods=["GET", "POST"])
@login_required
def job_notes(job_id: str):
    state_db: StateDatabase = current_app.config["STATE_DB"]

    if request.method == "POST":
        data = request.get_json() or {}
        note_text = str(data.get("note", "")).strip()
        if not note_text:
            return jsonify({"error": "Bad Request", "message": "Note text is required."}), 400

        note_id = state_db.add_job_note(
            job_id=job_id,
            user_id=g.current_user["user_id"],
            username=g.current_user["username"],
            note_text=note_text
        )
        return jsonify({"success": True, "note_id": note_id, "message": "Note added successfully."}), 201

    notes = state_db.get_job_notes(job_id)
    return jsonify({"notes": notes, "count": len(notes)})


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
    state_db: StateDatabase = current_app.config["STATE_DB"]
    job_record = state_db.get_job_by_id(job_id)
    if not job_record or not job_record.get("manifest_path"):
        abort(404)

    clean_filename = sanitize_filename(filename)
    job_dir = os.path.dirname(os.path.abspath(job_record["manifest_path"]))
    attachments_dir = os.path.join(job_dir, "attachments")
    target_file = os.path.abspath(os.path.join(attachments_dir, clean_filename))

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
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    response.headers["X-Download-Options"] = "noopen"
    return response


@job_bp.route("/api/jobs/upload", methods=["POST"])
@login_required
def upload_manual_email():
    """Endpoint for uploading a raw .eml file or drawings manually."""
    if "file" not in request.files:
        return jsonify({"error": "Bad Request", "message": "No file uploaded."}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"error": "Bad Request", "message": "Empty file."}), 400

    raw_bytes = uploaded_file.read()
    service: EmailParserService = current_app.config["SERVICE_INSTANCE"]

    try:
        parsed_email = service.imap_client.parse_raw_email(raw_bytes, uid="manual_upload")
        res = service.process_single_email(parsed_email)
        if res and res.get("status") == "SUCCESS":
            return jsonify({
                "success": True,
                "job_id": res["job_id"],
                "message": f"Successfully parsed and created job {res['job_id']}."
            }), 201
        else:
            return jsonify({"error": "Filtered", "message": "Email did not meet intake filter rules."}), 422
    except Exception as e:
        return jsonify({"error": "Processing Failed", "message": str(e)}), 500
