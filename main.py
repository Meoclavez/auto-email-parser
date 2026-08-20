#!/usr/bin/env python3
"""Command-line interface for the Automatic Email Parser & Downloader and Web Dashboard."""

import os
import sys
import argparse
import logging
from src.config import AppConfig
from src.service import EmailParserService
from src.storage.state_db import StateDatabase
from src.web.app import create_app
from src.web.auth import PasswordManager


def setup_logging(log_level: str):
    """Configures structured logging output."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def cmd_run(args):
    """Starts the continuous background email poller daemon."""
    config = AppConfig.load_from_yaml(args.config)
    setup_logging(args.log_level or config.log_level)
    service = EmailParserService(config)
    service.run_daemon()


def cmd_process_once(args):
    """Performs a single batch intake run and exits."""
    config = AppConfig.load_from_yaml(args.config)
    setup_logging(args.log_level or config.log_level)
    service = EmailParserService(config)
    count = service.process_once()
    print(f"\n[+] Single intake completed: {count} job(s) created.")


def cmd_test_connection(args):
    """Tests connection to IMAP server and validates credentials."""
    config = AppConfig.load_from_yaml(args.config)
    setup_logging(args.log_level or config.log_level)
    service = EmailParserService(config)

    print("\n--- IMAP Connection Diagnostic ---")
    print(f"Target Server : {config.imap.server}:{config.imap.port} (SSL: {config.imap.use_ssl})")
    print(f"Username      : {config.imap.username}")
    print(f"Target Mailbox: {config.imap.mailbox}")
    print("Connecting...")

    connected = service.imap_client.connect()
    if connected:
        print("[SUCCESS] IMAP Connection and authentication successful!")
        emails = service.imap_client.fetch_unread_emails()
        print(f"[INFO] Detected {len(emails)} unread email(s) ready for intake.")
        service.imap_client.close()
    else:
        print("[FAILED] Could not connect or authenticate to IMAP server.")
        sys.exit(1)


def cmd_stats(args):
    """Prints state database statistics."""
    config = AppConfig.load_from_yaml(args.config)
    state_db = StateDatabase(config.storage.database_path)
    stats = state_db.get_stats()
    
    print("\n--- Email Parser Processing Statistics ---")
    print(f"Total Emails Logged : {stats.get('TOTAL', 0)}")
    print(f"Successfully Processed: {stats.get('PROCESSED', 0)}")
    print(f"Filtered / Ignored    : {stats.get('IGNORED', 0)}")
    print(f"Pending Intake        : {stats.get('PENDING', 0)}")
    print(f"Failed / Errors       : {stats.get('FAILED', 0)}")
    print(f"Database Location     : {config.storage.database_path}\n")


def cmd_inspect_jobs(args):
    """Lists recent jobs from the state database."""
    config = AppConfig.load_from_yaml(args.config)
    state_db = StateDatabase(config.storage.database_path)
    jobs = state_db.get_recent_jobs(limit=args.limit)

    print(f"\n--- Recent Jobs (Last {args.limit}) ---")
    if not jobs:
        print("No job records found.")
        return

    for idx, j in enumerate(jobs, 1):
        status_symbol = "✓" if j["status"] == "PROCESSED" else ("✗" if j["status"] == "FAILED" else "—")
        print(f"{idx}. [{status_symbol}] {j['job_id'] or 'NO-JOB-ID'} ({j['status']})")
        print(f"    From   : {j['sender']}")
        print(f"    Subject: {j['subject']}")
        print(f"    Time   : {j['updated_at']}")
        if j['error_message']:
            print(f"    Error  : {j['error_message']}")
        if j['manifest_path']:
            print(f"    Path   : {j['manifest_path']}")
        print()


def cmd_web(args):
    """Starts the secure web dashboard server."""
    config = AppConfig.load_from_yaml(args.config)
    setup_logging(args.log_level or config.log_level)
    
    service = EmailParserService(config)
    app = create_app(config, service)

    print("\n================================================================")
    print(f"  EMAIL PARSER SECURE WEB DASHBOARD (On-Premises)")
    print(f"  Listening on: http://{args.host}:{args.port}")
    print(f"  Default Login: admin / AdminPass123!")
    print("================================================================\n")

    # Run with waitress or native development server
    try:
        from waitress import serve
        serve(app, host=args.host, port=args.port)
    except ImportError:
        app.run(host=args.host, port=args.port, debug=False)


def cmd_create_user(args):
    """Creates a new web user account."""
    config = AppConfig.load_from_yaml(args.config)
    state_db = StateDatabase(config.storage.database_path)
    
    pw_hash = PasswordManager.hash_password(args.password)
    user_id = state_db.create_user(username=args.username, password_hash=pw_hash, role=args.role)
    print(f"\n[+] User '{args.username}' ({args.role.upper()}) created successfully (ID: {user_id}).")


def main():
    parser = argparse.ArgumentParser(
        description="Automatic Email Parser & Downloader (100% On-Premise & Local Processing)"
    )
    parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="Path to YAML configuration file (default: config/config.yaml)"
    )
    parser.add_argument(
        "--log-level", "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override logging verbosity"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    p_run = subparsers.add_parser("run", help="Run background email poller daemon")
    p_run.set_defaults(func=cmd_run)

    # process-once command
    p_once = subparsers.add_parser("process-once", help="Process unread emails once and exit")
    p_once.set_defaults(func=cmd_process_once)

    # test-connection command
    p_test = subparsers.add_parser("test-connection", help="Test IMAP connectivity & auth")
    p_test.set_defaults(func=cmd_test_connection)

    # stats command
    p_stats = subparsers.add_parser("stats", help="Display processing metrics")
    p_stats.set_defaults(func=cmd_stats)

    # inspect-jobs command
    p_inspect = subparsers.add_parser("inspect-jobs", help="List recent processed jobs")
    p_inspect.add_argument("--limit", "-n", type=int, default=20, help="Number of records to show")
    p_inspect.set_defaults(func=cmd_inspect_jobs)

    # web command
    p_web = subparsers.add_parser("web", help="Start the secure web dashboard server")
    p_web.add_argument("--host", default="127.0.0.1", help="Binding interface (default: 127.0.0.1)")
    p_web.add_argument("--port", "-p", type=int, default=8080, help="Binding port (default: 8080)")
    p_web.set_defaults(func=cmd_web)

    # create-user command
    p_user = subparsers.add_parser("create-user", help="Create a web user account")
    p_user.add_argument("--username", "-u", required=True, help="Username")
    p_user.add_argument("--password", required=True, help="User password")
    p_user.add_argument("--role", choices=["admin", "estimator", "viewer"], default="viewer", help="User role")
    p_user.set_defaults(func=cmd_create_user)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
