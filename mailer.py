"""Das Team von Lux-Floor erfährt von einem Kunden.

Warum überhaupt: bis 10.09.2026 ging jede Benachrichtigung über einen Kunden nach
Telegram in Olegs private Gruppe, in der niemand aus dem Laden sitzt. Das Team
erfuhr also gar nichts. E-Mail ist der Kanal, in dem alle im Laden ohnehin den
ganzen Tag sitzen.

Ein Weg ganz ohne Zugangsdaten wurde am 10.09.2026 gesucht und verworfen: das
eigene Kontaktformular des Shops (/kontakt/, Contact Form 7, kein Captcha) nimmt
eine Absendung per Programm zwar an, wirft sie aber als Spam weg. Zweimal live
geprüft, mit nüchternem Text und mit Browser-Kopfzeilen: beide Male "spam".
Zustellung gab es nie. Deshalb steht hier kein Formular-Weg mehr: ein Kanal, der
nichts zustellt, ist schlimmer als keiner, weil er Zustellung vortäuscht.

Es bleibt: SMTP mit einem App-Passwort des Ladenpostfachs (Google lässt Programme
nur mit einem solchen Extra-Schlüssel ins Postfach, deshalb und nur deshalb).
Solange der Schlüssel fehlt, springt Telegram ein, damit kein Kunde verloren geht.
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


def _smtp_send(to: list, subject: str, body: str, env: dict, reply_to: str = "") -> None:
    msg = EmailMessage()
    msg["From"] = env["LEAD_MAIL_USER"]
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    # Die E-Mail des Kunden als Antwortadresse: das Team antwortet direkt aus
    # der Nachricht, ohne irgendwo nachzuschlagen.
    if reply_to or env.get("LEAD_MAIL_REPLY_TO"):
        msg["Reply-To"] = reply_to or env["LEAD_MAIL_REPLY_TO"]
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT) as s:
        s.starttls()
        s.login(env["LEAD_MAIL_USER"], env["LEAD_MAIL_PASSWORD"])
        s.send_message(msg)


def send_team_mail(subject: str, body: str, env: dict, reply_to: str = "") -> str:
    """Nachricht ans Team. Wirft nie.

    Rückgabe: "sent", "not_configured" oder "failed". Alles ausser "sent" muss der
    Aufrufer auffangen, sonst geht ein Kunde verloren.
    """
    if not configured(env):
        logger.info("Team-Mail nicht eingerichtet, übersprungen: %s", subject)
        return "not_configured"
    try:
        _smtp_send(recipients(env), subject, body, env, reply_to)
        logger.info("Team-Mail raus: %s", subject)
        return "sent"
    except Exception as e:                # niemals den Chat mitreißen
        logger.warning("Team-Mail fehlgeschlagen (nicht blockierend): %s", e)
        return "failed"
