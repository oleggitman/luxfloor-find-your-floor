"""Deterministic unit test for [[CHIPS]] extraction (no LLM, no network).

The "marker never leaks to the customer" guarantee lives in app._extract_chips,
not in the model, so this pins it directly.

  .venv/bin/python clients/luxfloor/site-assistant/test_chips.py
"""
from app import _extract_chips


def _check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True

    clean, opts = _extract_chips("Suchen Sie hell oder dunkel?\n[[CHIPS: Hell | Dunkel | Egal]]")
    ok &= _check("parses options", opts == ["Hell", "Dunkel", "Egal"])
    ok &= _check("strips marker, clean reply", "[[CHIPS" not in clean and clean == "Suchen Sie hell oder dunkel?")

    clean, opts = _extract_chips("Kein Marker, nur Text.")
    ok &= _check("no marker, empty options", opts == [])
    ok &= _check("no marker, reply unchanged", clean == "Kein Marker, nur Text.")

    clean, opts = _extract_chips("Frage\n[[CHIPS: Vinyl | Vinyl |  | Laminat ]]")
    ok &= _check("dedupes and drops blanks", opts == ["Vinyl", "Laminat"])
    ok &= _check("marker stripped on dedupe case", "[[CHIPS" not in clean)

    # 16.08: в проде модель заворачивает маркер в бэктики, после вырезания
    # маркера покупателю оставался хвост «``» (сессии 15.08, трижды).
    clean, opts = _extract_chips("Grau, sehr zeitlos! Und welcher Raum?\n`[[CHIPS: Küche | Bad | Flur]]`")
    ok &= _check("inline-code marker: options parsed", opts == ["Küche", "Bad", "Flur"])
    ok &= _check("inline-code marker: no backtick residue", "`" not in clean)

    clean, opts = _extract_chips("Frage?\n```\n[[CHIPS: Hell | Dunkel]]\n```")
    ok &= _check("fenced marker: options parsed", opts == ["Hell", "Dunkel"])
    ok &= _check("fenced marker: no backtick residue", "`" not in clean)

    print("ALL OK" if ok else "FAILURES")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
