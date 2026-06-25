"""Bitrix24 Phase-2 handler for Find Your Floor.

Implements create_lead: maps the tool schema output onto the live Bitrix24 CRM fields,
computes HOT/Warm score, fires a Telegram Smart Buzz alert for HOT leads.

Field map (confirmed 2026-06-24 via probe_bitrix.py against live instance):
  UF_CRM_1782288993  Stadt           string
  UF_CRM_1782289057  PLZ             string
  UF_CRM_1782289092  Interessiertes Produkt  string
  UF_CRM_1782289104  Menge m2        string
  UF_CRM_1782289152  Verlegung gewuenscht?   boolean (1/0)
  UF_CRM_1782289167  Zubehoer-Interesse      string
  UF_CRM_1782289198  Geschaetzter Auftragswert  double
  UF_CRM_1782289237  Lead-Score      enum (Hot=45, Warm=47)
  UF_CRM_1782289266  Profil          string
  UF_CRM_1782289299  DSGVO-Einwilligung      boolean (1/0)
  UF_CRM_1782289347  Info / Notiz    string
  UF_CRM_1782289403  Quelle          enum (Website-Assistent=49)

Responsible: ASSIGNED_BY_ID=17 (Alisa, primary salesperson for all inbound).
HOT alert: Telegram sendMessage to Ilya (user 1). No-op if TELEGRAM_BOT_TOKEN empty.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

ENV_PATH = Path(__file__).parent / ".env"

ASSIGNED_BY_ID = "17"      # Alisa (responsible). Co-notifying Alexey(13)/Ilya(1)
                           # is done via a Bitrix automation rule in the UI (leads
                           # have no observer field via API + webhook lacks im scope).
                           # Exact routing logic: TBD with Ilya.
QUELLE_WEBSITE = "49"      # Website-Assistent enum value
LEAD_SCORE_HOT  = "45"
LEAD_SCORE_WARM = "47"


def load_env(path: Path = ENV_PATH) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _is_hot(data: dict) -> bool:
    has_contact = bool(data.get("phone_or_whatsapp"))
    urgent      = data.get("urgency") == "needed_now"
    profile     = data.get("profile") or {}
    has_project = bool(
        data.get("area_sqm") and
        data.get("interested_products") and
        profile.get("material")
    )
    return has_contact and urgent and has_project


def _build_comments(data: dict) -> str:
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


def create_lead(data: dict, env: dict) -> dict:
    """Create a lead in Bitrix24 from the assistant's create_lead tool call data."""
    base = env.get("BITRIX_WEBHOOK_URL", "").rstrip("/") + "/"
    if not base or base == "/":
        return {"status": "error", "reason": "BITRIX_WEBHOOK_URL not configured"}

    if not data.get("dsgvo_consent"):
        return {"status": "error", "reason": "DSGVO consent not given — lead not written"}

    hot = _is_hot(data)
    lead_score_id = LEAD_SCORE_HOT if hot else LEAD_SCORE_WARM

    skus = data.get("interested_products") or []
    sku_str = ", ".join(skus) if skus else ""

    area = data.get("area_sqm")
    area_str = str(area) if area is not None else ""

    profile = data.get("profile") or {}
    profile_str = json.dumps(profile, ensure_ascii=False) if profile else ""

    name = data.get("name", "Unbekannt")
    flag = data.get("lead_flag", "normal")
    prefix = ""
    if flag == "auslandsversand":
        prefix = "[AUSLAND] "
    elif flag == "sonderanfrage":
        prefix = "[SONDERFALL] "
    title = f"{prefix}FYF: {name}"
    if area:
        title += f", {area}m2"
    if skus:
        title += f", {skus[0]}"

    fields: dict = {
        "TITLE":          title,
        "NAME":           name,
        "ASSIGNED_BY_ID": ASSIGNED_BY_ID,
        "ADDRESS_CITY":   data.get("stadt", ""),
        "ADDRESS_POSTAL_CODE": data.get("plz", ""),
        "SOURCE_DESCRIPTION": "Website-Assistent",
        "COMMENTS":       _build_comments(data),
        "UF_CRM_1782288993": data.get("stadt", ""),
        "UF_CRM_1782289057": data.get("plz", ""),
        "UF_CRM_1782289092": sku_str,
        "UF_CRM_1782289104": area_str,
        "UF_CRM_1782289152": "1" if data.get("verlegung_wanted") else "0",
        "UF_CRM_1782289167": data.get("zubehoer_interest", ""),
        "UF_CRM_1782289237": lead_score_id,
        "UF_CRM_1782289266": profile_str,
        "UF_CRM_1782289299": "1",
        "UF_CRM_1782289347": data.get("info_note", ""),
        "UF_CRM_1782289403": QUELLE_WEBSITE,
    }

    phone = data.get("phone_or_whatsapp")
    if phone:
        fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "WORK"}]

    email = data.get("email")
    if email:
        fields["EMAIL"] = [{"VALUE": email, "VALUE_TYPE": "WORK"}]

    if data.get("strasse"):
        fields["ADDRESS"] = data["strasse"]

    estimated_value = data.get("budget_eur_per_sqm")
    if estimated_value and area:
        fields["UF_CRM_1782289198"] = round(float(estimated_value) * float(area), 2)
        fields["OPPORTUNITY"] = fields["UF_CRM_1782289198"]

    try:
        r = requests.post(
            base + "crm.lead.add",
            json={"fields": fields},
            timeout=15,
        )
        r.raise_for_status()
        result = r.json()
        lead_id = result.get("result")
        logger.info("Bitrix lead created id=%s hot=%s", lead_id, hot)

        if hot:
            _send_telegram_alert(name, sku_str, area, data.get("stadt", ""), lead_id, env)

        return {"status": "ok", "lead_id": lead_id, "hot": hot}

    except requests.RequestException as e:
        logger.error("Bitrix lead creation failed: %s", e)
        return {"status": "error", "reason": str(e)}


def _send_telegram_alert(name: str, skus: str, area, city: str, lead_id, env: dict):
    token    = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id  = env.get("TELEGRAM_CHAT_ID", "")
    thread_id = env.get("TELEGRAM_HOT_THREAD_ID", "")

    if not token or not chat_id:
        logger.info("Telegram not configured, skipping HOT alert for lead %s", lead_id)
        return

    text = (
        "GORJACHIJ LID — Find Your Floor\n"
        f"Imja: {name}\n"
        f"Produkt: {skus}\n"
        f"Ploshhad: {area} m2\n"
        f"Gorod: {city}\n"
        f"Bitrix lead ID: {lead_id}"
    )
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
    }
    if thread_id:
        payload["message_thread_id"] = int(thread_id)

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=10,
        )
        logger.info("Telegram HOT alert sent for lead %s", lead_id)
    except Exception as e:
        logger.warning("Telegram alert failed (non-blocking): %s", e)
