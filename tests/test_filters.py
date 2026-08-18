"""Unit tests for the email filter engine."""

import unittest
from src.config import FilterConfig
from src.email_receiver.filters import EmailFilter
from src.email_receiver.models import EmailMessage, EmailAddress, AttachmentInfo


class TestFilters(unittest.TestCase):

    def setUp(self):
        self.config = FilterConfig(
            allowed_sender_domains=["@trusted-client.com", "@engineering.org"],
            blocked_sender_domains=["spammer.net", "bot.com"],
            required_subject_keywords=["RFQ", "Enquiry", "Quote"],
            excluded_subject_keywords=["Out of office", "Automatic reply"],
            intake_addresses=["enquiries@mycompany.com"],
            require_attachments=False,
            match_all_keywords=False
        )
        self.filter_engine = EmailFilter(self.config)

    def test_matching_email(self):
        msg = EmailMessage(
            uid="1",
            message_id="<123@trusted-client.com>",
            subject="New RFQ: Sheet Metal Components",
            sender=EmailAddress.parse("Alice <alice@trusted-client.com>"),
            to_recipients=[EmailAddress.parse("enquiries@mycompany.com")]
        )
        res = self.filter_engine.evaluate(msg)
        self.assertTrue(res.is_match)
        self.assertTrue(len(res.matched_rules) >= 2)

    def test_blocked_domain(self):
        msg = EmailMessage(
            uid="2",
            message_id="<456@spammer.net>",
            subject="Urgent RFQ enquiry",
            sender=EmailAddress.parse("Spam <bot@spammer.net>"),
            to_recipients=[EmailAddress.parse("enquiries@mycompany.com")]
        )
        res = self.filter_engine.evaluate(msg)
        self.assertFalse(res.is_match)
        self.assertIn("blocked", res.rejection_reasons[0].lower())

    def test_disallowed_domain(self):
        msg = EmailMessage(
            uid="3",
            message_id="<789@random-other.com>",
            subject="RFQ: Machining quote",
            sender=EmailAddress.parse("Bob <bob@random-other.com>"),
            to_recipients=[EmailAddress.parse("enquiries@mycompany.com")]
        )
        res = self.filter_engine.evaluate(msg)
        self.assertFalse(res.is_match)
        self.assertIn("allowed sender list", res.rejection_reasons[0])

    def test_excluded_subject_keyword(self):
        msg = EmailMessage(
            uid="4",
            message_id="<999@trusted-client.com>",
            subject="Automatic reply: Out of office regarding RFQ",
            sender=EmailAddress.parse("Alice <alice@trusted-client.com>"),
            to_recipients=[EmailAddress.parse("enquiries@mycompany.com")]
        )
        res = self.filter_engine.evaluate(msg)
        self.assertFalse(res.is_match)
        self.assertIn("excluded keyword", res.rejection_reasons[0].lower())

    def test_missing_required_keywords(self):
        msg = EmailMessage(
            uid="5",
            message_id="<888@trusted-client.com>",
            subject="Hello how are you today?",
            sender=EmailAddress.parse("Alice <alice@trusted-client.com>"),
            to_recipients=[EmailAddress.parse("enquiries@mycompany.com")]
        )
        res = self.filter_engine.evaluate(msg)
        self.assertFalse(res.is_match)
        self.assertIn("does not contain any required keywords", res.rejection_reasons[0])

    def test_intake_address_mismatch(self):
        msg = EmailMessage(
            uid="6",
            message_id="<777@trusted-client.com>",
            subject="RFQ for CNC Parts",
            sender=EmailAddress.parse("Alice <alice@trusted-client.com>"),
            to_recipients=[EmailAddress.parse("personal-inbox@mycompany.com")]
        )
        res = self.filter_engine.evaluate(msg)
        self.assertFalse(res.is_match)
        self.assertIn("No recipient matched", res.rejection_reasons[0])

    def test_require_attachments_rule(self):
        conf = FilterConfig(require_attachments=True)
        engine = EmailFilter(conf)

        msg_no_att = EmailMessage(
            uid="7",
            message_id="<111@a.com>",
            subject="RFQ",
            sender=EmailAddress.parse("a@a.com"),
            attachments=[]
        )
        self.assertFalse(engine.evaluate(msg_no_att).is_match)

        msg_with_att = EmailMessage(
            uid="8",
            message_id="<222@a.com>",
            subject="RFQ",
            sender=EmailAddress.parse("a@a.com"),
            attachments=[AttachmentInfo("draw.pdf", "draw.pdf", "application/pdf", 100, b"%PDF")]
        )
        self.assertTrue(engine.evaluate(msg_with_att).is_match)


if __name__ == "__main__":
    unittest.main()
