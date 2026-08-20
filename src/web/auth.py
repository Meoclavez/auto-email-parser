"""Authentication and Role-Based Access Control (RBAC) using Argon2id password hashing and session tokens."""

import logging
from functools import wraps
from typing import Optional, Dict, Any, Tuple
from flask import request, jsonify, redirect, url_for, g

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
except ImportError:
    import bcrypt
    _HASHER = None

from src.storage.state_db import StateDatabase

logger = logging.getLogger("EmailParser.WebAuth")


class PasswordManager:
    """Manages secure password hashing and verification using Argon2id with bcrypt fallback."""

    @staticmethod
    def hash_password(password: str) -> str:
        if not password or len(password) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        if _HASHER:
            return _HASHER.hash(password)
        else:
            salt = bcrypt.gensalt(rounds=12)
            return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        if not password or not password_hash:
            return False
        if _HASHER and password_hash.startswith("$argon2"):
            try:
                return _HASHER.verify(password_hash, password)
            except Exception:
                return False
        else:
            try:
                return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
            except Exception:
                return False


class AuthService:
    """Handles user authentication, session creation, and IP rate limiting."""

    def __init__(self, state_db: StateDatabase):
        self.state_db = state_db

    def authenticate_user(
        self,
        username: str,
        password: str,
        ip_address: str
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]], str]:
        """
        Validates login attempt with rate-limiting.
        Returns (success: bool, session_id: Optional[str], user_dict: Optional[Dict], message: str).
        """
        # 1. Check IP rate limit (brute force protection)
        if self.state_db.is_ip_rate_limited(ip_address, max_attempts=5, window_minutes=15):
            logger.warning(f"Login rate limit exceeded for IP: {ip_address}")
            return False, None, None, "Too many failed login attempts. IP temporarily blocked for 15 minutes."

        user = self.state_db.get_user_by_username(username)
        if not user:
            self.state_db.record_login_attempt(ip_address, success=False)
            return False, None, None, "Invalid username or password."

        # 2. Verify password hash
        if not PasswordManager.verify_password(password, user["password_hash"]):
            self.state_db.record_login_attempt(ip_address, success=False)
            return False, None, None, "Invalid username or password."

        # 3. Successful authentication
        self.state_db.record_login_attempt(ip_address, success=True)
        session_id = self.state_db.create_session(
            user_id=user["id"],
            username=user["username"],
            role=user["role"]
        )
        return True, session_id, user, "Login successful."

    def validate_request_session(self, req: request) -> Optional[Dict[str, Any]]:
        """Extracts and validates session token from Cookie or Authorization header."""
        session_id = req.cookies.get("session_id")
        
        # Fallback to Authorization: Bearer <token>
        if not session_id and req.headers.get("Authorization"):
            auth_header = req.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                session_id = auth_header[7:].strip()

        if not session_id:
            return None

        return self.state_db.get_session(session_id)

    def bootstrap_default_admin(self, default_password: str = "AdminPass123!") -> bool:
        """Creates the initial admin account if no users currently exist."""
        if self.state_db.count_users() == 0:
            pw_hash = PasswordManager.hash_password(default_password)
            self.state_db.create_user(username="admin", password_hash=pw_hash, role="admin")
            logger.info("Initialized default admin user: 'admin'")
            return True
        return False


def login_required(f):
    """Decorator requiring valid user authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_data = getattr(g, "current_user", None)
        if not session_data:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized", "message": "Authentication required."}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator requiring administrative privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_data = getattr(g, "current_user", None)
        if not session_data:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized", "message": "Authentication required."}), 401
            return redirect("/login")
        if session_data.get("role") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "Forbidden", "message": "Admin privileges required."}), 403
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated_function
