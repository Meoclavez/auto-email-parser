"""Unit tests for email-to-markdown formatting and HTML parsing."""

import unittest
from src.file_handler.markdown_writer import EmailMarkdownWriter
from src.email_receiver.models import EmailMessage, EmailAddress, AttachmentInfo, FilterResult


class TestMarkdownWriter(unittest.TestCase):

    def setUp(self):
        self.writer = EmailMarkdownWriter()

    def test_html_to_markdown_formatting(self):
        html_input = """
        <html>
          <body>
            <h2>Request for Quotation</h2>
            <p>Dear Sales Team,</p>
            <p>Please find attached our <strong>drawing</strong> for <em>batch 42</em>.</p>
            <ul>
              <li>Material: Stainless Steel 316</li>
              <li>Quantity: 500 pcs</li>
            </ul>
            <table>
              <tr><th>Part Name</th><th>Qty</th></tr>
              <tr><td>Bracket A</td><td>250</td></tr>
              <tr><td>Flange B</td><td>250</td></tr>
            </table>
            <p>Visit our website: <a href="https://example.com">Example Corp</a></p>
            <script>alert('malicious script');</script>
          </body>
        </html>
        """
        md = self.writer.html_to_markdown(html_input)
        
        self.assertIn("## Request for Quotation", md)
        self.assertIn("**drawing**", md)
        self.assertIn("*batch 42*", md)
        self.assertIn("- Material: Stainless Steel 316", md)
        self.assertIn("| Part Name | Qty |", md)
        self.assertIn("| Bracket A | 250 |", md)
        self.assertIn("[Example Corp](https://example.com)", md)
        # Verify script is stripped
        self.assertNotIn("alert(", md)
        self.assertNotIn("<script>", md)

    def test_generate_markdown_document_with_attachments(self):
        msg = EmailMessage(
            uid="101",
            message_id="<msg-101@company.com>",
            subject="Enquiry: CNC Milled Brackets",
            sender=EmailAddress.parse("Engineering <eng@company.com>"),
            to_recipients=[EmailAddress.parse("sales@factory.com")],
            date_str="Wed, 19 Aug 2026 10:00:00 +0000",
            body_plain="Hello,\n\nPlease see attached CAD model and PDF specification.\n\nRegards,\nTeam"
        )
        saved_att = AttachmentInfo(
            original_filename="bracket_rev2.dxf",
            sanitized_filename="JOB-20260819-0001_01_bracket_rev2.dxf",
            content_type="application/dxf",
            size_bytes=1048576,
            data=b"0" * (1024 * 1024)
        )
        quar_att = AttachmentInfo(
            original_filename="malicious.exe",
            sanitized_filename="JOB-20260819-0001_02_malicious.exe",
            content_type="application/x-msdownload",
            size_bytes=2048,
            data=b"MZ...",
            validation_reason="Forbidden file extension: '.exe' is explicitly prohibited."
        )

        filter_res = FilterResult(is_match=True, matched_rules=["Subject matched: Enquiry"])

        md_doc = self.writer.generate_markdown(
            email=msg,
            job_id="JOB-20260819-0001",
            filter_result=filter_res,
            saved_attachments=[saved_att],
            quarantined_attachments=[quar_att]
        )

        # Check metadata
        self.assertIn("# Email Enquiry: Enquiry: CNC Milled Brackets", md_doc)
        self.assertIn("- **Job Reference ID**: `JOB-20260819-0001`", md_doc)
        self.assertIn("- **From**: `Engineering <eng@company.com>`", md_doc)
        self.assertIn("- **Filter Match**: Subject matched: Enquiry", md_doc)

        # Check attachments table
        self.assertIn("[JOB-20260819-0001_01_bracket_rev2.dxf](attachments/JOB-20260819-0001_01_bracket_rev2.dxf)", md_doc)
        self.assertIn("1.00 MB", md_doc)

        # Check security alert
        self.assertIn("> [!WARNING]", md_doc)
        self.assertIn("malicious.exe", md_doc)

        # Check body
        self.assertIn("Please see attached CAD model and PDF specification.", md_doc)


if __name__ == "__main__":
    unittest.main()
