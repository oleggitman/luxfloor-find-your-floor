# Find Your Floor — Widget einbinden (WordPress)

Sobald der Render-Service live ist und Oleg die URL bestätigt hat, diesen
einen Code-Schnipsel in die WordPress-Seite einfügen.

## Der Code-Schnipsel (eine Zeile)

```html
<script src="https://DEINE-URL.onrender.com/widget.js"
        data-backend="https://DEINE-URL.onrender.com"></script>
```

`DEINE-URL` durch die echte Render-URL ersetzen (Oleg schickt sie).

---

## Einbinden — zwei Wege

### Weg A: Plugin (empfohlen, kein Code-Editor nötig)

1. WordPress Admin > Plugins > Neues Plugin hinzufügen
2. Suchen: **Insert Headers and Footers** (von WPBeginner)
3. Installieren > Aktivieren
4. Einstellungen > Insert Headers and Footers
5. Den Schnipsel in das Feld **Scripts in Footer** einfügen
6. Speichern

### Weg B: Theme-Datei direkt bearbeiten

1. WordPress Admin > Design > Theme-Editor
2. Datei: **footer.php** auswählen
3. Den Schnipsel direkt **vor** `</body>` einfügen
4. Datei aktualisieren

---

## Testen

1. lux-floor.de im Browser öffnen (normales Browserfenster, kein Admin)
2. Unten rechts: goldene Chat-Schaltfläche erscheint
3. Klicken > Frage eingeben, z.B. "Ich suche einen Boden fuers Wohnzimmer"
4. Assistent antwortet auf Deutsch

---

## URL aktualisieren

Falls sich die Render-URL ändert: den Schnipsel suchen und beide Vorkommen
von `DEINE-URL.onrender.com` durch die neue URL ersetzen.

---

## WICHTIG: WP Rocket (Caching-Plugin)

lux-floor.de nutzt WP Rocket. Zwei Einstellungen muessen das Widget dauerhaft
ausschliessen, sonst startet der Chat nicht von selbst und Updates kommen nicht an:

1. WP Rocket, Tab "File Optimization", Block "Delay JavaScript Execution", Feld
   "Excluded JavaScript Files": `luxfloor-find-your-floor.onrender.com` eintragen.
   (Ohne das laedt WP Rocket das Widget als `type="text/rocketlazyloadscript"`,
   dann erscheint die Chat-Sprechblase erst nach dem Scrollen.)
2. Gleichen Eintrag im Block "Minify JavaScript files", Feld "Excluded
   JavaScript Files". (Sonst serviert WP Rocket eine alte, zwischengespeicherte
   Kopie, und neue Deploys erreichen die Seite nicht.)
3. Speichern, dann "Clear cache".

Danach laedt das Widget direkt von Render, ist immer aktuell und startet ohne
Interaktion. Status: erledigt und verifiziert am 2026-07-01.

---

Fragen: Oleg kontaktieren.
