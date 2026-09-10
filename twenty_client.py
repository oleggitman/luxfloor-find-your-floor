"""Twenty CRM handler for Find Your Floor (replaces bitrix_client.py).

create_lead maps the assistant's captured data onto Twenty:
  - a Person (contact + address)
  - an Opportunity at stage "Новый лид" (NEW_LEAD), linked to the Person (pointOfContact),
    owner = Alisa (TWENTY_OWNER_ID) when set, carrying the qualification fields.
Computes HOT/Warm score and fires a Telegram Smart Buzz alert for HOT leads (no-op if token empty).

Field/stage names come from the schema built by clients/luxfloor/migration/twenty_schema.py.
Funnel + mapping source of truth: clients/luxfloor/analysis/bitrix-funnel.md
"""
from __future__ import annotations

import json
import logging

import requests

from mailer import send_team_mail

logger = logging.getLogger(__name__)

NEW_LEAD_STAGE = "NEW_LEAD"
QUELLE = "Website-Assistent"
URGENCY_MAP = {"needed_now": "NEEDED_NOW", "has_time": "HAS_TIME", "needs_storage": "NEEDS_STORAGE"}
FLAG_MAP = {"normal": "NORMAL", "auslandsversand": "AUSLANDSVERSAND", "sonderanfrage": "SONDERANFRAGE"}


def _base(env: dict) -> str:
    return env.get("TWENTY_API_URL", "").rstrip("/")


def _headers(env: dict) -> dict:
    return {"Authorization": f"Bearer {env.get('TWENTY_API_KEY', '')}", "Content-Type": "application/json"}


def _is_hot(data: dict) -> bool:
    has_contact = bool(data.get("phone_or_whatsapp"))
    urgent = data.get("urgency") == "needed_now"
    profile = data.get("profile") or {}
    has_project = bool(
        data.get("area_sqm") and data.get("interested_products") and profile.get("material")
    )
    return has_contact and urgent and has_project


def _build_notiz(data: dict) -> str:
    lines = ["== Find Your Floor Assistent =="]
    summary = data.get("conversation_summary")
    if summary:
        lines.append(f"ZUSAMMENFASSUNG: {summary}")
    flag = data.get("lead_flag", "normal")
    if flag and flag != "normal":
        lines.append(f"SONDERFALL: {flag.upper()} (Team muss aktiv zurueckrufen)")
    lines.append(f"Dringlichkeit: {data.get('urgency', '')}")
    if data.get("action") and data.get("action") != "none":
        lines.append(f"Aktion: {data['action']}")
    if data.get("showroom_slot"):
        lines.append(f"Showroom-Termin: {data['showroom_slot']}")
    if data.get("strasse"):
        lines.append(f"Strasse: {data['strasse']}")
    return "\n".join(lines)


def _split_name(full: str) -> dict:
    parts = (full or "Unbekannt").strip().split(None, 1)
    return {"firstName": parts[0], "lastName": parts[1] if len(parts) > 1 else ""}


def _phone_field(phone: str) -> dict:
    """Any phone must be written, never rejected. Numbers with an explicit +XX
    keep it and Twenty infers the country itself (verified live: +39 -> IT);
    forcing DE next to a foreign +XX made Twenty 400 the whole person, which
    lost the Italy lead on 2026-07-31. Bare numbers default to DE (shop's home)."""
    phone = (phone or "").strip()
    if phone.startswith("+"):
        return {"primaryPhoneNumber": phone}
    return {"primaryPhoneNumber": phone, "primaryPhoneCountryCode": "DE"}


def _person_body(data: dict) -> dict:
    body: dict = {"name": _split_name(data.get("name", "Unbekannt"))}
    email = data.get("email")
    if email:
        body["emails"] = {"primaryEmail": email}
    phone = data.get("phone_or_whatsapp")
    if phone:
        body["phones"] = _phone_field(phone)
    for field in ("stadt", "plz", "strasse"):
        if data.get(field):
            body[field] = data[field]
    return body


def _find_person_by_email(base: str, headers: dict, email: str) -> str | None:
    """Ищет существующую карточку РОВНО по адресу почты.

    Проверено живыми запросами к их Twenty 10.08.2026 (лид Jost Dolinsek):
      - вторая карточка с той же почтой отклоняется, 400 «A duplicate entry
        was detected», именно на этом сломался лид;
      - полный тёзка с другой почтой создаётся спокойно (201);
      - тот же телефон при другой почте тоже создаётся (201);
      - встроенный сопоставитель дублей Twenty ищет ПО ИМЕНИ и на «Thomas Simon»
        отдаёт чужого человека, поэтому источником id он быть не может.
    Отсюда правило: связываем только по почте, ни по имени, ни по телефону.
    Почта сверяется без учёта регистра (фильтр `ilike`), и найденная запись
    перепроверяется на точное совпадение, чтобы служебные символы шаблона не
    подтянули чужой адрес."""
    email = (email or "").strip()
    if not email:
        return None
    try:
        r = requests.get(f"{base}/rest/people", params={"filter": f"emails.primaryEmail[ilike]:{email}"},
                         headers=headers, timeout=15)
        if not r.ok:
            return None
        for p in (r.json().get("data") or {}).get("people") or []:
            found = ((p.get("emails") or {}).get("primaryEmail") or "").strip()
            if found.lower() == email.lower():
                return p.get("id")
    except Exception as e:  # поиск никогда не роняет запись лида
        logger.warning("person lookup by email failed: %s", e)
    return None


def _enrich_person(base: str, headers: dict, person_id: str, data: dict) -> None:
    """Дозаполняет ПУСТЫЕ поля найденной карточки тем, что принёс разговор.
    Ничего уже заполненного не перезаписывает: данные команды главнее наших."""
    try:
        r = requests.get(f"{base}/rest/people/{person_id}", headers=headers, timeout=15)
        if not r.ok:
            return
        cur = (r.json().get("data") or {}).get("person") or {}
        patch: dict = {}
        if data.get("email") and not (cur.get("emails") or {}).get("primaryEmail"):
            patch["emails"] = {"primaryEmail": data["email"]}
        if data.get("phone_or_whatsapp") and not (cur.get("phones") or {}).get("primaryPhoneNumber"):
            patch["phones"] = _phone_field(data["phone_or_whatsapp"])
        for field in ("stadt", "plz", "strasse"):
            if data.get(field) and not cur.get(field):
                patch[field] = data[field]
        if patch:
            requests.patch(f"{base}/rest/people/{person_id}", json=patch, headers=headers, timeout=15)
            logger.info("Existing person %s enriched: %s", person_id, ", ".join(patch))
    except Exception as e:  # дозаполнение необязательное, лид важнее
        logger.warning("person enrich failed: %s", e)


def _create_person(base: str, headers: dict, data: dict) -> str | None:
    email = data.get("email")
    existing = _find_person_by_email(base, headers, email) if email else None
    if existing:
        logger.info("Existing person reused id=%s", existing)
        _enrich_person(base, headers, existing, data)
        return existing
    r = requests.post(f"{base}/rest/people", json=_person_body(data), headers=headers, timeout=15)
    if r.status_code == 400 and "duplicate" in (r.text or "").lower():
        # Гонка: карточку завели между поиском и записью. Ищем ещё раз.
        existing = _find_person_by_email(base, headers, email) if email else None
        logger.info("Duplicate on create, resolved to existing id=%s", existing)
        if existing:
            _enrich_person(base, headers, existing, data)
            return existing
        # Не нашли: сделка всё равно пишется, контакты уезжают в заметку и алерт.
        r.raise_for_status()
    r.raise_for_status()
    return (r.json().get("data", {}).get("createPerson") or {}).get("id")


def _kontaktzeile(data: dict) -> list:
    """Die Kontaktdaten IM Text, damit das Team direkt schreiben kann und keine
    CRM öffnen muss (Regel vom 10.08.2026)."""
    bits = [f"Name: {data.get('name') or 'Unbekannt'}"]
    if data.get("phone_or_whatsapp"):
        bits.append(f"Telefon/WhatsApp: {data['phone_or_whatsapp']}")
    if data.get("email"):
        bits.append(f"E-Mail: {data['email']}")
    addr = ", ".join(filter(None, [data.get("strasse"), data.get("plz"),
                                   data.get("stadt")]))
    if addr:
        bits.append(f"Adresse: {addr}")
    return bits


def notify_lead(data: dict, sku_str: str, area, hot: bool, opp_id, env: dict) -> str:
    """Das Team erfährt von JEDEM Kunden, per E-Mail.

    Vorher ging nur ein HEISSER Lead raus, und zwar nach Telegram zu Oleg, wo
    niemand aus dem Laden sitzt. Ein Showroom-Termin gilt nach der Punktevergabe
    nie als heiß, also erfuhr vom Termin niemand: Befund 10.09.2026.
    """
    action = data.get("action") or "none"
    if action == "showroom_booking":
        subject = f"Showroom-Termin: {data.get('showroom_slot') or 'Zeit offen'}"
    elif hot:
        subject = "Heisser Lead aus dem Berater-Chat"
    elif (data.get("lead_flag") or "normal") != "normal":
        subject = f"Sonderanfrage aus dem Berater-Chat ({data['lead_flag']})"
    else:
        subject = "Neuer Lead aus dem Berater-Chat"

    lines = _kontaktzeile(data)
    if data.get("showroom_slot"):
        lines.append(f"Wunschtermin: {data['showroom_slot']} "
                     f"(bitte beim Kunden bestaetigen)")
    if sku_str:
        lines.append(f"Produkt: {sku_str}")
    if area:
        lines.append(f"Flaeche: {area} m2")
    if data.get("urgency"):
        lines.append(f"Dringlichkeit: {data['urgency']}")
    if data.get("conversation_summary"):
        lines.append("")
        lines.append(f"Worum es ging: {data['conversation_summary']}")
    if data.get("info_note"):
        lines.append(f"Notiz: {data['info_note']}")
    if opp_id:
        lines.append("")
        lines.append(f"CRM: {opp_id}")
    body = "\n".join(lines)

    status = send_team_mail(subject, body, env)
    if status != "sent":
        # Netz darunter: solange das Postfach nicht steht (oder gerade streikt),
        # geht die Nachricht den alten Weg. Ein Kunde darf nie verloren gehen,
        # nur weil ein Schluessel fehlt.
        _send_problem_alert(
            f"[Почта команде не ушла: {status}] {subject}\n{body}", env)
    return status


def create_lead(data: dict, env: dict) -> dict:
    """Create a Person + Opportunity in Twenty from the assistant's create_lead tool call."""
    base = _base(env)
    if not base:
        return {"status": "error", "reason": "TWENTY_API_URL not configured"}
    if not data.get("dsgvo_consent"):
        return {"status": "error", "reason": "DSGVO consent not given, lead not written"}

    headers = _headers(env)
    hot = _is_hot(data)

    skus = data.get("interested_products") or []
    sku_str = ", ".join(skus) if skus else ""
    area = data.get("area_sqm")
    profile = data.get("profile") or {}
    name = data.get("name", "Unbekannt")

    # title, same convention as the Bitrix build
    flag = data.get("lead_flag", "normal")
    prefix = {"auslandsversand": "[AUSLAND] ", "sonderanfrage": "[SONDERFALL] "}.get(flag, "")
    title = f"{prefix}FYF: {name}"
    if area:
        title += f", {area}m2"
    if skus:
        title += f", {skus[0]}"

    # The opportunity is the lead and is written ALWAYS. A person/contact
    # failure (bad phone format, API hiccup) must never take the deal down
    # with it: the contact then travels as plain text in the note instead.
    person_id = None
    person_err = ""
    try:
        person_id = _create_person(base, headers, data)
    except requests.RequestException as e:
        detail = getattr(e.response, "text", "")[:300] if getattr(e, "response", None) else ""
        person_err = f"{e} {detail}".strip()
        logger.error("Twenty person creation failed, writing contact into note: %s", person_err)

    try:
        opp: dict = {
            "name": title,
            "stage": NEW_LEAD_STAGE,
            "quelle": QUELLE,
            "leadScore": "HOT" if hot else "WARM",
            "dsgvoEinwilligung": True,
            "verlegungGewunscht": bool(data.get("verlegung_wanted")),
            "notiz": _build_notiz(data),
        }
        if person_id:
            opp["pointOfContactId"] = person_id
        owner_id = env.get("TWENTY_OWNER_ID")
        if owner_id:
            opp["ownerId"] = owner_id
        if sku_str:
            opp["interessiertesProdukt"] = sku_str
        if area is not None:
            opp["mengeM2"] = float(area)
        if data.get("zubehoer_interest"):
            opp["zubehoerInteresse"] = data["zubehoer_interest"]
        if data.get("urgency") in URGENCY_MAP:
            opp["dringlichkeit"] = URGENCY_MAP[data["urgency"]]
        opp["leadFlag"] = FLAG_MAP.get(flag, "NORMAL")
        if profile:
            opp["profil"] = json.dumps(profile, ensure_ascii=False)
        if data.get("info_note"):
            opp["notiz"] = opp["notiz"] + f"\n{data['info_note']}"
        if person_id is None:
            contact_lines = ["", "!! KONTAKT (Person-Anlage fehlgeschlagen, Daten hier):",
                             f"Name: {name}"]
            if data.get("phone_or_whatsapp"):
                contact_lines.append(f"Telefon/WhatsApp: {data['phone_or_whatsapp']}")
            if data.get("email"):
                contact_lines.append(f"E-Mail: {data['email']}")
            addr = ", ".join(filter(None, [data.get("strasse"), data.get("plz"), data.get("stadt")]))
            if addr:
                contact_lines.append(f"Adresse: {addr}")
            if person_err:
                contact_lines.append(f"(Fehler: {person_err[:160]})")
            opp["notiz"] = opp["notiz"] + "\n".join(contact_lines)

        est = data.get("budget_eur_per_sqm")
        if est and area:
            opp["amount"] = {"amountMicros": int(round(float(est) * float(area) * 1_000_000)),
                             "currencyCode": "EUR"}

        r = requests.post(f"{base}/rest/opportunities", json=opp, headers=headers, timeout=15)
        r.raise_for_status()
        opp_id = (r.json().get("data", {}).get("createOpportunity") or {}).get("id")
        logger.info("Twenty lead created opp=%s person=%s hot=%s", opp_id, person_id, hot)

        # Kunden gehören dem Team, nicht Oleg (seine Ansage 10.09.2026 13:27).
        notify_lead(data, sku_str, area, hot, opp_id, env)
        if person_id is None:
            # Алерт обязан нести сами контакты: команда связывается с клиентом
            # из сообщения, не открывая CRM и не спрашивая никого (10.08.2026).
            bits = [f"Имя: {name}"]
            if data.get("phone_or_whatsapp"):
                bits.append(f"Телефон/WhatsApp: {data['phone_or_whatsapp']}")
            if data.get("email"):
                bits.append(f"Почта: {data['email']}")
            addr = ", ".join(filter(None, [data.get("strasse"), data.get("plz"), data.get("stadt")]))
            if addr:
                bits.append(f"Адрес: {addr}")
            send_team_mail(
                "Lead ohne Kontaktkarte in der CRM: bitte manuell nachtragen",
                "Der Lead ist gespeichert, aber ohne Kontaktkarte. "
                "Die Daten stehen hier:\n" + "\n".join(bits)
                + f"\nCRM: {opp_id}", env)
            _send_problem_alert(
                "Технический сбой: лид записан без карточки контакта. "
                f"Команде письмо ушло, контакты у них.\nCRM: {opp_id}\n"
                f"Причина: {person_err[:200]}", env)

        return {"status": "ok", "lead_id": opp_id, "hot": hot}

    except requests.RequestException as e:
        detail = getattr(e.response, "text", "")[:300] if getattr(e, "response", None) else ""
        logger.error("Twenty lead creation failed: %s %s", e, detail)
        # Полные контакты в алерте, чтобы команда могла связаться с клиентом
        # сразу и внести его в CRM руками (CRM в этот момент недоступна).
        contact_bits = [f"Имя: {name}"]
        if data.get("phone_or_whatsapp"):
            contact_bits.append(f"Телефон/WhatsApp: {data['phone_or_whatsapp']}")
        if data.get("email"):
            contact_bits.append(f"Почта: {data['email']}")
        addr = ", ".join(filter(None, [data.get("strasse"), data.get("plz"), data.get("stadt")]))
        if addr:
            contact_bits.append(f"Адрес: {addr}")
        send_team_mail(
            "Neuer Kunde aus dem Berater-Chat (CRM gerade nicht erreichbar)",
            "Bitte manuell aufnehmen, alle Daten hier:\n"
            + "\n".join(contact_bits)
            + f"\nProdukt: {sku_str}\nFlaeche: {area} m2"
            + (f"\nWorum es ging: {data.get('conversation_summary', '')[:300]}"
               if data.get("conversation_summary") else ""), env)
        _send_problem_alert(
            "СБОЙ записи лида в CRM. Команде письмо с контактами ушло.\n"
            + f"\nПродукт: {sku_str}\nПлощадь: {area} м²"
            + (f"\nЗапрос: {data.get('conversation_summary', '')[:200]}" if data.get('conversation_summary') else "")
            + f"\nОшибка: {f'{e} {detail}'.strip()[:200]}", env)
        return {"status": "error", "reason": f"{e} {detail}".strip()}


def _send_problem_alert(text: str, env: dict):
    """Any create_lead failure alerts the same Telegram chat as HOT leads.
    Before 2026-08-04 failures only went to the server log and the Italy lead
    (63 m2, 31.07) died silently; this must never be silent again. Non-blocking."""
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    thread_id = env.get("TELEGRAM_HOT_THREAD_ID", "")
    if not token or not chat_id:
        logger.warning("Telegram not configured, problem alert lost: %s", text[:120])
        return
    payload: dict = {"chat_id": chat_id, "text": "⚠️ Проблема, Find Your Floor\n" + text}
    if thread_id:
        payload["message_thread_id"] = int(thread_id)
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=10)
        logger.info("Telegram problem alert sent")
    except Exception as e:
        logger.warning("Telegram problem alert failed (non-blocking): %s", e)


def _send_telegram_alert(name: str, skus: str, area, city: str, lead_id, env: dict):
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    thread_id = env.get("TELEGRAM_HOT_THREAD_ID", "")
    if not token or not chat_id:
        logger.info("Telegram not configured, skipping HOT alert for lead %s", lead_id)
        return
    text = (
        "🔥 Горячий лид, Find Your Floor\n"
        f"Имя: {name}\nПродукт: {skus}\nПлощадь: {area} м²\nГород: {city}\n"
        f"Twenty opp ID: {lead_id}"
    )
    payload: dict = {"chat_id": chat_id, "text": text}
    if thread_id:
        payload["message_thread_id"] = int(thread_id)
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=10)
        logger.info("Telegram HOT alert sent for lead %s", lead_id)
    except Exception as e:
        logger.warning("Telegram alert failed (non-blocking): %s", e)
