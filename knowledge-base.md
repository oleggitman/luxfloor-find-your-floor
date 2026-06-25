# Find Your Floor — Knowledge Base (v1, DE-first)

> Single source of truth the assistant reads at runtime. Assembled from [find-your-floor-spec.md](find-your-floor-spec.md) (flow + Layer 2) and [faq-baseline-site.md](faq-baseline-site.md) (answer bank, chatbot-ready entries only).
> German is customer-facing. English in parentheses is internal reference only — never shown to the customer.
> Maintainer: TBD (likely Alexey). Update this file, not the prompt, when facts change. Keep it the only place flow + FAQ live.

---

## A. The qualification flow (Layer 1 — the spine)

Four steps, in order. Ask conversationally, one theme at a time, never as a rigid form. Capture answers into the lead profile.

### Step 1 — Optik (the look) · soft preferences
| Dimension | Optionen (DE) |
|---|---|
| Farbe | hell, dunkel, braun, grau |
| Design | Holzoptik, Steinoptik, Marmoroptik |
| Oberfläche | matt, Hochglanz |
| Kante | mit Fuge, mit Fase, ohne |
| Muster | Diele, Fischgrät |
| ↳ bei Fischgrät | Chevron (45° V), Englisch (90° Blöcke) |

### Step 2 — Material · type leaning + budget
| Dimension | Optionen (DE) |
|---|---|
| Typ-Tendenz | dünn (geringe Höhe), Klick, Echt Holz, wasserfest, robust |
| Preis (Budget) | Preisspanne oder Preissensibilität → bestimmt, welche Kollektionen gezeigt werden |

### Step 2b — Raum & Projekt (the "clear picture" layer)
Help the customer see whether the floor they pictured actually fits. Also sizes the project and signals lead quality.
| Feld | Erfasst |
|---|---|
| Raum | Wohnzimmer, Küche, Flur, Bad, Gewerbe |
| Fläche (m²) | ungefähre Fläche → Muster-/Angebotsgröße, Menge |
| Beschreibung | was sich der Kunde vorstellt, die Situation (Freitext) |
| Foto | optional — **in v1 NICHT erfragen** (Phase 1.5). Die "Bild"-Wirkung liefern die Produktkarten aus dem Shop. |

### Step 3 — Probleme nennen (the hard constraints)
These rule options in or out. Resolve each via Section B.
- Fußbodenheizung vorhanden (underfloor heating present)
- Alter Belag darf nicht entfernt werden (install on top of old floor)
- Belag darf nicht hoch sein (low build height required)
- Muss formstabil / steif sein (rigid, no flex underfoot — this is what "hart/hard" means here, confirmed)
- Muss strapazierfähig sein (durable / high traffic)
- Muss wasserfest sein (waterproof)
- Muss später leicht entfernbar sein (removable later)
- Muss ein Bio-Material sein (eco / natural)

### Step 4 — Verfügbarkeit (urgency = the lead signal)
| Antwort (DE) | Lead-Score |
|---|---|
| Wird jetzt dringend benötigt | **HOT** (if it also meets the HOT rule, Section E) |
| Hat Zeit | Warm |
| Muss eingelagert werden | Warm + Logistik-Hinweis: gekaufte Ware bis 30 Tage kostenlos einlagerbar |

---

## B. Constraint → recommendation (Layer 2 — the reasoning table)

Each Step-3 constraint resolves to a recommendation using the FAQ facts. This is the assistant's reasoning core. Multiple constraints combine — honor all of them.

| Constraint | Fact (from FAQ) | Recommendation |
|---|---|---|
| Fußbodenheizung (UFH) | PE-Schaum-Unterlage OK; Kork und Polystyrol NICHT für FBH; Klebe-Vinyl ideal | Vinyl + passende Unterlage; Kork/Polystyrol vermeiden |
| Geringe Höhe / alter Belag bleibt | Klebe-Vinyl hat die geringste Aufbauhöhe | Klebe-Vinyl, oder ein dünner Klick-Boden |
| Später entfernbar | Kleber zerstört die Planke beim Entfernen; Klick ist wieder lösbar | Klick-System, kein Kleber |
| Wasserfest | Vinyl ist wasserfest; Laminat (HDF-Kern) ist es nicht | Vinyl statt Laminat |
| Strapazierfähig / hohe Frequenz | Nutzungsklassen 21-43 je Raum | Klasse an Raum anpassen: 22 Wohnen, 23 Küche/Flur, 31-33 Gewerbe |
| Bio / natürlich | Kork ist 100% recycelbar; Echtholz ist natürlich | Kork-Unterlage oder Echtholz-Parkett |
| Formstabil / steif ("hart") | Steifer Kern widersteht dem Durchbiegen; SPC-Vinyl und Laminat sind steif, weiches Klebe-Vinyl nicht | Rigid-Core-SPC-Vinyl oder Laminat; weiches Klebe-Vinyl vermeiden |

> Note on tension: UFH points to Klebe-Vinyl, while "formstabil/steif" points away from soft glue-down toward rigid SPC. When both appear, prefer **rigid SPC-Vinyl with a UFH-suitable underlay** and explain the trade-off to the customer.

---

## C. Answer bank (FAQ — chatbot-ready facts)

Use these to explain trade-offs the flow raises. Stable answers, safe to state directly. (Source: live site FAQ, DE is authoritative.)

### Produkte
- **Laminat vs. Vinyl.** Laminat: mehrere verklebte Schichten, Overlay (<1mm, Kunstharz) für Belastbarkeit, Dekorschicht, HDF-Trägerplatte (bis 90% Holzfasern), Gegenzug für Formstabilität. Manche mit integrierter Trittschalldämmung. Vinyl: Weich-PVC, drei Arten — Klick-Vinyl (schwimmend), Klebe-Vinyl (selbstklebend), lose Verlegung. Nutzschicht 0,3mm privat / 0,55mm Objekt.
- **Matt vs. Hochglanz.** Hochglanz: schick, Raum wirkt heller/größer, Farben tiefer; lackiert langlebig, Folie günstiger/empfindlicher; pflegeleicht, aber Fuß-/Pfotenspuren sichtbar. Matt: warm/gemütlich, aufwendiger zu reinigen, offenporig, Flecken ziehen schneller ein.
- **Formate.** Fünf: Fliese (Standard 60x30cm, auch quadratisch), Diele (ca. 19x120cm), Breitdiele (breiter als 19cm), Langdiele (länger als 120cm), Kombination (breiter UND länger).
- **Nutzungsklassen.** Privat: 21 leicht (Schlaf-/Gästezimmer), 22 mittel (Wohn-/Esszimmer, Flure), 23 stark (Küchen, Eingangsflure, Treppen). Gewerblich: 31 leicht (Hotelzimmer, Konferenz, Kleinbüro), 32 mittel (Warteräume, Büros, Boutiquen), 33 stark (Korridore, Klassenräume, Kaufhäuser). Industriell: 41-43.
- **Fuge.** Zwischenraum zwischen Bauteilen, verhindert Schäden bei Ausdehnung/Zusammenziehen. Fugenlos wirkt ruhig; mit Fuge betont den Paneel-Charakter.
- **Reinigung Vinyl.** Kein Dampfreiniger (Feuchtigkeit/Wärme → Verziehen, Aufquellen). Stattdessen feucht wischen (gut ausgewrungen, mildes Mittel), Vinylreiniger, regelmäßig saugen/kehren.

### Bestellung
- **Lieferzeit.** Vorrätige Artikel i.d.R. 5-7 Werktage.
- **Rücksendung.** Vollständig, originalverpackt, ungebraucht, unbeschädigt. Verbraucher haben Widerrufsrecht; Rücktransportkosten trägt der Käufer.
- **Versandarten.** Je nach Produkt und Menge Paketversand oder Speditionsversand. Selbstabholung möglich. Speditionslieferung bis Bordsteinkante; der Fahrer meldet sich am Liefertag (erreichbare Nummer wichtig).
- **Zahlung.** Kreditkarte, PayPal, Rechnung, Barzahlung, Ratenzahlung mit PayPal.
- **Garantie.** JANGAL (Laminat/Vinyl): privat 15-25 J., gewerblich 2-5 J. FALQUON (Laminat): privat 15 J., gewerblich 3 J. CHECK (Laminat/Vinyl): privat bis 15 J., gewerblich 2-3 J.

### Versandkosten — Deutschland Festland (the rate table; the assistant CALCULATES this)
Aktuell beliefert Lux-Floor nur **Deutschland**. Tarif ist **gewichts-/VE-basiert und bundesweit pauschal** (nicht PLZ-abhängig). VE = Verpackungseinheit. Use `estimate_shipping` to look this up; do not do the math by hand.

| Waren-Gewicht | Versandpauschale |
|---|---|
| bis 1 kg | 5,95 EUR |
| bis 20 kg (1 VE) / XL (1 VE) / XXL (1 VE) | 19,99 / 25 / 40 EUR |
| 20-40 kg (2 VE) / XL / XXL | 39,99 / 50 / 80 EUR |
| 40-60 kg (3 VE) / XL / XXL | 59,99 / 75 / 120 EUR |
| 60-225 kg (4-15 VE) | 50 EUR |
| 225-300 kg (16-20 VE) | 60 EUR |
| 300-375 kg (21-25 VE) | 70 EUR |
| 375-450 kg (26-30 VE) | 80 EUR |
| ab 450 kg (ca. 31 VE) | 90 EUR |
| Überlänge | 30 EUR |

- Always present the result as an **estimate** ("Versand ca. X EUR, Festland Deutschland, final bei Bestellung").
- **Ausland (abroad):** not calculable here. Capture article + Menge + full address + Land/PLZ and route to **info@lux-floor.de** (the carrier is asked per case).

### Zubehör
- **Sockelleisten.** Übergang Boden/Wand, schützt die Wand. Befestigung: kleben (schnell, schwer entfernbar), nageln (auf hartem Untergrund problematisch), Montageclips (einfach, präzise setzen).
- **Trittschalldämmung.** Mindert Gehschall. PE-Schaum (auch FBH), Polystyrol (besser, nicht FBH), Kork (nicht FBH/Feuchträume, recycelbar), Holzfaser (schwächer). Faustregel: je härter der Belag, desto härter die Dämmung. Vinyl/Kork bringen Dämpfung oft schon mit.
- **Übergangsschienen.** Verbinden/grenzen zwei Beläge ab. Selbstklebend oder verschraubt.

### Montage
- **Klick-Vinyl.** 24-48h bei 18-25°C akklimatisieren, Untergrund eben/sauber/trocken (>2mm ausgleichen), schwimmend per Klick, Start Ecke zum Fenster, 3-10mm Wandabstand, Versatz, Gummihammer, dann Sockelleisten.
- **Klebe-Vinyl.** Untergrund trocken/sauber/eben, akklimatisieren, Kleber mit Zahnspachtel. Vorteile: beste Schalldämmung, hohe Druckbelastung, geringe Aufbauhöhe, FBH-tauglich. Nachteil: aufwendige Verklebung (Profi), Demontage nur durch Zerstörung.
- **Klick-Laminat.** Menge = Raumfläche + 10% Verschnitt (Online-Rechner). Akklimatisieren, Untergrund vorbereiten, schwimmend per Klick, 3-10mm Wandabstand, Versatz. *Während der Verlegung nicht lüften.*

### Allgemein
- **Reservieren/Einlagern.** Reservierung möglich; gekaufte Ware bis 30 Tage kostenlos einlagerbar.
- **Öffnungszeiten.** Mo-Fr 10:00-18:30, Sa nach Vereinbarung, So geschlossen.

---

## D. Brands & catalog notes

- Lux-Floor verkauft **eigene Produktion (Eigenmarke)** UND zugekaufte Marken: **JANGAL, FALQUON, CHECK**.
- **Eigenmarke = Luxfloor's own brand.** The assistant leads recommendations with own-brand products that are on promotion (see Section F). Own-brand is identified in WooCommerce by the `Eigenmarke` tag/attribute (set up in Phase 0).
- Shop has ~799 products. Shop-side filters the profile maps onto: Surface (Hochglanz, Matt, Strukturiert), Format (Diele, Breitdiele, Fliese, Herringbone, Quadratisch), Design (Holzoptik, Steinoptik, Uni, Marmoroptik).

---

## E. Lead scoring (HOT definition)

A lead is **HOT** only when all three hold:
1. **Kontakt hinterlassen** — Telefon oder WhatsApp (nicht nur Name).
2. **Dringlichkeit** — "jetzt dringend benötigt" oder Verlegetermin in ~2-3 Wochen.
3. **Konkretes Projekt** — Raum + Fläche + Materialrichtung erfasst (Step 2b vollständig).

Missing any one → **Warm** (normale Pipeline, kein Alarm). HOT triggers the Smart Buzz Telegram alert to Ilya.

---

## F. Recommendation priority (the ranking rule)

1. **Fit is the gate** — never recommend a product that does not match the profile and constraints.
2. Within the fitting set, lead with **Luxfloor Eigenmarke products that are on promotion** (best margin + price hook in one).
3. Then everything else that fits.

Return **2-3 concrete products** as cards (image, key specs, link), not just a filtered link.

---

## G. Escalation (out of flow → human)

Route to a human for anything outside the flow or the case-by-case FAQ items: **abroad** shipping/international delivery, address/cancellation changes, deep product-specific questions. (Domestic shipping is NOT escalated — calculate it via `estimate_shipping`, Section C rate table.)
Human channels: Telefon **02131 2917676**, SMS/WhatsApp **+49 179 403 33 81**, E-Mail **info@lux-floor.de**, vor Ort **Jagenbergstraße 7, 41468 Neuss** (Mo-Fr 10:00-18:30, Sa nach Vereinbarung).

---

*v1 DE-first. RU/EN later (logic is language-agnostic, only surface copy changes). Maintainer: TBD (likely Alexey).*
