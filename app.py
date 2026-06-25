"""Find Your Floor — production FastAPI backend.

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

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bitrix_client import create_lead, load_env
from woo_client import WooClient, dispatch as woo_dispatch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HERE = Path(__file__).parent

ENV = load_env(HERE / ".env")
SYSTEM_PROMPT  = (HERE / "system-prompt.md").read_text()
KNOWLEDGE_BASE = (HERE / "knowledge-base.md").read_text()
MODEL = ENV.get("ASSISTANT_MODEL", "claude-sonnet-4-6")

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
    if name in ("search_products", "estimate_shipping"):
        return woo_dispatch(name, args, woo)
    if name == "create_lead":
        return create_lead(args, ENV)
    raise ValueError(f"unknown tool: {name}")


app = FastAPI(title="Find Your Floor Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lux-floor.de", "https://www.lux-floor.de"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/widget.js")
def serve_widget():
    path = HERE / "widget.js"
    return FileResponse(path, media_type="application/javascript")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    _prune_sessions()

    sid = req.session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = {"messages": [], "last_active": time.time()}
    session = sessions[sid]
    session["last_active"] = time.time()

    messages = session["messages"]
    messages.append({"role": "user", "content": req.message})

    reply = _run_turn(messages)
    session["last_active"] = time.time()

    return ChatResponse(reply=reply, session_id=sid)


def _run_turn(messages: list) -> str:
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
            return "".join(b.text for b in resp.content if b.type == "text")

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            logger.info("tool=%s args=%s", block.name, list(block.input.keys()))
            try:
                result = _dispatch_tool(block.name, block.input)
                if block.name == "create_lead":
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
