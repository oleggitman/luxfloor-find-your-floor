"""Conversational scenario pack for the Find Your Floor brain (uses the LLM).

Drives multi-turn buyer personas through the assistant and asserts on the TOOL
TRACE + final text (which tools fire, with sane args, escalation when it should,
single-SKU shipping, own-brand recommendations). This is the hard-test suite that
catches prompt-level regressions the deterministic handler tests can't see.

  all:   .venv/bin/python clients/luxfloor/site-assistant/scenarios.py
  one:   .venv/bin/python clients/luxfloor/site-assistant/scenarios.py dog_fbh
  quick: .venv/bin/python clients/luxfloor/site-assistant/scenarios.py --quick   (first 3)

Each scenario costs a few LLM turns. Keep the catalog live; assertions are on
behaviour, not exact SKUs.
"""
from __future__ import annotations

import sys

import anthropic

from woo_client import WooClient, load_env, dispatch
from harness import SYSTEM, TOOLS


# --- a turn loop that RECORDS the tool trace --------------------------------
def drive(client, woo, model, turns):
    """Run a full conversation; return (trace, final_texts).
    trace = list of {tool, args, result} across all turns."""
    messages, trace, finals = [], [], []
    for user_text in turns:
        messages.append({"role": "user", "content": user_text})
        while True:
            resp = client.messages.create(
                model=model, max_tokens=1200, system=SYSTEM,
                tools=TOOLS, messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                finals.append("".join(b.text for b in resp.content if b.type == "text"))
                break
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                try:
                    result = dispatch(block.name, block.input, woo)
                except Exception as e:
                    result = {"status": "error", "reason": str(e)}
                trace.append({"tool": block.name, "args": block.input, "result": result})
                import json
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(result, ensure_ascii=False)})
            messages.append({"role": "user", "content": results})
    return trace, finals


# --- assertion helpers ------------------------------------------------------
def calls(trace, tool):
    return [t for t in trace if t["tool"] == tool]


def any_escalation_text(finals):
    blob = " ".join(finals).lower()
    return any(s in blob for s in ["info@lux-floor.de", "02131", "+49 179", "e-mail", "kontaktier"])


def text_has(finals, tokens):
    blob = " ".join(finals).lower()
    return any(t.lower() in blob for t in tokens)


def asks_for_contact(finals):
    blob = " ".join(finals).lower()
    return any(t in blob for t in ["ihre telefonnummer", "ihre e-mail", "wie heißen sie",
                                   "ihren namen", "ihre nummer", "kontaktdaten"])


# --- the scenarios ----------------------------------------------------------
# Each: turns (customer lines) + check(trace, finals) -> (ok: bool, detail: str)
SCENARIOS = {
    "dog_fbh": {
        "desc": "Wohnzimmer, Hund, Fußbodenheizung, Hochglanz Steinoptik -> own-brand rec + single-SKU Versand",
        "turns": [
            "Hallo, ich suche einen Boden fürs Wohnzimmer, Hochglanz in heller Steinoptik.",
            "Ca. 25 m², wir haben einen Hund und eine Fußbodenheizung.",
            "Was empfehlt ihr und was kostet der Versand nach Köln?",
        ],
        "check": lambda tr, fn: _dog_fbh(tr, fn),
    },
    "bathroom_waterproof": {
        "desc": "Bad -> waterproof constraint passed, wet-room product",
        "turns": [
            "Ich brauche einen Boden fürs Badezimmer, ca. 8 m².",
            "Es muss natürlich wasserfest sein, in Holzoptik.",
            "Hell und matt bitte. Zeig mir konkrete Produkte, die passen.",
        ],
        "check": lambda tr, fn: _bathroom(tr, fn),
    },
    "abroad_escalate": {
        "desc": "Customer in Wien -> shipping must NOT be calculated, route to email",
        "turns": [
            "Hallo, ich wohne in Wien, Österreich. Ich interessiere mich für Klick-Vinyl in Holzoptik fürs Wohnzimmer, ca. 30 m².",
            "Könnt ihr mir sagen, was die Lieferung nach Wien kostet?",
        ],
        "check": lambda tr, fn: _abroad(tr, fn),
    },
    "budget_cap": {
        "desc": "Price-sensitive customer -> budget_max passed to search",
        "turns": [
            "Ich suche einen günstigen Laminatboden fürs Schlafzimmer, ca. 14 m².",
            "Mein Budget liegt bei maximal 15 Euro pro Quadratmeter.",
            "Hell und matt, keine Fußbodenheizung. Zeig mir bitte konkrete Produkte.",
        ],
        "check": lambda tr, fn: _budget(tr, fn),
    },
    "commercial_nk": {
        "desc": "Ladenfläche / Gewerbe -> usage_class_min >= 31",
        "turns": [
            "Ich brauche einen sehr robusten Boden für mein Ladengeschäft, viel Kundenlauf.",
            "Es sind ca. 60 m², Holzoptik in mattem Hell wäre schön.",
            "Hohe Beanspruchung muss er aushalten. Zeig mir bitte passende Produkte.",
        ],
        "check": lambda tr, fn: _commercial(tr, fn),
    },
    "out_of_scope": {
        "desc": "Out-of-flow question -> escalate to a human, no fabricated answer",
        "turns": [
            "Verlegt ihr den Boden auch bei mir zu Hause in der Schweiz, in Zürich?",
        ],
        "check": lambda tr, fn: _out_of_scope(tr, fn),
    },
    "vague_customer": {
        "desc": "Vague customer -> assistant keeps qualifying, doesn't search prematurely",
        "turns": [
            "Hi, ich brauche neuen Boden.",
        ],
        "check": lambda tr, fn: _vague(tr, fn),
    },
    "faq_answered": {
        "desc": "Pure FAQ question -> answered from KB, no premature search, no forced funnel",
        "turns": [
            "Was ist eigentlich der Unterschied zwischen Laminat und Vinyl?",
        ],
        "check": lambda tr, fn: _faq_answered(tr, fn),
    },
    "faq_return_no_funnel": {
        "desc": "Routine return question -> answers policy from KB, does NOT demand contact",
        "turns": [
            "Kann ich Ware zurückgeben, wenn sie mir zuhause nicht gefällt?",
        ],
        "check": lambda tr, fn: _faq_return(tr, fn),
    },
    "faq_out_of_kb": {
        "desc": "Question not in KB (Mengenrabatt) -> escalate to human, do not invent",
        "turns": [
            "Bekomme ich einen Mengenrabatt, wenn ich über 100 m² bestelle?",
        ],
        "check": lambda tr, fn: _faq_out_of_kb(tr, fn),
    },
    "door_beraten": {
        "desc": "Opening door 'Beraten Sie mich' -> guided, asks a question, no blind search",
        "turns": ["Beraten Sie mich"],
        "check": lambda tr, fn: _door_guided(tr, fn),
    },
    "door_suche": {
        "desc": "Opening door 'Ich suche einen Boden' -> asks direction, no blind search",
        "turns": ["Ich suche einen Boden"],
        "check": lambda tr, fn: _door_guided(tr, fn),
    },
    "door_frage": {
        "desc": "Opening door 'Ich habe eine Frage' -> serve-first, no search, no forced contact",
        "turns": ["Ich habe eine Frage"],
        "check": lambda tr, fn: _door_frage(tr, fn),
    },
}


def _dog_fbh(tr, fn):
    sp = calls(tr, "search_products")
    es = calls(tr, "estimate_shipping")
    if not sp:
        return False, "search_products never called"
    cons = sp[-1]["args"].get("constraints", [])
    if "underfloor_heating" not in cons:
        return False, f"FBH constraint missing from {cons}"
    if es:
        items = es[-1]["args"].get("items", [])
        if len(items) != 1:
            return False, f"shipping should be ONE sku, got {len(items)}"
    else:
        # acceptable fallback: it asked which product to price rather than guessing
        blob = " ".join(fn).lower()
        if not any(w in blob for w in ["welch", "entscheid", "favorit", "gefällt", "wähl"]):
            return False, "no shipping estimate and did not ask which product to price"
    # own-brand surfaced
    prods = sp[-1]["result"].get("products", [])
    if not (prods and prods[0].get("is_eigenmarke")):
        return False, "top recommendation is not own-brand"
    return True, f"FBH+single-SKU shipping ({es[-1]['result'].get('rate_eur')} EUR), own-brand top"


def _bathroom(tr, fn):
    sp = calls(tr, "search_products")
    if not sp:
        return False, "search_products never called"
    cons = sp[-1]["args"].get("constraints", [])
    room = sp[-1]["args"].get("room")
    if "waterproof" not in cons and room != "Bad":
        return False, f"no waterproof/Bad signal (cons={cons}, room={room})"
    prods = sp[-1]["result"].get("products", [])
    if not prods:
        return False, "no wet-room products returned"
    return True, "waterproof gate applied, products returned"


def _abroad(tr, fn):
    es = calls(tr, "estimate_shipping")
    # acceptable: either no shipping call at all, or a call that returned escalate
    calculated = [e for e in es if e["result"].get("status") == "ok"]
    if calculated:
        return False, "calculated a domestic rate for an abroad customer"
    if not any_escalation_text(fn):
        return False, "did not route the customer to a human/email"
    return True, "no DE rate calculated; routed to email"


def _budget(tr, fn):
    sp = calls(tr, "search_products")
    if not sp:
        return False, "search_products never called"
    bm = sp[-1]["args"].get("budget_max_eur_per_sqm")
    if not bm or bm > 16:
        return False, f"budget_max not honored (got {bm})"
    return True, f"budget_max={bm} passed"


def _commercial(tr, fn):
    sp = calls(tr, "search_products")
    if not sp:
        return False, "search_products never called"
    a = sp[-1]["args"]
    nk = a.get("usage_class_min")
    if (nk is None or nk < 31) and a.get("room") != "Gewerbe":
        return False, f"no commercial NK floor (nk={nk}, room={a.get('room')})"
    return True, f"commercial durability requested (nk={nk}, room={a.get('room')})"


def _out_of_scope(tr, fn):
    if calls(tr, "estimate_shipping"):
        return False, "tried to calculate shipping for Switzerland"
    if not any_escalation_text(fn):
        return False, "did not escalate to a human channel"
    return True, "escalated, no fabricated cross-border install answer"


def _vague(tr, fn):
    if calls(tr, "search_products"):
        return False, "searched products with no profile yet"
    # should ask a qualifying question
    if "?" not in " ".join(fn):
        return False, "did not ask a qualifying question"
    return True, "kept qualifying instead of searching blind"


def _faq_answered(tr, fn):
    if calls(tr, "search_products"):
        return False, "ran a product search for a pure info question"
    # answered from the KB (laminate=HDF/layers, vinyl=PVC/click)
    if not text_has(fn, ["HDF", "PVC", "Klick", "Schicht", "Nutzschicht"]):
        return False, "answer does not contain a KB fact about laminate/vinyl"
    return True, "answered from KB, no funnel"


def _faq_return(tr, fn):
    if not text_has(fn, ["originalverpackt", "widerruf", "ungebraucht", "rücksend",
                          "zurücksch", "unbeschädigt"]):
        return False, "did not state the return policy from KB"
    if asks_for_contact(fn):
        return False, "demanded contact details to answer a simple question"
    return True, "stated return policy, did not force contact"


def _faq_out_of_kb(tr, fn):
    # discount is not in the KB -> must route to a human, not invent a number
    import re
    if re.search(r"\b\d{1,2}\s?%", " ".join(fn)):
        return False, "invented a discount percentage"
    if not any_escalation_text(fn):
        return False, "did not route the discount question to a human"
    return True, "no invented discount, routed to human"


def _door_guided(tr, fn):
    # doors 1 and 2: must not blind-search on the opening tap, must ask something
    if calls(tr, "search_products"):
        return False, "searched products with no profile yet"
    if "?" not in " ".join(fn):
        return False, "did not ask a qualifying question"
    return True, "asked a question, no blind search"


def _door_frage(tr, fn):
    # door 3: serve-first, no product search, must not demand contact to start
    if calls(tr, "search_products"):
        return False, "ran a product search for a general-question opener"
    if asks_for_contact(fn):
        return False, "demanded contact just to take a question"
    return True, "stayed in serve mode, invited the question"


def main():
    env = load_env()
    model = env.get("ASSISTANT_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"])
    woo = WooClient(env)

    args = [a for a in sys.argv[1:]]
    names = list(SCENARIOS)
    if "--quick" in args:
        names = names[:3]
    elif args:
        names = [a for a in args if a in SCENARIOS]
        if not names:
            print(f"unknown scenario. options: {', '.join(SCENARIOS)}")
            sys.exit(2)

    print("=" * 64)
    print(f"FIND YOUR FLOOR, CONVERSATIONAL SCENARIOS · model={model}")
    print("=" * 64)
    passed = failed = 0
    for name in names:
        sc = SCENARIOS[name]
        print(f"\n▶ {name}: {sc['desc']}")
        try:
            trace, finals = drive(client, woo, model, sc["turns"])
            ok, detail = sc["check"](trace, finals)
            tools_fired = ", ".join(f"{t['tool']}" for t in trace) or "none"
            mark = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
            print(f"  [{mark}] {detail}")
            print(f"  tools fired: {tools_fired}")
            passed += ok
            failed += not ok
        except Exception as e:
            failed += 1
            print(f"  [\033[31mERROR\033[0m] {e}")

    print("\n" + "=" * 64)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 64)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
