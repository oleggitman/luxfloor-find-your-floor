"""WooCommerce handlers for the Find Your Floor assistant.

Implements the two Phase-1 tools the assistant calls:
  - search_products   : fit-gated, own-brand-on-promotion-first product search
  - estimate_shipping : deterministic Festland (DE mainland) shipping from the KB rate table

Contract: clients/luxfloor/site-assistant/tool-schemas.md
Rate table + ranking rule: knowledge-base.md sections C + F
Verified against the live catalog 2026-06-12: own brand = attribute Hersteller=LUX,
sqm-per-VE = attribute "Paketinhalt (qm)", weight = native Woo weight (kg per VE).

Read-only against Woo. Loads keys from the sibling .env (gitignored).
"""
from __future__ import annotations

import math
import re
import time
from pathlib import Path

import requests

ENV_PATH = Path(__file__).parent / ".env"

# --- live-catalog facts (verified 2026-06-12) -------------------------------
OWN_BRAND_VALUE = "LUX"            # attribute "Hersteller" value marking Eigenmarke
ATTR_HERSTELLER = "Hersteller"
ATTR_OBERFLAECHE = "Oberfläche"     # Hochglanz / Matt / Strukturiert  -> surface
ATTR_OPTIK = "Dekoart / Optik"      # Holz / Stein / Uni / Muster       -> design
ATTR_NUTZUNGSKLASSE = "Nutzungsklasse"
ATTR_NASSBEREICH = "Sanitär/Nassbereich"   # "Ja" -> waterproof-capable
ATTR_KLICK = "Klicksystem"
ATTR_FORMAT = "Format"
# m2-per-package lives in any of these (first non-empty wins); all need de-number parsing
ATTR_SQM_PER_VE = ["Paketinhalt (qm)", "Platz in einer Packung", "Karton"]

# spec enum -> live "Dekoart / Optik" value
DESIGN_MAP = {
    "Holzoptik": "Holz",
    "Steinoptik": "Stein",
    "Marmoroptik": "Stein",   # no separate marble value; marble is a Stein decor
    "Uni": "Uni",
}

# Festland DE rate table (knowledge-base.md §C). Standard column; weight-driven.
# Note the non-monotonic step: 60-225kg (pallet/spedition) is a flat 50 EUR,
# cheaper than the 40-60kg parcel tier (59.99). That is the real published table.
SHIPPING_TIERS = [
    (1, 5.95),       # bis 1 kg
    (20, 19.99),     # bis 20 kg  (1 VE)
    (40, 39.99),     # 20-40 kg   (2 VE)
    (60, 59.99),     # 40-60 kg   (3 VE)
    (225, 50.0),     # 60-225 kg  (4-15 VE)  <- spedition flat
    (300, 60.0),     # 225-300 kg (16-20 VE)
    (375, 70.0),     # 300-375 kg (21-25 VE)
    (450, 80.0),     # 375-450 kg (26-30 VE)
    (float("inf"), 90.0),  # ab 450 kg
]


# --- env --------------------------------------------------------------------
def load_env(path: Path = ENV_PATH) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# --- number / attribute helpers --------------------------------------------
def de_num(raw) -> float | None:
    """Parse a German-or-English decimal out of messy text.
    '2,664' -> 2.664 | '10 Paneele -2.196 m²' -> 2.196 | '2.196' -> 2.196
    Picks the last number that looks like an m2 area (has a decimal part)."""
    if raw is None:
        return None
    s = str(raw)
    # find all numbers with optional , or . decimals
    nums = re.findall(r"\d+(?:[.,]\d+)?", s)
    if not nums:
        return None
    # prefer a decimal (area) over a bare integer (panel count)
    decimals = [n for n in nums if "," in n or "." in n]
    pick = decimals[-1] if decimals else nums[-1]
    try:
        return float(pick.replace(",", "."))
    except ValueError:
        return None


def attr_value(product: dict, name: str) -> str | None:
    for a in product.get("attributes", []):
        if a.get("name") == name:
            opts = a.get("options") or []
            return opts[0] if opts else None
    return None


def attr_values(product: dict, name: str) -> list[str]:
    for a in product.get("attributes", []):
        if a.get("name") == name:
            return a.get("options") or []
    return []


def sqm_per_ve(product: dict) -> float | None:
    for name in ATTR_SQM_PER_VE:
        v = de_num(attr_value(product, name))
        if v and v > 0:
            return v
    return None


def max_nutzungsklasse(product: dict) -> int | None:
    vals = attr_values(product, ATTR_NUTZUNGSKLASSE)
    nk = []
    for v in vals:
        m = re.search(r"\b(2[1-3]|3[1-4]|4[0-3])\b", str(v))  # 21-23 living, 31-34 comm., 40-43 vinyl wear
        if m:
            nk.append(int(m.group(1)))
    return max(nk) if nk else None


# --- WooCommerce client -----------------------------------------------------
class WooClient:
    def __init__(self, env: dict | None = None):
        env = env or load_env()
        self.base = env["WOO_BASE_URL"].rstrip("/")
        self.auth = (env["WOO_CONSUMER_KEY"], env["WOO_CONSUMER_SECRET"])
        self.session = requests.Session()

    def _get(self, path: str, _attempts: int = 3, **params):
        url = f"{self.base}/wp-json/wc/v3/{path}"
        last = None
        for i in range(_attempts):
            try:
                r = self.session.get(url, auth=self.auth, params=params, timeout=30)
                r.raise_for_status()
                return r
            except (requests.ConnectionError, requests.Timeout) as e:
                last = e  # transient network blip; brief backoff then retry
                time.sleep(1.5 * (i + 1))
        raise last

    def _category_ids(self, slugs: list[str]) -> list[int]:
        if not slugs:
            return []
        ids = []
        for cat in self._get("products/categories", per_page=100).json():
            if cat["slug"] in slugs or cat["name"] in slugs:
                ids.append(cat["id"])
        return ids

    def _fetch_pool(self, category_ids: list[int], on_sale_only: bool,
                    max_products: int = 200) -> list[dict]:
        """Pull an in-stock candidate pool, paginating up to max_products."""
        pool, page = [], 1
        while len(pool) < max_products:
            params = dict(per_page=100, page=page, status="publish",
                          stock_status="instock")
            if category_ids:
                params["category"] = ",".join(map(str, category_ids))
            if on_sale_only:
                params["on_sale"] = "true"
            batch = self._get("products", **params).json()
            if not batch:
                break
            pool.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return pool[:max_products]

    # ---- TOOL 1: search_products -------------------------------------------
    def search_products(self, *, constraints: list[str], surface=None, format=None,
                        design=None, color=None, material_type=None, room=None,
                        usage_class_min=None, budget_max_eur_per_sqm=None,
                        limit: int = 3) -> dict:
        constraints = constraints or []

        # 1. narrow the fetch with native category filters where we safely can
        cat_slugs = []
        if material_type in ("Klick-Vinyl",):
            cat_slugs.append("Klick-Vinyl")
        elif material_type in ("Klebe-Vinyl",):
            cat_slugs.append("Klebe-Vinyl")
        elif material_type == "Laminat":
            cat_slugs.append("Laminat")
        if design == "Steinoptik" or design == "Marmoroptik":
            cat_slugs.append("Stein-Dekor")
        elif design == "Holzoptik":
            cat_slugs.append("Holz-Dekor")

        cat_ids = self._category_ids(cat_slugs) if cat_slugs else []
        pool = self._fetch_pool(cat_ids, on_sale_only=False)

        # 2. fit gate + scoring in Python on the rich attribute data
        design_live = DESIGN_MAP.get(design) if design else None
        fitting = []
        for p in pool:
            if not self._fits(p, constraints, surface, design_live, format,
                              room, usage_class_min, budget_max_eur_per_sqm):
                continue
            fitting.append(self._card(p))

        # 3. rank: own-brand+on-sale first, then own-brand OR on-sale, then rest
        def rank_key(c):
            return (
                -(2 * c["is_eigenmarke"] + 1 * c["on_sale"]),  # commercial pref
                c["price"] if c["price"] else 1e9,             # cheaper first within tier
            )
        fitting.sort(key=rank_key)
        return {"count": len(fitting), "products": fitting[:limit]}

    def _fits(self, p, constraints, surface, design_live, format, room,
              usage_class_min, budget_max) -> bool:
        # surface (Oberfläche)
        if surface and (attr_value(p, ATTR_OBERFLAECHE) or "").strip() != surface:
            return False
        # design (Dekoart / Optik)
        if design_live and (attr_value(p, ATTR_OPTIK) or "").strip() != design_live:
            return False
        # format
        if format and (attr_value(p, ATTR_FORMAT) or "").strip() != format:
            return False
        # usage class floor (room durability)
        need_nk = usage_class_min or self._room_nk(room)
        if need_nk:
            nk = max_nutzungsklasse(p)
            if nk is not None and nk < need_nk:
                return False
        # waterproof / wet room
        if ("waterproof" in constraints or room == "Bad") and \
                (attr_value(p, ATTR_NASSBEREICH) or "").strip().lower() != "ja":
            return False
        # budget
        if budget_max:
            try:
                if float(p.get("price") or 0) > budget_max:
                    return False
            except ValueError:
                pass
        return True

    @staticmethod
    def _room_nk(room) -> int | None:
        return {"Wohnzimmer": 22, "Schlafzimmer": 22, "Flur": 23, "Kueche": 23,
                "Bad": 23, "Gewerbe": 31}.get(room)

    @staticmethod
    def _card(p: dict) -> dict:
        hersteller = attr_value(p, ATTR_HERSTELLER) or ""
        img = (p.get("images") or [{}])[0].get("src", "")
        try:
            price = float(p.get("price") or 0)
        except ValueError:
            price = 0.0
        return {
            "name": p.get("name"),
            "sku": p.get("sku") or str(p.get("id")),
            "id": p.get("id"),
            "image_url": img,
            "price": price,
            "sale_price": p.get("sale_price") or None,
            "on_sale": bool(p.get("on_sale")),
            "is_eigenmarke": hersteller.strip().upper() == OWN_BRAND_VALUE,
            "hersteller": hersteller,
            "nutzungsklasse": max_nutzungsklasse(p),
            "surface": attr_value(p, ATTR_OBERFLAECHE),
            "optik": attr_value(p, ATTR_OPTIK),
            "format": attr_value(p, ATTR_FORMAT),
            "url": p.get("permalink"),
            "weight_kg_per_ve": de_num(p.get("weight")),
            "sqm_per_ve": sqm_per_ve(p),
        }

    # ---- TOOL 2: estimate_shipping -----------------------------------------
    def estimate_shipping(self, *, items: list[dict], country: str = "DE") -> dict:
        if (country or "DE").upper() != "DE":
            return {"status": "escalate", "channel": "info@lux-floor.de",
                    "reason": "Auslandsversand wird pro Fall berechnet."}

        total_weight = 0.0
        total_ve = 0
        detail = []
        for it in items:
            sku, area = it["sku"], float(it["area_sqm"])
            prod = self._product_by_sku(sku)
            if not prod:
                return {"status": "error", "reason": f"SKU {sku} nicht gefunden."}
            card = self._card(prod)
            spv, wpv = card["sqm_per_ve"], card["weight_kg_per_ve"]
            if not spv or not wpv:
                return {"status": "escalate", "channel": "info@lux-floor.de",
                        "reason": f"Gewichts-/VE-Daten für {sku} unvollständig."}
            ve = math.ceil(area / spv)
            w = ve * wpv
            total_ve += ve
            total_weight += w
            detail.append({"sku": sku, "area_sqm": area, "ve": ve,
                           "weight_kg": round(w, 1)})

        rate = next(r for cap, r in SHIPPING_TIERS if total_weight <= cap)
        return {
            "status": "ok",
            "rate_eur": rate,
            "total_weight_kg": round(total_weight, 1),
            "total_ve": total_ve,
            "country": "DE",
            "items": detail,
            "note": "Schätzung Festland Deutschland, final bei Bestellung.",
        }

    def _product_by_sku(self, sku: str) -> dict | None:
        hits = self._get("products", sku=sku).json()
        if hits:
            return hits[0]
        if sku.isdigit():  # we fall back to product id
            try:
                return self._get(f"products/{sku}").json()
            except requests.HTTPError:
                return None
        return None


# Tool dispatch map for the harness / backend
def dispatch(name: str, args: dict, client: WooClient):
    if name == "search_products":
        return client.search_products(**args)
    if name == "estimate_shipping":
        return client.estimate_shipping(**args)
    raise ValueError(f"unknown tool {name}")


if __name__ == "__main__":
    # quick smoke test of the handlers without the LLM
    import json
    c = WooClient()
    print(">>> search_products: Hochglanz Steinoptik, durable, Wohnzimmer")
    res = c.search_products(constraints=["durable_high_traffic"],
                            surface="Hochglanz", design="Steinoptik",
                            room="Wohnzimmer", limit=3)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if res["products"]:
        sku = res["products"][0]["sku"]
        print(f"\n>>> estimate_shipping: 25 m² of {sku}")
        print(json.dumps(c.estimate_shipping(items=[{"sku": sku, "area_sqm": 25}]),
                         indent=2, ensure_ascii=False))
