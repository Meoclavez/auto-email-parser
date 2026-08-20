"""Filter and mailbox configuration management routes."""

import yaml
from flask import Blueprint, request, jsonify, current_app
from src.web.auth import admin_required

config_bp = Blueprint("config", __name__)


@config_bp.route("/api/config", methods=["GET"])
@admin_required
def get_config():
    config = current_app.config["APP_CONFIG"]
    return jsonify({
        "imap": {
            "server": config.imap.server,
            "port": config.imap.port,
            "username": config.imap.username,
            "password_masked": "********" if config.imap.password else "",
            "use_ssl": config.imap.use_ssl,
            "mailbox": config.imap.mailbox,
            "poll_interval_seconds": config.imap.poll_interval_seconds
        },
        "filters": {
            "allowed_sender_domains": config.filters.allowed_sender_domains,
            "blocked_sender_domains": config.filters.blocked_sender_domains,
            "required_subject_keywords": config.filters.required_subject_keywords,
            "excluded_subject_keywords": config.filters.excluded_subject_keywords,
            "subject_regex": config.filters.subject_regex,
            "intake_addresses": config.filters.intake_addresses,
            "require_attachments": config.filters.require_attachments,
            "match_all_keywords": config.filters.match_all_keywords
        },
        "storage": {
            "base_dir": config.storage.base_dir,
            "job_id_prefix": config.storage.job_id_prefix
        }
    })


@config_bp.route("/api/config/filters", methods=["POST"])
@admin_required
def update_filters():
    data = request.get_json() or {}
    config = current_app.config["APP_CONFIG"]

    if "allowed_sender_domains" in data:
        config.filters.allowed_sender_domains = list(data["allowed_sender_domains"])
    if "blocked_sender_domains" in data:
        config.filters.blocked_sender_domains = list(data["blocked_sender_domains"])
    if "required_subject_keywords" in data:
        config.filters.required_subject_keywords = list(data["required_subject_keywords"])
    if "excluded_subject_keywords" in data:
        config.filters.excluded_subject_keywords = list(data["excluded_subject_keywords"])
    if "subject_regex" in data:
        config.filters.subject_regex = data["subject_regex"] or None
    if "intake_addresses" in data:
        config.filters.intake_addresses = list(data["intake_addresses"])
    if "require_attachments" in data:
        config.filters.require_attachments = bool(data["require_attachments"])
    if "match_all_keywords" in data:
        config.filters.match_all_keywords = bool(data["match_all_keywords"])

    # Update active filter engine
    service = current_app.config.get("SERVICE_INSTANCE")
    if service:
        service.filter_engine.config = config.filters

    return jsonify({"success": True, "message": "Filter rules updated successfully."})
