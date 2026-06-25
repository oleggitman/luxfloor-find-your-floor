"""Probe the live Bitrix24 instance to list lead fields and verify custom field codes.

Read-only. Loads config from the sibling .env.
Run: .venv/bin/python clients/luxfloor/site-assistant/probe_bitrix.py
"""
from __future__ import annotations
from pathlib import Path
import json, requests

ENV_PATH = Path(__file__).parent / ".env"


def load_env(path: Path = ENV_PATH) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main():
    env = load_env()
    base = env["BITRIX_WEBHOOK_URL"].rstrip("/") + "/"
    r = requests.post(base + "crm.lead.fields", json={}, timeout=15)
    r.raise_for_status()
    fields = r.json().get("result", {})

    print(f"Total fields: {len(fields)}\n")

    print("=== CUSTOM FIELDS (UF_CRM_*) ===")
    for k, v in sorted(fields.items()):
        if k.startswith("UF_"):
            items = v.get("items", [])
            print(f"  {k}  type={v.get('type','')}  title={v.get('title','')!r}")
            for it in items:
                print(f"    -> ID={it['ID']}  VALUE={it['VALUE']!r}")

    print("\n=== STANDARD FIELDS ===")
    for k, v in sorted(fields.items()):
        if not k.startswith("UF_"):
            print(f"  {k}: {v.get('title','')!r}")


if __name__ == "__main__":
    main()
