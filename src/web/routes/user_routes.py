"""User management, company onboarding, and team administration API routes."""

from flask import Blueprint, request, jsonify, current_app, g
from src.web.auth import login_required, admin_required, PasswordManager
from src.storage.state_db import StateDatabase

user_bp = Blueprint("users", __name__)


@user_bp.route("/api/users", methods=["GET"])
@admin_required
def list_users():
    state_db: StateDatabase = current_app.config["STATE_DB"]
    users = state_db.get_all_users()
    return jsonify({"users": users, "count": len(users)})


@user_bp.route("/api/users", methods=["POST"])
@admin_required
def create_team_user():
    data = request.get_json() or {}
    username = str(data.get("username", "")).strip().lower()
    full_name = str(data.get("full_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    role = str(data.get("role", "estimator")).lower()

    if not username or not password:
        return jsonify({"error": "Bad Request", "message": "Username and password required."}), 400

    if role not in ("admin", "estimator", "viewer"):
        return jsonify({"error": "Bad Request", "message": "Invalid role."}), 400

    state_db: StateDatabase = current_app.config["STATE_DB"]
    if state_db.get_user_by_username(username):
        return jsonify({"error": "Conflict", "message": f"Username '{username}' already exists."}), 409

    pw_hash = PasswordManager.hash_password(password)
    user_id = state_db.create_user(
        username=username,
        full_name=full_name,
        email=email,
        password_hash=pw_hash,
        role=role
    )

    state_db.record_audit_log(
        user_id=g.current_user["user_id"],
        username=g.current_user["username"],
        action="CREATE_USER",
        target=f"{username} ({role})",
        ip_address=request.remote_addr
    )

    return jsonify({"success": True, "id": user_id, "message": f"User '{username}' created successfully."}), 201


@user_bp.route("/api/users/<int:user_id>/role", methods=["PUT"])
@admin_required
def update_user_role(user_id: int):
    data = request.get_json() or {}
    role = str(data.get("role", "")).lower()
    if role not in ("admin", "estimator", "viewer"):
        return jsonify({"error": "Bad Request", "message": "Invalid role."}), 400

    state_db: StateDatabase = current_app.config["STATE_DB"]
    updated = state_db.update_user_role(user_id, role)
    if not updated:
        return jsonify({"error": "Not Found", "message": "User not found."}), 404

    return jsonify({"success": True, "message": f"Role updated to '{role}'."})


@user_bp.route("/api/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user_active(user_id: int):
    # Prevent self-deactivation
    if g.current_user["user_id"] == user_id:
        return jsonify({"error": "Forbidden", "message": "Cannot deactivate your own administrator account."}), 400

    state_db: StateDatabase = current_app.config["STATE_DB"]
    updated = state_db.toggle_user_active(user_id)
    if not updated:
        return jsonify({"error": "Not Found", "message": "User not found."}), 404

    return jsonify({"success": True, "message": "User status updated."})


@user_bp.route("/api/auth/register", methods=["POST"])
def register_company_and_admin():
    """Registration endpoint for creating initial company account or team onboarding."""
    data = request.get_json() or {}
    company_name = str(data.get("company_name", "")).strip()
    full_name = str(data.get("full_name", "")).strip()
    username = str(data.get("username", "")).strip().lower()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not username or not password or len(password) < 6:
        return jsonify({"error": "Bad Request", "message": "Valid username and password (min 6 chars) required."}), 400

    state_db: StateDatabase = current_app.config["STATE_DB"]
    if state_db.get_user_by_username(username):
        return jsonify({"error": "Conflict", "message": f"Username '{username}' already exists."}), 409

    company_id = None
    if company_name:
        company_id = state_db.create_company(company_name)

    # First user registered in an empty DB gets admin role, subsequent get estimator role
    user_count = state_db.count_users()
    assigned_role = "admin" if user_count == 0 else "estimator"

    pw_hash = PasswordManager.hash_password(password)
    user_id = state_db.create_user(
        username=username,
        full_name=full_name,
        email=email,
        password_hash=pw_hash,
        role=assigned_role,
        company_id=company_id
    )

    state_db.record_audit_log(
        user_id=user_id,
        username=username,
        action="USER_REGISTERED",
        target=f"{username} ({assigned_role})",
        ip_address=request.remote_addr
    )

    return jsonify({
        "success": True,
        "message": f"Account '{username}' registered successfully as {assigned_role.upper()}.",
        "role": assigned_role
    }), 201
