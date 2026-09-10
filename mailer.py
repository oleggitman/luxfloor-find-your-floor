"""Das Team von Lux-Floor erfährt von einem Kunden. Ohne Schlüssel, ohne Kosten.

Warum überhaupt: bis 10.09.2026 ging jede Benachrichtigung über einen Kunden nach
Telegram in Olegs private Gruppe, in der niemand aus dem Laden sitzt. Das Team
erfuhr also gar nichts. E-Mail ist der Kanal, in dem alle im Laden ohnehin den
ganzen Tag sitzen.

Der Weg dorthin ohne jedes Passwort: der Shop hat auf /kontakt/ sein EIGENES
Kontaktformular (Contact Form 7, Formular 527, kein Captcha). Wir füllen es aus,
und WordPress verschickt die Mail selbst, genau wie bei einer Kundenanfrage. Kein
App-Passwort, kein Anbieter, keine laufenden Kosten, niemand muss etwas
einrichten. Am 10.09.2026 gegen die Live-Seite geprüft.

Wer später doch ein Postfach einrichten will, setzt LEAD_MAIL_USER und
LEAD_MAIL_PASSWORD, dann geht es über SMTP. Das ist die Ausnahme, nicht die Regel.

Nichts hier darf je einen Besucher kosten: schlägt beides fehl, wird geloggt und
der Chat läuft weiter.
"""
import logging
import smtplib
from email.message import EmailMessage

import requests

logger = logging.getLogger(__name__)

SHOP_BASE = "https://lux-floor.de"
SHOP_FORM_ID = "527"                      # /kontakt/, Pflicht: Name, E-Mail, Text
SHOP_FORM_URL = (f"{SHOP_BASE}/wp-json/contact-form-7/v1/contact-forms/"
                 f"{SHOP_FORM_ID}/feedback")
FALLBACK_SENDER = "info@lux-floor.de"     # wenn der Kunde keine Mail hinterließ
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
DEFAULT_TO = "luxfloor24@gmail.com, info@lux-floor.de"
TIMEOUT = 15


def recipients(env: dict) -> list:
    raw = (env or {}).get("LEAD_MAIL_TO") or DEFAULT_TO
    return [a.strip() for a in raw.split(",") if a.strip()]


def configured(env: dict) -> bool:
    """Ist ein eigenes Postfach hinterlegt? Ohne das geht es über das Shop-Formular."""
    env = env or {}
    return bool(env.get("LEAD_MAIL_USER") and env.get("LEAD_MAIL_PASSWORD"))


def _post_shop_form(fields: dict) -> str:
    """Schickt das Kontaktformular des Shops ab. Gibt den CF7-Status zurück."""
    payload = {
        "_wpcf7": SHOP_FORM_ID,
        "_wpcf7_unit_tag": f"wpcf7-f{SHOP_FORM_ID}-o1",
        "_wpcf7_version": "6.0",
        "_wpcf7_locale": "de_DE",
    }
    payload.update(fields)
    files = {k: (None, v) for k, v in payload.items()}   # CF7 will multipart
    r = requests.post(SHOP_FORM_URL, files=files, timeout=TIMEOUT)
    try:
        return (r.json() or {}).get("status", "")
    except ValueError:
        return f"http_{r.status_code}"


def _smtp_send(to: list, subject: str, body: str, env: dict) -> None:
    msg = EmailMessage()
    msg["From"] = env["LEAD_MAIL_USER"]
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if env.get("LEAD_MAIL_REPLY_TO"):
        msg["Reply-To"] = env["LEAD_MAIL_REPLY_TO"]
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT) as s:
        s.starttls()
        s.login(env["LEAD_MAIL_USER"], env["LEAD_MAIL_PASSWORD"])
        s.send_message(msg)


def send_team_mail(subject: str, body: str, env: dict, reply_to: str = "") -> str:
    """Nachricht ans Team. Wirft nie. Rückgabe: "sent" oder "failed".

    reply_to: die E-Mail des Kunden, falls vorhanden. Sie wird zur Absenderadresse
    des Formulars, damit das Team direkt auf die Nachricht antworten kann.
    """
    try:
        if configured(env):
            _smtp_send(recipients(env), subject, body, env)
            logger.info("Team-Mail per SMTP raus: %s", subject)
            return "sent"
        status = _post_shop_form({
            "your-name": "Berater-Chat (KI-Bodenberater)",
            "your-email": reply_to or FALLBACK_SENDER,
            "your-comment": f"{subject}\n\n{body}",
        })
        if status == "mail_sent":
            logger.info("Team-Mail über das Shop-Formular raus: %s", subject)
            return "sent"
        logger.warning("Shop-Formular hat abgelehnt (%s): %s", status, subject)
        return "failed"
    except Exception as e:                # niemals den Chat mitreißen
        logger.warning("Team-Mail fehlgeschlagen (nicht blockierend): %s", e)
        return "failed"
