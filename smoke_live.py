"""Contract-level smoke test against the LIVE deployed /chat.

Asserts only what must always hold, no flaky LLM-content checks:
  - HTTP 200
  - options is a list
  - reply is a non-empty string
  - reply has no [[CHIPS marker leak
Product link/image presence is a soft note, never a failure.

  .venv/bin/python clients/luxfloor/site-assistant/smoke_live.py [BASE_URL]
"""
import sys

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1
        else "https://luxfloor-find-your-floor.onrender.com").rstrip("/")

CASES = [
    "Beraten Sie mich",
    "Ich suche einen Boden",
    "Ich habe eine Frage",
    "Wie sind Ihre Oeffnungszeiten?",
]


def post(msg, sid=None):
    r = requests.post(BASE + "/chat",
                      json={"session_id": sid, "message": msg}, timeout=90)
    return r.status_code, r.json()


def main():
    print(f"smoke_live against {BASE}")
    ok = True
    for msg in CASES:
        try:
            status, d = post(msg)
        except Exception as e:
            print("FAIL", repr(msg), "request error:", e)
            ok = False
            continue
        reply = d.get("reply", "")
        options = d.get("options")
        checks = [
            ("http 200", status == 200),
            ("options is list", isinstance(options, list)),
            ("reply non-empty", isinstance(reply, str) and bool(reply.strip())),
            ("no [[CHIPS leak", "[[CHIPS" not in reply),
        ]
        for cname, cond in checks:
            if not cond:
                ok = False
            print(("PASS" if cond else "FAIL"), f"{msg!r}: {cname}")
        if msg == "Ich suche einen Boden" and "lux-floor.de" not in reply:
            print("  (note) no product link yet, expected while still qualifying")
    print("SMOKE OK" if ok else "SMOKE FAILURES")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
