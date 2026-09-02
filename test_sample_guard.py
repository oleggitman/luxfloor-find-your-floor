"""Deterministic unit test for the sample-chip guard (no LLM, no network).

Freezes the two failure modes of the "Kostenloses Muster bestellen" chip found in
the 2026-09-02 log review (cards 87/93, raw session 31.08 07:10):
  1. the chain: more than the ONE allowed narrowing question before any product,
  2. self-pick: on a repeat press the model chooses a product the visitor never picked.
The chip is deterministic input, so the guard lives in code like the price and
handoff guards, not in the prompt.

  .venv/bin/python clients/luxfloor/site-assistant/test_sample_guard.py
"""
from app import _needs_sample_guard, _products_shown, _sample_question_spent

CHIP = "Kostenloses Muster bestellen"
PRODUCT_REPLY = ("Hier sind drei Optionen:\n**1. Lux Floor 4163 Sakura**\n"
                 "![Sakura](https://lux-floor.de/wp-content/uploads/sakura.jpg)\n"
                 "[Zum Produkt](https://lux-floor.de/produkt/lux-floor-4163-sakura/)")
CONTACT_REPLY = "Sie erreichen unser Team unter info@lux-floor.de oder 02131 2917676."
QUESTION = "Welche Optik schwebt Ihnen vor?"


def u(text):
    return {"role": "user", "content": text}


def a(text):
    return {"role": "assistant", "content": text}


def _check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True

    # --- _products_shown ---
    ok &= _check("empty history: no products",
                 not _products_shown([]))
    ok &= _check("assistant reply with product link counts",
                 _products_shown([a(PRODUCT_REPLY)]))
    ok &= _check("bare contact mention does not count",
                 not _products_shown([a(CONTACT_REPLY)]))
    ok &= _check("user message with a link does not count",
                 not _products_shown([u(PRODUCT_REPLY)]))

    # --- the chain: one question allowed, the second fires ---
    ok &= _check("fresh press + no tool = fine (one question allowed)",
                 not _needs_sample_guard(CHIP, {"tools": []}, []))
    ok &= _check("second question after the press = guard fires (31.08 chain)",
                 _needs_sample_guard("Steinoptik", {"tools": []},
                                     [u(CHIP), a(QUESTION), u("Steinoptik")]))
    ok &= _check("answer turn that fetches products = fine",
                 not _needs_sample_guard("Steinoptik", {"tools": ["search_products"]},
                                         [u(CHIP), a(QUESTION), u("Steinoptik")]))
    ok &= _check("products shown since the press = pending state over",
                 not _needs_sample_guard("Und in Weiß?", {"tools": []},
                                         [u(CHIP), a(PRODUCT_REPLY), u("Und in Weiß?")]))
    ok &= _check("page-url prefix on the chip still counts as a press",
                 _needs_sample_guard("hell", {"tools": []},
                                     [u("[Seite: https://lux-floor.de/produkt/x]\n" + CHIP),
                                      a(QUESTION), u("hell")]))
    ok &= _check("chip far in the past (chain cap) = gives up",
                 not _needs_sample_guard("ok", {"tools": []},
                                         [u(CHIP)] + [a(QUESTION), u("hm")] * 5))
    ok &= _check("no press anywhere = never fires",
                 not _needs_sample_guard("Steinoptik", {"tools": []},
                                         [u("Hallo"), a(QUESTION), u("Steinoptik")]))

    # --- self-pick on a repeat press ---
    shown = [a(PRODUCT_REPLY)]
    ok &= _check("repeat press + lookup ran = guard fires (self-pick)",
                 _needs_sample_guard(CHIP, {"tools": ["lookup_product"]}, shown))
    ok &= _check("repeat press + no tool (asks which one) = fine",
                 not _needs_sample_guard(CHIP, {"tools": []}, shown))
    ok &= _check("fresh press from product page (lookup ran) = fine",
                 not _needs_sample_guard(CHIP, {"tools": ["lookup_product"]}, []))
    ok &= _check("chip match tolerates case/whitespace",
                 not _needs_sample_guard("  kostenloses muster bestellen ",
                                         {"tools": []}, []))

    # --- helper directly ---
    ok &= _check("question spent detector: true on second product-less turn",
                 _sample_question_spent([u(CHIP), a(QUESTION), u("Steinoptik")]))
    ok &= _check("question spent detector: false right after the press",
                 not _sample_question_spent([u(CHIP)]))

    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
