# EGID-Matching

Beim Start öffnet das Skript einen Windows-Dialog zur Auswahl der
Excel-Eingabedatei. Danach fragt ein Speicherdialog nach dem Ausgabeort und
Dateinamen. Der vorgeschlagene Dateiname ist `gebaeude_egid_matching.xlsx`.
Vor dem Überschreiben einer vorhandenen Datei fragt der Speicherdialog nach.

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe main.py
```

Die Eingabe enthält diese Spalten und darf danach beliebige weitere Spalten
enthalten:

| Kontrollnummer | Gebäudenummer | Strasse | Hausnummer | Hausnummer Zusatz | Postleitzahl |
| --- | --- | --- | --- | --- | --- |

`Hausnummer Zusatz` darf leer sein. Beim Adressvergleich werden Hausnummer und
Zusatz verbunden: `30` und `a` ergeben `30a`, `30` und `.1` ergeben `30.1`.
Die ursprünglichen Werte bleiben im Import erhalten. Die bisherigen Namen
`Gebäude (Nr.)`, `Strassennamen`, `Nr.` und `PLZ` werden weiterhin akzeptiert.
Bei älteren Dateien ohne `Hausnummer Zusatz` gilt der Zusatz als leer.

Die Ausgabedatei enthält weiterhin `Matching`, `Zusammenfassung` und
`Kategorien-Hinweise`. Im Blatt `Matching` stehen zuerst `Suchadresse`,
`GVBSID`, `Matching-Zusammenfassung` und `Zweckbestimmung`, danach folgen die
übrigen Spalten. `Zweckbestimmung` übernimmt den importierten Wert; fehlt die
Spalte in der Eingabe, bleibt sie in `Matching` leer.
Die Suchadresse wird in `Matching` und `Ergebnis` identisch aufgebaut.
Beide Tabellen werden aufsteigend nach `Kontrollnummer` sortiert. Zahlen und
als Text gespeicherte ganze Zahlen werden numerisch sortiert (2 vor 10),
danach folgen andere Texte und zuletzt leere Kontrollnummern. Bei gleicher
Kontrollnummer bleibt die ursprüngliche Reihenfolge erhalten.
Das zusätzliche Blatt `Ergebnis` enthält alle importierten
Spalten in ursprünglicher Spaltenreihenfolge und ihre Originalwerte.
Direkt nach `Postleitzahl` (bei
älteren Dateien `PLZ`) werden die Spalten `Suchadresse` und `EGID` eingefügt.
`Suchadresse` verbindet Strasse, Hausnummer samt Zusatz und Postleitzahl in
einem Feld, beispielsweise `Teststrasse 30a, 0000`. Zwischen Hausnummer und
Zusatz steht kein Leerzeichen; vor der Postleitzahl stehen ein Komma und ein
Leerzeichen. Die Spalte `EGID` enthält nur die
automatisch zugeordnete EGID aus `perfect_match` oder `super_match`; bei
Prüffällen und fehlenden Treffern bleibt sie leer.

## Rückfall beim Abbrechen

Wird einer der beiden Dialoge abgebrochen oder geschlossen, verwirft das
Skript die Dialogauswahl und verwendet `data/test_match_data.xlsx` relativ
zum Skriptverzeichnis (hier: `C:\dev\repos\egid_match\data\test_match_data.xlsx`).
Mit `--input` lässt sich eine andere Test-Eingabedatei festlegen.
Die Ausgabe heisst dann immer
`gebaeude_egid_matching_TEST.xlsx`. Sie liegt im Ordner von `--output` oder,
ohne diese Option, im aktuellen Arbeitsverzeichnis. Der Start ohne Argumente
unterstützt damit ebenfalls den Testlauf bei Dialogabbruch.

Beispiel mit Platzhaltern für die bisherigen Testpfade:

```powershell
.\.venv\Scripts\python.exe main.py --input "PFAD\testeingabe.xlsx" --output "AUSGABEORDNER\gebaeude_egid_matching.xlsx" --gwr-db "PFAD\test_gwr.sqlite"
```

`--gwr-db` bestimmt wie bisher die verwendete GWR-Datenbank. Ohne diese Option
gilt der im Skript konfigurierte Standardpfad. Auch beim Dialogabbruch bleibt
diese Einstellung erhalten. `--input` und `--output` dienen zusätzlich als
Vorschläge für die Dialoge.

## Prüfung ohne Datendateien

Die Tests simulieren die Dialoge und Datei-/Datenbankzugriffe. Excel-Import und
-Export werden ausschliesslich mit synthetischen Datensätzen im Arbeitsspeicher
geprüft. Es werden keine Datendateien oder Dialogfenster geöffnet:

```powershell
.\.venv\Scripts\python.exe -I -B tests\test_file_selection.py
```
