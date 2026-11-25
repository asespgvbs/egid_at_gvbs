# EGID-Matching

Das Repository unterstützt die Zuordnung von GVBS-Gebäuden zu EGIDs des Gebäude-
und Wohnungsregisters (GWR). Es umfasst drei Programme:

| Programm | Aufgabe | Ergebnis |
| --- | --- | --- |
| **Matching** | Vergleicht jede GVBS-Eingabezeile mit GWR-Adressen und kategorisiert den Treffer. Eindeutige Fälle werden nach den Regeln automatisch zugeteilt. | Excel-Arbeitsmappe mit einer Zeile pro GVBS-Eingabezeile und Kategorieblättern |
| **Zuordnung** | Unterstützt die manuelle n:m-Zuteilung ausgewählter Prüffälle aus einer Matching-Arbeitsmappe. | Lokaler Bearbeitungsstand in SQLite und exportierbare Excel-Arbeitsmappe |
| **EGID-Abdeckung** | Wertet den bestehenden GWR-EGID-Bestand aus der Perspektive der EGIDs aus. | Separate Excel-Arbeitsmappe mit einer Zeile pro bestehender EGID |

Ein typischer Ablauf ist: **GVBS-Eingabe und GWR bereitstellen → Matching ausführen
→ vollständige Matching-Arbeitsmappe im Zuordnungstool laden → Prüffälle bearbeiten
und exportieren**. Die EGID-Abdeckung ist optional und läuft unabhängig von der
Zuordnungsdatenbank. Sie liest die GVBS-Eingabe und das GWR erneut ein.

Die vollständige Bedienung der manuellen Zuordnung steht in der
[Anleitung zum Zuordnungswerkzeug](docs/ZUORDNUNG.md). Start:

```powershell
.\.venv\Scripts\python.exe -m egid_match.zuordnung
```

### Voraussetzungen

- Windows mit Python **3.14 oder neuer**, einer eingerichteten Projektumgebung
  und `openpyxl` ab Version 3.1.5; die Projektabhängigkeiten stehen in
  [pyproject.toml](pyproject.toml). Die folgenden Beispiele verwenden die
  vorhandene virtuelle Umgebung `.venv` im Repository.
- Eine GVBS-Eingabe als `.xlsx` und eine passende lokale GWR-SQLite-Datenbank.
  Die benötigten Eingabespalten sind unten beschrieben. Der im Quellcode
  konfigurierte GWR-Standardpfad ist installationsabhängig; mit `--gwr-db`
  lässt sich ein anderer Pfad angeben.
- Für die Dateidialoge wird Tkinter benötigt. Die Zuordnungsoberfläche läuft
  lokal im Browser; für Karte und externe Geodienste ist eine Internetverbindung
  nötig. Die reine Bearbeitung und der Export benötigen keine Geodatenverbindung.

Die Startbefehle setzen eine bereits eingerichtete Umgebung voraus; sie richten
keine Abhängigkeiten selbst ein. Bei einer neuen Umgebung müssen die in
`pyproject.toml` angegebenen Abhängigkeiten und das Projekt verfügbar gemacht
werden.

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

## Matching

Der Anwendungscode liegt als Paket unter `src/egid_match/`. Die GVBSID-Auswertung
wird als Modul gestartet:

```powershell
cd 'C:\Pfad\zum\Repository'
.\.venv\Scripts\python.exe -m egid_match.matching
```

Beim Start öffnet das Skript einen Windows-Dialog zur Auswahl der
Excel-Eingabedatei. Danach fragt ein Speicherdialog nach dem Ausgabeort und
Dateinamen. Der vorgeschlagene Dateiname ist `gebaeude_egid_matching.xlsx`.
Vor dem Überschreiben einer vorhandenen Datei fragt der Speicherdialog nach.

Das erste Tabellenblatt der Eingabe enthält diese Spaltennamen. Ihre Reihenfolge
ist frei; weitere Spalten dürfen an beliebiger Stelle stehen:

| Kontrollnummer | Gebäudenummer | Strasse | Hausnummer | Hausnummer Zusatz | Postleitzahl |
| --- | --- | --- | --- | --- | --- |

`Hausnummer Zusatz` darf leer sein. Beim Adressvergleich werden Hausnummer und
Zusatz verbunden: `30` und `a` ergeben `30a`, `30` und `.1` ergeben `30.1`.
Die ursprünglichen Werte bleiben im Import erhalten. Die bisherigen Namen
`Gebäude (Nr.)`, `Strassennamen`, `Nr.` und `PLZ` werden weiterhin akzeptiert.
Bei älteren Dateien ohne `Hausnummer Zusatz` gilt der Zusatz als leer.

Alle oben aufgeführten Spalten ausser `Hausnummer Zusatz` müssen vorhanden sein.
Doppelte Spaltennamen, auch durch die aufgeführten Aliasnamen, werden abgelehnt.
Die optionale Eingabespalte `EGID_zugeteilt` darf an beliebiger Stelle stehen.
Sie enthält bereits manuell vergebene positive EGIDs; mehrere Werte werden durch
Komma, Semikolon oder Zeilenumbruch getrennt. Ungültige Einträge führen zu einem
Fehler. Eine Zeile mit Eintrag erhält `manuell_zugeteilt` und keine weitere
automatische Zuteilung. Betrifft eine solche EGID bei einer anderen Zeile einen
direkten oder Suffix-Kandidaten, erhält diese `zuordnungskonflikt` und keine
automatische Zuteilung. Die Konflikte werden im Zuordnungstool zur Prüfung geladen;
die bereits vergebenen EGIDs sind dort gesperrt. `manuell_zugeteilt` wird grau,
`zuordnungskonflikt` rot dargestellt; in den Zusammenfassungen bleibt eine
Konfliktzeile mit Anzahl 0 ungefärbt. Fehlt die Spalte oder ist sie leer, bleibt
das bisherige Verhalten erhalten. Der bereits eingetragene Wert bleibt in der
Eingabespalte erhalten; die Matching-Spalte `EGID` wird für diese Zeile nicht
zusätzlich befüllt.

Ein erneuter Import gleicht Prüffälle anhand der GVBSID mit der ausgewählten
Zuordnungsdatenbank ab: Neue Fälle werden ergänzt, vorhandene Importangaben
aktualisiert und gespeicherte manuelle Entscheidungen beibehalten. Fälle, die
in der neuen Datei fehlen oder inzwischen automatisch beziehungsweise manuell
zugeteilt sind, werden nicht automatisch entfernt oder abgeschlossen. Die
Sperrliste wird bei erneutem Import ergänzt; zuvor gespeicherte Sperren werden
nicht automatisch entfernt. Die App überwacht die Excel-Datei nicht; für neue
Fälle ist ein erneuter Import erforderlich. Enthält die Matching-Datei keine
importierbaren Prüffälle, meldet die App dies und führt keinen Import aus.

Nach dem ersten regulären Matching wird ausschliesslich für die ursprünglichen
`no_match`-Einträge einmal ohne Eingabe-PLZ gesucht. Strasse und Hausnummer samt
Zusatz müssen nach derselben Normalisierung wie im regulären Matching exakt
übereinstimmen; es gibt keine Ähnlichkeitssuche oder Suffix-Ableitung.
Für diese Suche zählen nur bestehende GWR-Gebäude in Basel, Riehen und Bettingen.
Die Gemeindegrenze wird über `building.GGDE` oder `building.GGDENR` (BFS-Nummern
2701, 2702, 2703), ersatzweise `building.GGDENAME`, geprüft. Fehlen diese Angaben,
wird die PLZ-Korrektur mit einer verständlichen Meldung abgebrochen.

Genau eine unterschiedliche GWR-PLZ führt zur Korrektur. Mehrere EGIDs oder
Adressen mit derselben PLZ zählen dabei als eine PLZ. Bei keiner oder mehreren
möglichen PLZ bleibt die bisherige PLZ erhalten und der Eintrag bleibt `no_match`.
Alle Korrekturen werden gemeinsam angewendet. Danach wird der vollständige
reguläre Kategoriencheck über den gesamten Bestand wiederholt: Auch bislang
zugeordnete GVBSIDs können durch neue Konkurrenz oder veränderte Suffixbeziehungen
eine andere Kategorie erhalten. Es erfolgt keine weitere PLZ-Korrekturrunde.

Die Eingabedatei wird nicht verändert. In den Ausgaben werden korrigierte PLZ
und Suchadresse verwendet. Bei Korrekturen dokumentieren die zusätzlichen Spalten
`PLZ ursprünglich` und `PLZ korrigiert` sowie die Matching-Zusammenfassung die Änderung.
Dasselbe Verfahren gilt für die eigenständige EGID-Abdeckung.

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
Spalten in ursprünglicher Spaltenreihenfolge und ihre Originalwerte, mit Ausnahme
der oben beschriebenen eindeutigen PLZ-Korrekturen.
Direkt nach `Postleitzahl` (bei
älteren Dateien `PLZ`) werden die Spalten `Suchadresse` und `EGID` eingefügt.
`Suchadresse` verbindet Strasse, Hausnummer samt Zusatz und Postleitzahl in
einem Feld, beispielsweise `Teststrasse 30a, 0000`. Zwischen Hausnummer und
Zusatz steht kein Leerzeichen; vor der Postleitzahl stehen ein Komma und ein
Leerzeichen. Die Spalte `EGID` enthält nur die
automatisch zugeordnete EGID aus `perfect_match`, `super_match`,
`oneEgid_oneAddress_multipleGVBSIDs`,
`oneEgid_multipleAddresses_multipleGVBSIDs`, `address_suffix_pair_ge4` oder
`review_suffix_single_gvbsid_multiple_egid`.
Bei der Paarregel erhält Gebäudenummer 1 die `.1`-EGID. Wenn mehrere GVBSIDs dieselbe
EGID als einzigen Adresskandidaten haben, erhalten sie alle diese EGID,
auch bei unterschiedlichen GVBS-Adressen, sofern mindestens eine EGRID
vorhanden ist und kein Hausnummernzusatzkonflikt besteht. Bei Prüffällen
und fehlenden Treffern bleibt die EGID leer.

Jede Zeile erhält genau eine Kategorie. Nach der regulären Adressprüfung und
einer allfälligen Paarprüfung haben `manuell_zugeteilt` und anschliessend
`zuordnungskonflikt` Vorrang vor dem vorläufigen Ergebnis.

Für die Suffixprüfung zählen ausschliesslich Punkt-Zahl-Zusätze wie `30.1`,
`30.2` oder `30.12`. `30a`, `30A` und `30B` gelten als eigenständige Adressen
und lösen gegenüber `30` keinen Suffix-Prüffall aus.

Adress-Suffix-Fälle werden zusätzlich als Paare geprüft: Eine Kontrollnummer muss
im gesamten Import **genau zweimal** vorkommen, mit Gebäudenummer **0 und 1** an
derselben Hauptadresse. Die Haupt-EGID und genau eine zusätzliche EGID mit
Hausnummer **`.1`** müssen auf derselben EGRID eindeutig sein. Weitere numerische
Suffix-EGIDs verhindern die Paarregel auch dann, wenn sie eine eigene GVBSID haben.
Konkurrierende GVBSIDs verhindern die Paarregel ebenfalls.

Die Spalte **`Kubatur`** bestimmt das Verhältnis `Kubatur 0 / Kubatur 1`:

| Neue Kategorie | Verhältnis | Zuordnung | Farbe |
| --- | --- | --- | --- |
| `address_suffix_pair_ge4` | ≥ 4 | Gebäudenummer 0 → Haupt-EGID, Gebäudenummer 1 → `.1`-EGID | Hellbraun |
| `address_suffix_pair_lt4` | < 4 | Keine automatische Zuordnung; beide Fälle manuell prüfen | Orange |

Beide Kubaturen müssen positive, endliche Zahlen sein. Fehlt eine Kubatur oder
ist sie ungültig, bleibt das Paar in `review_address_suffix`. Dasselbe gilt bei
mindestens drei Importzeilen zur Kontrollnummer und bei anderen Gebäudenummern.
Einzelne Gebäude mit Nummer 0 erhalten gegebenenfalls die unten beschriebene
eigene Kategorie mit automatischer Zuordnung des direkten Treffers. Die
Originaladressen und direkten EGID-Kandidaten bleiben erhalten.
`Kubaturverhältnis 0/1`, `Zuordnungsadresse` und die Zusammenfassung
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
| 6 | `review_suffix_single_gvbsid_multiple_egid` | Ja, direkter Treffer |
| 7 | `review_address_suffix` | Nein |
| 8 | `perfect_match` | Ja |
| 9 | `super_match` | Ja |
| 10 | `oneEgid_oneAddress_multipleGVBSIDs` | Ja |
| 11 | `oneEgid_multipleAddresses_multipleGVBSIDs` | Ja |

**`review_suffix_single_gvbsid_multiple_egid`** (dunkelgelb, `#E6C200`) erfasst eine Hauptadresse mit genau
einer Importzeile `Kontrollnummer-0`. Diese Kontrollnummer darf im gesamten Import
kein weiteres Mal vorkommen, auch nicht mit Gebäudenummer 1 an einer anderen
Adresse. Der eindeutige Hauptadress-Treffer hat auf derselben EGRID eine oder
mehrere zusätzliche EGIDs mit Suffixadressen, für die keine eigene GVBSID
importiert wurde. Nur Punkt-Zahl-Zusätze sind zulässig; die Anzahl
der Zusätze ist nicht begrenzt. Der direkte EGID-Treffer wird unabhängig von der
Kubatur automatisch zugeordnet. Die Suffix-EGIDs bleiben unzugeordnet und werden
weiterhin in der Matching-Zusammenfassung aufgeführt. Die Kategorie wird separat
in Excel und der EGID-Abdeckung ausgewiesen.
Das Excel-Blatt heisst wegen der Grenze von 31 Zeichen `review_suffix_1gvbsid_n_egid`.
Ältere, noch nicht automatisch zugeordnete Fälle dieser Kategorie bleiben in der
Zuordnungsapp importierbar; der alte Name `review_suffix_single_building` wird erkannt.

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
unterstützt damit ebenfalls den Testlauf bei Dialogabbruch. Die Testausgabe
wird ohne weiteren Speicherdialog geschrieben; ein vorhandener gleichnamiger
Ausgabestand kann dabei überschrieben werden.

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
.\.venv\Scripts\python.exe -I -B tests\test_matching_contract.py
.\.venv\Scripts\python.exe -I -B tests\test_postal_correction.py
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
9. `review_suffix_single_gvbsid_multiple_egid`
10. `review_address_suffix`
11. `invalid_gwr_data`
12. `zuordnungskonflikt`
13. `manuell_zugeteilt`
14. `kein direkter Adresstreffer`

Eine EGID zählt genau einmal als automatisch zugeordnet, als direkter
Adresskandidat ohne automatische Zuordnung oder als EGID ohne direkten
Adresskandidaten und ohne automatische Paarzuordnung. Die Summe dieser drei Zustände und die Summe der
Hauptkategorien müssen jeweils der gesamten EGID-Anzahl entsprechen.
EGIDs, die ausschliesslich über Hausnummernzusätze erkannt wurden, werden separat
gekennzeichnet und nicht zusätzlich zur Gesamtzahl addiert. Mit automatischer
Paarzuordnung zählen sie zum automatischen Zustand, sonst zum Zustand ohne
direkten Kandidaten. Nicht zugeordnete Zusatzbeziehungen stehen im Blatt
`EGID-ohne-GVBSID`.

Die Abdeckungsstatistik zählt ausschliesslich tatsächlich im Matching automatisch
eingetragene EGIDs als automatisch zugeordnet. Ein Wert aus `EGID_zugeteilt`
allein erhöht diesen automatischen Zähler nicht.
