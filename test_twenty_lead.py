#!/usr/bin/env python3
"""Регрессия потерянного лида 31.07.2026 (Италия, 63 м², CONFLICTING_PHONE_COUNTRY_CODE).

Три инварианта create_lead:
1. Телефон с «+XX» уходит БЕЗ навязанного кода страны (Twenty сама выводит IT из +39).
2. Падение создания персоны НЕ роняет сделку: сделка пишется всегда, контакт уезжает
   текстом в заметку, в Telegram уходит алерт.
3. Любой сбой записи лида даёт алерт (до 04.08 сбои были молчаливыми).

Запуск: python3 test_twenty_lead.py (офлайн, все запросы замоканы).
"""
import unittest
from unittest import mock

import twenty_client as tc

ENV = {"TWENTY_API_URL": "https://api.example", "TWENTY_API_KEY": "k",
       "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c"}

LEAD = {
    "name": "Mario Rossi", "phone_or_whatsapp": "+39 333 1234567",
    "email": "mario@example.it", "stadt": "Mailand", "plz": "20100",
    "strasse": "Via Roma 1", "urgency": "needed_now", "dsgvo_consent": True,
    "interested_products": ["World of SPC 3567 Ferndale Oak"], "area_sqm": 63,
    "lead_flag": "auslandsversand", "conversation_summary": "Lieferung nach Italien",
    "profile": {"material": "Klick-Vinyl"},
}


def resp(status=201, payload=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = payload or {}
    if status >= 400:
        err = tc.requests.RequestException("400 Client Error")
        err.response = r
        r.raise_for_status.side_effect = err
        r.text = '{"code":"CONFLICTING_PHONE_COUNTRY_CODE"}'
    else:
        r.raise_for_status.return_value = None
    return r


class PhoneField(unittest.TestCase):
    def test_plus_number_has_no_forced_country(self):
        f = tc._phone_field("+39 333 1234567")
        self.assertEqual(f, {"primaryPhoneNumber": "+39 333 1234567"})

    def test_bare_number_defaults_de(self):
        f = tc._phone_field("01761234567")
        self.assertEqual(f["primaryPhoneCountryCode"], "DE")


class LeadSurvivesPersonFailure(unittest.TestCase):
    def test_person_400_still_creates_opportunity_with_contact_in_note(self):
        calls = []

        def fake_post(url, json=None, headers=None, timeout=None):
            calls.append((url, json))
            if "/rest/people" in url:
                return resp(400)
            if "/rest/opportunities" in url:
                return resp(201, {"data": {"createOpportunity": {"id": "opp-1"}}})
            return resp(200)  # telegram

        with mock.patch.object(tc.requests, "post", side_effect=fake_post):
            out = tc.create_lead(dict(LEAD), ENV)

        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["lead_id"], "opp-1")
        opp_call = [j for u, j in calls if u and "/rest/opportunities" in u][0]
        self.assertNotIn("pointOfContactId", opp_call)
        self.assertIn("+39 333 1234567", opp_call["notiz"])
        self.assertIn("mario@example.it", opp_call["notiz"])
        tg = [j for u, j in calls if "api.telegram.org" in u]
        self.assertTrue(any("BEZ kontakta" in j["text"] for j in tg))

    def test_opportunity_failure_sends_problem_alert(self):
        calls = []

        def fake_post(url, json=None, headers=None, timeout=None):
            calls.append((url, json))
            if "/rest/people" in url:
                return resp(201, {"data": {"createPerson": {"id": "p-1"}}})
            if "/rest/opportunities" in url:
                return resp(400)
            return resp(200)

        with mock.patch.object(tc.requests, "post", side_effect=fake_post):
            out = tc.create_lead(dict(LEAD), ENV)

        self.assertEqual(out["status"], "error")
        tg = [j for u, j in calls if "api.telegram.org" in u]
        self.assertTrue(any("SBOJ zapisi lida" in j["text"] for j in tg))


if __name__ == "__main__":
    unittest.main(verbosity=2)
