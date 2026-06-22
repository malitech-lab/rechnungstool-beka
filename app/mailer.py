"""E-Mail-Versand von Belegen (Rechnung/Mahnung/Angebot) per SMTP.

Der Nachrichtenbau (`build_message`) ist bewusst vom Netzwerk-Versand (`_smtp_send`)
getrennt, damit er ohne echten Mailserver getestet werden kann. Die SMTP-Zugangs-
daten liegen in den Firmen-Einstellungen (lokal, im geschützten Datenordner).
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage


class MailError(Exception):
    pass


def _ssl_context() -> ssl.SSLContext:
    """TLS-Kontext für den Mailversand – möglichst robust gegen
    CERTIFICATE_VERIFY_FAILED über alle Umgebungen (Windows-EXE, macOS, Linux).

    1) Betriebssystem-Zertifikatsspeicher via truststore: unter Windows der
       umfassendste Speicher (findet auch fehlende Zwischenzertifikate/AIA, immer
       aktuell) – das löst die meisten Mailserver-Zertifikatsprobleme.
    2) sonst das certifi-Wurzelbundle.
    3) sonst der Python-Standardkontext.
    """
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def is_configured(company: dict) -> bool:
    return bool((company.get("smtp_host") or "").strip()
                and (smtp_from(company)).strip())


def smtp_from(company: dict) -> str:
    # Absender: explizit gesetzt, sonst der Login (= authentifiziertes Postfach;
    # vermeidet DMARC-Ablehnung), erst zuletzt die Firmen-E-Mail.
    return (company.get("smtp_from") or company.get("smtp_user")
            or company.get("email") or "").strip()


def build_message(company: dict, to: str, subject: str, body: str,
                  attachments: list[tuple[str, bytes, str]]) -> EmailMessage:
    """Baut die E-Mail. attachments = Liste (dateiname, bytes, mimetype z.B. 'application/pdf')."""
    if not (to or "").strip():
        raise MailError("Keine Empfänger-E-Mail angegeben.")
    msg = EmailMessage()
    msg["From"] = smtp_from(company)
    msg["To"] = to.strip()
    msg["Subject"] = subject or "Ihre Rechnung"
    msg.set_content(body or "")
    for fname, data, mime in attachments:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(data, maintype=maintype or "application",
                           subtype=subtype or "octet-stream", filename=fname)
    return msg


def _smtp_send(company: dict, msg: EmailMessage) -> None:
    host = (company.get("smtp_host") or "").strip()
    port = int(company.get("smtp_port") or 587)
    user = (company.get("smtp_user") or "").strip()
    pw = company.get("smtp_password") or ""
    security = (company.get("smtp_security") or "starttls").lower()
    if security not in ("ssl", "starttls", "none"):
        security = "starttls"   # unbekannter Wert -> sichere Voreinstellung
    if user and security == "none":
        # niemals Zugangsdaten über eine unverschlüsselte Verbindung senden
        raise MailError("Login über unverschlüsselte Verbindung abgelehnt – bitte "
                        "STARTTLS oder SSL/TLS in den Einstellungen wählen.")
    try:
        if security == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=30, context=_ssl_context()) as s:
                if user:
                    s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                if security == "starttls":
                    s.starttls(context=_ssl_context())
                    s.ehlo()
                if user:
                    s.login(user, pw)
                s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"E-Mail konnte nicht gesendet werden: {e}") from e


def send(company: dict, to: str, subject: str, body: str,
         attachments: list[tuple[str, bytes, str]]) -> None:
    if not is_configured(company):
        raise MailError("E-Mail-Versand ist nicht eingerichtet – bitte in den "
                        "Einstellungen die SMTP-Daten hinterlegen.")
    msg = build_message(company, to, subject, body, attachments)
    _smtp_send(company, msg)
