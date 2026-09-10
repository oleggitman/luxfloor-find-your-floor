"""Wer erfährt von einem Kunden: das Team, nicht Oleg.

Befund 10.09.2026: der einzige Benachrichtigungsweg war Telegram in Olegs eigene
Gruppe "Gitman AIOS Command Center" (zwei Mitglieder: er und der Bot). Das Team
von Lux-Floor stand dort nie drin. Ein heißer Lead, ein Showroom-Wunsch oder ein
Lead, den die CRM nicht angenommen hat, erreichte den Laden also nie.

Seine Ansage 10.09.2026 13:27 und 13:39: alles über Kunden gehört dem Team,
Oleg bekommt nur noch, was am Assistenten selbst kaputt ist (Server, Fehler,
Budget), weil das wir reparieren.

Also zwei getrennte Wege:
  Team  -> E-Mail an luxfloor24@gmail.com und info@lux-floor.de
  Oleg  -> Telegram, nur technische Störungen

Ohne konfiguriertes Postfach darf nichts krachen: der Assistent antwortet weiter,
die Benachrichtigung fällt still aus und wird geloggt.
"""
import unittest
from unittest import mock

import mailer
import twenty_client


ENV_MAIL = {
    "LEAD_MAIL_USER": "luxfloor24@gmail.com",
    "LEAD_MAIL_PASSWORD": "app-passwort",
    "LEAD_MAIL_TO": "luxfloor24@gmail.com, info@lux-floor.de",
}


class MailerBasics(unittest.TestCase):

    def test_ohne_smtp_ist_der_shop_weg_der_normale(self):
        self.assertFalse(mailer.configured({}))

    def test_mit_konfiguration_geht_es_an_beide_adressen(self):
        with mock.patch.object(mailer, "_smtp_send", return_value=None) as sent:
            res = mailer.send_team_mail("Neuer Lead", "Anna, 0170...", ENV_MAIL)
        self.assertEqual(res, "sent")
        args = sent.call_args[0]
        self.assertEqual(args[0], ["luxfloor24@gmail.com", "info@lux-floor.de"])
        self.assertIn("Neuer Lead", args[1])
        self.assertIn("Anna", args[2])

    def test_ein_kaputtes_postfach_bricht_den_chat_nicht(self):
        with mock.patch.object(mailer, "_smtp_send", side_effect=OSError("no route")):
            self.assertEqual(mailer.send_team_mail("x", "y", ENV_MAIL), "failed")


class WhoGetsWhat(unittest.TestCase):

    def test_heisser_lead_geht_ans_team_nicht_an_oleg(self):
        with mock.patch.object(twenty_client, "send_team_mail",
                               return_value="sent") as team, \
             mock.patch.object(twenty_client, "_send_telegram_alert") as tg:
            twenty_client.notify_lead(
                {"name": "Anna", "phone_or_whatsapp": "0170123",
                 "conversation_summary": "80 m2 Wohnzimmer"},
                sku_str="4163 Sakura", area=80, hot=True,
                opp_id="opp-1", env=ENV_MAIL)
        self.assertTrue(team.called)
        self.assertFalse(tg.called, "heiße Leads gehören nicht mehr in Olegs Telegram")

    def test_showroom_benachrichtigt_immer_auch_wenn_nicht_hot(self):
        with mock.patch.object(twenty_client, "send_team_mail",
                               return_value="sent") as team:
            twenty_client.notify_lead(
                {"name": "Bernd", "email": "b@x.de", "action": "showroom_booking",
                 "showroom_slot": "Morgen vormittags"},
                sku_str="", area=None, hot=False, opp_id="opp-2", env=ENV_MAIL)
        self.assertTrue(team.called, "ein Termin ohne Nachricht ist kein Termin")
        body = team.call_args[0][1]
        self.assertIn("Morgen vormittags", body)
        self.assertIn("Bernd", body)

    def test_normaler_warmer_lead_geht_auch_raus(self):
        with mock.patch.object(twenty_client, "send_team_mail",
                               return_value="sent") as team:
            twenty_client.notify_lead(
                {"name": "Clara", "email": "c@x.de"},
                sku_str="4161", area=20, hot=False, opp_id="opp-3", env=ENV_MAIL)
        self.assertTrue(team.called)

    def test_technische_stoerung_bleibt_bei_oleg(self):
        with mock.patch.object(twenty_client, "requests") as rq:
            twenty_client._send_problem_alert("Assistent antwortet nicht", {
                "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c"})
        self.assertTrue(rq.post.called)


class NobodyIsEverLost(unittest.TestCase):
    """Oleg bekommt Kunden nicht mehr, auch nicht als Rückfalltür (seine Ansage
    10.09.2026 13:27). Der verlässliche Weg ist die Aufgabe in der CRM. Telegram
    meldet sich nur noch, wenn WIRKLICH nichts geklappt hat, weder Aufgabe noch
    Mail: dann ist ein Kunde in Gefahr und das ist eine Störung, keine Meldung."""

    def test_aufgabe_da_also_kein_telegram(self):
        with mock.patch.object(twenty_client, "send_team_mail",
                               return_value="not_configured"), \
             mock.patch.object(twenty_client, "_send_problem_alert") as tg:
            twenty_client.notify_lead(
                {"name": "Dora", "phone_or_whatsapp": "0170999"},
                sku_str="4161", area=30, hot=False, opp_id="opp-9", env={},
                task_id="task-1")
        self.assertFalse(tg.called)

    def test_weder_aufgabe_noch_mail_ist_eine_stoerung(self):
        with mock.patch.object(twenty_client, "send_team_mail",
                               return_value="failed"), \
             mock.patch.object(twenty_client, "_send_problem_alert") as tg:
            twenty_client.notify_lead(
                {"name": "Egon", "email": "e@x.de"},
                sku_str="", area=None, hot=True, opp_id="opp-10", env={},
                task_id=None)
        self.assertTrue(tg.called)
        self.assertIn("e@x.de", tg.call_args[0][0])

    def test_mit_postfach_kein_telegram(self):
        with mock.patch.object(twenty_client, "send_team_mail",
                               return_value="sent"), \
             mock.patch.object(twenty_client, "_send_problem_alert") as tg:
            twenty_client.notify_lead(
                {"name": "Frida", "email": "f@x.de"},
                sku_str="", area=None, hot=True, opp_id="opp-11", env=ENV_MAIL,
                task_id="task-2")
        self.assertFalse(tg.called)


if __name__ == "__main__":
    unittest.main()
