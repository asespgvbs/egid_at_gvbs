# EGID-Matching

Für die manuelle n:m-Zuordnung der Prüffälle gibt es zusätzlich das eigenständige
[lokale Zuordnungswerkzeug](docs/ZUORDNUNG.md):

```powershell
.\.venv\Scripts\python.exe -m egid_match.zuordnung
```

Es verwendet vorhandene Abhängigkeiten ohne weitere Installation. Datenbankwahl,
Import, Bearbeitungsstand, amtliche Geodatenanbindung und vollständiger Export sind in
der verlinkten Anleitung beschrieben. Die beiden Auswertungen bleiben unabhängig.

## Paketstruktur und Startbefehle

```text
src/egid_match/
  common.py              Gemeinsame Fehlerklassen und Text-/ID-Helfer
  matching.py            GVBSID-Matching
  abdeckung.py           EGID-Abdeckung
  zuordnung/
    app.py               Lokale Oberfläche und HTTP-Endpunkte
    store.py             Zuordnungsdatenbank und Excel-Import/-Export
    geo.py               Parzellen-/Gebäudekontext
    geometrie.py         Geometrieprüfung
    geo_transport.py     Begrenzte Geodienstabfragen
    gwr.py               Koordinaten und GWR-Adressabfrage
    quellen.py           Öffentliche Quellenprofile
    static/              JavaScript und CSS
    templates/           HTML
tests/                   Synthetische Python-/JavaScript-Tests
docs/                    Bedienungs- und Geodatendokumentation
```

Die Programme lassen sich aus dem Repository mit der vorhandenen Python-Umgebung starten:

| Programm | Modulaufruf | Konsolenbefehl nach Installation/Aktualisierung der Projektumgebung |
| --- | --- | --- |
| Matching | `python -m egid_match.matching` | `egid-match` |
| Abdeckung | `python -m egid_match.abdeckung` | `egid-abdeckung` |
| Zuordnungsoberfläche | `python -m egid_match.zuordnung` | `egid-zuordnung` |

`python -m egid_match` startet ebenfalls das Matching. Die Oberfläche lädt ihre
HTML-/CSS-/JS-Dateien über Paketressourcen; die URLs unter `/static/` bleiben gleich.
Daten und lokale Einstellungen werden durch die Paketstruktur nicht verschoben.

Das Projekt enthält zwei eigenständige Auswertungen mit getrennten Excel-Dateien:

| Python-Modul | Perspektive | Standardausgabe |
| --- | --- | --- |
| `egid_match.matching` | Eine Ergebniszeile pro GVBS-Eingabezeile | `gebaeude_egid_matching.xlsx` |
| `egid_match.abdeckung` | Eine Ergebniszeile pro bestehender EGID | `egid_abdeckung.xlsx` |

Der Anwendungscode liegt als Paket unter `src/egid_match/`. Die GVBSID-Auswertung
wird als Modul gestartet:

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe -m egid_match.matching
```

Beim Start öffnet das Skript einen Windows-Dialog zur Auswahl der
Excel-Eingabedatei. Danach fragt ein Speicherdialog nach dem Ausgabeort und
Dateinamen. Der vorgeschlagene Dateiname ist `gebaeude_egid_matching.xlsx`.
Vor dem Überschreiben einer vorhandenen Datei fragt der Speicherdialog nach.

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe -m egid_match.matching
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
`oneEgid_oneAddress_multipleGVBSIDs`,
`oneEgid_multipleAddresses_multipleGVBSIDs` oder `address_suffix_pair_ge4`.
Bei der Paarregel erhält Gebäudenummer 1 die `.1`-EGID. Wenn mehrere GVBSIDs dieselbe
EGID als einzigen Adresskandidaten haben, erhalten sie alle diese EGID,
auch bei unterschiedlichen GVBS-Adressen, sofern mindestens eine EGRID
vorhanden ist und kein Hausnummernzusatzkonflikt besteht. Bei Prüffällen
und fehlenden Treffern bleibt die EGID leer.

Die Kategorien werden sequentiell in dieser Reihenfolge geprüft. Die erste
zutreffende Kategorie wird vergeben; jede Zeile erhält genau eine Kategorie.

Adress-Suffix-Fälle werden zusätzlich als Paare geprüft: Eine Kontrollnummer muss
im gesamten Import **genau zweimal** vorkommen, mit Gebäudenummer **0 und 1** an
derselben Hauptadresse. Die Haupt-EGID und genau eine zusätzliche EGID mit
Hausnummer **`.1`** müssen auf derselben EGRID eindeutig sein. Weitere Suffix-EGIDs
oder konkurrierende GVBSIDs verhindern die Paarregel.

Die Spalte **`Kubatur`** bestimmt das Verhältnis `Kubatur 0 / Kubatur 1`:

| Neue Kategorie | Verhältnis | Zuordnung | Farbe |
| --- | --- | --- | --- |
| `address_suffix_pair_ge4` | ≥ 4 | Gebäudenummer 0 → Haupt-EGID, Gebäudenummer 1 → `.1`-EGID | Ocker |
| `address_suffix_pair_lt4` | < 4 | Keine automatische Zuordnung; beide Fälle manuell prüfen | Orange |

Beide Kubaturen müssen positive, endliche Zahlen sein. Fehlt eine Kubatur oder
ist sie ungültig, bleibt der Fall in `review_address_suffix`. Dasselbe gilt bei
einer oder mindestens drei Importzeilen zur Kontrollnummer und bei anderen
Gebäudenummern. Die Originaladressen und direkten EGID-Kandidaten bleiben
erhalten. `Kubaturverhältnis 0/1`, `Zuordnungsadresse` und die Zusammenfassung
dokumentieren die Paarentscheidung. Beide neuen Kategorien erscheinen auch in
den Kategorieblättern, Hinweisen und Statistiken. Die allgemeine Prüfreihenfolge
vor der zusätzlichen Paarprüfung lautet:

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
zum aktuellen Arbeitsverzeichnis. Beim Start im Repository bleibt dies
`C:\dev\repos\egid_match\data\test_match_data.xlsx`.
Mit `--input` lässt sich eine andere Test-Eingabedatei festlegen.
Die Ausgabe heisst dann immer
`gebaeude_egid_matching_TEST.xlsx`. Sie liegt im Ordner von `--output` oder,
ohne diese Option, im aktuellen Arbeitsverzeichnis. Der Start ohne Argumente
unterstützt damit ebenfalls den Testlauf bei Dialogabbruch.

Beispiel mit Platzhaltern für die bisherigen Testpfade:

```powershell
.\.venv\Scripts\python.exe -m egid_match.matching --input "PFAD\testeingabe.xlsx" --output "AUSGABEORDNER\gebaeude_egid_matching.xlsx" --gwr-db "PFAD\test_gwr.sqlite"
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
.\.venv\Scripts\python.exe -I -B tests\test_suffix_pairs.py
.\.venv\Scripts\python.exe -I -B tests\test_package.py
```

## Eigenständige EGID-Abdeckung

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe -m egid_match.abdeckung
```

Ohne `--input` werden die GVBS-Eingabe und die neue Ausgabedatei über Dialoge
ausgewählt. Der vorgeschlagene Dateiname ist `egid_abdeckung.xlsx`. Bei
Dialogabbruch endet nur diese neue Auswertung ohne Datenzugriff. Der bisherige
Testlauf bei Dialogabbruch in `egid_match.matching` bleibt erhalten.

Mit `--input` und optional `--output` läuft die EGID-Auswertung ohne Dateidialoge.
Beispiel mit Platzhaltern:

```powershell
.\.venv\Scripts\python.exe -m egid_match.abdeckung --input "PFAD\gvbs_eingabe.xlsx" --output "AUSGABEORDNER\egid_abdeckung.xlsx" --gwr-db "PFAD\gwr_basel_stadt.sqlite"
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
dem Kennzeichen `Automatische Zuordnung = Ja` und einer der automatischen
Kategorien. Die zugeordnete EGID muss Teil des GWR-Bestands und entweder direkter
Kandidat oder der durch `address_suffix_pair_ge4` zugeordnete `.1`-Kandidat sein.
Kategoriennamen allein erzeugen keine Zuordnung. Automatisch zugeordnete
Suffix-EGIDs zählen zum automatischen Abdeckungszustand und erscheinen nicht
im Blatt `EGID-ohne-GVBSID`.

Alle Kategorien direkter Kandidaten bleiben sichtbar. Bei mehreren Kategorien
bestimmt ausschliesslich für die Statistik diese Priorität die Hauptkategorie:

1. `perfect_match`
2. `super_match`
3. `oneEgid_oneAddress_multipleGVBSIDs`
4. `oneEgid_multipleAddresses_multipleGVBSIDs`
5. `address_suffix_pair_ge4`
6. `address_suffix_pair_lt4`
7. `multiple_egid`
8. `multiple_gvbsid_multiple_egid`
9. `review_address_suffix`
10. `invalid_gwr_data`
11. `kein direkter Adresstreffer`

Eine EGID zählt genau einmal als automatisch zugeordnet, als direkter
Adresskandidat ohne automatische Zuordnung oder als EGID ohne direkten
Adresskandidaten und ohne automatische Paarzuordnung. Die Summe dieser drei Zustände und die Summe der
Hauptkategorien müssen jeweils der gesamten EGID-Anzahl entsprechen.
EGIDs, die ausschliesslich über Hausnummernzusätze erkannt wurden, werden separat
gekennzeichnet und nicht zusätzlich zur Gesamtzahl addiert. Mit automatischer
Paarzuordnung zählen sie zum automatischen Zustand, sonst zum Zustand ohne
direkten Kandidaten. Nicht zugeordnete Zusatzbeziehungen stehen im Blatt
`EGID-ohne-GVBSID`.
