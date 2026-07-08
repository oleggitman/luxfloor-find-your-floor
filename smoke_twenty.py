"""End-to-end smoke test for twenty_client.create_lead against the live Twenty workspace.
Creates a test Person+Opportunity, reads them back, verifies fields, then deletes them.
Run: python3 clients/luxfloor/site-assistant/smoke_twenty.py
"""
from __future__ import annotations
from pathlib import Path
import json
import requests
import twenty_client as tc

ENV_PATH = Path(__file__).parent / ".env"


def load_env(p):
    out = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


env = load_env(ENV_PATH)
base = env["TWENTY_API_URL"].rstrip("/")
H = {"Authorization": f"Bearer {env['TWENTY_API_KEY']}", "Content-Type": "application/json"}

# 0) discover POST response shape
r = requests.post(f"{base}/rest/people", json={"name": {"firstName": "ZZTEST", "lastName": "Shape"}},
                  headers=H, timeout=15)
print("raw person create keys:", list(r.json().get("data", {}).keys()), "http", r.status_code)
probe_id = None
d = r.json().get("data", {})
for k, v in d.items():
    if isinstance(v, dict) and v.get("id"):
        probe_id = v["id"]
print("probe person id:", probe_id)
if probe_id:
    requests.delete(f"{base}/rest/people/{probe_id}", headers=H, timeout=15)

# 1) run create_lead with a HOT sample
sample = {
    "name": "Max Mustermann",
    "phone_or_whatsapp": "+49 176 1234567",
    "email": "max@example.de",
    "stadt": "Neuss",
    "plz": "41460",
    "strasse": "Teststraße 1",
    "interested_products": ["CHECK One 2110 Nordstern Travertin"],
    "area_sqm": 25,
    "budget_eur_per_sqm": 30,
    "verlegung_wanted": True,
    "zubehoer_interest": "Trittschalldämmung",
    "profile": {"optik": "Steinoptik", "material": "Klick-Vinyl", "constraints": ["wasserfest"]},
    "urgency": "needed_now",
    "info_note": "Küche, dringend",
    "conversation_summary": "Kunde sucht wasserfestes Klick-Vinyl in Steinoptik fuer die Kueche, 25 m2, dringend.",
    "lead_flag": "normal",
    "action": "sample_request",
    "dsgvo_consent": True,
}
res = tc.create_lead(sample, env)
print("\ncreate_lead result:", res)
assert res["status"] == "ok", res
assert res["hot"] is True, "expected HOT (contact+urgent+project)"
opp_id = res["lead_id"]

# 2) read back the opportunity with its fields + linked person
q = ("?filter=id[eq]:" + opp_id) if False else ""
g = requests.get(f"{base}/rest/opportunities/{opp_id}", headers=H, timeout=15)
opp = g.json().get("data", {})
opp = opp.get("opportunity", opp) if isinstance(opp, dict) else opp
print("\n=== opportunity read-back ===")
for k in ["name", "stage", "leadScore", "dringlichkeit", "leadFlag", "quelle", "mengeM2",
          "verlegungGewunscht", "zubehoerInteresse", "dsgvoEinwilligung", "amount",
          "interessiertesProdukt", "profil", "notiz", "pointOfContactId", "ownerId"]:
    print(f"  {k}: {opp.get(k)}")

person_id = opp.get("pointOfContactId")
if person_id:
    pg = requests.get(f"{base}/rest/people/{person_id}", headers=H, timeout=15).json().get("data", {})
    pg = pg.get("person", pg)
    print("\n=== person read-back ===")
    for k in ["name", "emails", "phones", "stadt", "plz", "strasse"]:
        print(f"  {k}: {pg.get(k)}")

# 3) cleanup
requests.delete(f"{base}/rest/opportunities/{opp_id}", headers=H, timeout=15)
if person_id:
    requests.delete(f"{base}/rest/people/{person_id}", headers=H, timeout=15)
print("\ncleanup done (test records deleted)")
