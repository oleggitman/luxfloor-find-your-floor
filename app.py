"""Find Your Floor, production FastAPI backend.

Endpoints:
  POST /chat    {session_id?, message} -> {reply, session_id}
  GET  /health  -> {status: "ok"}

Sessions are in-memory dicts with 2-hour TTL. Session loss on Render restart
is acceptable for v1 (user starts a fresh chat).

Tools wired:
  search_products   -> woo_client
  estimate_shipping -> woo_client
  create_lead       -> bitrix_client
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bitrix_client import create_lead
from distill import _read_log, _scrub, run_distill
from woo_client import WooClient, dispatch as woo_dispatch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HERE = Path(__file__).parent


def _load_env() -> dict:
    """Load from .env file if present (local dev), then overlay os.environ."""
    out = {}
    env_file = HERE / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    out.update(os.environ)
    return out


ENV = _load_env()
SYSTEM_PROMPT  = (HERE / "system-prompt.md").read_text()
KNOWLEDGE_BASE = (HERE / "knowledge-base.md").read_text()
MODEL = ENV.get("ASSISTANT_MODEL", "claude-sonnet-4-6")

# --- conversation logging (observability) ---
# One JSON line per turn to LOG_PATH + an in-memory ring buffer for /admin.
# LOG_PATH is ephemeral on Render unless a persistent disk is mounted there.
# Safe with the current single-worker uvicorn (render.yaml has no --workers);
# the buffer is per-process if workers are ever added.
LOG_PATH = ENV.get("LOG_PATH", str(HERE / "conversations.jsonl"))
ADMIN_TOKEN = ENV.get("ADMIN_TOKEN", "")
# Read-only token, scoped to the anonymized /admin/cards feed only. Safe to hand
# to a client's own AIOS: it cannot read raw conversations or trigger distill/purge.
CARDS_TOKEN = ENV.get("CARDS_TOKEN", "")
CONV_LOG: deque = deque(maxlen=200)

# --- anonymized distillation (cards.jsonl lives next to the raw log) ---
# Raw turns are a short buffer: phone/email are masked at write time, the whole
# conversation is distilled into one anonymized card once it settles, and raw
# older than RAW_RETAIN_HOURS is purged. Personal data never lives long-term.
_LOG_DIR = os.path.dirname(LOG_PATH) or "."
CARDS_PATH = ENV.get("CARDS_PATH", os.path.join(_LOG_DIR, "cards.jsonl"))
MARKER_PATH = ENV.get("DISTILL_MARKER_PATH", os.path.join(_LOG_DIR, "distilled.json"))
RAW_RETAIN_HOURS = float(ENV.get("RAW_RETAIN_HOURS", "48"))
DISTILL_MIN_INTERVAL = 3600  # at most once an hour, kicked off after a /chat reply
_last_distill = {"ts": 0.0}


def _log_turn(session_id: str, user: str, assistant: str, options: list, meta: dict) -> None:
    """Append one turn to the ring buffer and JSONL. Never breaks a reply.
    Phone numbers and emails are masked here so the raw buffer never holds them;
    the real lead contact still reaches Bitrix via create_lead (session memory)."""
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session_id": session_id,
        "user": _scrub(user),
        "assistant": _scrub(assistant),
        "options": options,
        "tools": meta.get("tools", []),
        "lead": meta.get("lead"),
    }
    CONV_LOG.append(rec)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("conv log write failed: %s", e)


def _read_recent(limit: int) -> list:
    """Read the last `limit` turns from the durable JSONL (survives restarts on a
    persistent disk). Falls back to the in-memory buffer if the file is missing."""
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        out = []
        for ln in lines:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
        return out
    except OSError:
        return list(CONV_LOG)[-limit:]

SYSTEM = [
    {"type": "text", "text": SYSTEM_PROMPT},
    {"type": "text", "text": "# KNOWLEDGE BASE\n\n" + KNOWLEDGE_BASE,
     "cache_control": {"type": "ephemeral"}},
]

TOOLS = [
    {
        "name": "search_products",
        "description": (
            "Search the Lux-Floor WooCommerce catalog for floors matching the "
            "customer's profile and constraints. Returns up to `limit` products as "
            "cards, pre-ranked: fitting own-brand-on-promotion first, then other "
            "fitting products. Only call once you have enough of the profile (look + "
            "material direction + at least the room or key constraints). Never "
            "recommend a product this tool did not return."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "surface":   {"type": "string", "enum": ["Hochglanz", "Matt", "Strukturiert"]},
                "format":    {"type": "string", "enum": ["Diele", "Breitdiele", "Fliese", "Herringbone", "Quadratisch"]},
                "design":    {"type": "string", "enum": ["Holzoptik", "Steinoptik", "Uni", "Marmoroptik"]},
                "color":     {"type": "string", "enum": ["hell", "dunkel", "braun", "grau"]},
                "material_type": {"type": "string", "enum": ["Klick-Vinyl", "Klebe-Vinyl", "SPC-Rigid-Vinyl", "Laminat", "Echtholz", "lose-Verlegung"]},
                "constraints": {"type": "array", "items": {"type": "string", "enum": ["underfloor_heating", "low_build_height", "install_on_top", "rigid", "waterproof", "durable_high_traffic", "removable_later", "eco_natural"]}},
                "room":      {"type": "string", "enum": ["Wohnzimmer", "Kueche", "Flur", "Bad", "Schlafzimmer", "Gewerbe"]},
                "usage_class_min": {"type": "integer"},
                "budget_max_eur_per_sqm": {"type": "number"},
                "limit":     {"type": "integer", "default": 3},
            },
            "required": ["constraints"],
        },
    },
    {
        "name": "lookup_product",
        "description": (
            "Look up a SPECIFIC product the visitor names: an article number/SKU "
            "(e.g. CheckOne-2157, D2935), an exact product name, or a pasted "
            "lux-floor.de link. Use this whenever the customer references a concrete "
            "product rather than a profile. Returns up to `limit` full cards (name, "
            "sku, price, on-sale, surface/optik/format, usage class, url, m2-per-"
            "package, weight). If count is 0, say so plainly and offer to help "
            "differently or pass it to the team, never invent a price or specs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The article number, product name, or shop link the visitor gave."},
                "limit": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "estimate_shipping",
        "description": (
            "Estimate domestic German (Festland) shipping cost for the chosen "
            "product(s) and area in m2. Germany mainland only; for abroad do NOT call "
            "this, escalate to info@lux-floor.de. Present the result as an estimate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sku":      {"type": "string"},
                            "area_sqm": {"type": "number"},
                        },
                        "required": ["sku", "area_sqm"],
                    },
                },
                "country": {"type": "string", "default": "DE"},
            },
            "required": ["items"],
        },
    },
    {
        "name": "create_lead",
        "description": (
            "Create a lead in Bitrix24 with the captured profile, contact, and consent. "
            "Call once: after the customer has given DSGVO consent and at least "
            "Name + (Telefon/WhatsApp OR E-Mail) + Stadt + PLZ. "
            "Do NOT call without consent. The backend computes the estimated value "
            "and HOT/Warm score and notifies the team; you only pass honest captured data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name":               {"type": "string"},
                "phone_or_whatsapp":  {"type": "string"},
                "email":              {"type": "string"},
                "stadt":              {"type": "string"},
                "plz":                {"type": "string"},
                "strasse":            {"type": "string"},
                "interested_products": {"type": "array", "items": {"type": "string"}},
                "area_sqm":           {"type": "number"},
                "budget_eur_per_sqm": {"type": "number"},
                "verlegung_wanted":   {"type": "boolean"},
                "zubehoer_interest":  {"type": "string"},
                "profile": {
                    "type": "object",
                    "properties": {
                        "optik":       {"type": "string"},
                        "material":    {"type": "string"},
                        "constraints": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "urgency":    {"type": "string", "enum": ["needed_now", "has_time", "needs_storage"]},
                "info_note":  {"type": "string"},
                "conversation_summary": {"type": "string", "description": "VERY brief summary for the sales team: what the customer wants, key concerns, budget signal. Max 2-3 short sentences. German."},
                "lead_flag":  {"type": "string", "enum": ["normal", "auslandsversand", "sonderanfrage"], "description": "Mark 'auslandsversand' for abroad delivery, 'sonderanfrage' for any special request the assistant cannot resolve. Default 'normal'."},
                "action":     {"type": "string", "enum": ["none", "sample_request", "showroom_booking"]},
                "showroom_slot": {"type": "string"},
                "dsgvo_consent": {"type": "boolean"},
            },
            "required": ["name", "stadt", "plz", "urgency", "dsgvo_consent"],
        },
    },
]

woo = WooClient(ENV)
ai  = anthropic.Anthropic(api_key=ENV["ANTHROPIC_API_KEY"])

SESSION_TTL = 7200
sessions: dict[str, dict] = {}


def _prune_sessions():
    now = time.time()
    stale = [sid for sid, s in sessions.items() if now - s["last_active"] > SESSION_TTL]
    for sid in stale:
        del sessions[sid]


def _dispatch_tool(name: str, args: dict) -> dict:
    if name in ("search_products", "estimate_shipping", "lookup_product"):
        return woo_dispatch(name, args, woo)
    if name == "create_lead":
        return create_lead(args, ENV)
    raise ValueError(f"unknown tool: {name}")


def _require_admin(token: str) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN not configured")
    if not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


def _require_cards(token: str) -> None:
    """Auth for the anonymized cards feed: the read-only CARDS_TOKEN OR the
    full ADMIN_TOKEN. Lets a client's AIOS read cards without the master key."""
    if CARDS_TOKEN and hmac.compare_digest(token, CARDS_TOKEN):
        return
    if ADMIN_TOKEN and hmac.compare_digest(token, ADMIN_TOKEN):
        return
    raise HTTPException(status_code=401, detail="unauthorized")


def _maybe_distill() -> None:
    """Throttled background pass: distill settled conversations into anonymized
    cards and purge raw older than the retain window. Runs at most once an hour,
    kicked off after a /chat reply. Never raises into the request path."""
    now = time.time()
    if now - _last_distill["ts"] < DISTILL_MIN_INTERVAL:
        return
    _last_distill["ts"] = now
    try:
        stats = run_distill(LOG_PATH, CARDS_PATH, MARKER_PATH, ai, MODEL,
                            retain_hours=RAW_RETAIN_HOURS)
        logger.info("distill: %s", stats)
    except Exception as e:  # noqa: BLE001
        logger.warning("distill run failed: %s", e)


app = FastAPI(title="Find Your Floor Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    options: list[str] = []


# Quick-reply chips: the model may append one [[CHIPS: a | b | c]] marker to its
# reply. We strip it from the visible text and return the options to the widget,
# which renders them as tappable buttons. No marker -> no chips (graceful).
CHIPS_RE = re.compile(r"\[\[\s*CHIPS\s*:\s*(.*?)\]\]", re.IGNORECASE | re.DOTALL)


def _extract_chips(reply: str) -> tuple[str, list[str]]:
    m = CHIPS_RE.search(reply)
    if not m:
        return reply.strip(), []
    seen, options = set(), []
    for opt in m.group(1).split("|"):
        opt = opt.strip()
        if opt and opt not in seen:
            seen.add(opt)
            options.append(opt)
    clean = CHIPS_RE.sub("", reply).strip()
    return clean, options[:6]


# --- abuse / cost protection (in-memory) ---
PER_IP_HOURLY_LIMIT = 40
GLOBAL_DAILY_LIMIT = 600
_ip_hits: dict[str, list] = {}
_daily = {"day": None, "count": 0}

RATE_LIMIT_MSG = (
    "Wir haben heute schon sehr viele Anfragen. Bitte kontaktieren Sie uns "
    "direkt: Telefon 02131 2917676, WhatsApp +49 179 403 33 81 oder "
    "info@lux-floor.de. Wir helfen Ihnen gerne weiter."
)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    if _daily["day"] != today:
        _daily["day"] = today
        _daily["count"] = 0
    if _daily["count"] >= GLOBAL_DAILY_LIMIT:
        return True
    hits = [t for t in _ip_hits.get(ip, []) if now - t < 3600]
    if len(hits) >= PER_IP_HOURLY_LIMIT:
        _ip_hits[ip] = hits
        return True
    hits.append(now)
    _ip_hits[ip] = hits
    _daily["count"] += 1
    return False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"commit": ENV.get("RENDER_GIT_COMMIT", "unknown"),
            "branch": ENV.get("RENDER_GIT_BRANCH", "unknown")}


@app.get("/admin/conversations")
def admin_conversations(token: str = "", limit: int = 50):
    """Recent raw turns (short buffer) for quality review. Token-gated. Phone/email
    are masked at write time; names may persist up to RAW_RETAIN_HOURS, keep private."""
    _require_admin(token)
    turns = _read_recent(max(1, min(limit, 500)))
    convos: dict = {}
    for t in turns:
        convos.setdefault(t.get("session_id"), []).append(t)
    return {"count": len(turns), "sessions": convos}


@app.post("/admin/distill")
def admin_distill(token: str = ""):
    """Force a distillation + purge pass now (the same job /chat triggers hourly)."""
    _require_admin(token)
    return run_distill(LOG_PATH, CARDS_PATH, MARKER_PATH, ai, MODEL,
                       retain_hours=RAW_RETAIN_HOURS)


@app.get("/admin/cards")
def admin_cards(token: str = "", limit: int = 100):
    """Anonymized analysis cards (long-term store). No names/contacts/addresses.
    This is the source Ilya's AIOS reads. Read-only CARDS_TOKEN or ADMIN_TOKEN."""
    _require_cards(token)
    cards = _read_log(CARDS_PATH)[-max(1, min(limit, 1000)):]
    return {"count": len(cards), "cards": cards}


@app.get("/widget.js")
def serve_widget():
    path = HERE / "widget.js"
    return FileResponse(path, media_type="application/javascript")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, background_tasks: BackgroundTasks):
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
    if _rate_limited(ip):
        sid = req.session_id or str(uuid.uuid4())
        return ChatResponse(reply=RATE_LIMIT_MSG, session_id=sid)

    _prune_sessions()

    sid = req.session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = {"messages": [], "last_active": time.time()}
    session = sessions[sid]
    session["last_active"] = time.time()

    messages = session["messages"]
    messages.append({"role": "user", "content": req.message})

    reply_raw, meta = _run_turn(messages)
    session["last_active"] = time.time()

    reply, options = _extract_chips(reply_raw)
    _log_turn(sid, req.message, reply, options, meta)
    background_tasks.add_task(_maybe_distill)
    return ChatResponse(reply=reply, session_id=sid, options=options)


def _run_turn(messages: list) -> tuple[str, dict]:
    used_tools: list = []
    lead = None
    while True:
        resp = ai.messages.create(
            model=MODEL,
            max_tokens=1200,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return text, {"tools": used_tools, "lead": lead}

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            used_tools.append(block.name)
            logger.info("tool=%s args=%s", block.name, list(block.input.keys()))
            try:
                result = _dispatch_tool(block.name, block.input)
                if block.name == "create_lead":
                    lead = {"id": result.get("lead_id"), "hot": result.get("hot")}
                    logger.info("lead created id=%s hot=%s",
                                result.get("lead_id"), result.get("hot"))
            except Exception as e:
                result = {"status": "error", "reason": str(e)}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
        messages.append({"role": "user", "content": tool_results})
