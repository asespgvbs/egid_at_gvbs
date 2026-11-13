# EGID-Matching

Das Projekt enthält zwei eigenständige Auswertungen mit getrennten Excel-Dateien:

| Skript | Perspektive | Standardausgabe |
| --- | --- | --- |
| `gvbsid_matching.py` | Eine Ergebniszeile pro GVBS-Eingabezeile | `gebaeude_egid_matching.xlsx` |
| `egid_abdeckung.py` | Eine Ergebniszeile pro bestehender EGID | `egid_abdeckung.xlsx` |

Die bisherige Anwendung wurde unverändert nach `gvbsid_matching.py` verschoben.
Die GVBSID-Auswertung wird direkt gestartet:

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe gvbsid_matching.py
```

Beim Start öffnet das Skript einen Windows-Dialog zur Auswahl der
Excel-Eingabedatei. Danach fragt ein Speicherdialog nach dem Ausgabeort und
Dateinamen. Der vorgeschlagene Dateiname ist `gebaeude_egid_matching.xlsx`.
Vor dem Überschreiben einer vorhandenen Datei fragt der Speicherdialog nach.

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe gvbsid_matching.py
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
automatisch zugeordnete EGID aus `perfect_match`, `super_match`,
`oneEgid_oneAddress_multipleGVBSIDs` oder
`oneEgid_multipleAddresses_multipleGVBSIDs`. Wenn mehrere GVBSIDs dieselbe
EGID als einzigen Adresskandidaten haben, erhalten sie alle diese EGID,
auch bei unterschiedlichen GVBS-Adressen, sofern mindestens eine EGRID
vorhanden ist und kein Hausnummernzusatzkonflikt besteht. Bei Prüffällen
und fehlenden Treffern bleibt die EGID leer.

Die Kategorien werden sequentiell in dieser Reihenfolge geprüft. Die erste
zutreffende Kategorie wird vergeben; jede Zeile erhält genau eine Kategorie.

| Prüfung | Kategorie | Automatische EGID-Zuordnung |
| --- | --- | --- |
| 1 | `invalid_input` | Nein |
| 2 | `no_match` | Nein |
| 3 | `multiple_egid` | Nein |
| 4 | `multiple_gvbsid_multiple_egid` | Nein |
| 5 | `invalid_gwr_data` | Nein |
| 6 | `review_address_suffix` | Nein |
| 7 | `perfect_match` | Ja |
| 8 | `super_match` | Ja |
| 9 | `oneEgid_oneAddress_multipleGVBSIDs` | Ja |
| 10 | `oneEgid_multipleAddresses_multipleGVBSIDs` | Ja |

Fehlende EGRID und Hausnummernzusatzkonflikte verhindern damit auch bei
mehreren GVBSIDs eine automatische Zuordnung. `perfect_match` und
`super_match` setzen voraus, dass keine andere GVBSID dieselbe EGID als
einzigen Adresskandidaten hat. Die bestehende Anzeigereihenfolge in der
Excel-Zusammenfassung und den Kategorieblättern bleibt erhalten.

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
.\.venv\Scripts\python.exe gvbsid_matching.py --input "PFAD\testeingabe.xlsx" --output "AUSGABEORDNER\gebaeude_egid_matching.xlsx" --gwr-db "PFAD\test_gwr.sqlite"
```

`--gwr-db` bestimmt wie bisher die verwendete GWR-Datenbank. Ohne diese Option
gilt der im Skript konfigurierte Standardpfad. Auch beim Dialogabbruch bleibt
diese Einstellung erhalten. `--input` und `--output` dienen zusätzlich als
Vorschläge für die Dialoge.

## Prüfung ohne Datendateien

Die Tests simulieren die Dialoge und Datei-/Datenbankzugriffe. Excel-Import und
-Export werden ausschliesslich mit synthetischen Datensätzen im Arbeitsspeicher
geprüft. Die ergänzende Bestandsabfrage wird mit einer vollständig synthetischen
SQLite-Datenbank im Arbeitsspeicher geprüft. Es werden keine Datendateien oder
Dialogfenster geöffnet und keine Excel-Dateien geschrieben:

```powershell
.\.venv\Scripts\python.exe -I -B tests\test_file_selection.py
.\.venv\Scripts\python.exe -I -B tests\test_egid_abdeckung.py
```

## Eigenständige EGID-Abdeckung

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe egid_abdeckung.py
```

Ohne `--input` werden die GVBS-Eingabe und die neue Ausgabedatei über Dialoge
ausgewählt. Der vorgeschlagene Dateiname ist `egid_abdeckung.xlsx`. Bei
Dialogabbruch endet nur diese neue Auswertung ohne Datenzugriff. Der bisherige
Testlauf bei Dialogabbruch in `gvbsid_matching.py` bleibt erhalten.

Mit `--input` und optional `--output` läuft die EGID-Auswertung ohne Dateidialoge.
Beispiel mit Platzhaltern:

```powershell
.\.venv\Scripts\python.exe egid_abdeckung.py --input "PFAD\gvbs_eingabe.xlsx" --output "AUSGABEORDNER\egid_abdeckung.xlsx" --gwr-db "PFAD\gwr_basel_stadt.sqlite"
```

Die angegebene GWR-Datenbank muss den Bestand des Kantons Basel-Stadt enthalten.
Ohne `--gwr-db` gilt derselbe konfigurierte Standardpfad wie bisher. Es werden
nur bestehende Gebäude mit `GSTAT = 1004` berücksichtigt. Eine ergänzende,
lesende Abfrage ermittelt alle unterschiedlichen EGIDs aus `building`, auch
wenn keine Adresse oder EGRID vorhanden ist. Für die neue Ausgabe werden auch
unvollständige GWR-Adressen erhalten und als solche gekennzeichnet. Mehrere
Adressen und EGRIDs erscheinen vollständig, mit Zeilenumbrüchen innerhalb der
Zelle. Strasse, Hausnummer und PLZ im Blatt ohne GVBSID stehen in derselben
Adressreihenfolge; fehlende Bestandteile sind als `(fehlt)` markiert.

Die Auswertung ruft das bestehende Python-Matching direkt auf. Eine zuvor
erzeugte Matching-Excel-Datei wird weder benötigt noch eingelesen. Die bisherige
GVBSID-Ausgabe wird von diesem Skript nicht erzeugt oder verändert.

Die neue Arbeitsmappe enthält:

- `EGID-Zusammenfassung`: Hauptkategorien und die drei Abdeckungszustände mit
  Anzahl und Anteil am gesamten EGID-Bestand, Anzahl der ausschliesslich über
  Hausnummernzusätze erkannten EGIDs sowie Kontrollsummen und Differenzen.
- `EGID-Gesamtübersicht`: genau eine Zeile je EGID mit allen Adressen, EGRIDs,
  direkten GVBSIDs und deren Matching-Kategorien sowie Zuordnungsstatus.
- `EGID-ohne-GVBSID`: alle EGIDs ohne direkten Adresskandidaten, einschliesslich
  EGIDs ohne Adresse/EGRID und Hinweisen auf Beziehungen über Hausnummernzusätze.
- `Kategorien-Hinweise`: Definitionen der Kategorien in statistischer
  Prioritätsreihenfolge sowie Erklärungen zu tatsächlicher Zuordnung, den drei
  Abdeckungszuständen, Hausnummernzusätzen und Kontrollsummen.
- `Inkonsistenzen`: nur bei Auffälligkeiten, beispielsweise Kandidaten oder
  zugeordnete EGIDs ausserhalb des vollständigen GWR-Bestands. Diese Beziehungen
  werden separat dokumentiert und erhöhen die EGID-Gesamtzahl nicht.

Eine automatische Zuordnung gilt nur bei einer tatsächlich eingetragenen EGID,
dem Kennzeichen `Automatische Zuordnung = Ja` und einer der vier aktuellen
automatischen Kategorien. Die zugeordnete EGID muss zugleich direkter Kandidat
und Teil des GWR-Bestands sein. Kategoriennamen allein erzeugen keine Zuordnung.

Alle Kategorien direkter Kandidaten bleiben sichtbar. Bei mehreren Kategorien
bestimmt ausschliesslich für die Statistik diese Priorität die Hauptkategorie:

1. `perfect_match`
2. `super_match`
3. `oneEgid_oneAddress_multipleGVBSIDs`
4. `oneEgid_multipleAddresses_multipleGVBSIDs`
5. `multiple_egid`
6. `multiple_gvbsid_multiple_egid`
7. `review_address_suffix`
8. `invalid_gwr_data`
9. `kein direkter Adresstreffer`

Eine EGID zählt genau einmal als automatisch zugeordnet, als direkter
Adresskandidat ohne automatische Zuordnung oder als EGID ohne direkten
Adresskandidaten. Die Summe dieser drei Zustände und die Summe der
Hauptkategorien müssen jeweils der gesamten EGID-Anzahl entsprechen.
EGIDs, die ausschliesslich über Hausnummernzusätze erkannt wurden, sind eine
gekennzeichnete Teilmenge der EGIDs ohne direkten Kandidaten und werden nicht
zusätzlich zur Gesamtzahl addiert. Zugehörige GVBSIDs dieser Zusatzbeziehungen
stehen im Blatt `EGID-ohne-GVBSID`.
