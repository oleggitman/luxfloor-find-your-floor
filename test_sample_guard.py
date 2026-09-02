"""Deterministic unit test for the sample-chip guard (no LLM, no network).

Freezes the two failure modes of the "Kostenloses Muster bestellen" chip found in
the 2026-09-02 log review (cards 87/93, raw session 31.08 07:10):
  1. interrogation: a question chain instead of showing products,
  2. self-pick: on a repeat press the model chooses a product the visitor never picked.
The chip is deterministic input, so the guard lives in code like the price and
handoff guards, not in the prompt.

  .venv/bin/python clients/luxfloor/site-assistant/test_sample_guard.py
"""
from app import _needs_sample_guard, _products_shown

CHIP = "Kostenloses Muster bestellen"
PRODUCT_REPLY = ("Hier sind drei Optionen:\n**1. Lux Floor 4163 Sakura**\n"
                 "![Sakura](https://lux-floor.de/wp-content/uploads/sakura.jpg)\n"
                 "[Zum Produkt](https://lux-floor.de/produkt/lux-floor-4163-sakura/)")
CONTACT_REPLY = "Sie erreichen unser Team unter info@lux-floor.de oder 02131 2917676."


def _check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True

    # --- _products_shown ---
    ok &= _check("empty history: no products",
                 not _products_shown([]))
    ok &= _check("assistant reply with product link counts",
                 _products_shown([{"role": "assistant", "content": PRODUCT_REPLY}]))
    ok &= _check("bare contact mention does not count",
                 not _products_shown([{"role": "assistant", "content": CONTACT_REPLY}]))
    ok &= _check("user message with a link does not count",
                 not _products_shown([{"role": "user", "content": PRODUCT_REPLY}]))

    # --- trigger 1: interrogation on a fresh press ---
    ok &= _check("fresh press + no product tool = guard fires",
                 _needs_sample_guard(CHIP, {"tools": []}, []))
    ok &= _check("fresh press + search_products ran = fine",
                 not _needs_sample_guard(CHIP, {"tools": ["search_products"]}, []))
    ok &= _check("fresh press from product page (lookup ran) = fine",
                 not _needs_sample_guard(CHIP, {"tools": ["lookup_product"]}, []))

    # --- trigger 2: self-pick on a repeat press ---
    shown = [{"role": "assistant", "content": PRODUCT_REPLY}]
    ok &= _check("repeat press + lookup ran = guard fires (self-pick)",
                 _needs_sample_guard(CHIP, {"tools": ["lookup_product"]}, shown))
    ok &= _check("repeat press + no tool (asks which one) = fine",
                 not _needs_sample_guard(CHIP, {"tools": []}, shown))

    # --- non-chip input never triggers ---
    ok &= _check("ordinary message never triggers",
                 not _needs_sample_guard("Ich suche einen Boden", {"tools": []}, []))
    ok &= _check("chip match tolerates case/whitespace",
                 _needs_sample_guard("  kostenloses muster bestellen ", {"tools": []}, []))

    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
