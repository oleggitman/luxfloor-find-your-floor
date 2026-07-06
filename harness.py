"""Find Your Floor — CLI test harness (Phase 1: the brain).

Wires the locked system prompt + knowledge base to Claude (Sonnet 4.6) with the
two live WooCommerce tools (search_products, estimate_shipping). Lets you talk to
the assistant the way a site visitor would and watch it qualify + recommend like
Ilya sells, before any widget or hosting exists.

  interactive:  .venv/bin/python clients/luxfloor/site-assistant/harness.py
  scripted run: .venv/bin/python clients/luxfloor/site-assistant/harness.py --scripted

create_lead (Bitrix) is Phase 2 and intentionally NOT wired here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import anthropic

from woo_client import WooClient, load_env, dispatch

HERE = Path(__file__).parent
SYSTEM_PROMPT = (HERE / "system-prompt.md").read_text()
KNOWLEDGE_BASE = (HERE / "knowledge-base.md").read_text()

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
                "surface": {"type": "string", "enum": ["Hochglanz", "Matt", "Strukturiert"]},
                "format": {"type": "string", "enum": ["Diele", "Breitdiele", "Fliese", "Herringbone", "Quadratisch"]},
                "design": {"type": "string", "enum": ["Holzoptik", "Steinoptik", "Uni", "Marmoroptik"]},
                "color": {"type": "string", "enum": ["hell", "dunkel", "braun", "grau"]},
                "material_type": {"type": "string", "enum": ["Klick-Vinyl", "Klebe-Vinyl", "SPC-Rigid-Vinyl", "Laminat", "Echtholz", "lose-Verlegung"]},
                "constraints": {"type": "array", "items": {"type": "string", "enum": ["underfloor_heating", "low_build_height", "install_on_top", "rigid", "waterproof", "durable_high_traffic", "removable_later", "eco_natural"]}},
                "room": {"type": "string", "enum": ["Wohnzimmer", "Kueche", "Flur", "Bad", "Schlafzimmer", "Gewerbe"]},
                "usage_class_min": {"type": "integer"},
                "budget_max_eur_per_sqm": {"type": "number"},
                "limit": {"type": "integer", "default": 3},
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
                            "sku": {"type": "string"},
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
        "name": "lookup_product",
        "description": (
            "Look up a SPECIFIC product the visitor names: an article number/SKU "
            "(e.g. CheckOne-2157, D2935), an exact product name, or a pasted "
            "lux-floor.de link. Returns up to `limit` full cards. If count is 0, "
            "say so plainly and escalate; never invent a price or specs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
]

# Static system blocks; cache the big KB so repeated turns are cheap.
SYSTEM = [
    {"type": "text", "text": SYSTEM_PROMPT},
    {"type": "text", "text": "# KNOWLEDGE BASE\n\n" + KNOWLEDGE_BASE,
     "cache_control": {"type": "ephemeral"}},
]


def run_turn(client, woo, model, messages):
    """Drive one user turn to completion, resolving any tool calls. Returns the
    assistant's final visible text and the updated message list."""
    while True:
        resp = client.messages.create(
            model=model, max_tokens=1200, system=SYSTEM,
            tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return text, messages, resp.usage

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            print(f"   [tool: {block.name}({_fmt_args(block.input)})]")
            try:
                result = dispatch(block.name, block.input, woo)
                status = "ok"
            except Exception as e:  # surface tool failure to the model, don't crash
                result = {"status": "error", "reason": str(e)}
                status = "error"
            n = result.get("count")
            print(f"   [-> {status}" + (f", {n} products" if n is not None else "") + "]")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _to_json(result),
            })
        messages.append({"role": "user", "content": tool_results})


def _fmt_args(d):
    return ", ".join(f"{k}={v}" for k, v in d.items() if v not in (None, [], ""))


def _to_json(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)


SCRIPT = [
    "Hallo, ich suche einen neuen Boden fürs Wohnzimmer.",
    "Hochglanz gefällt mir, am liebsten Steinoptik in Hell.",
    "Es ist ein Wohnzimmer, ca. 25 m². Wir laufen viel mit dem Hund durch.",
    "Wir haben eine Fußbodenheizung. Was würdet ihr empfehlen?",
    "Klingt gut. Was würde der Versand nach Köln kosten?",
]


def main():
    env = load_env()
    model = env.get("ASSISTANT_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"])
    woo = WooClient(env)
    scripted = "--scripted" in sys.argv

    print(f"Find Your Floor harness · model={model} · "
          f"{'SCRIPTED' if scripted else 'interactive (Strg-C zum Beenden)'}\n")
    messages = []
    total_in = total_out = 0

    def turn(user_text):
        nonlocal total_in, total_out
        print(f"\033[36mKunde:\033[0m {user_text}")
        messages.append({"role": "user", "content": user_text})
        text, _, usage = run_turn(client, woo, model, messages)
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        print(f"\033[32mAssistent:\033[0m {text}\n")

    try:
        if scripted:
            for line in SCRIPT:
                turn(line)
        else:
            while True:
                user_text = input("\033[36mKunde:\033[0m ").strip()
                if user_text:
                    turn(user_text)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        print(f"--- tokens: in={total_in} out={total_out} ---")


if __name__ == "__main__":
    main()
