"""Authentication API and portal routes."""

import os
from flask import Blueprint, request, jsonify, make_response, send_from_directory, g, current_app
from src.web.auth import AuthService, login_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not username or not password:
        return jsonify({"error": "Bad Request", "message": "Username and password are required."}), 400

    ip_address = request.remote_addr or "127.0.0.1"
    auth_service: AuthService = current_app.config["AUTH_SERVICE"]

    success, session_id, user_dict, message = auth_service.authenticate_user(
        username=username,
        password=password,
        ip_address=ip_address
    )

    if not success:
        status_code = 429 if "Too many" in message else 401
        return jsonify({"error": "Authentication Failed", "message": message}), status_code

    response = make_response(jsonify({
        "success": True,
        "message": message,
        "user": {
            "id": user_dict["id"],
            "username": user_dict["username"],
            "role": user_dict["role"]
        }
    }))

    # Secure Cookie Settings
    is_secure = request.is_secure
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=86400,  # 24 hours
        httponly=True,
        secure=is_secure,
        samesite="Strict",
        path="/"
    )
    return response


@auth_bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session_id = request.cookies.get("session_id")
    auth_service: AuthService = current_app.config["AUTH_SERVICE"]
    if session_id:
        auth_service.state_db.delete_session(session_id)

    response = make_response(jsonify({"success": True, "message": "Logged out successfully."}))
    response.delete_cookie("session_id", path="/")
    return response


@auth_bp.route("/api/auth/me", methods=["GET"])
@login_required
def api_me():
    user = g.current_user
    return jsonify({
        "authenticated": True,
        "user": {
            "username": user["username"],
            "role": user["role"],
            "expires_at": user["expires_at"]
        }
    })


@auth_bp.route("/login", methods=["GET"])
def serve_login_page():
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    return send_from_directory(static_dir, "login.html")


@auth_bp.route("/", methods=["GET"])
def serve_root():
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    return send_from_directory(static_dir, "index.html")
