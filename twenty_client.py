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


def _create_person(base: str, headers: dict, data: dict) -> str | None:
    body: dict = {"name": _split_name(data.get("name", "Unbekannt"))}
    email = data.get("email")
    if email:
        body["emails"] = {"primaryEmail": email}
    phone = data.get("phone_or_whatsapp")
    if phone:
        body["phones"] = _phone_field(phone)
    if data.get("stadt"):
        body["stadt"] = data["stadt"]
    if data.get("plz"):
        body["plz"] = data["plz"]
    if data.get("strasse"):
        body["strasse"] = data["strasse"]
    r = requests.post(f"{base}/rest/people", json=body, headers=headers, timeout=15)
    r.raise_for_status()
    return (r.json().get("data", {}).get("createPerson") or {}).get("id")


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

        if hot:
            _send_telegram_alert(name, sku_str, area, data.get("stadt", ""), opp_id, env)
        if person_id is None:
            _send_problem_alert(
                f"Лид записан, но БЕЗ карточки контакта (телефон и адрес лежат в заметке сделки).\n"
                f"Имя: {name}\nTwenty opp ID: {opp_id}\nПричина: {person_err[:200]}", env)

        return {"status": "ok", "lead_id": opp_id, "hot": hot}

    except requests.RequestException as e:
        detail = getattr(e.response, "text", "")[:300] if getattr(e, "response", None) else ""
        logger.error("Twenty lead creation failed: %s %s", e, detail)
        _send_problem_alert(
            f"СБОЙ записи лида в Twenty! Данные клиента НЕ сохранились.\n"
            f"Имя: {name}\nПродукт: {sku_str}\nПлощадь: {area} м²\n"
            f"Ошибка: {f'{e} {detail}'.strip()[:300]}", env)
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
