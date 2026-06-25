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

Fragen: Oleg kontaktieren.
