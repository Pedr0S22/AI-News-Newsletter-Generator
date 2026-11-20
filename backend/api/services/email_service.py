import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import markdown as md_lib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from api.configs.config import settings
from api.configs.logging import get_logger
from api.models.dtos.newsletter import NewsletterStructuredContent

logger = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


class EmailService:
    """Renders Structured JSON newsletters into clean HTML/Markdown and sends via Mailpit SMTP."""

    def __init__(self):
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render_markdown(self, content: NewsletterStructuredContent) -> str:
        """Deterministically renders Structured JSON into clean reader-facing Markdown."""
        edition_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
        lines = [
            f"# {content.edition_title}",
            f"*{edition_date}*",
            "",
            content.intro.strip(),
            "",
            "---",
            "",
        ]
        for blurb in sorted(content.blurbs, key=lambda b: b.rank_order):
            lines.extend(
                [
                    f"## {blurb.rank_order}. {blurb.headline}",
                    f"*{blurb.theme} • Source: {blurb.source_name}*",
                    "",
                    blurb.body.strip(),
                    "",
                    f"[Read Original Article]({blurb.source_url})",
                    "",
                    "---",
                    "",
                ]
            )
        lines.append(content.outro.strip())
        return "\n".join(lines).strip()

    def render_html(self, content: NewsletterStructuredContent) -> str:
        """Deterministically renders Structured JSON into responsive HTML email (zero internal scores)."""
        template = self.jinja_env.get_template("newsletter_email.html")
        edition_date = datetime.now(timezone.utc).strftime("%B %d, %Y")

        rendered_blurbs = []
        for blurb in sorted(content.blurbs, key=lambda b: b.rank_order):
            body_html = md_lib.markdown(blurb.body.strip(), extensions=["nl2br"])
            rendered_blurbs.append(
                {
                    "rank_order": blurb.rank_order,
                    "theme": blurb.theme,
                    "headline": blurb.headline,
                    "body_html": body_html,
                    "source_name": blurb.source_name,
                    "source_url": blurb.source_url,
                }
            )

        return template.render(
            edition_title=content.edition_title,
            subject=content.subject,
            edition_date=edition_date,
            intro=content.intro.strip(),
            blurbs=rendered_blurbs,
            outro=content.outro.strip(),
        )

    def send_email(
        self,
        recipients: list[str],
        subject: str,
        plain_markdown: str,
        html_body: str,
    ) -> list[str]:
        """Dispatches a multipart HTML + plain-text newsletter via SMTP (Mailpit)."""
        clean_recipients = [r.strip() for r in recipients if r and r.strip()]
        if not clean_recipients:
            raise ValueError("No valid recipients provided for email dispatch.")

        from_header = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            for recipient in clean_recipients:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = from_header
                msg["To"] = recipient

                msg.attach(MIMEText(plain_markdown, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))
                server.sendmail(settings.SMTP_FROM_EMAIL, [recipient], msg.as_string())

        logger.info(
            f"Dispatched newsletter '{subject}' to {len(clean_recipients)} recipient(s) via "
            f"{settings.SMTP_HOST}:{settings.SMTP_PORT}."
        )
        return clean_recipients
