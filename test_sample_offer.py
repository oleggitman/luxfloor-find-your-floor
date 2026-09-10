"""Musterbestellung: der Shop hat den Knopf, der Chat soll ihn nutzen.

Befund vom 10.09.2026 (33 Gespräche, 02. bis 09.09): 16 Besucher wollten ein
kostenloses Muster, abgeschlossen wurde KEINES. Der Bot fragt nach der Produktwahl
nach Name, Stadt, PLZ und Einwilligung im Chatfenster. Im gleichen Zeitraum hat der
Shop über seinen eigenen Knopf "Gratis muster bestellen" 39 Muster ausgeliefert
(21 Bestellungen, Position `Produktmuster`, Dekor im Positionsfeld `Produkt`).

Also: nach der Dekorwahl schickt der Bot zur Produktseite, wo der Knopf steht.
Die Daten nimmt die normale Kasse auf, nicht das Chatfenster.

Der Knopf existiert NICHT überall. Am 10.09.2026 an 17 Produkten geprüft:
  vorhanden  Klick-Vinyl, Klebe-Vinyl, Designboden, Laminat
  fehlt      B-Ware, Parkett, Fliesen, Sockelleisten/Zubehör, Akustik
Ein Muster zu versprechen, wo es keinen Knopf gibt, schickt den Kunden ins Leere.
"""
import unittest

from woo_client import sample_available


def prod(name="CHECK One - 2478 Buchäcker Oak", cats=("klick-vinyl",)):
    return {"name": name, "categories": [{"slug": c, "name": c} for c in cats]}


class SampleAvailability(unittest.TestCase):

    def test_bodenkategorien_haben_den_knopf(self):
        for slug in ("klick-vinyl", "klebe-vinyl", "designboden", "laminat"):
            with self.subTest(slug=slug):
                self.assertTrue(sample_available(prod(cats=(slug,))))

    def test_unterkategorie_zaehlt_auch(self):
        # ein Produkt hängt in mehreren Kategorien: Holz-Dekor + Klick-Vinyl
        self.assertTrue(sample_available(prod(cats=("holz-dekor", "klick-vinyl"))))

    def test_ohne_knopf_kein_versprechen(self):
        for slug in ("parkett", "fliesen", "sockelleisten", "zubehoer", "akustik"):
            with self.subTest(slug=slug):
                self.assertFalse(sample_available(prod(cats=(slug,))))

    def test_b_ware_ist_ausgenommen(self):
        self.assertFalse(sample_available(
            prod(name="B-Ware FALQUON Wood - Q1026 Artic", cats=("laminat",))))

    def test_unbekannte_kategorie_verspricht_nichts(self):
        self.assertFalse(sample_available(prod(cats=("wand", "irgendwas"))))

    def test_leeres_produkt_faellt_nicht_um(self):
        self.assertFalse(sample_available({}))
        self.assertFalse(sample_available(None))


class CardCarriesTheFlag(unittest.TestCase):

    def test_karte_traegt_sample_available(self):
        from woo_client import WooClient
        card = WooClient._card({
            "id": 24344, "name": "Lux Floor - 4162 Cherry", "sku": "LF-4162",
            "price": "70.23", "regular_price": "70.23",
            "permalink": "https://lux-floor.de/shop/vinylboden/lux-floor-4162/",
            "categories": [{"slug": "klick-vinyl", "name": "Klick-Vinyl"}],
            "images": [{"src": "x.jpg"}], "attributes": [], "meta_data": [],
        })
        self.assertIn("sample_available", card)
        self.assertTrue(card["sample_available"])
        # die Musterseite ist die Produktseite: dort steht der Knopf
        self.assertEqual(card["sample_url"], card["url"])

    def test_ohne_knopf_keine_musterseite(self):
        from woo_client import WooClient
        card = WooClient._card({
            "id": 23316, "name": "Parador - Eiche Dune / Parkett", "sku": "P-1460",
            "price": "115.16", "regular_price": "115.16",
            "permalink": "https://lux-floor.de/shop/parkett/1460-parador/",
            "categories": [{"slug": "parkett", "name": "Parkett"}],
            "images": [{"src": "x.jpg"}], "attributes": [], "meta_data": [],
        })
        self.assertFalse(card["sample_available"])
        self.assertIsNone(card["sample_url"])


if __name__ == "__main__":
    unittest.main()
