"""Flask Web Application Factory with security headers, session middleware, and route registration."""

import os
from flask import Flask, request, g, jsonify, redirect
from src.config import AppConfig
from src.storage.state_db import StateDatabase
from src.service import EmailParserService
from src.web.auth import AuthService
from src.web.routes.auth_routes import auth_bp
from src.web.routes.job_routes import job_bp
from src.web.routes.quarantine_routes import quarantine_bp
from src.web.routes.config_routes import config_bp
from src.web.routes.service_routes import service_bp
from src.web.routes.events_routes import events_bp


def create_app(config: AppConfig, service: EmailParserService = None) -> Flask:
    """Creates and configures the Flask dashboard application."""
    static_folder = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(
        __name__,
        static_folder=static_folder,
        static_url_path="/static"
    )

    # Secret key for sessions / CSRF
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "secure_onprem_email_parser_dashboard_key_2026")

    # Dependency injection
    state_db = StateDatabase(config.storage.database_path)
    auth_service = AuthService(state_db)
    service_instance = service or EmailParserService(config)

    app.config["APP_CONFIG"] = config
    app.config["STATE_DB"] = state_db
    app.config["AUTH_SERVICE"] = auth_service
    app.config["SERVICE_INSTANCE"] = service_instance

    # Auto-bootstrap default admin account if database is fresh
    auth_service.bootstrap_default_admin("AdminPass123!")

    # 1. Global Session Validation Middleware
    @app.before_request
    def authenticate_request():
        g.current_user = auth_service.validate_request_session(request)

    # 2. Strict Security Headers Middleware
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        
        # CSP: Strict self-origin policy (no external CDNs or scripts allowed)
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )
        return response

    # 3. Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(job_bp)
    app.register_blueprint(quarantine_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(service_bp)
    app.register_blueprint(events_bp)

    return app
