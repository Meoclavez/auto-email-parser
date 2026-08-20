"""Quarantine inspection and admin management routes."""

import os
from flask import Blueprint, jsonify, send_file, current_app, abort
from src.web.auth import login_required, admin_required
from src.security.sanitizer import sanitize_filename

quarantine_bp = Blueprint("quarantine", __name__)


@quarantine_bp.route("/api/quarantine", methods=["GET"])
@login_required
def list_quarantined_files():
    config = current_app.config["APP_CONFIG"]
    quarantine_dir = os.path.abspath(config.storage.quarantine_dir)
    
    if not os.path.exists(quarantine_dir):
        return jsonify({"files": [], "count": 0})

    quarantine_list = []
    for fname in sorted(os.listdir(quarantine_dir)):
        fpath = os.path.join(quarantine_dir, fname)
        if os.path.isfile(fpath):
            stat = os.stat(fpath)
            quarantine_list.append({
                "filename": fname,
                "size_bytes": stat.st_size,
                "created_at": stat.st_ctime
            })

    return jsonify({"files": quarantine_list, "count": len(quarantine_list)})


@quarantine_bp.route("/api/quarantine/<filename>/download", methods=["GET"])
@admin_required
def download_quarantined_file(filename: str):
    """Admin-only download of quarantined threat for offline malware analysis."""
    config = current_app.config["APP_CONFIG"]
    quarantine_dir = os.path.abspath(config.storage.quarantine_dir)
    clean_name = sanitize_filename(filename)
    target_path = os.path.abspath(os.path.join(quarantine_dir, clean_name))

    if not target_path.startswith(quarantine_dir + os.sep) or not os.path.exists(target_path):
        abort(404)

    response = send_file(
        target_path,
        as_attachment=True,
        download_name=f"QUARANTINED_{clean_name}",
        mimetype="application/octet-stream"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


@quarantine_bp.route("/api/quarantine/<filename>", methods=["DELETE"])
@admin_required
def delete_quarantined_file(filename: str):
    config = current_app.config["APP_CONFIG"]
    quarantine_dir = os.path.abspath(config.storage.quarantine_dir)
    clean_name = sanitize_filename(filename)
    target_path = os.path.abspath(os.path.join(quarantine_dir, clean_name))

    if not target_path.startswith(quarantine_dir + os.sep) or not os.path.exists(target_path):
        abort(404)

    try:
        os.remove(target_path)
        return jsonify({"success": True, "message": f"Purged '{clean_name}' from quarantine."})
    except Exception as e:
        return jsonify({"error": "Delete Error", "message": str(e)}), 500
