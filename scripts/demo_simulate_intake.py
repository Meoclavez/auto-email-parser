#!/usr/bin/env python3
"""Demonstration script simulating intake of realistic engineering email enquiries."""

import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import AppConfig
from src.service import EmailParserService


def run_demo():
    print("=================================================================")
    print("      AUTOMATIC EMAIL PARSER & ATTACHMENT DOWNLOADER DEMO        ")
    print("=================================================================")

    config = AppConfig.load_from_yaml("config/config.yaml")
    service = EmailParserService(config)

    # Pre-flight check
    if not service.pre_flight_checks():
        print("[!] Pre-flight checks failed.")
        return

    # Simulate Email 1: Valid CAD & Drawing enquiry from ACME Engineering
    msg1 = MIMEMultipart()
    msg1["Subject"] = "Urgent: RFQ-4089 - Custom CNC Milled Titanium Brackets"
    msg1["From"] = "Sarah Connor <sarah@acme-aerospace.com>"
    msg1["To"] = "enquiries@company.com"
    msg1["Date"] = "Wed, 19 Aug 2026 09:15:00 +0000"
    msg1["Message-ID"] = "<acme-rfq-4089@acme-aerospace.com>"

    body1 = """
    <h2>Request for Quote - Bracket Project</h2>
    <p>Dear Sales & Estimation Team,</p>
    <p>Please provide pricing and lead time for <strong>500 units</strong> of the attached bracket.</p>
    <ul>
      <li>Material: Titanium Grade 5 (Ti-6Al-4V)</li>
      <li>Surface Treatment: Bead blasted and anodized</li>
      <li>Tolerance: +/- 0.05 mm</li>
    </ul>
    <p>Refer to attached drawings and 3D CAD model for full specifications.</p>
    <p>Best regards,<br><strong>Sarah Connor</strong><br>Lead Procurement Engineer</p>
    """
    msg1.attach(MIMEText(body1, "html", "utf-8"))

    # Attachments for Email 1
    # 1. PDF
    pdf_part = MIMEApplication(b"%PDF-1.5\nTechnical drawing specification sheet\n%%EOF", _subtype="pdf")
    pdf_part.add_header("Content-Disposition", "attachment", filename="bracket_spec_revB.pdf")
    msg1.attach(pdf_part)

    # 2. DXF CAD
    dxf_part = MIMEApplication(b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF", _subtype="dxf")
    dxf_part.add_header("Content-Disposition", "attachment", filename="bracket_profile.dxf")
    msg1.attach(dxf_part)

    # 3. Disguised executable attempt (Simulating security quarantine)
    bad_part = MIMEApplication(b"MZ\x90\x00Malicious payload disguised as document", _subtype="pdf")
    bad_part.add_header("Content-Disposition", "attachment", filename="invoice_details.pdf")
    msg1.attach(bad_part)

    # Parse and process Email 1
    email_obj1 = service.imap_client.parse_raw_email(msg1.as_bytes(), uid="9001")
    print(f"\n[+] Processing incoming email from: {email_obj1.sender.raw}")
    print(f"    Subject: {email_obj1.subject}")
    print(f"    Attachments detected: {len(email_obj1.attachments)}")

    result1 = service.process_single_email(email_obj1)
    if result1:
        print(f"\n[SUCCESS] Job created: {result1['job_id']}")
        print(f"  Folder: {result1['job_dir']}")
        print(f"  Markdown Document: {result1['md_file']}")
        print(f"  Manifest: {result1['manifest_file']}")
        print(f"  Valid Attachments Saved : {result1['saved_attachments_count']}")
        print(f"  Quarantined Attachments : {result1['quarantined_attachments_count']}")

        print("\n--- Generated Markdown Preview (First 25 lines) ---")
        with open(result1['md_file'], 'r') as f:
            lines = [f.readline() for _ in range(25)]
            print("".join(lines))


if __name__ == "__main__":
    run_demo()
