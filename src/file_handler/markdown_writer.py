"""Markdown generator converting email metadata, attachments summary, and HTML/plain bodies into clean GFM."""

import os
import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup, NavigableString, Tag
from src.email_receiver.models import EmailMessage, AttachmentInfo, FilterResult


class EmailMarkdownWriter:
    """
    Renders an EmailMessage and its attachments into a clean, structured
    GitHub Flavored Markdown (GFM) document with error annotations.
    """

    def __init__(self):
        pass

    def generate_markdown(
        self,
        email: EmailMessage,
        job_id: str,
        filter_result: Optional[FilterResult] = None,
        saved_attachments: Optional[List[AttachmentInfo]] = None,
        quarantined_attachments: Optional[List[AttachmentInfo]] = None,
        extra_notes: Optional[List[str]] = None
    ) -> str:
        """
        Creates the complete Markdown string for email_content.md.
        """
        saved_atts = saved_attachments or []
        quar_atts = quarantined_attachments or []
        rules = filter_result.matched_rules if filter_result else []

        md_lines: List[str] = []

        # 1. Title
        md_lines.append(f"# Email Enquiry: {email.subject or '(No Subject)'}")
        md_lines.append("")

        # 2. Metadata Information Card
        md_lines.append("## 📧 Enquiry Metadata")
        md_lines.append("")
        md_lines.append(f"- **Job Reference ID**: `{job_id}`")
        md_lines.append(f"- **Date Received**: {email.date_str or 'Unknown'}")
        md_lines.append(f"- **From**: `{email.sender.raw}`")
        if email.sender.domain:
            md_lines.append(f"- **Sender Domain**: `{email.sender.domain}`")
        
        to_str = ", ".join(f"`{r.raw}`" for r in email.to_recipients) if email.to_recipients else "_None_"
        md_lines.append(f"- **To**: {to_str}")

        if email.cc_recipients:
            cc_str = ", ".join(f"`{r.raw}`" for r in email.cc_recipients)
            md_lines.append(f"- **Cc**: {cc_str}")

        md_lines.append(f"- **Subject**: {email.subject or '(No Subject)'}")
        if email.message_id:
            md_lines.append(f"- **Message-ID**: `{email.message_id}`")

        if rules:
            md_lines.append(f"- **Filter Match**: {', '.join(rules)}")

        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

        # 3. Quarantined / Security Warnings (if any)
        if quar_atts:
            md_lines.append("> [!WARNING]")
            md_lines.append("> **Attachment Security Warnings**")
            for qa in quar_atts:
                md_lines.append(f"> - ⚠️ **`{qa.original_filename}`**: {qa.validation_reason}")
            md_lines.append("")

        if extra_notes:
            md_lines.append("> [!NOTE]")
            for note in extra_notes:
                md_lines.append(f"> - {note}")
            md_lines.append("")

        # 4. Attachments Summary Table
        md_lines.append("## 📎 Attachments")
        md_lines.append("")
        if saved_atts:
            md_lines.append("| # | Saved Filename | Original Filename | Size | Type | SHA-256 |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for idx, att in enumerate(saved_atts, start=1):
                size_str = self._format_size(att.size_bytes)
                rel_link = f"attachments/{att.sanitized_filename}"
                sha_short = att.sha256[:12] if att.sha256 else "N/A"
                md_lines.append(
                    f"| {idx} | [{att.sanitized_filename}]({rel_link}) | `{att.original_filename}` | {size_str} | `{att.content_type}` | `{sha_short}...` |"
                )
        else:
            md_lines.append("_No valid attachments detected in this email._")

        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

        # 5. Email Body Section
        md_lines.append("## 📝 Email Body")
        md_lines.append("")

        body_markdown = self._extract_body_markdown(email)
        md_lines.append(body_markdown)
        md_lines.append("")

        return "\n".join(md_lines)

    def write_to_file(self, target_path: str, content: str, permissions: int = 0o640) -> None:
        """
        Atomically writes markdown content to the target path with designated file permissions.
        """
        temp_path = f"{target_path}.tmp.{os.getpid()}"
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)

        os.chmod(temp_path, permissions)
        os.replace(temp_path, target_path)

    def _extract_body_markdown(self, email: EmailMessage) -> str:
        """
        Extracts body and converts to Markdown using fallback hierarchy:
        1. Parse HTML body if available
        2. Fallback to plain text body
        3. Fallback to placeholder if body is empty
        """
        if email.body_html and email.body_html.strip():
            try:
                converted = self.html_to_markdown(email.body_html)
                if converted and converted.strip():
                    return converted
            except Exception as e:
                # Log parser error annotation and fallback to plain text
                fallback_text = email.body_plain or email.body_html
                return f"> [!NOTE]\n> HTML parser encountered an issue ({str(e)}). Displaying plain text fallback:\n\n```text\n{fallback_text.strip()}\n```"

        if email.body_plain and email.body_plain.strip():
            # Clean plain text and format nicely
            cleaned_plain = self._clean_plain_text(email.body_plain)
            return cleaned_plain

        return "_[This email contains no text body]_"

    def html_to_markdown(self, html_content: str) -> str:
        """
        Converts HTML to sanitized GitHub Flavored Markdown.
        Strips scripts, styles, objects, and unsafe iframe elements.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Strip dangerous or non-content tags
        for tag in soup(["script", "style", "iframe", "object", "embed", "link", "meta", "noscript"]):
            tag.decompose()

        return self._convert_element(soup).strip()

    def _convert_element(self, element) -> str:
        """Recursively converts BeautifulSoup elements into Markdown."""
        if isinstance(element, NavigableString):
            text = str(element)
            # Normalize whitespace
            return re.sub(r'[ \t\r\f\v]+', ' ', text)

        if not isinstance(element, Tag):
            return ""

        tag_name = element.name.lower()
        inner_content = "".join(self._convert_element(child) for child in element.children)

        # Headings
        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            return f"\n\n{'#' * level} {inner_content.strip()}\n\n"

        # Paragraphs & Divs
        if tag_name in ("p", "div"):
            inner = inner_content.strip()
            return f"\n\n{inner}\n\n" if inner else ""

        # Line breaks
        if tag_name == "br":
            return "\n"

        # Emphasis / Bold
        if tag_name in ("strong", "b"):
            inner = inner_content.strip()
            return f"**{inner}**" if inner else ""

        if tag_name in ("em", "i"):
            inner = inner_content.strip()
            return f"*{inner}*" if inner else ""

        # Links
        if tag_name == "a":
            href = element.get("href", "").strip()
            inner = inner_content.strip() or href
            # Sanitize javascript: links
            if href.lower().startswith("javascript:"):
                return inner
            return f"[{inner}]({href})" if href else inner

        # Lists
        if tag_name in ("ul", "ol"):
            return f"\n\n{inner_content}\n\n"

        if tag_name == "li":
            inner = inner_content.strip()
            return f"- {inner}\n"

        # Blockquotes
        if tag_name == "blockquote":
            lines = inner_content.strip().split("\n")
            quoted = "\n".join(f"> {line}" for line in lines if line.strip())
            return f"\n\n{quoted}\n\n"

        # Code
        if tag_name == "code":
            return f"`{inner_content.strip()}`"

        if tag_name == "pre":
            return f"\n\n```\n{inner_content.strip()}\n```\n\n"

        # Tables
        if tag_name == "table":
            return self._convert_table(element)

        # Horizontal Rule
        if tag_name == "hr":
            return "\n\n---\n\n"

        return inner_content

    def _convert_table(self, table_tag: Tag) -> str:
        """Converts HTML table to Markdown table format."""
        rows = table_tag.find_all("tr")
        if not rows:
            return ""

        table_matrix: List[List[str]] = []
        for tr in rows:
            cells = tr.find_all(["th", "td"])
            row_data = [re.sub(r'\s+', ' ', cell.get_text().strip()) for cell in cells]
            if any(row_data):
                table_matrix.append(row_data)

        if not table_matrix:
            return ""

        num_cols = max(len(row) for row in table_matrix)
        normalized = [row + [""] * (num_cols - len(row)) for row in table_matrix]

        lines = ["\n"]
        # Header row
        header = normalized[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * num_cols) + " |")

        # Body rows
        for row in normalized[1:]:
            lines.append("| " + " | ".join(row) + " |")

        lines.append("\n")
        return "\n".join(lines)

    @staticmethod
    def _clean_plain_text(text: str) -> str:
        """Cleans and standardizes raw plaintext emails."""
        # Replace Windows CRLF
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        # Collapse >3 newlines
        normalized = re.sub(r'\n{3,}', '\n\n', normalized)
        return normalized.strip()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Formats byte sizes into readable units (KB, MB)."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
