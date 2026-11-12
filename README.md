# EGID-Matching

Beim Start öffnet das Skript einen Windows-Dialog zur Auswahl der
Excel-Eingabedatei. Danach fragt ein Speicherdialog nach dem Ausgabeort und
Dateinamen. Der vorgeschlagene Dateiname ist `gebaeude_egid_matching.xlsx`.
Vor dem Überschreiben einer vorhandenen Datei fragt der Speicherdialog nach.

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe gvbs_egid_match.py
```

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
.\.venv\Scripts\python.exe gvbs_egid_match.py --input "PFAD\testeingabe.xlsx" --output "AUSGABEORDNER\gebaeude_egid_matching.xlsx" --gwr-db "PFAD\test_gwr.sqlite"
```

`--gwr-db` bestimmt wie bisher die verwendete GWR-Datenbank. Ohne diese Option
gilt der im Skript konfigurierte Standardpfad. Auch beim Dialogabbruch bleibt
diese Einstellung erhalten. `--input` und `--output` dienen zusätzlich als
Vorschläge für die Dialoge.

## Prüfung ohne Datendateien

Die Tests simulieren die Dialoge und ersetzen sämtliche Excel- und
Datenbankzugriffe. Sie verwenden ausschliesslich synthetische Datensätze und
öffnen keine Dialogfenster:

```powershell
.\.venv\Scripts\python.exe -I -B tests\test_file_selection.py
```
