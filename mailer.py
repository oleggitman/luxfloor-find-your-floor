"""E-Mail ans Team von Lux-Floor. Bewusst so klein wie möglich.

Warum überhaupt: bis 10.09.2026 ging jede Benachrichtigung über einen heißen Lead
in Olegs private Telegram-Gruppe, in der niemand aus dem Laden sitzt. Das Team
erfuhr von einem Kunden also gar nicht. E-Mail ist der einzige Kanal, in dem alle
im Laden ohnehin den ganzen Tag sitzen.

Absender ist das Postfach des Ladens selbst (luxfloor24@gmail.com), Empfänger sind
dasselbe Postfach und info@lux-floor.de. Mail von ihnen an sie, nichts Fremdes im
Spiel, kein Spam-Verdacht, keine Kosten.

Google lässt kein Programm mit dem normalen Passwort ins Postfach. Deshalb, und
nur deshalb, braucht es ein App-Passwort (Google-Konto, Sicherheit, App-Passwörter,
zwei Minuten, einmalig) in `LEAD_MAIL_PASSWORD`.

Ist nichts konfiguriert, passiert nichts: der Chat läuft weiter, die Nachricht
fällt still aus und steht im Log. Ein leeres Postfach darf nie einen Besucher
kosten.
"""
import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
DEFAULT_TO = "luxfloor24@gmail.com, info@lux-floor.de"
TIMEOUT = 15


def recipients(env: dict) -> list:
    raw = (env or {}).get("LEAD_MAIL_TO") or DEFAULT_TO
    return [a.strip() for a in raw.split(",") if a.strip()]


def configured(env: dict) -> bool:
    env = env or {}
    return bool(env.get("LEAD_MAIL_USER") and env.get("LEAD_MAIL_PASSWORD"))


def _smtp_send(to: list, subject: str, body: str, env: dict) -> None:
    msg = EmailMessage()
    msg["From"] = env["LEAD_MAIL_USER"]
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    reply_to = env.get("LEAD_MAIL_REPLY_TO")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT) as s:
        s.starttls()
        s.login(env["LEAD_MAIL_USER"], env["LEAD_MAIL_PASSWORD"])
        s.send_message(msg)


def send_team_mail(subject: str, body: str, env: dict) -> str:
    """Schickt eine Nachricht ans Team. Wirft nie.

    Rückgabe: "sent", "not_configured" oder "failed". Der Aufrufer soll den Wert
    loggen und weiterarbeiten, egal was drinsteht.
    """
    if not configured(env):
        logger.info("Team-Mail nicht konfiguriert, übersprungen: %s", subject)
        return "not_configured"
    try:
        _smtp_send(recipients(env), subject, body, env)
        logger.info("Team-Mail raus: %s", subject)
        return "sent"
    except Exception as e:              # niemals den Chat mitreißen
        logger.warning("Team-Mail fehlgeschlagen (nicht blockierend): %s", e)
        return "failed"
