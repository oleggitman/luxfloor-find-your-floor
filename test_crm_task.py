"""Jeder Kunde aus dem Chat wird zu einer Aufgabe in der CRM.

Warum das und nichts anderes (10.09.2026 der Reihe nach durchprobiert):
  Telegram   das Team sitzt dort nicht, nur Oleg.
  E-Mail     braucht einen Zugangsschlüssel, den erst jemand anlegen muss.
  Workflow   die CRM verbietet das Anlegen per API ("Method not allowed", auch
             mit Admin-Schlüssel), es geht nur von Hand im Bildschirm.
  WhatsApp   funktioniert, hängt aber daran, dass der KUNDE tippt. Tut er es
             nicht, erfährt niemand etwas.

Aufgaben dagegen legt die API an, und das Team arbeitet dort schon: in der CRM
stehen echte eigene Aufgaben ("Preisanfrage WPC rot 80 m²", "Angebot Haka").
Die Aufgabe hängt am Deal und am Kontakt, also sieht man beim Öffnen sofort alles.
Niemand bei Lux-Floor muss dafür etwas einrichten.

Nur für Kunden aus dem Chat, nicht für jede Regung in der Datenbank.
"""
import unittest
from unittest import mock

import twenty_client


ENV = {"TWENTY_API_URL": "https://api.twenty.com", "TWENTY_API_KEY": "k",
       "TWENTY_TASK_ASSIGNEE_ID": "c344d84f-ce44-42ad-90aa-6072fc7baaf0"}


class TaskForEveryChatCustomer(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(twenty_client, "_post_json")
        self.post = patcher.start()
        self.addCleanup(patcher.stop)
        self.post.side_effect = lambda path, body, env: (
            {"data": {"createTask": {"id": "task-1"}}} if path.endswith("/tasks")
            else {"data": {"createTaskTarget": {"id": "tt-1"}}})

    def _calls(self, path_end):
        return [c for c in self.post.call_args_list if c[0][0].endswith(path_end)]

    def test_showroom_wird_zur_aufgabe_mit_der_uhrzeit_im_titel(self):
        twenty_client.create_team_task(
            {"name": "Bernd Meyer", "action": "showroom_booking",
             "showroom_slot": "Morgen vormittags", "phone_or_whatsapp": "0170123"},
            opp_id="opp-1", person_id="p-1", sku_str="4163 Sakura", area=None, env=ENV)
        body = self._calls("/tasks")[0][0][1]
        self.assertIn("Showroom", body["title"])
        self.assertIn("Morgen vormittags", body["title"])
        self.assertIn("Bernd Meyer", body["title"])

    def test_kontakt_steht_im_text_damit_niemand_suchen_muss(self):
        twenty_client.create_team_task(
            {"name": "Clara", "email": "c@x.de", "phone_or_whatsapp": "0170999",
             "conversation_summary": "80 m2 Wohnzimmer, Steinoptik"},
            opp_id="opp-2", person_id="p-2", sku_str="4161", area=80, env=ENV)
        text = self._calls("/tasks")[0][0][1]["bodyV2"]["markdown"]
        for muss in ("0170999", "c@x.de", "80 m2 Wohnzimmer", "4161"):
            self.assertIn(muss, text)

    def test_aufgabe_haengt_am_deal_und_am_kontakt(self):
        twenty_client.create_team_task(
            {"name": "Dora"}, opp_id="opp-3", person_id="p-3",
            sku_str="", area=None, env=ENV)
        ziele = [c[0][1] for c in self._calls("/taskTargets")]
        self.assertIn({"taskId": "task-1", "targetOpportunityId": "opp-3"}, ziele)
        self.assertIn({"taskId": "task-1", "targetPersonId": "p-3"}, ziele)

    def test_ohne_kontaktkarte_nur_der_deal(self):
        twenty_client.create_team_task(
            {"name": "Egon"}, opp_id="opp-4", person_id=None,
            sku_str="", area=None, env=ENV)
        ziele = [c[0][1] for c in self._calls("/taskTargets")]
        self.assertEqual(ziele, [{"taskId": "task-1", "targetOpportunityId": "opp-4"}])

    def test_aufgabe_geht_an_das_team_und_ist_offen(self):
        twenty_client.create_team_task(
            {"name": "Frida"}, opp_id="opp-5", person_id=None,
            sku_str="", area=None, env=ENV)
        body = self._calls("/tasks")[0][0][1]
        self.assertEqual(body["assigneeId"], ENV["TWENTY_TASK_ASSIGNEE_ID"])
        self.assertEqual(body["status"], "TODO")

    def test_ein_fehler_hier_darf_den_lead_nicht_kosten(self):
        self.post.side_effect = RuntimeError("CRM weg")
        self.assertEqual(
            twenty_client.create_team_task({"name": "Gustav"}, opp_id="o", person_id=None,
                                           sku_str="", area=None, env=ENV),
            None)


if __name__ == "__main__":
    unittest.main()
