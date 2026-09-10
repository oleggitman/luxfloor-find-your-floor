"""Ein Kunde, bei dem der Katalog nicht reicht, wird zu einer Aufgabe in der CRM.

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


class NurWennEinMenschUebernehmenMuss(unittest.TestCase):
    """Seine Ansage 10.09.2026 15:22: es geht um EINEN Fall, nicht um jeden Lead.

    Die Grenze ist: MUSS ein Mensch etwas tun? Zwei Fälle sagen ja, der Katalog
    reicht nicht (kein Produkt, Sonderwunsch, Auslandsversand) und ein Kunde hat
    eine Showroom-Zeit gewählt, die jemand bestätigen muss. Ein normaler Lead
    sagt nein: er steht in der CRM und braucht niemanden.
    """

    def setUp(self):
        patcher = mock.patch.object(twenty_client, "_post_json")
        self.post = patcher.start()
        self.addCleanup(patcher.stop)
        self.post.side_effect = lambda path, body, env: (
            {"data": {"createTask": {"id": "task-1"}}} if path.endswith("/tasks")
            else {"data": {"createTaskTarget": {"id": "tt-1"}}})

    def _tasks(self):
        return [c[0][1] for c in self.post.call_args_list if c[0][0].endswith("/tasks")]

    def test_sonderanfrage_erzeugt_eine_aufgabe(self):
        twenty_client.create_team_task(
            {"name": "Clara", "lead_flag": "sonderanfrage",
             "phone_or_whatsapp": "0170999", "email": "c@x.de",
             "info_note": "weisses mattes Vinyl, gibt es nicht im Katalog",
             "conversation_summary": "80 m2 Wohnzimmer"},
            opp_id="opp-2", person_id="p-2", sku_str="4161", area=80, env=ENV)
        self.assertEqual(len(self._tasks()), 1)
        body = self._tasks()[0]
        self.assertIn("Clara", body["title"])
        text = body["bodyV2"]["markdown"]
        for muss in ("0170999", "c@x.de", "weisses mattes Vinyl", "80 m2 Wohnzimmer"):
            self.assertIn(muss, text)

    def test_auslandsversand_auch(self):
        twenty_client.create_team_task(
            {"name": "Dirk", "lead_flag": "auslandsversand"},
            opp_id="o", person_id=None, sku_str="", area=None, env=ENV)
        self.assertEqual(len(self._tasks()), 1)

    def test_normaler_lead_erzeugt_KEINE_aufgabe(self):
        twenty_client.create_team_task(
            {"name": "Bernd", "lead_flag": "normal", "email": "b@x.de"},
            opp_id="o", person_id="p", sku_str="4163", area=20, env=ENV)
        self.assertEqual(self._tasks(), [])

    def test_showroom_erzeugt_eine_aufgabe_mit_der_uhrzeit(self):
        """Ein Termin, von dem niemand weiss, ist kein Termin. Der Kunde hat eine
        Zeit gewaehlt, ein Mensch muss sie bestaetigen."""
        twenty_client.create_team_task(
            {"name": "Bernd", "action": "showroom_booking",
             "showroom_slot": "Morgen vormittags", "phone_or_whatsapp": "0170123"},
            opp_id="o", person_id="p", sku_str="4163 Sakura", area=None, env=ENV)
        body = self._tasks()[0]
        self.assertIn("Showroom", body["title"])
        self.assertIn("Morgen vormittags", body["title"])
        self.assertIn("Bernd", body["title"])
        self.assertIn("0170123", body["bodyV2"]["markdown"])

    def test_aufgabe_haengt_am_deal_und_am_kontakt(self):
        twenty_client.create_team_task(
            {"name": "Dora", "lead_flag": "sonderanfrage"}, opp_id="opp-3",
            person_id="p-3", sku_str="", area=None, env=ENV)
        ziele = [c[0][1] for c in self.post.call_args_list
                 if c[0][0].endswith("/taskTargets")]
        self.assertIn({"taskId": "task-1", "targetOpportunityId": "opp-3"}, ziele)
        self.assertIn({"taskId": "task-1", "targetPersonId": "p-3"}, ziele)

    def test_aufgabe_geht_an_das_team_und_ist_offen(self):
        twenty_client.create_team_task(
            {"name": "Frida", "lead_flag": "sonderanfrage"}, opp_id="opp-5",
            person_id=None, sku_str="", area=None, env=ENV)
        body = self._tasks()[0]
        self.assertEqual(body["assigneeId"], ENV["TWENTY_TASK_ASSIGNEE_ID"])
        self.assertEqual(body["status"], "TODO")

    def test_aufgabe_ist_heute_faellig_damit_sie_nicht_untergeht(self):
        """Das Team hat eine lebendige Aufgabenliste (17 Aufgaben, laufend
        abgearbeitet). Ein Kunde wartet nicht, also steht die Aufgabe im Heute
        und nicht irgendwo in der Liste."""
        twenty_client.create_team_task(
            {"name": "Hilde", "lead_flag": "sonderanfrage"}, opp_id="o",
            person_id=None, sku_str="", area=None, env=ENV)
        body = self._tasks()[0]
        self.assertIn("dueAt", body)
        self.assertTrue(body["dueAt"].startswith(
            __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).strftime("%Y-%m-%d")))

    def test_ein_fehler_hier_darf_den_lead_nicht_kosten(self):
        self.post.side_effect = RuntimeError("CRM weg")
        self.assertIsNone(twenty_client.create_team_task(
            {"name": "Gustav", "lead_flag": "sonderanfrage"}, opp_id="o",
            person_id=None, sku_str="", area=None, env=ENV))


if __name__ == "__main__":
    unittest.main()
