"""Übergabe an das Team per WhatsApp, ohne bezahlte Plattform.

Der Shop hat auf jeder Seite eine WhatsApp-Nummer (wa.me/491794033381), und dort
antworten laut Ilya wirklich Menschen, Mo bis Fr von 9 bis 18 Uhr.

Der Kunde tippt selbst, das ist Absicht: schreibt ER zuerst, hat das Team seine
Nummer und darf 24 Stunden frei antworten. Umgekehrt (wir schicken dem Team seine
Nummer, das Team schreibt zuerst) bräuchte es die bezahlte WhatsApp-Plattform und
seine Einwilligung. Ilyas Beobachtung: Deutsche geben ihre Nummer ungern heraus,
weil sie Anrufe fürchten. Wenn sie uns schreiben, geben sie gar nichts her.

Der Bot weiß von sich aus nicht, wie spät es ist. Ohne diese Zeile hätte er nur
raten können, ob gerade jemand im Laden sitzt.
"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app import shop_open_now, team_hours_block

BERLIN = ZoneInfo("Europe/Berlin")


def at(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=BERLIN)


class OpeningHours(unittest.TestCase):

    def test_werktag_im_fenster_ist_offen(self):
        self.assertTrue(shop_open_now(at(2026, 9, 10, 9, 0)))    # Donnerstag 9:00
        self.assertTrue(shop_open_now(at(2026, 9, 10, 13, 30)))
        self.assertTrue(shop_open_now(at(2026, 9, 10, 17, 59)))

    def test_vor_und_nach_dem_fenster_ist_zu(self):
        self.assertFalse(shop_open_now(at(2026, 9, 10, 8, 59)))
        self.assertFalse(shop_open_now(at(2026, 9, 10, 18, 0)))
        self.assertFalse(shop_open_now(at(2026, 9, 10, 23, 30)))

    def test_wochenende_ist_zu(self):
        self.assertFalse(shop_open_now(at(2026, 9, 12, 12, 0)))   # Samstag
        self.assertFalse(shop_open_now(at(2026, 9, 13, 12, 0)))   # Sonntag


class TheLineTheBotGets(unittest.TestCase):

    def test_offen_heisst_direkt_uebergeben(self):
        block = team_hours_block(at(2026, 9, 10, 11, 0))
        self.assertIn("wa.me/491794033381", block)
        self.assertIn("BESETZT", block)

    def test_zu_heisst_kontakt_einsammeln(self):
        block = team_hours_block(at(2026, 9, 10, 22, 0))
        self.assertIn("wa.me/491794033381", block)
        self.assertIn("NICHT besetzt", block)

    def test_die_zeile_ist_kurz(self):
        # sie hängt an JEDER Anfrage, sie darf den Prompt nicht aufblähen
        self.assertLess(len(team_hours_block(at(2026, 9, 10, 11, 0))), 700)


class ShowroomGehtAuchUeberWhatsApp(unittest.TestCase):
    """Am 10.09.2026 durchgespielt und verworfen: E-Mail ans Team braucht einen
    Schlüssel, und ein Workflow in der CRM lässt sich per API nicht anlegen
    ("Method not allowed", auch mit Admin-Schlüssel). Beides braucht einen
    Menschen, der etwas einrichtet.

    Was ohne alles funktioniert, steht schon: der Kunde tippt selbst auf WhatsApp.
    Also gilt das auch für den Termin. Die CRM behält den Eintrag als Historie,
    die Nachricht kommt dort an, wo das Team tatsächlich sitzt.
    """

    def test_die_zeile_verlangt_whatsapp_auch_beim_termin(self):
        for block in (team_hours_block(at(2026, 9, 10, 11, 0)),
                      team_hours_block(at(2026, 9, 10, 22, 0))):
            self.assertIn("showroom", block.lower(),
                          "der Termin muss in der Zeile vorkommen, sonst denkt "
                          "das Modell, WhatsApp sei nur für Sonderwünsche")

    def test_offen_und_zu_nennen_beide_den_link(self):
        self.assertIn("wa.me/491794033381", team_hours_block(at(2026, 9, 10, 11, 0)))
        self.assertIn("wa.me/491794033381", team_hours_block(at(2026, 9, 10, 22, 0)))


if __name__ == "__main__":
    unittest.main()
