"""Email filter engine evaluating sender domains, subject keywords, intake addresses, and attachments."""

import re
from typing import List, Optional
from src.config import FilterConfig
from src.email_receiver.models import EmailMessage, FilterResult


class EmailFilter:
    """
    Evaluates incoming emails against defined business and intake criteria.
    """

    def __init__(self, config: FilterConfig):
        self.config = config
        self._compiled_subject_regex = None
        if self.config.subject_regex:
            try:
                self._compiled_subject_regex = re.compile(self.config.subject_regex, re.IGNORECASE)
            except re.error as e:
                # Fallback to None if invalid regex
                self._compiled_subject_regex = None

    def evaluate(self, email: EmailMessage) -> FilterResult:
        """
        Runs an email through the filter rules.
        Returns a FilterResult indicating whether it passed and reason details.
        """
        matched_rules: List[str] = []
        rejection_reasons: List[str] = []

        sender_email = email.sender.email.lower()
        sender_domain = email.sender.domain.lower()
        subject_lower = email.subject.lower()

        # 1. Blocked sender / domain check
        if self.config.blocked_sender_domains:
            for blocked in self.config.blocked_sender_domains:
                blocked_clean = blocked.lower().lstrip('@')
                if sender_domain == blocked_clean or sender_email.endswith(f"@{blocked_clean}"):
                    rejection_reasons.append(f"Sender domain '{sender_domain}' is in blocked list ({blocked})")
                    return FilterResult(is_match=False, rejection_reasons=rejection_reasons)

        # 2. Allowed sender / domain check (if configured)
        if self.config.allowed_sender_domains:
            domain_matched = False
            for allowed in self.config.allowed_sender_domains:
                allowed_clean = allowed.lower().lstrip('@')
                if sender_domain == allowed_clean or sender_domain.endswith(f".{allowed_clean}") or sender_email == allowed_clean:
                    domain_matched = True
                    matched_rules.append(f"Sender domain matched whitelist: {allowed}")
                    break
            if not domain_matched:
                rejection_reasons.append(f"Sender domain '{sender_domain}' is not in allowed sender list")
                return FilterResult(is_match=False, rejection_reasons=rejection_reasons)

        # 3. Intake address check (To / Cc)
        if self.config.intake_addresses:
            intake_matched = False
            all_recipients = [r.lower() for r in email.all_recipient_emails]
            for intake in self.config.intake_addresses:
                intake_clean = intake.lower()
                if any(intake_clean in r for r in all_recipients):
                    intake_matched = True
                    matched_rules.append(f"Dedicated intake address matched: {intake}")
                    break
            if not intake_matched:
                rejection_reasons.append(f"No recipient matched configured intake addresses ({self.config.intake_addresses})")
                return FilterResult(is_match=False, rejection_reasons=rejection_reasons)

        # 4. Excluded subject keywords (e.g., auto-replies, newsletters)
        if self.config.excluded_subject_keywords:
            for exc_kw in self.config.excluded_subject_keywords:
                if exc_kw.lower() in subject_lower:
                    rejection_reasons.append(f"Subject contains excluded keyword: '{exc_kw}'")
                    return FilterResult(is_match=False, rejection_reasons=rejection_reasons)

        # 5. Required subject keywords check
        if self.config.required_subject_keywords:
            if self.config.match_all_keywords:
                missing = [kw for kw in self.config.required_subject_keywords if kw.lower() not in subject_lower]
                if missing:
                    rejection_reasons.append(f"Subject missing required keywords: {missing}")
                    return FilterResult(is_match=False, rejection_reasons=rejection_reasons)
                matched_rules.append(f"Subject matched all keywords: {self.config.required_subject_keywords}")
            else:
                found_kws = [kw for kw in self.config.required_subject_keywords if kw.lower() in subject_lower]
                if not found_kws:
                    # If regex is also configured, check if regex matches
                    if not (self._compiled_subject_regex and self._compiled_subject_regex.search(email.subject)):
                        rejection_reasons.append(f"Subject does not contain any required keywords: {self.config.required_subject_keywords}")
                        return FilterResult(is_match=False, rejection_reasons=rejection_reasons)
                else:
                    matched_rules.append(f"Subject matched keywords: {found_kws}")

        # 6. Subject Regex check (if configured and not already matched by keywords)
        if self._compiled_subject_regex:
            if self._compiled_subject_regex.search(email.subject):
                matched_rules.append(f"Subject matched regex pattern: {self.config.subject_regex}")
            elif not self.config.required_subject_keywords:
                rejection_reasons.append(f"Subject does not match regex pattern: {self.config.subject_regex}")
                return FilterResult(is_match=False, rejection_reasons=rejection_reasons)

        # 7. Require attachments check
        if self.config.require_attachments:
            if not email.attachments or len(email.attachments) == 0:
                rejection_reasons.append("Email has no attachments (required by policy)")
                return FilterResult(is_match=False, rejection_reasons=rejection_reasons)
            matched_rules.append(f"Attachments present ({len(email.attachments)} found)")

        # If no specific filter rules were configured, accept all
        if not matched_rules:
            matched_rules.append("Default rule: Email accepted (no restrictive filters set)")

        return FilterResult(is_match=True, matched_rules=matched_rules)
