"""Mailbox management API routes with encrypted credential storage and connection diagnostics."""

from flask import Blueprint, request, jsonify, current_app, g
from src.web.auth import admin_required
from src.storage.state_db import StateDatabase
from src.security.encryption import CredentialCipher
from src.email_receiver.mailbox_manager import MailboxManager

mailbox_bp = Blueprint("mailbox", __name__)


@mailbox_bp.route("/api/mailboxes", methods=["GET"])
@admin_required
def list_mailboxes():
    state_db: StateDatabase = current_app.config["STATE_DB"]
    mailboxes = state_db.get_all_mailboxes()
    return jsonify({"mailboxes": mailboxes, "count": len(mailboxes)})


@mailbox_bp.route("/api/mailboxes", methods=["POST"])
@admin_required
def create_mailbox():
    data = request.get_json() or {}
    name = str(data.get("name", "")).strip()
    server = str(data.get("server", "")).strip()
    port = int(data.get("port", 993))
    use_ssl = bool(data.get("use_ssl", True))
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    folder = str(data.get("folder", "INBOX")).strip()
    poll_interval = int(data.get("poll_interval_seconds", 60))

    if not name or not server or not username or not password:
        return jsonify({"error": "Bad Request", "message": "Name, server, username, and password are required."}), 400

    cipher: CredentialCipher = current_app.config.get("CREDENTIAL_CIPHER") or CredentialCipher()
    encrypted_pw = cipher.encrypt(password)

    state_db: StateDatabase = current_app.config["STATE_DB"]
    mb_id = state_db.add_mailbox(
        name=name,
        server=server,
        port=port,
        use_ssl=use_ssl,
        username=username,
        encrypted_password=encrypted_pw,
        folder=folder,
        poll_interval=poll_interval
    )

    state_db.record_audit_log(
        user_id=g.current_user["user_id"],
        username=g.current_user["username"],
        action="CREATE_MAILBOX",
        target=f"{name} ({username}@{server})",
        ip_address=request.remote_addr
    )

    return jsonify({"success": True, "id": mb_id, "message": f"Mailbox '{name}' added successfully."}), 201


@mailbox_bp.route("/api/mailboxes/<int:mb_id>", methods=["PUT"])
@admin_required
def update_mailbox(mb_id: int):
    data = request.get_json() or {}
    name = str(data.get("name", "")).strip()
    server = str(data.get("server", "")).strip()
    port = int(data.get("port", 993))
    use_ssl = bool(data.get("use_ssl", True))
    username = str(data.get("username", "")).strip()
    password = data.get("password")
    folder = str(data.get("folder", "INBOX")).strip()
    poll_interval = int(data.get("poll_interval_seconds", 60))

    cipher: CredentialCipher = current_app.config.get("CREDENTIAL_CIPHER") or CredentialCipher()
    encrypted_pw = cipher.encrypt(password) if password else None

    state_db: StateDatabase = current_app.config["STATE_DB"]
    updated = state_db.update_mailbox(
        mailbox_id=mb_id,
        name=name,
        server=server,
        port=port,
        use_ssl=use_ssl,
        username=username,
        encrypted_password=encrypted_pw,
        folder=folder,
        poll_interval=poll_interval
    )

    if not updated:
        return jsonify({"error": "Not Found", "message": "Mailbox not found."}), 404

    return jsonify({"success": True, "message": "Mailbox updated successfully."})


@mailbox_bp.route("/api/mailboxes/<int:mb_id>/toggle", methods=["POST"])
@admin_required
def toggle_mailbox(mb_id: int):
    state_db: StateDatabase = current_app.config["STATE_DB"]
    toggled = state_db.toggle_mailbox(mb_id)
    if not toggled:
        return jsonify({"error": "Not Found", "message": "Mailbox not found."}), 404

    mb = state_db.get_mailbox(mb_id)
    new_state = "Active" if mb["is_active"] else "Inactive"
    return jsonify({"success": True, "is_active": bool(mb["is_active"]), "message": f"Mailbox '{mb['name']}' is now {new_state}."})


@mailbox_bp.route("/api/mailboxes/<int:mb_id>/test", methods=["POST"])
@admin_required
def test_saved_mailbox(mb_id: int):
    state_db: StateDatabase = current_app.config["STATE_DB"]
    mb = state_db.get_mailbox(mb_id)
    if not mb:
        return jsonify({"error": "Not Found", "message": "Mailbox not found."}), 404

    cipher: CredentialCipher = current_app.config.get("CREDENTIAL_CIPHER") or CredentialCipher()
    decrypted_pw = cipher.decrypt(mb["encrypted_password"])

    mailbox_manager = MailboxManager(state_db, cipher)
    success, message, unread_count = mailbox_manager.test_mailbox_connection(
        server=mb["server"],
        port=int(mb["port"]),
        use_ssl=bool(mb["use_ssl"]),
        username=mb["username"],
        password=decrypted_pw,
        folder=mb.get("folder", "INBOX")
    )

    status_str = "CONNECTED" if success else "ERROR"
    state_db.update_mailbox_status(mb_id, status_str, None if success else message)

    return jsonify({
        "success": success,
        "message": message,
        "unread_count": unread_count
    })


@mailbox_bp.route("/api/mailboxes/test-direct", methods=["POST"])
@admin_required
def test_direct_mailbox():
    data = request.get_json() or {}
    server = str(data.get("server", "")).strip()
    port = int(data.get("port", 993))
    use_ssl = bool(data.get("use_ssl", True))
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    folder = str(data.get("folder", "INBOX")).strip()

    if not server or not username or not password:
        return jsonify({"error": "Bad Request", "message": "Server, username, and password required."}), 400

    state_db: StateDatabase = current_app.config["STATE_DB"]
    mailbox_manager = MailboxManager(state_db)
    success, message, unread_count = mailbox_manager.test_mailbox_connection(
        server=server,
        port=port,
        use_ssl=use_ssl,
        username=username,
        password=password,
        folder=folder
    )

    return jsonify({
        "success": success,
        "message": message,
        "unread_count": unread_count
    })


@mailbox_bp.route("/api/mailboxes/<int:mb_id>", methods=["DELETE"])
@admin_required
def delete_mailbox(mb_id: int):
    state_db: StateDatabase = current_app.config["STATE_DB"]
    mb = state_db.get_mailbox(mb_id)
    deleted = state_db.delete_mailbox(mb_id)
    if not deleted:
        return jsonify({"error": "Not Found", "message": "Mailbox not found."}), 404

    state_db.record_audit_log(
        user_id=g.current_user["user_id"],
        username=g.current_user["username"],
        action="DELETE_MAILBOX",
        target=mb.get("name", f"ID {mb_id}") if mb else str(mb_id),
        ip_address=request.remote_addr
    )
    return jsonify({"success": True, "message": "Mailbox removed."})
