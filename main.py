#!/usr/bin/env python3
"""Command-line interface for the Automatic Email Parser & Downloader."""

import os
import sys
import argparse
import logging
from src.config import AppConfig
from src.service import EmailParserService
from src.storage.state_db import StateDatabase


def setup_logging(log_level: str):
    """Configures structured logging output."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def cmd_run(args):
    """Starts the continuous background polling daemon."""
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
