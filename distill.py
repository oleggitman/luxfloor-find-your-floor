"""Find Your Floor, conversation anonymization + distillation.

Two jobs, both keep personal data out of long-term storage:

1. _scrub(text): mask phone numbers and emails in raw text BEFORE it is ever
   written to the conversation log. Defense-in-depth; the lead's real contact
   still reaches Bitrix via the create_lead tool (from in-memory session state),
   not from the log.

2. run_distill(...): once settled, each conversation is turned into ONE
   anonymized card (topic, interest, questions, sentiment, masked quotes, no
   names/contacts/addresses) appended to cards.jsonl. The card is what lives
   long-term and flows to Ilya's AIOS. Raw turns older than retain_hours are
   then purged. conversation_id is the existing random session_id, so a single
   visitor's journey can be stitched without storing who they are.
"""
from __future__ import annotations

import calendar
import json
import logging
import os
import re
import time
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

# --- redaction ---------------------------------------------------------------
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Phone-ish runs: optional +, then digits with spaces / () / . / - / slashes.
# We only mask if the run carries 7..15 actual digits, so PLZ (5), prices,
# m2 areas and usage classes are left alone.
_PHONE_RE = re.compile(r"(?<![\w])\+?\d[\d\s().\-/]{5,}\d(?![\w])")


def _scrub(text: Optional[str]) -> Optional[str]:
    """Mask emails and phone numbers. Idempotent, never raises on normal input."""
    if not text:
        return text
    out = _EMAIL_RE.sub("[email]", text)

    def _mask_phone(m: re.Match) -> str:
        digits = sum(c.isdigit() for c in m.group(0))
        return "[telefon]" if 7 <= digits <= 15 else m.group(0)

    return _PHONE_RE.sub(_mask_phone, out)


# --- timestamps --------------------------------------------------------------
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _ts_epoch(ts: str) -> float:
    """Parse a log ts ('...Z', UTC) to epoch seconds. 0.0 if unparseable."""
    try:
        return float(calendar.timegm(time.strptime(ts, _TS_FMT)))
    except (ValueError, TypeError):
        return 0.0


# --- log io ------------------------------------------------------------------
def _read_log(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return out


def _load_marker(path: str) -> "OrderedDict[str, float]":
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return OrderedDict((str(k), float(v)) for k, v in data.items())
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return OrderedDict()


def _save_marker(path: str, marker: "OrderedDict[str, float]", keep_secs: float, now: float) -> None:
    pruned = OrderedDict((k, v) for k, v in marker.items() if now - v < keep_secs)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(pruned, f)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("distill marker save failed: %s", e)


def _append_card(path: str, card: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(card, ensure_ascii=False) + "\n")


def _purge_old(path: str, retain_secs: float, now: float) -> int:
    """Rewrite the log keeping only turns newer than retain window. Returns count purged."""
    rows = _read_log(path)
    if not rows:
        return 0
    kept = [r for r in rows if now - _ts_epoch(r.get("ts", "")) < retain_secs]
    purged = len(rows) - len(kept)
    if purged <= 0:
        return 0
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            for r in kept:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("distill purge failed: %s", e)
        return 0
    return purged


# --- the model pass ----------------------------------------------------------
_CARD_TOOL = {
    "name": "emit_card",
    "description": "Emit the anonymized analysis card for one conversation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {"type": "string", "description": "Main language of the visitor, e.g. de, ru, en."},
            "topic": {"type": "string", "description": "One short line: what the conversation was about."},
            "products_interest": {"type": "array", "items": {"type": "string"},
                                  "description": "Floor types / looks / SKUs the visitor showed interest in."},
            "questions": {"type": "array", "items": {"type": "string"},
                          "description": "Concrete questions or concerns the visitor raised."},
            "constraints": {"type": "array", "items": {"type": "string"},
                            "description": "Practical constraints mentioned (underfloor heating, install on top, waterproof, budget, room, area, etc.)."},
            "bot_answered": {"type": "string", "enum": ["fully", "partially", "no"],
                             "description": "Did the assistant resolve what the visitor needed?"},
            "unresolved": {"type": "string", "description": "What stayed open or where the bot fell short. Empty if none."},
            "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative", "mixed"]},
            "quotes": {"type": "array", "items": {"type": "string"},
                       "description": "1-3 short, representative visitor quotes. Mask any phone/email/name/address as [redacted]."},
            "summary": {"type": "string", "description": "2-3 sentence neutral summary for quality review. No personal data."},
        },
        "required": ["language", "topic", "bot_answered", "sentiment", "summary"],
    },
}

_DISTILL_SYSTEM = (
    "You distill one website-assistant conversation (a flooring shop) into a single "
    "ANONYMIZED analysis card by calling emit_card.\n"
    "ABSOLUTE RULE: never put personal data in ANY field. No names, no phone numbers, "
    "no emails, no street addresses, no order numbers that identify a person. If a quote "
    "contains any of these, replace that part with [redacted]. The card is for quality "
    "review and aggregate analytics only, not for contacting anyone.\n"
    "Be faithful to what actually happened. Do not invent interest, questions, or outcomes "
    "that are not in the transcript. Keep fields short."
)


def distill_conversation(turns: list[dict], client, model: str) -> Optional[dict]:
    """Run one model pass over a conversation's turns -> anonymized card fields.
    Returns None on failure (caller skips this conversation, raw stays until purge)."""
    lines = []
    for t in turns:
        u = (t.get("user") or "").strip()
        a = (t.get("assistant") or "").strip()
        if u:
            lines.append("VISITOR: " + u)
        if a:
            lines.append("ASSISTANT: " + a)
    transcript = "\n".join(lines)[:12000]
    if not transcript:
        return None
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=900,
            system=_DISTILL_SYSTEM,
            tools=[_CARD_TOOL],
            tool_choice={"type": "tool", "name": "emit_card"},
            messages=[{"role": "user", "content": "Distill this conversation:\n\n" + transcript}],
        )
    except Exception as e:  # noqa: BLE001 - never break the batch on one bad call
        logger.warning("distill model call failed: %s", e)
        return None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_card":
            card = dict(block.input)
            # second redaction rail over free-text fields the model produced
            card["quotes"] = [_scrub(q) for q in card.get("quotes", []) if q]
            card["summary"] = _scrub(card.get("summary"))
            card["topic"] = _scrub(card.get("topic"))
            return card
    return None


def run_distill(
    log_path: str,
    cards_path: str,
    marker_path: str,
    client,
    model: str,
    settle_secs: float = 7200.0,
    retain_hours: float = 48.0,
    now: Optional[float] = None,
) -> dict:
    """Distill settled, not-yet-distilled conversations into cards, then purge old raw.

    settle_secs: a conversation must be quiet this long before distillation, so we
                 never card a chat that is still ongoing.
    retain_hours: raw turns older than this are deleted regardless of distill status
                  (personal-data minimization is the priority).
    """
    now = time.time() if now is None else now
    retain_secs = retain_hours * 3600.0

    rows = _read_log(log_path)
    groups: "OrderedDict[str, list]" = OrderedDict()
    for r in rows:
        groups.setdefault(r.get("session_id") or "_none", []).append(r)

    marker = _load_marker(marker_path)
    distilled = 0
    for sid, turns in groups.items():
        if sid in marker:
            continue
        last_ts = max((_ts_epoch(t.get("ts", "")) for t in turns), default=0.0)
        if now - last_ts < settle_secs:
            continue  # still active, wait
        card = distill_conversation(turns, client, model)
        marker[sid] = last_ts  # mark even on None, so we don't retry a bad convo forever
        if not card:
            continue
        ts_list = sorted(t.get("ts", "") for t in turns if t.get("ts"))
        lead_turn = next((t for t in turns if t.get("lead")), None)
        card.update({
            "conversation_id": sid,
            "date": (ts_list[0][:10] if ts_list else None),
            "ts_first": (ts_list[0] if ts_list else None),
            "ts_last": (ts_list[-1] if ts_list else None),
            "turns_count": len(turns),
            "lead_created": bool(lead_turn),
            "lead_hot": (lead_turn.get("lead", {}).get("hot") if lead_turn else None),
        })
        try:
            _append_card(cards_path, card)
            distilled += 1
        except OSError as e:
            logger.warning("card append failed: %s", e)
            marker.pop(sid, None)  # allow retry next run

    _save_marker(marker_path, marker, keep_secs=retain_secs + 86400.0, now=now)
    purged = _purge_old(log_path, retain_secs, now)

    cards_total = len(_read_log(cards_path))
    return {"distilled": distilled, "purged": purged, "cards_total": cards_total}
