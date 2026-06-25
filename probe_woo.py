"""Probe the live Lux-Floor WooCommerce catalog to verify Phase 0 data assumptions.

Checks: total product count, brand taxonomy (for Eigenmarke own-brand-first ranking),
and whether weight + m2-per-package (VE) data is present (for estimate_shipping).
Read-only. Loads keys from the sibling .env (gitignored).
"""
import os
import sys
import json
from pathlib import Path
import requests

ENV = Path(__file__).parent / ".env"


def load_env(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main():
    env = load_env(ENV)
    base = env["WOO_BASE_URL"].rstrip("/")
    auth = (env["WOO_CONSUMER_KEY"], env["WOO_CONSUMER_SECRET"])
    api = f"{base}/wp-json/wc/v3"

    def get(path, **params):
        r = requests.get(f"{api}/{path}", auth=auth, params=params, timeout=30)
        r.raise_for_status()
        return r

    print("=" * 60)
    print("LUX-FLOOR WOOCOMMERCE PROBE")
    print("=" * 60)

    # 1. Total product count
    r = get("products", per_page=1)
    total = r.headers.get("X-WP-Total", "?")
    pages = r.headers.get("X-WP-TotalPages", "?")
    print(f"\n[1] CATALOG SIZE: {total} products ({pages} pages)")

    # 2. Brand taxonomy — categories, tags, attributes
    print("\n[2] BRAND TAXONOMY (for Eigenmarke own-brand ranking)")
    cats = get("products/categories", per_page=100).json()
    print(f"  Categories ({len(cats)}): " +
          ", ".join(c["name"] for c in cats[:40]))
    tags = get("products/tags", per_page=100).json()
    print(f"  Tags ({len(tags)}): " +
          (", ".join(t["name"] for t in tags[:60]) if tags else "(none)"))
    attrs = get("products/attributes").json()
    print(f"  Global attributes ({len(attrs)}):")
    for a in attrs:
        terms = get(f"products/attributes/{a['id']}/terms", per_page=100).json()
        names = ", ".join(t["name"] for t in terms[:25])
        print(f"    - {a['name']} (slug={a['slug']}): {names}")

    # 3. Sample products — weight, dimensions, VE/m2 meta, sale flag, brand hints
    print("\n[3] SAMPLE PRODUCTS (weight + VE/m2 + sale + attributes)")
    sample = get("products", per_page=5, status="publish").json()
    for p in sample:
        print(f"\n  • {p['name'][:55]}  (id {p['id']})")
        print(f"    price={p.get('price')}  on_sale={p.get('on_sale')}  "
              f"sale_price={p.get('sale_price') or '-'}")
        print(f"    weight={p.get('weight') or '(empty)'}  "
              f"dims={p.get('dimensions')}")
        print(f"    categories={[c['name'] for c in p.get('categories', [])]}")
        print(f"    tags={[t['name'] for t in p.get('tags', [])]}")
        pa = [(a['name'], a.get('options')) for a in p.get('attributes', [])]
        print(f"    attributes={pa}")
        meta = [(m['key'], m['value']) for m in p.get('meta_data', [])
                if not m['key'].startswith('_') or 'vpe' in m['key'].lower()
                or 've' in m['key'].lower() or 'm2' in m['key'].lower()
                or 'qm' in m['key'].lower() or 'paket' in m['key'].lower()]
        print(f"    meta(filtered)={meta[:15]}")

    print("\n" + "=" * 60)
    print("DONE")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"HTTP ERROR: {e.response.status_code} {e.response.reason}")
        print(e.response.text[:500])
        sys.exit(1)
