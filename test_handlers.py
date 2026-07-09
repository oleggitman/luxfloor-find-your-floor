"""Deterministic regression suite for the Find Your Floor handlers (no LLM).

Runs against the LIVE Woo catalog, so it asserts invariants (fit gate holds,
own-brand-on-sale ranks first, shipping math + escalation) rather than exact
SKUs, which keeps it stable as the catalog changes. Fast + cheap: this is the
guard you run after any handler/prompt change.

  .venv/bin/python clients/luxfloor/site-assistant/test_handlers.py
"""
from __future__ import annotations

import math
import sys

from woo_client import (WooClient, de_num, max_nutzungsklasse, OWN_BRAND_VALUE,
                        SHIPPING_TIERS)

woo = WooClient()
PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    mark = "\033[32mPASS\033[0m" if cond else "\033[31mFAIL\033[0m"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail and not cond else ""))


def commercial_score(c):
    return 2 * c["is_eigenmarke"] + 1 * c["on_sale"]


# --- unit: number parsing (no network) --------------------------------------
def test_de_num():
    print("\nde_num (German/free-text decimal parsing)")
    check("'2,664' -> 2.664", de_num("2,664") == 2.664)
    check("'10 Paneele -2.196 m²' -> 2.196", de_num("10 Paneele -2.196 m²") == 2.196)
    check("'2.196' -> 2.196", de_num("2.196") == 2.196)
    check("'8 Paneele = 2,664m²' -> 2.664", de_num("8 Paneele = 2,664m²") == 2.664)
    check("None -> None", de_num(None) is None)
    check("'15' -> 15.0", de_num("15") == 15.0)


# --- search_products invariants ---------------------------------------------
def test_fit_gate_surface_design():
    print("\nsearch_products: fit gate (surface + design)")
    res = woo.search_products(constraints=[], surface="Hochglanz",
                              design="Steinoptik", room="Wohnzimmer", limit=5)
    prods = res["products"]
    check("returns at least 1", len(prods) >= 1, f"got {len(prods)}")
    check("all are Hochglanz", all(p["surface"] == "Hochglanz" for p in prods),
          str([p["surface"] for p in prods]))
    check("all are Stein optik", all(p["optik"] == "Stein" for p in prods),
          str([p["optik"] for p in prods]))


def test_own_brand_first():
    print("\nsearch_products: own-brand-on-sale ranks first (the locked rule)")
    res = woo.search_products(constraints=[], surface="Hochglanz",
                              design="Steinoptik", limit=10)
    prods = res["products"]
    scores = [commercial_score(p) for p in prods]
    check("commercial score is non-increasing (no reseller above LUX-on-sale)",
          all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)),
          str(scores))
    if prods:
        check("top result is own-brand (LUX) when own-brand fits",
              prods[0]["is_eigenmarke"],
              f"top hersteller={prods[0]['hersteller']}")


def test_waterproof_bad():
    print("\nsearch_products: Bad / waterproof gate")
    res = woo.search_products(constraints=["waterproof"], room="Bad", limit=8)
    prods = res["products"]
    # the live attribute is Sanitär/Nassbereich=Ja; handler enforces it
    check("returns candidates", len(prods) >= 1, f"got {len(prods)}")
    # every returned product must be wet-room capable -> we re-pull one to confirm
    if prods:
        full = woo._product_by_sku(prods[0]["sku"])
        from woo_client import attr_value, ATTR_NASSBEREICH
        check("top product is wet-room capable (Nassbereich=Ja)",
              (attr_value(full, ATTR_NASSBEREICH) or "").lower() == "ja")


def test_usage_class_floor():
    print("\nsearch_products: Nutzungsklasse floor (Gewerbe -> NK31+)")
    res = woo.search_products(constraints=[], usage_class_min=31, limit=8)
    prods = res["products"]
    bad = [p for p in prods if p["nutzungsklasse"] is not None and p["nutzungsklasse"] < 31]
    check("no product below requested NK31", not bad,
          str([(p["sku"], p["nutzungsklasse"]) for p in bad]))


def test_budget_cap():
    print("\nsearch_products: budget cap")
    res = woo.search_products(constraints=[], budget_max_eur_per_sqm=20, limit=8)
    prods = res["products"]
    over = [p for p in prods if p["price_per_sqm_eur"] and p["price_per_sqm_eur"] > 20]
    check("no product over 20 EUR/m²", not over,
          str([(p["sku"], p["price_per_sqm_eur"]) for p in over]))


def test_no_fit_fallback():
    print("\nsearch_products: no-fit returns empty (graceful, never a wrong rec)")
    # impossible combo: ultra-low budget + premium gloss stone
    res = woo.search_products(constraints=[], surface="Hochglanz",
                              design="Steinoptik", budget_max_eur_per_sqm=1, limit=5)
    check("count == 0 for impossible budget", res["count"] == 0, f"got {res['count']}")


def test_cards_have_shipping_fields():
    print("\nsearch_products: cards carry weight + sqm/VE (feed estimate_shipping)")
    res = woo.search_products(constraints=[], surface="Hochglanz",
                              design="Steinoptik", limit=3)
    for p in res["products"]:
        check(f"{p['sku']} has weight + sqm_per_ve",
              p["weight_kg_per_ve"] and p["sqm_per_ve"],
              f"w={p['weight_kg_per_ve']} spv={p['sqm_per_ve']}")


# --- estimate_shipping ------------------------------------------------------
def _a_lux_sku():
    res = woo.search_products(constraints=[], surface="Hochglanz",
                              design="Steinoptik", limit=1)
    return res["products"][0] if res["products"] else None


def test_shipping_math():
    print("\nestimate_shipping: VE/weight math + tier lookup")
    card = _a_lux_sku()
    if not card:
        check("found a SKU to test", False); return
    area = 25.0
    est = woo.estimate_shipping(items=[{"sku": card["sku"], "area_sqm": area}])
    check("status ok", est["status"] == "ok", str(est))
    exp_ve = math.ceil(area / card["sqm_per_ve"])
    exp_w = exp_ve * card["weight_kg_per_ve"]
    exp_rate = next(r for cap, r in SHIPPING_TIERS if exp_w <= cap)
    check(f"VE = ceil({area}/{card['sqm_per_ve']}) = {exp_ve}", est["total_ve"] == exp_ve,
          f"got {est['total_ve']}")
    check(f"weight = {exp_w} kg", abs(est["total_weight_kg"] - exp_w) < 0.5,
          f"got {est['total_weight_kg']}")
    check(f"rate = {exp_rate} EUR", est["rate_eur"] == exp_rate, f"got {est['rate_eur']}")


def test_shipping_small_order():
    print("\nestimate_shipping: tiny order lands in a low tier")
    card = _a_lux_sku()
    if not card:
        check("found a SKU", False); return
    est = woo.estimate_shipping(items=[{"sku": card["sku"], "area_sqm": 2}])
    check("status ok", est["status"] == "ok")
    check("rate is a real tier value",
          est["rate_eur"] in [r for _, r in SHIPPING_TIERS], str(est.get("rate_eur")))


def test_shipping_abroad_escalates():
    print("\nestimate_shipping: abroad escalates (never guesses)")
    card = _a_lux_sku()
    est = woo.estimate_shipping(items=[{"sku": card["sku"], "area_sqm": 25}], country="AT")
    check("status escalate", est["status"] == "escalate", str(est))
    check("routes to info@lux-floor.de", est.get("channel") == "info@lux-floor.de")


def test_shipping_bad_sku():
    print("\nestimate_shipping: unknown SKU errors cleanly")
    est = woo.estimate_shipping(items=[{"sku": "DOES-NOT-EXIST-999", "area_sqm": 25}])
    check("status error (not a crash, not a fake rate)", est["status"] == "error", str(est))


# --- lookup_product (specific product by code/name/link) --------------------
def test_lookup_exact_sku():
    print("\nlookup_product: exact SKU is resolved")
    res = woo.lookup_product(query="CheckOne-2157")
    check("finds at least 1", res["count"] >= 1, str(res["count"]))
    if res["products"]:
        p = res["products"][0]
        check("card carries a real price + name",
              bool(p["name"]) and p["price_per_sqm_eur"] and p["price_per_sqm_eur"] > 0,
              f"name={p['name']!r} price/m²={p['price_per_sqm_eur']} pkg={p['price_per_package_eur']}")


def test_lookup_code_token():
    print("\nlookup_product: prefixed/hyphenated code resolves via its core token")
    # visitors type 'FAL-D2935'; Woo search only matches the 'D2935' core token
    res = woo.lookup_product(query="FAL-D2935")
    check("finds candidates for D2935", res["count"] >= 1, str(res["count"]))


def test_lookup_by_name():
    print("\nlookup_product: product name resolves")
    res = woo.lookup_product(query="Kronotex Amazone")
    check("finds candidates by name", res["count"] >= 1, str(res["count"]))


def test_lookup_by_link():
    print("\nlookup_product: pasted shop link resolves via its slug")
    res = woo.lookup_product(
        query="https://lux-floor.de/shop/wand/1798-falquon-d2935-weiss-wandpaneel/")
    check("finds candidates from the link slug", res["count"] >= 1, str(res["count"]))


def test_lookup_not_found():
    print("\nlookup_product: unknown code returns empty (honest escalation, no invention)")
    res = woo.lookup_product(query="DURATEST disk 91123")
    check("count == 0 for a non-catalog code", res["count"] == 0, str(res["count"]))
    check("empty products list", res["products"] == [])


def test_lookup_empty_query():
    print("\nlookup_product: empty query is safe")
    res = woo.lookup_product(query="   ")
    check("count == 0, no crash", res["count"] == 0, str(res))


def main():
    print("=" * 60)
    print("FIND YOUR FLOOR — HANDLER REGRESSION SUITE (live catalog)")
    print("=" * 60)
    for t in [test_de_num, test_fit_gate_surface_design, test_own_brand_first,
              test_waterproof_bad, test_usage_class_floor, test_budget_cap,
              test_no_fit_fallback, test_cards_have_shipping_fields,
              test_shipping_math, test_shipping_small_order,
              test_shipping_abroad_escalates, test_shipping_bad_sku,
              test_lookup_exact_sku, test_lookup_code_token, test_lookup_by_name,
              test_lookup_by_link, test_lookup_not_found, test_lookup_empty_query]:
        try:
            t()
        except Exception as e:
            global FAIL
            FAIL += 1
            print(f"  [\033[31mERROR\033[0m] {t.__name__}: {e}")
    print("\n" + "=" * 60)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
