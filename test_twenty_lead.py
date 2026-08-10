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
    r.ok = status < 400
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


NO_PEOPLE = {"data": {"people": []}}


class LeadSurvivesPersonFailure(unittest.TestCase):
    def test_person_400_still_creates_opportunity_with_contact_in_note(self):
        calls = []

        def fake_post(url, json=None, headers=None, timeout=None):
            calls.append((url, json))
            if "/rest/people/duplicates" in url:
                return resp(200, {"data": [{"personDuplicates": []}]})
            if "/rest/people" in url:
                return resp(400)
            if "/rest/opportunities" in url:
                return resp(201, {"data": {"createOpportunity": {"id": "opp-1"}}})
            return resp(200)  # telegram

        with mock.patch.object(tc.requests, "post", side_effect=fake_post), \
                mock.patch.object(tc.requests, "get", return_value=resp(200, NO_PEOPLE)):
            out = tc.create_lead(dict(LEAD), ENV)

        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["lead_id"], "opp-1")
        opp_call = [j for u, j in calls if u and "/rest/opportunities" in u][0]
        self.assertNotIn("pointOfContactId", opp_call)
        self.assertIn("+39 333 1234567", opp_call["notiz"])
        self.assertIn("mario@example.it", opp_call["notiz"])
        tg = [j for u, j in calls if "api.telegram.org" in u]
        card_alerts = [j["text"] for j in tg if "БЕЗ карточки контакта" in j["text"]]
        self.assertTrue(card_alerts)
        # алерт несёт контакты: команда звонит из сообщения, не открывая CRM
        self.assertIn("+39 333 1234567", card_alerts[0])
        self.assertIn("mario@example.it", card_alerts[0])

    def test_opportunity_failure_sends_problem_alert(self):
        calls = []

        def fake_post(url, json=None, headers=None, timeout=None):
            calls.append((url, json))
            if "/rest/people/duplicates" in url:
                return resp(200, {"data": [{"personDuplicates": []}]})
            if "/rest/people" in url:
                return resp(201, {"data": {"createPerson": {"id": "p-1"}}})
            if "/rest/opportunities" in url:
                return resp(400)
            return resp(200)

        with mock.patch.object(tc.requests, "post", side_effect=fake_post), \
                mock.patch.object(tc.requests, "get", return_value=resp(200, NO_PEOPLE)):
            out = tc.create_lead(dict(LEAD), ENV)

        self.assertEqual(out["status"], "error")
        tg = [j for u, j in calls if "api.telegram.org" in u]
        failure_alerts = [j["text"] for j in tg if "СБОЙ записи лида" in j["text"]]
        self.assertTrue(failure_alerts)
        # алерт обязан нести контакты клиента: команда связывается без CRM
        self.assertIn("+39 333 1234567", failure_alerts[0])
        self.assertIn("mario@example.it", failure_alerts[0])


class ReturningCustomerReusesCard(unittest.TestCase):
    """Регрессия 10.08.2026 (лид Jost Dolinsek).

    Клиент оформил заказ в шопе в 17:31, карточка человека завелась. В 17:36 он
    же прошёл через ассистента, тот попытался завести ВТОРУЮ карточку на ту же
    почту и получил 400 «A duplicate entry was detected». Сделка записалась, но
    осталась без контакта, а в Telegram ушёл алерт без телефона и почты.
    Инвариант: повторный клиент подхватывает свою карточку, сделка привязана,
    алерта нет."""

    def _run(self, fake_post, fake_get, patched=None):
        calls = []

        def post(url, json=None, headers=None, timeout=None):
            calls.append((url, json))
            return fake_post(url, json)

        def patch(url, json=None, headers=None, timeout=None):
            if patched is not None:
                patched.append((url, json))
            return resp(200)

        with mock.patch.object(tc.requests, "post", side_effect=post), \
                mock.patch.object(tc.requests, "get", side_effect=fake_get), \
                mock.patch.object(tc.requests, "patch", side_effect=patch):
            out = tc.create_lead(dict(LEAD), ENV)
        return out, calls

    def test_existing_person_found_by_email_is_linked(self):
        def fake_post(url, json=None):
            if "/rest/people" in url:
                raise AssertionError("вторую карточку человека заводить нельзя")
            if "/rest/opportunities" in url:
                return resp(201, {"data": {"createOpportunity": {"id": "opp-2"}}})
            return resp(200)

        def fake_get(url, params=None, headers=None, timeout=None):
            if "/rest/people/" in url:  # чтение найденной карточки перед дозаполнением
                return resp(200, {"data": {"person": {
                    "emails": {"primaryEmail": "mario@example.it"},
                    "phones": {"primaryPhoneNumber": "+39 333 1234567"},
                    "stadt": "Mailand", "plz": "20100", "strasse": "Via Roma 1"}}})
            return resp(200, {"data": {"people": [
                {"id": "p-existing", "emails": {"primaryEmail": "MARIO@Example.it"}}]}})

        out, calls = self._run(fake_post, fake_get)
        self.assertEqual(out["status"], "ok")
        opp = [j for u, j in calls if "/rest/opportunities" in u][0]
        self.assertEqual(opp["pointOfContactId"], "p-existing")
        self.assertNotIn("Person-Anlage fehlgeschlagen", opp["notiz"])
        tg = [j["text"] for u, j in calls if "api.telegram.org" in u]
        self.assertFalse([t for t in tg if "БЕЗ карточки контакта" in t])

    def test_stranger_with_other_email_is_never_linked(self):
        """Полный тёзка с другой почтой это ДРУГОЙ человек: заводим новую карточку.
        Twenty такую запись пропускает (проверено живьём, 201), а её встроенный
        поиск дублей матчит по имени и отдал бы чужого."""
        def fake_post(url, json=None):
            if "/rest/people/duplicates" in url:
                raise AssertionError("сопоставитель дублей Twenty матчит по имени, брать его нельзя")
            if "/rest/people" in url:
                return resp(201, {"data": {"createPerson": {"id": "p-new"}}})
            if "/rest/opportunities" in url:
                return resp(201, {"data": {"createOpportunity": {"id": "opp-4"}}})
            return resp(200)

        def fake_get(url, params=None, headers=None, timeout=None):
            return resp(200, {"data": {"people": [
                {"id": "p-namesake", "emails": {"primaryEmail": "jemand.anders@example.it"}}]}})

        out, calls = self._run(fake_post, fake_get)
        opp = [j for u, j in calls if "/rest/opportunities" in u][0]
        self.assertEqual(opp["pointOfContactId"], "p-new")

    def test_duplicate_on_create_resolves_to_existing_person(self):
        """Гонка: поиск пустой, а запись уже упирается в дубль."""
        state = {"searches": 0}

        def fake_post(url, json=None):
            if "/rest/people" in url:
                r = resp(400)
                r.text = '{"statusCode":400,"messages":["A duplicate entry was detected"]}'
                return r
            if "/rest/opportunities" in url:
                return resp(201, {"data": {"createOpportunity": {"id": "opp-3"}}})
            return resp(200)

        def fake_get(url, params=None, headers=None, timeout=None):
            if "/rest/people/" in url:
                return resp(200, {"data": {"person": {}}})
            state["searches"] += 1
            if state["searches"] == 1:  # до записи карточки ещё нет
                return resp(200, {"data": {"people": []}})
            return resp(200, {"data": {"people": [
                {"id": "p-existing", "emails": {"primaryEmail": "mario@example.it"}}]}})

        patched: list = []
        out, calls = self._run(fake_post, fake_get, patched)
        self.assertEqual(out["status"], "ok")
        opp = [j for u, j in calls if "/rest/opportunities" in u][0]
        self.assertEqual(opp["pointOfContactId"], "p-existing")
        tg = [j["text"] for u, j in calls if "api.telegram.org" in u]
        self.assertFalse([t for t in tg if "БЕЗ карточки контакта" in t])
        # пустая карточка дозаполняется тем, что принёс разговор
        self.assertTrue(patched)
        self.assertEqual(patched[0][1]["stadt"], "Mailand")

    def test_unresolvable_duplicate_still_writes_the_lead(self):
        """Худший случай: дубль есть, а найти его не удалось. Лид обязан уцелеть:
        сделка пишется, контакты в заметке и в алерте."""
        def fake_post(url, json=None):
            if "/rest/people" in url:
                r = resp(400)
                r.text = '{"statusCode":400,"messages":["A duplicate entry was detected"]}'
                return r
            if "/rest/opportunities" in url:
                return resp(201, {"data": {"createOpportunity": {"id": "opp-5"}}})
            return resp(200)

        def fake_get(url, params=None, headers=None, timeout=None):
            return resp(200, {"data": {"people": []}})

        out, calls = self._run(fake_post, fake_get)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["lead_id"], "opp-5")
        opp = [j for u, j in calls if "/rest/opportunities" in u][0]
        self.assertNotIn("pointOfContactId", opp)
        self.assertIn("mario@example.it", opp["notiz"])
        tg = [j["text"] for u, j in calls if "api.telegram.org" in u]
        self.assertTrue([t for t in tg if "БЕЗ карточки контакта" in t])

    def test_search_outage_never_loses_the_lead(self):
        """Поиск недоступен (сеть, 500): падать нельзя, лид пишется как обычно."""
        def fake_post(url, json=None):
            if "/rest/people" in url:
                return resp(201, {"data": {"createPerson": {"id": "p-new"}}})
            if "/rest/opportunities" in url:
                return resp(201, {"data": {"createOpportunity": {"id": "opp-6"}}})
            return resp(200)

        def fake_get(url, params=None, headers=None, timeout=None):
            raise tc.requests.RequestException("CRM search down")

        out, calls = self._run(fake_post, fake_get)
        self.assertEqual(out["status"], "ok")
        opp = [j for u, j in calls if "/rest/opportunities" in u][0]
        self.assertEqual(opp["pointOfContactId"], "p-new")

    def test_enrich_never_overwrites_existing_values(self):
        cur = {"emails": {"primaryEmail": "alt@example.it"},
               "phones": {"primaryPhoneNumber": "+39 000 0000000"},
               "stadt": "Rom", "plz": "", "strasse": ""}
        patched: list = []

        def fake_get(url, headers=None, timeout=None):
            return resp(200, {"data": {"person": cur}})

        def fake_patch(url, json=None, headers=None, timeout=None):
            patched.append(json)
            return resp(200)

        with mock.patch.object(tc.requests, "get", side_effect=fake_get), \
                mock.patch.object(tc.requests, "patch", side_effect=fake_patch):
            tc._enrich_person("https://api.example", {}, "p-existing", dict(LEAD))

        self.assertEqual(patched, [{"plz": "20100", "strasse": "Via Roma 1"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
